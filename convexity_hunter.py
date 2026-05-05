"""Convexity Hunter — V2 lottery scanner.

Built on the actual physics of why $100 contracts go to $4,000 in a week:
not pattern matching, but the math of options convexity + smart-money flow
+ catalyst proximity.

THREE PILLARS (multiplicative, all must be strong):

1. LEVERAGE QUALITY (40%) — the contract physics
   - Gamma per dollar of premium (Γ/P): the real explosive metric
   - Delta in 0.10-0.30 sweet zone: room to expand convexity
   - Move-to-3x: what % stock move triples the contract
   - Theta efficiency: days you can hold before decay kills you

2. SMART MONEY SIGNAL (35%) — who's buying and how
   - Strike-level V/OI (unusual on this contract)
   - Adjacent-strikes V/OI (multi-strike sweep)
   - Same-side concentration (call% or put% of expiry flow)
   - IV expansion (front IV vs back IV term structure)
   - Block-size proxy (avg trade size estimation)

3. CATALYST SETUP (25%) — the why behind the move
   - IV term structure inversion (front >> back = event priced in)
   - Stock breakout/breakdown vs 20-day range
   - Sector relative strength (proxy via stock vs avg)
   - Volume surge vs 30-day average

Score uses geometric mean (multiplicative) so all three pillars must be
present — this kills false positives where one factor dominates.

NOT a probability estimator. High score = setup matches the explosive-move
template. Most still expire worthless. Position size accordingly.
"""

import math
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict


# ============================================================
# Universe — re-use lottery_scanner.UNIVERSE for consistency
# ============================================================
from lottery_scanner import UNIVERSE, ALL_TICKERS, fetch_quote_data


# ============================================================
# OPTIONS PHYSICS — the math that makes $100 → $4000 possible
# ============================================================

def move_to_multiplier(premium, delta, gamma, multiplier):
    """Solve for stock move ΔS that takes contract to N * premium.

    Uses 2nd-order Taylor: P_new ≈ P + D*ΔS + 0.5*G*ΔS²
    Set equal to N*P, solve quadratic.

    Returns ΔS (positive = bullish move for calls, bearish for puts) or None.
    """
    if premium <= 0 or gamma <= 0:
        return None
    target = multiplier * premium
    # 0.5*G*ΔS² + D*ΔS + (P - N*P) = 0
    a = 0.5 * gamma
    b = abs(delta)
    c = premium - target
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    delta_s = (-b + math.sqrt(disc)) / (2 * a)
    return delta_s if delta_s > 0 else None


def lognormal_prob_above(spot, target_move, iv, days_to_expiry):
    """Probability stock moves by target_move (in $) within DTE under lognormal IV.

    Returns 0-1 probability. Uses Black-Scholes-ish: ln(S_T/S_0) ~ N(μT, σ²T).
    """
    if spot <= 0 or iv <= 0 or days_to_expiry <= 0 or target_move <= 0:
        return 0.0
    if iv > 5:
        iv = iv / 100  # normalize to decimal
    sigma_t = iv * math.sqrt(days_to_expiry / 365)
    if sigma_t <= 0:
        return 0.0
    target_ratio = target_move / spot
    # ln(1 + r) ≈ r for small moves
    ln_target = math.log(1 + target_ratio) if target_ratio > -0.99 else -99
    # Drift assumption ≈ 0 for short DTE, no risk-free rate
    z = ln_target / sigma_t
    # 1 - Φ(z) using error function
    return 0.5 * (1 - math.erf(z / math.sqrt(2)))


# ============================================================
# PILLAR 1 — LEVERAGE QUALITY (40%)
# ============================================================

def score_leverage_quality(contract):
    """Pure physics of the contract: how explosive is it intrinsically?"""
    mark = contract["mark"]
    delta = abs(contract.get("delta", 0))
    gamma = contract.get("gamma", 0)
    theta = abs(contract.get("theta", 0))
    dte = max(contract["dte"], 1)

    # Sub 1: Gamma per dollar premium (the actual leverage metric)
    if mark > 0 and gamma > 0:
        gpd = gamma / mark
        # Typical gpd for sweet-spot contracts: 0.05 - 0.30
        if gpd >= 0.20:
            s_gpd = 10
        elif gpd >= 0.10:
            s_gpd = 8
        elif gpd >= 0.05:
            s_gpd = 6
        elif gpd >= 0.02:
            s_gpd = 4
        else:
            s_gpd = 2
    else:
        s_gpd = 0

    # Sub 2: Delta in 0.10-0.30 sweet zone (room to expand)
    if 0.12 <= delta <= 0.28:
        s_delta = 10  # Sweet spot — most explosive convexity
    elif 0.08 <= delta < 0.12 or 0.28 < delta <= 0.40:
        s_delta = 7
    elif 0.05 <= delta < 0.08 or 0.40 < delta <= 0.55:
        s_delta = 5
    elif delta < 0.05:
        s_delta = 2  # Too far OTM, low probability
    else:
        s_delta = 3  # Too ITM, less convexity left

    # Sub 3: Move-to-3x feasibility — what % move triples the contract?
    if contract["spot"] > 0 and gamma > 0:
        ds_3x = move_to_multiplier(mark, delta, gamma, 3)
        if ds_3x:
            move_pct_3x = (ds_3x / contract["spot"]) * 100
            if move_pct_3x <= 5:
                s_move = 10  # 3x on a 5% move is elite
            elif move_pct_3x <= 8:
                s_move = 8
            elif move_pct_3x <= 12:
                s_move = 6
            elif move_pct_3x <= 18:
                s_move = 4
            else:
                s_move = 2
        else:
            s_move = 1
    else:
        s_move = 0

    # Sub 4: Theta efficiency — days of premium runway
    if theta > 0 and mark > 0:
        days_runway = mark / theta
        if days_runway >= dte:
            s_theta = 10  # Premium covers full holding period
        elif days_runway >= dte * 0.7:
            s_theta = 7
        elif days_runway >= dte * 0.4:
            s_theta = 4
        else:
            s_theta = 2
    else:
        s_theta = 5  # Unknown — neutral

    # Weighted sub-scores within pillar
    score = (s_gpd * 0.40 + s_delta * 0.25 + s_move * 0.25 + s_theta * 0.10)
    return {
        "score": round(score, 2),
        "subs": {
            "gamma_per_dollar": s_gpd,
            "delta_zone": s_delta,
            "move_to_3x": s_move,
            "theta_runway": s_theta,
        },
    }


# ============================================================
# PILLAR 2 — SMART MONEY SIGNAL (35%)
# ============================================================

def score_smart_money(contract, chain_context):
    """Detection of unusual flow: who's buying, how big, how coordinated."""
    vol = contract["volume"]
    oi = contract["oi"]

    # Sub 1: Strike V/OI ratio
    if oi > 0:
        voi = vol / oi
        if voi >= 10:
            s_voi = 10  # Massive new positioning
        elif voi >= 5:
            s_voi = 9
        elif voi >= 2:
            s_voi = 7
        elif voi >= 1:
            s_voi = 5
        elif voi >= 0.5:
            s_voi = 3
        else:
            s_voi = 1
    else:
        s_voi = 8 if vol > 200 else 4 if vol > 50 else 1  # New strike with volume

    # Sub 2: Adjacent-strike sweep (multi-strike unusual)
    side = contract["side"]
    expiration = contract["expiration"]
    same_side_chain = chain_context.get(f"{side}_{expiration}", [])
    strike = contract["strike"]
    # Count adjacent strikes (within ±10% of this strike) with V/OI > 1
    adjacent_unusual = 0
    for c in same_side_chain:
        if c["strike"] == strike:
            continue
        if abs(c["strike"] - strike) / strike <= 0.10:
            adj_voi = c["volume"] / max(c["oi"], 1)
            if adj_voi > 1:
                adjacent_unusual += 1
    if adjacent_unusual >= 4:
        s_sweep = 10  # Coordinated multi-strike attack
    elif adjacent_unusual >= 2:
        s_sweep = 7
    elif adjacent_unusual >= 1:
        s_sweep = 5
    else:
        s_sweep = 2

    # Sub 3: Same-side concentration (% of total flow on this side)
    total_call_vol = chain_context.get("total_call_vol", 0)
    total_put_vol = chain_context.get("total_put_vol", 0)
    total = total_call_vol + total_put_vol
    if total > 0:
        side_share = (total_call_vol if side == "CALL" else total_put_vol) / total
        if side_share >= 0.80:
            s_skew = 10  # Heavily one-sided
        elif side_share >= 0.65:
            s_skew = 8
        elif side_share >= 0.55:
            s_skew = 6
        elif side_share >= 0.45:
            s_skew = 4
        else:
            s_skew = 2
    else:
        s_skew = 3

    # Sub 4: IV term structure inversion (front >> back = event priced in)
    front_iv = chain_context.get("front_iv", 0)
    back_iv = chain_context.get("back_iv", 0)
    if front_iv > 0 and back_iv > 0:
        term_ratio = front_iv / back_iv
        if term_ratio >= 1.5:
            s_term = 10  # Strong inversion = event imminent
        elif term_ratio >= 1.25:
            s_term = 7
        elif term_ratio >= 1.10:
            s_term = 5
        elif term_ratio >= 1.0:
            s_term = 4
        else:
            s_term = 3  # Normal contango — no event priced in
    else:
        s_term = 4

    # Sub 5: Block size proxy (avg trade size = total volume / num strikes traded)
    # If volume per strike is high, suggests block prints
    num_strikes_traded = len([c for c in same_side_chain if c["volume"] > 0])
    if num_strikes_traded > 0:
        avg_vol_per_strike = (total_call_vol if side == "CALL" else total_put_vol) / max(num_strikes_traded, 1)
        if avg_vol_per_strike >= 5000:
            s_block = 10
        elif avg_vol_per_strike >= 2000:
            s_block = 8
        elif avg_vol_per_strike >= 500:
            s_block = 6
        elif avg_vol_per_strike >= 100:
            s_block = 4
        else:
            s_block = 2
    else:
        s_block = 1

    score = (s_voi * 0.30 + s_sweep * 0.25 + s_skew * 0.15
             + s_term * 0.20 + s_block * 0.10)
    return {
        "score": round(score, 2),
        "subs": {
            "strike_voi": s_voi,
            "adjacent_sweep": s_sweep,
            "side_concentration": s_skew,
            "iv_term_structure": s_term,
            "block_size": s_block,
        },
    }


# ============================================================
# PILLAR 3 — CATALYST SETUP (25%)
# ============================================================

def score_catalyst(contract, stock_data):
    """Macro setup: is there a reason for the move to happen?"""

    # Sub 1: Stock momentum / breakout
    pct_5d = stock_data.get("pct_change_5d", 0)
    pct_today = stock_data.get("pct_change_today", 0)
    side = contract["side"]
    # For calls, want bullish momentum; for puts, bearish
    if side == "CALL":
        directional_5d = pct_5d
        directional_today = pct_today
    else:
        directional_5d = -pct_5d
        directional_today = -pct_today

    momentum_score = 0
    if directional_5d >= 15:
        momentum_score += 6
    elif directional_5d >= 8:
        momentum_score += 4
    elif directional_5d >= 4:
        momentum_score += 2
    elif directional_5d >= 0:
        momentum_score += 1
    else:
        momentum_score = max(0, momentum_score - 2)  # wrong direction

    if directional_today >= 5:
        momentum_score += 4
    elif directional_today >= 2:
        momentum_score += 2
    elif directional_today >= 0:
        momentum_score += 1
    s_momentum = min(10, max(0, momentum_score))

    # Sub 2: Volume surge (catalyst confirmation)
    vol_ratio = stock_data.get("volume_vs_avg", 1.0)
    if vol_ratio >= 4:
        s_volume = 10
    elif vol_ratio >= 2.5:
        s_volume = 8
    elif vol_ratio >= 1.5:
        s_volume = 6
    elif vol_ratio >= 1.1:
        s_volume = 4
    else:
        s_volume = 2

    # Sub 3: Earnings proximity (if within DTE = catalyst priced)
    earnings_dte = stock_data.get("earnings_dte")
    contract_dte = contract["dte"]
    if earnings_dte is not None and 0 < earnings_dte <= contract_dte:
        # Earnings WITHIN contract life — high catalyst score
        s_earnings = 10
    elif earnings_dte is not None and earnings_dte <= contract_dte + 7:
        s_earnings = 7  # Just after expiry — less useful but still energy
    elif earnings_dte is not None and earnings_dte <= 30:
        s_earnings = 4
    else:
        s_earnings = 3  # Unknown / no earnings catalyst — neutral

    # Sub 4: Range position — breaking out of recent range?
    # Use absolute pct_5d as proxy (without direction filtering)
    abs_5d = abs(pct_5d)
    if abs_5d >= 20:
        s_range = 10  # Major regime shift
    elif abs_5d >= 12:
        s_range = 8
    elif abs_5d >= 6:
        s_range = 5
    elif abs_5d >= 3:
        s_range = 3
    else:
        s_range = 1  # Boring range = no catalyst

    score = (s_momentum * 0.35 + s_volume * 0.25
             + s_earnings * 0.20 + s_range * 0.20)
    return {
        "score": round(score, 2),
        "subs": {
            "directional_momentum": s_momentum,
            "volume_surge": s_volume,
            "earnings_proximity": s_earnings,
            "range_break": s_range,
        },
    }


# ============================================================
# COMPOSITE — multiplicative geometric mean across pillars
# ============================================================

def composite_mlc_score(leverage, smart_money, catalyst):
    """Multiplicative composite. Geometric mean penalizes weak pillars.

    Geometric mean(L, S, C) — all three must be strong for high score.
    A 10 in one pillar can't compensate for 2 in another.
    """
    L = leverage["score"]
    S = smart_money["score"]
    C = catalyst["score"]
    if L <= 0 or S <= 0 or C <= 0:
        return 0.0
    # Weighted geometric mean — weights as exponents
    score = (L ** 0.40) * (S ** 0.35) * (C ** 0.25)
    return round(score, 2)


# ============================================================
# CHAIN CONTEXT BUILDER — feeds smart money scorer with chain-wide data
# ============================================================

def build_chain_context(contracts):
    """Pre-compute chain-wide signals so each contract scorer has context."""
    ctx = {}
    total_call_vol = sum(c["volume"] for c in contracts if c["side"] == "CALL")
    total_put_vol = sum(c["volume"] for c in contracts if c["side"] == "PUT")
    ctx["total_call_vol"] = total_call_vol
    ctx["total_put_vol"] = total_put_vol

    # Group by side+expiration for adjacent-sweep detection
    grouped = defaultdict(list)
    for c in contracts:
        grouped[f"{c['side']}_{c['expiration']}"].append(c)
    for k, v in grouped.items():
        ctx[k] = v

    # Term structure: front-week vs back-week IV (avg ATM-ish)
    # Use ATM contracts (delta closest to 0.5) to estimate IV
    by_dte = defaultdict(list)
    for c in contracts:
        if c["iv"] > 0 and 0.3 < abs(c["delta"]) < 0.7:
            by_dte[c["dte"]].append(c["iv"])
    if by_dte:
        sorted_dtes = sorted(by_dte.keys())
        front_dte = sorted_dtes[0]
        back_dte = sorted_dtes[-1] if len(sorted_dtes) > 1 else front_dte
        ctx["front_iv"] = np.mean(by_dte[front_dte]) if by_dte[front_dte] else 0
        ctx["back_iv"] = np.mean(by_dte[back_dte]) if by_dte[back_dte] else 0
    else:
        ctx["front_iv"] = 0
        ctx["back_iv"] = 0

    return ctx


# ============================================================
# SCAN PIPELINE
# ============================================================

def fetch_options_full(client, symbol, max_dte=21):
    """Fetch options chain with Greeks. Same shape as lottery_scanner but
    keeps gamma + theta which V2 needs."""
    try:
        today = datetime.now()
        to_date = today + timedelta(days=max_dte)
        resp = client.option_chains(
            symbol=symbol,
            contractType="ALL",
            includeUnderlyingQuote=False,
            fromDate=today.strftime("%Y-%m-%d"),
            toDate=to_date.strftime("%Y-%m-%d"),
            strikeCount=50,
        )
        if not resp.ok:
            return None
        data = resp.json()
        contracts = []
        for side, key in [("CALL", "callExpDateMap"), ("PUT", "putExpDateMap")]:
            exp_map = data.get(key, {})
            for exp_key, strikes in exp_map.items():
                exp_parts = exp_key.split(":")
                exp_date = exp_parts[0]
                dte = int(exp_parts[1]) if len(exp_parts) > 1 else 0
                if dte > max_dte:
                    continue
                for strike_key, contract_list in strikes.items():
                    for c in contract_list:
                        contracts.append({
                            "side": side,
                            "strike": float(c.get("strikePrice", strike_key)),
                            "expiration": exp_date,
                            "dte": c.get("daysToExpiration", dte),
                            "mark": float(c.get("mark", 0)),
                            "bid": float(c.get("bid", 0)),
                            "ask": float(c.get("ask", 0)),
                            "volume": int(c.get("totalVolume", 0)),
                            "oi": int(c.get("openInterest", 0)),
                            "iv": float(c.get("volatility", 0)),
                            "delta": float(c.get("delta", 0)),
                            "gamma": float(c.get("gamma", 0)),
                            "theta": float(c.get("theta", 0)),
                            "vega": float(c.get("vega", 0)),
                        })
        return contracts
    except Exception:
        return None


def scan_symbol_v2(client, symbol, max_dte=21, max_premium=2.50):
    """Full V2 scan pipeline for one symbol."""
    stock_data = fetch_quote_data(client, symbol)
    if not stock_data or stock_data["spot"] <= 0:
        return []

    contracts = fetch_options_full(client, symbol, max_dte=max_dte)
    if not contracts:
        return []

    chain_ctx = build_chain_context(contracts)

    results = []
    for c in contracts:
        if c["mark"] <= 0 or c["mark"] > max_premium or c["mark"] < 0.10:
            continue
        # Liquidity floor
        if c["oi"] < 50 and c["volume"] < 100:
            continue
        # Reject extreme spreads
        if c["bid"] > 0 and c["ask"] > 0:
            spread_pct = (c["ask"] - c["bid"]) / max((c["bid"] + c["ask"]) / 2, 0.01)
            if spread_pct > 0.50:
                continue

        c["spot"] = stock_data["spot"]

        leverage = score_leverage_quality(c)
        smart = score_smart_money(c, chain_ctx)
        catalyst = score_catalyst(c, stock_data)
        composite = composite_mlc_score(leverage, smart, catalyst)

        # Reverse calc: move % needed for 3x, 5x, 10x
        ds_3x = move_to_multiplier(c["mark"], abs(c["delta"]), c["gamma"], 3)
        ds_5x = move_to_multiplier(c["mark"], abs(c["delta"]), c["gamma"], 5)
        ds_10x = move_to_multiplier(c["mark"], abs(c["delta"]), c["gamma"], 10)
        spot = stock_data["spot"]
        pct_3x = (ds_3x / spot * 100) if ds_3x else None
        pct_5x = (ds_5x / spot * 100) if ds_5x else None
        pct_10x = (ds_10x / spot * 100) if ds_10x else None

        # Implied probability via lognormal
        prob_3x = lognormal_prob_above(spot, ds_3x, c["iv"], c["dte"]) if ds_3x else 0
        prob_5x = lognormal_prob_above(spot, ds_5x, c["iv"], c["dte"]) if ds_5x else 0
        prob_10x = lognormal_prob_above(spot, ds_10x, c["iv"], c["dte"]) if ds_10x else 0

        results.append({
            "symbol": symbol,
            "side": c["side"],
            "strike": c["strike"],
            "expiration": c["expiration"],
            "dte": c["dte"],
            "mark": c["mark"],
            "bid": c["bid"],
            "ask": c["ask"],
            "cost": c["mark"] * 100,
            "volume": c["volume"],
            "oi": c["oi"],
            "iv": c["iv"] if c["iv"] < 5 else c["iv"] / 100,
            "delta": c["delta"],
            "gamma": c["gamma"],
            "theta": c["theta"],
            "spot": spot,
            "pct_today": stock_data["pct_change_today"],
            "pct_5d": stock_data["pct_change_5d"],
            "vol_vs_avg": stock_data["volume_vs_avg"],
            "leverage": leverage,
            "smart_money": smart,
            "catalyst": catalyst,
            "score": composite,
            "pct_3x": pct_3x,
            "pct_5x": pct_5x,
            "pct_10x": pct_10x,
            "prob_3x": prob_3x,
            "prob_5x": prob_5x,
            "prob_10x": prob_10x,
            "front_iv": chain_ctx["front_iv"],
            "back_iv": chain_ctx["back_iv"],
        })

    return results


def scan_universe_v2(client, tickers=None, max_dte=21, min_score=5.0,
                    max_premium=2.50, max_workers=5, progress_cb=None):
    """Scan a list of tickers in parallel using V2 algo."""
    if tickers is None:
        tickers = ALL_TICKERS

    all_results = []
    completed = 0
    total = len(tickers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(scan_symbol_v2, client, t, max_dte, max_premium): t
            for t in tickers
        }
        for fut in as_completed(futures):
            symbol = futures[fut]
            try:
                results = fut.result()
                all_results.extend(results)
            except Exception:
                pass
            completed += 1
            if progress_cb:
                progress_cb(completed, total, symbol)

    qualified = [r for r in all_results if r["score"] >= min_score]
    qualified.sort(key=lambda x: x["score"], reverse=True)
    return qualified
