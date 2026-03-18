"""Close Direction Signal — composite BUY/SELL/NEUTRAL signal for MOC trading."""

import numpy as np
from config import SIGNAL_WEIGHTS, SIGNAL_THRESHOLD


def calculate_close_signal(options_df, spot_price, gex_by_strike):
    """Calculate composite close direction signal from options data.

    Args:
        options_df: DataFrame with call_volume, put_volume, call_mark, put_mark,
                    dte, call_OI, put_OI columns
        spot_price: current SPX price
        gex_by_strike: Series of net GEX per strike (index=strike, value=net_gex)

    Returns:
        dict with keys:
            direction: "BUY", "SELL", or "NEUTRAL"
            composite_score: float in [-1, 1]
            confidence: float 0-100
            net_premium: float (raw dollar value)
            components: dict of {name: {value, normalized, weight, contribution}}
    """
    if options_df.empty:
        return _neutral_result()

    components = {}

    # 1. Net Premium Flow
    net_prem_raw, net_prem_norm = _net_premium_flow(options_df)
    components["net_premium"] = {
        "label": "Net Premium Flow",
        "value": net_prem_raw,
        "normalized": net_prem_norm,
        "weight": SIGNAL_WEIGHTS["net_premium"],
        "contribution": net_prem_norm * SIGNAL_WEIGHTS["net_premium"],
    }

    # 2. GEX Magnet Direction
    gex_val, gex_norm = _gex_magnet_direction(gex_by_strike, spot_price)
    components["gex_magnet"] = {
        "label": "GEX Magnet",
        "value": gex_val,
        "normalized": gex_norm,
        "weight": SIGNAL_WEIGHTS["gex_magnet"],
        "contribution": gex_norm * SIGNAL_WEIGHTS["gex_magnet"],
    }

    # 3. 0DTE Volume Skew
    skew_val, skew_norm = _zero_dte_skew(options_df)
    components["zero_dte_skew"] = {
        "label": "0DTE Skew",
        "value": skew_val,
        "normalized": skew_norm,
        "weight": SIGNAL_WEIGHTS["zero_dte_skew"],
        "contribution": skew_norm * SIGNAL_WEIGHTS["zero_dte_skew"],
    }

    # 4. Put/Call Volume Ratio
    pc_val, pc_norm = _put_call_ratio(options_df)
    components["pc_ratio"] = {
        "label": "P/C Ratio",
        "value": pc_val,
        "normalized": pc_norm,
        "weight": SIGNAL_WEIGHTS["pc_ratio"],
        "contribution": pc_norm * SIGNAL_WEIGHTS["pc_ratio"],
    }

    # Composite score = weighted sum of normalized signals
    composite = sum(c["contribution"] for c in components.values())
    composite = np.clip(composite, -1.0, 1.0)

    if composite > SIGNAL_THRESHOLD:
        direction = "BUY"
    elif composite < -SIGNAL_THRESHOLD:
        direction = "SELL"
    else:
        direction = "NEUTRAL"

    confidence = abs(composite) * 100

    return {
        "direction": direction,
        "composite_score": round(composite, 4),
        "confidence": round(confidence, 1),
        "net_premium": net_prem_raw,
        "components": components,
    }


def _net_premium_flow(df):
    """Net premium = sum(call_vol * call_mark) - sum(put_vol * put_mark), in dollars (*100)."""
    call_prem = (df["call_volume"] * df["call_mark"] * 100).sum()
    put_prem = (df["put_volume"] * df["put_mark"] * 100).sum()
    net = call_prem - put_prem
    total = call_prem + put_prem
    if total == 0:
        return 0.0, 0.0
    # Normalize: net / total gives [-1, 1]
    normalized = np.clip(net / total, -1.0, 1.0)
    return net, normalized


def _gex_magnet_direction(gex_by_strike, spot_price):
    """Direction from spot to highest-GEX strike (magnet).

    If spot is below magnet → bullish (pulled up) → positive.
    If spot is above magnet → bearish (pulled down) → negative.
    """
    if gex_by_strike.empty:
        return 0.0, 0.0

    magnet_strike = gex_by_strike.idxmax()
    distance = magnet_strike - spot_price

    # Normalize by a reasonable range (50 points = full signal)
    normalized = np.clip(distance / 50.0, -1.0, 1.0)
    return distance, normalized


def _zero_dte_skew(df):
    """0DTE call volume / (call + put volume). > 0.55 bullish, < 0.45 bearish."""
    zero_dte = df[df["dte"] == 0]
    if zero_dte.empty:
        # Fall back to dte <= 1 for after-hours or weekends
        zero_dte = df[df["dte"] <= 1]
    if zero_dte.empty:
        return 0.5, 0.0

    call_vol = zero_dte["call_volume"].sum()
    put_vol = zero_dte["put_volume"].sum()
    total = call_vol + put_vol
    if total == 0:
        return 0.5, 0.0

    ratio = call_vol / total  # 0 to 1, with 0.5 = neutral
    # Map [0, 1] to [-1, 1]: (ratio - 0.5) * 2, then amplify
    # 0.55 → +0.1*2 = +0.2, then scale so 0.65 → ~1.0
    normalized = np.clip((ratio - 0.5) / 0.15, -1.0, 1.0)
    return ratio, normalized


def _put_call_ratio(df):
    """Total call_volume / put_volume. > 1.2 bullish, < 0.8 bearish."""
    call_vol = df["call_volume"].sum()
    put_vol = df["put_volume"].sum()
    if put_vol == 0:
        if call_vol > 0:
            return 999.0, 1.0
        return 1.0, 0.0

    ratio = call_vol / put_vol
    # Normalize: ratio of 1.0 = neutral, map using log scale
    # log(1.0) = 0, log(1.2) ≈ 0.18, log(0.8) ≈ -0.22
    if ratio <= 0:
        return 0.0, -1.0
    log_ratio = np.log(ratio)
    # Scale so log(1.5) ≈ 0.4 → 1.0
    normalized = np.clip(log_ratio / 0.4, -1.0, 1.0)
    return ratio, normalized


def _neutral_result():
    """Return a neutral signal when no data is available."""
    return {
        "direction": "NEUTRAL",
        "composite_score": 0.0,
        "confidence": 0.0,
        "net_premium": 0.0,
        "components": {
            "net_premium": {"label": "Net Premium Flow", "value": 0, "normalized": 0, "weight": SIGNAL_WEIGHTS["net_premium"], "contribution": 0},
            "gex_magnet": {"label": "GEX Magnet", "value": 0, "normalized": 0, "weight": SIGNAL_WEIGHTS["gex_magnet"], "contribution": 0},
            "zero_dte_skew": {"label": "0DTE Skew", "value": 0, "normalized": 0, "weight": SIGNAL_WEIGHTS["zero_dte_skew"], "contribution": 0},
            "pc_ratio": {"label": "P/C Ratio", "value": 0, "normalized": 0, "weight": SIGNAL_WEIGHTS["pc_ratio"], "contribution": 0},
        },
    }
