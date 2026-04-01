"""Contract Scanner — finds 0DTE SPX options with 3-5x potential."""

import numpy as np
from datetime import datetime
import pytz

from config import (
    SCANNER_PRICE_MIN, SCANNER_PRICE_MAX, SCANNER_MAX_DTE, SCANNER_TOP_N,
    SCANNER_WEIGHTS, SCANNER_VOLUME_SPIKE_MULTIPLIER,
    SCANNER_GAMMA_DELTA_THRESHOLD, SCANNER_CONFIDENCE_THRESHOLD,
    SCANNER_WINDOWS,
)


def scan_contracts(options_df, spot_price, signal):
    """Scan option chain for high-potential 0DTE contracts.

    Args:
        options_df: DataFrame with all option fields including bid/ask/theta/vega/iv
        spot_price: current SPX price
        signal: dict from calculate_close_signal()

    Returns:
        dict with direction, contracts, alert_active, alert_type, alert_reasons,
        timing_window, scan_summary
    """
    if options_df.empty:
        return _empty_result()

    direction, direction_reason = _resolve_direction(signal)
    candidates = _filter_candidates(options_df, spot_price, direction)
    scored = _score_candidates(candidates, spot_price, direction, options_df)
    scored.sort(key=lambda c: c["score"], reverse=True)
    top_contracts = scored[:SCANNER_TOP_N]
    timing_window = _get_current_window()
    alert_active, alert_type, alert_reasons = _evaluate_alerts(
        top_contracts, timing_window, signal
    )

    return {
        "direction": direction,
        "direction_reason": direction_reason,
        "contracts": top_contracts,
        "alert_active": alert_active,
        "alert_type": alert_type,
        "alert_reasons": alert_reasons,
        "timing_window": timing_window,
        "scan_summary": {
            "total_0dte": len(options_df[options_df["dte"] <= SCANNER_MAX_DTE]),
            "in_price_range": len(candidates),
            "scored": len(scored),
            "price_range": f"${SCANNER_PRICE_MIN:.2f} - ${SCANNER_PRICE_MAX:.2f}",
            "direction_score": signal["composite_score"],
            "direction_confidence": signal["confidence"],
        },
    }


def _resolve_direction(signal):
    """Pick CALLS or PUTS based on close signal."""
    score = signal["composite_score"]
    confidence = signal["confidence"]

    if confidence < SCANNER_CONFIDENCE_THRESHOLD:
        return "CALLS", f"Low confidence ({confidence:.0f}%), defaulting to CALLS"

    if score > 0:
        return "CALLS", f"Bullish signal: {score:+.4f}, {confidence:.0f}% confidence"
    else:
        return "PUTS", f"Bearish signal: {score:+.4f}, {confidence:.0f}% confidence"


def _filter_candidates(options_df, spot_price, direction):
    """Filter to 0DTE contracts in the $4.00-$5.50 price range."""
    zero_dte = options_df[options_df["dte"] <= SCANNER_MAX_DTE].copy()
    if zero_dte.empty:
        zero_dte = options_df[options_df["dte"] <= 1].copy()
    if zero_dte.empty:
        return []

    prefix = "call" if direction == "CALLS" else "put"
    candidates = []

    for _, row in zero_dte.iterrows():
        mark = row.get(f"{prefix}_mark", 0)
        if mark < SCANNER_PRICE_MIN or mark > SCANNER_PRICE_MAX:
            continue

        bid = row.get(f"{prefix}_bid", 0)
        ask = row.get(f"{prefix}_ask", 0)
        delta = row.get(f"{prefix}_delta", 0)
        gamma = row.get(f"{prefix}_gamma", 0)
        theta = row.get(f"{prefix}_theta", 0)
        vega = row.get(f"{prefix}_vega", 0)
        iv = row.get(f"{prefix}_iv", 0)
        volume = row.get(f"{prefix}_volume", 0)
        oi = row.get(f"{prefix}_OI", 0)

        spread = ask - bid if ask > 0 and bid > 0 else 0
        spread_pct = spread / mark if mark > 0 else 1.0
        abs_delta = abs(delta)
        gamma_delta_ratio = gamma / abs_delta if abs_delta > 0.001 else 0
        vol_oi_ratio = volume / oi if oi > 0 else 0

        candidates.append({
            "strike": row["strike"],
            "expiration": row.get("expiration", ""),
            "mark": mark,
            "bid": bid,
            "ask": ask,
            "delta": delta,
            "gamma": gamma,
            "theta": theta,
            "vega": vega,
            "iv": iv,
            "volume": int(volume),
            "oi": int(oi),
            "spread": spread,
            "spread_pct": spread_pct,
            "gamma_delta_ratio": gamma_delta_ratio,
            "vol_oi_ratio": vol_oi_ratio,
        })

    return candidates


def _score_candidates(candidates, spot_price, direction, options_df):
    """Score each candidate 0-100 based on 3-5x move potential."""
    if not candidates:
        return []

    gamma_ratios = [c["gamma_delta_ratio"] for c in candidates]
    max_gamma_ratio = max(gamma_ratios) if gamma_ratios else 1
    iv_values = [c["iv"] for c in candidates if c["iv"] > 0]
    max_iv = max(iv_values) if iv_values else 1
    min_iv = min(iv_values) if iv_values else 0

    prefix = "call" if direction == "CALLS" else "put"
    zero_dte = options_df[options_df["dte"] <= SCANNER_MAX_DTE]
    if zero_dte.empty:
        zero_dte = options_df[options_df["dte"] <= 1]
    avg_volume = zero_dte[f"{prefix}_volume"].mean() if not zero_dte.empty else 1

    scored = []
    for c in candidates:
        components = {}

        # Gamma acceleration (30%)
        if max_gamma_ratio > 0:
            components["gamma_accel"] = min(c["gamma_delta_ratio"] / max_gamma_ratio * 100, 100)
        else:
            components["gamma_accel"] = 0

        # Volume activity (25%)
        components["volume_activity"] = min(c["vol_oi_ratio"] / 3.0 * 100, 100)

        # Spread tightness (20%)
        components["spread_tight"] = max((1 - c["spread_pct"]) * 100, 0)

        # IV room (15%)
        if max_iv > min_iv and c["iv"] > 0:
            iv_pct = (c["iv"] - min_iv) / (max_iv - min_iv)
            components["iv_room"] = (1 - iv_pct) * 100
        else:
            components["iv_room"] = 50

        # OTM distance (10%)
        if direction == "CALLS":
            distance = c["strike"] - spot_price
        else:
            distance = spot_price - c["strike"]

        if 5 <= distance <= 20:
            components["distance_otm"] = 100
        elif 0 < distance < 5:
            components["distance_otm"] = distance / 5 * 80
        elif 20 < distance <= 40:
            components["distance_otm"] = max(100 - (distance - 20) / 20 * 80, 20)
        else:
            components["distance_otm"] = 10

        score = sum(components[k] * SCANNER_WEIGHTS[k] for k in SCANNER_WEIGHTS)

        c["score"] = round(score, 1)
        c["score_components"] = {k: round(v, 1) for k, v in components.items()}
        c["avg_volume"] = avg_volume
        scored.append(c)

    return scored


def _get_current_window():
    """Check if current time is in a scanner timing window."""
    eastern = pytz.timezone("US/Eastern")
    now = datetime.now(eastern)
    current_minutes = now.hour * 60 + now.minute

    for window in SCANNER_WINDOWS:
        start = window["start_hour"] * 60 + window["start_min"]
        end = window["end_hour"] * 60 + window["end_min"]
        if start <= current_minutes <= end:
            return {
                "name": window["name"],
                "start": f"{window['start_hour']}:{window['start_min']:02d}",
                "end": f"{window['end_hour']}:{window['end_min']:02d}",
            }
    return None


def _evaluate_alerts(contracts, timing_window, signal):
    """Check if alert conditions are met."""
    if not contracts:
        return False, None, []

    reasons = []
    top = contracts[0]

    # Volume spike
    volume_spike = False
    avg_vol = top.get("avg_volume", 0)
    if avg_vol > 0 and top["volume"] > avg_vol * SCANNER_VOLUME_SPIKE_MULTIPLIER:
        volume_spike = True
        reasons.append(f"Volume spike: {top['volume']:,} vs avg {avg_vol:,.0f} ({top['volume']/avg_vol:.1f}x)")

    # Gamma setup
    gamma_setup = False
    if top["gamma_delta_ratio"] > SCANNER_GAMMA_DELTA_THRESHOLD:
        gamma_setup = True
        reasons.append(f"Gamma accel: {top['gamma_delta_ratio']:.4f} (>{SCANNER_GAMMA_DELTA_THRESHOLD})")

    # Timing window
    in_window = timing_window is not None
    if in_window:
        reasons.append(f"{timing_window['name']} ({timing_window['start']}-{timing_window['end']} ET)")

    # Direction confidence
    confident = signal["confidence"] > SCANNER_CONFIDENCE_THRESHOLD
    if confident:
        reasons.append(f"Direction: {signal['confidence']:.0f}% ({signal['direction']})")

    active_triggers = sum([volume_spike, gamma_setup, in_window])
    if active_triggers >= 3:
        return True, "COMPOSITE", reasons
    elif volume_spike:
        return True, "VOLUME_SPIKE", reasons
    elif gamma_setup and in_window:
        return True, "GAMMA_SETUP", reasons
    elif in_window and confident:
        return True, "TIME_WINDOW", reasons
    else:
        return False, None, reasons


def _empty_result():
    return {
        "direction": "CALLS",
        "direction_reason": "No data available",
        "contracts": [],
        "alert_active": False,
        "alert_type": None,
        "alert_reasons": [],
        "timing_window": None,
        "scan_summary": {
            "total_0dte": 0, "in_price_range": 0, "scored": 0,
            "price_range": "", "direction_score": 0, "direction_confidence": 0,
        },
    }
