"""Factor 2 Signal Engine — 5 independent signals for 0DTE SPX direction.

Replaces the overlapping volume-based signals with truly independent factors:
1. Net Delta Flow (30%) — dollar-weighted directional positioning
2. GEX Flip Level (25%) — are we in amplification or dampening zone
3. IV Skew Shift (20%) — institutional hedging pressure
4. OI Walls (15%) — magnetic strike levels
5. Intraday Momentum (10%) — trend confirmation from price action
"""

import numpy as np
import pandas as pd

FACTOR2_WEIGHTS = {
    "net_delta_flow": 0.30,
    "gex_flip": 0.25,
    "iv_skew": 0.20,
    "oi_walls": 0.15,
    "momentum": 0.10,
}

FACTOR2_THRESHOLD = 0.20  # Lower threshold — these signals are independent


def calculate_signal_v2(options_df, spot_price, gex_by_strike, price_history=None):
    """Calculate Factor 2 composite signal.

    Args:
        options_df: full options chain DataFrame
        spot_price: current SPX price
        gex_by_strike: Series of net GEX per strike
        price_history: list of (timestamp, price) tuples for momentum

    Returns:
        dict with direction, composite_score, confidence, components, flip_level
    """
    if options_df.empty:
        return _empty_result()

    components = {}

    # 1. Net Delta Flow — volume × delta × mark, calls vs puts
    ndf_val, ndf_norm = _net_delta_flow(options_df)
    components["net_delta_flow"] = {
        "label": "Net Delta Flow",
        "value": ndf_val,
        "normalized": ndf_norm,
        "weight": FACTOR2_WEIGHTS["net_delta_flow"],
        "contribution": ndf_norm * FACTOR2_WEIGHTS["net_delta_flow"],
    }

    # 2. GEX Flip Level — position relative to zero-gamma level
    flip_level, gex_val, gex_norm = _gex_flip_signal(gex_by_strike, spot_price)
    components["gex_flip"] = {
        "label": "GEX Flip Level",
        "value": gex_val,
        "normalized": gex_norm,
        "weight": FACTOR2_WEIGHTS["gex_flip"],
        "contribution": gex_norm * FACTOR2_WEIGHTS["gex_flip"],
    }

    # 3. IV Skew Shift — put IV vs call IV at same distance OTM
    skew_val, skew_norm = _iv_skew_shift(options_df, spot_price)
    components["iv_skew"] = {
        "label": "IV Skew",
        "value": skew_val,
        "normalized": skew_norm,
        "weight": FACTOR2_WEIGHTS["iv_skew"],
        "contribution": skew_norm * FACTOR2_WEIGHTS["iv_skew"],
    }

    # 4. OI Walls — net OI above vs below spot
    wall_val, wall_norm = _oi_wall_signal(options_df, spot_price)
    components["oi_walls"] = {
        "label": "OI Walls",
        "value": wall_val,
        "normalized": wall_norm,
        "weight": FACTOR2_WEIGHTS["oi_walls"],
        "contribution": wall_norm * FACTOR2_WEIGHTS["oi_walls"],
    }

    # 5. Intraday Momentum — price trend from history
    mom_val, mom_norm = _intraday_momentum(price_history, spot_price)
    components["momentum"] = {
        "label": "Momentum",
        "value": mom_val,
        "normalized": mom_norm,
        "weight": FACTOR2_WEIGHTS["momentum"],
        "contribution": mom_norm * FACTOR2_WEIGHTS["momentum"],
    }

    # Composite
    composite = sum(c["contribution"] for c in components.values())
    composite = np.clip(composite, -1.0, 1.0)

    if composite > FACTOR2_THRESHOLD:
        direction = "BUY"
    elif composite < -FACTOR2_THRESHOLD:
        direction = "SELL"
    else:
        direction = "NEUTRAL"

    confidence = abs(composite) * 100

    return {
        "direction": direction,
        "composite_score": round(composite, 4),
        "confidence": round(confidence, 1),
        "components": components,
        "flip_level": flip_level,
    }


def _net_delta_flow(df):
    """Net dollar-delta flow: sum(volume × |delta| × mark × 100) for calls vs puts.

    This captures NOTIONAL positioning, not just contract count.
    A whale buying 100 deep ITM calls shows up here but not in simple volume.
    """
    # Call flow: volume × delta × mark (positive = bullish flow)
    call_flow = (df["call_volume"] * df["call_delta"].abs() * df["call_mark"] * 100).sum()
    # Put flow: volume × |delta| × mark (positive number)
    put_flow = (df["put_volume"] * df["put_delta"].abs() * df["put_mark"] * 100).sum()

    net = call_flow - put_flow
    total = call_flow + put_flow

    if total == 0:
        return 0.0, 0.0

    # Normalize: net/total gives [-1, 1]
    normalized = np.clip(net / total, -1.0, 1.0)
    return net, normalized


def _gex_flip_signal(gex_by_strike, spot_price):
    """Find the 0-gamma level and determine if spot is above or below it.

    Above flip = positive gamma = dealers dampen moves = mean-reverting
    Below flip = negative gamma = dealers amplify moves = trending/explosive

    Signal: if spot > flip → bullish (dealers support), spot < flip → bearish (dealers push down)
    """
    if gex_by_strike.empty:
        return spot_price, 0.0, 0.0

    sorted_gex = gex_by_strike.sort_index()

    # Find where GEX crosses zero (from positive to negative going down)
    flip_level = None
    strikes = sorted_gex.index.values
    values = sorted_gex.values

    for i in range(len(strikes) - 1):
        # Look for sign change
        if values[i] * values[i + 1] < 0:
            # Linear interpolation
            s1, s2 = strikes[i], strikes[i + 1]
            v1, v2 = values[i], values[i + 1]
            flip_level = s1 + (s2 - s1) * (-v1) / (v2 - v1)
            break

    if flip_level is None:
        # No crossover — check if all positive or all negative
        if values.sum() > 0:
            flip_level = strikes[0]  # All positive, flip below range
        else:
            flip_level = strikes[-1]  # All negative, flip above range

    distance = spot_price - flip_level
    # Normalize: 20 pts above flip = fully bullish
    normalized = np.clip(distance / 20.0, -1.0, 1.0)

    return round(flip_level, 1), distance, normalized


def _iv_skew_shift(df, spot_price):
    """Compare put IV to call IV at similar distances OTM.

    Higher put IV relative to call IV = institutional hedging = bearish pressure.
    We look at 0DTE or nearest expiry contracts 5-20 points OTM on each side.
    """
    zero_dte = df[df["dte"] <= 1].copy()
    if zero_dte.empty:
        zero_dte = df.copy()
    if zero_dte.empty:
        return 0.0, 0.0

    # OTM calls: strikes above spot
    otm_calls = zero_dte[
        (zero_dte["strike"] > spot_price) &
        (zero_dte["strike"] <= spot_price + 30) &
        (zero_dte["call_iv"] > 0)
    ]
    # OTM puts: strikes below spot
    otm_puts = zero_dte[
        (zero_dte["strike"] < spot_price) &
        (zero_dte["strike"] >= spot_price - 30) &
        (zero_dte["call_iv"] > 0)
    ]

    if otm_calls.empty or otm_puts.empty:
        return 0.0, 0.0

    avg_call_iv = otm_calls["call_iv"].mean()
    avg_put_iv = otm_puts["put_iv"].mean()

    if avg_call_iv == 0:
        return 0.0, 0.0

    # Skew ratio: put_iv / call_iv. >1 = puts more expensive = bearish hedging
    skew = avg_put_iv / avg_call_iv
    # Normalize: skew of 1.3 = fully bearish, 0.7 = fully bullish
    # Inverted: high put IV = bearish = negative signal
    normalized = np.clip(-(skew - 1.0) / 0.3, -1.0, 1.0)

    return round(skew, 3), normalized


def _oi_wall_signal(df, spot_price):
    """OI wall analysis — massive OI acts as magnetic levels.

    If more call OI above spot than put OI below → price pulled up (bullish)
    If more put OI below → price pulled/pinned down (bearish)
    """
    above = df[df["strike"] > spot_price]
    below = df[df["strike"] <= spot_price]

    # Call OI above spot = resistance/magnet above
    call_oi_above = above["call_OI"].sum()
    # Put OI below spot = support/magnet below
    put_oi_below = below["put_OI"].sum()

    # Total OI walls
    total = call_oi_above + put_oi_below
    if total == 0:
        return 0.0, 0.0

    # More call OI above = bullish pull, more put OI below = bearish pull
    net = call_oi_above - put_oi_below
    normalized = np.clip(net / total, -1.0, 1.0)

    return net, normalized


def _intraday_momentum(price_history, current_price):
    """Simple momentum from price history — direction and magnitude.

    Uses the last ~5-10 data points to determine trend.
    """
    if not price_history or len(price_history) < 3:
        return 0.0, 0.0

    # Use last 10 points (about 3-4 minutes at 20s refresh)
    recent = price_history[-10:]
    start_price = recent[0][1]

    if start_price == 0:
        return 0.0, 0.0

    change = current_price - start_price
    change_pct = change / start_price * 100

    # Normalize: 0.1% move = moderate signal, 0.3% = full signal
    normalized = np.clip(change_pct / 0.3, -1.0, 1.0)

    return round(change_pct, 4), normalized


def find_gex_flip_level(gex_by_strike):
    """Public helper to find the 0-gamma level for the dedicated tab."""
    if gex_by_strike.empty:
        return None, {}

    sorted_gex = gex_by_strike.sort_index()
    strikes = sorted_gex.index.values
    values = sorted_gex.values

    flip_level = None
    for i in range(len(strikes) - 1):
        if values[i] * values[i + 1] < 0:
            s1, s2 = strikes[i], strikes[i + 1]
            v1, v2 = values[i], values[i + 1]
            flip_level = s1 + (s2 - s1) * (-v1) / (v2 - v1)
            break

    # Determine gamma regime
    total_gex = values.sum()
    positive_gex = values[values > 0].sum()
    negative_gex = values[values < 0].sum()

    # Find max positive GEX strike (dealer magnet)
    max_gex_strike = strikes[np.argmax(values)] if len(values) > 0 else None

    info = {
        "flip_level": round(flip_level, 1) if flip_level else None,
        "total_gex": total_gex,
        "positive_gex": positive_gex,
        "negative_gex": negative_gex,
        "max_gex_strike": float(max_gex_strike) if max_gex_strike is not None else None,
        "regime": "POSITIVE" if total_gex > 0 else "NEGATIVE",
        "gex_by_strike": sorted_gex,
    }

    return flip_level, info


def _empty_result():
    return {
        "direction": "NEUTRAL",
        "composite_score": 0.0,
        "confidence": 0.0,
        "flip_level": None,
        "components": {
            "net_delta_flow": {"label": "Net Delta Flow", "value": 0, "normalized": 0, "weight": 0.30, "contribution": 0},
            "gex_flip": {"label": "GEX Flip Level", "value": 0, "normalized": 0, "weight": 0.25, "contribution": 0},
            "iv_skew": {"label": "IV Skew", "value": 0, "normalized": 0, "weight": 0.20, "contribution": 0},
            "oi_walls": {"label": "OI Walls", "value": 0, "normalized": 0, "weight": 0.15, "contribution": 0},
            "momentum": {"label": "Momentum", "value": 0, "normalized": 0, "weight": 0.10, "contribution": 0},
        },
    }
