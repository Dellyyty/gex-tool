"""Pre-Breakout Hunter — stealth accumulation detector.

Designed to catch the SETUP before the move, not the move in progress.

Core thesis: explosive moves often have a 'quiet' positioning phase where
smart money builds a position via OTM options BEFORE the stock catalyst
fires. By the time the stock is +20%, the easy money is already made.

Pre-breakout signals (the 'before' state):
- Heavy V/OI on OTM options (someone positioning)
- IV term structure inversion (event priced in soon)
- Stock has been QUIET (low 5d move, 3-8% range) — potential energy
- Stock volume elevated WITHOUT proportional price move (accumulation)
- Earnings or catalyst within DTE window
- No FOMO-style move yet (otherwise we'd be late)

THREE PILLARS (geometric mean):

1. STEALTH FLOW (50%) — smart money positioning quietly
   - Strike V/OI (heavy weight — the cleanest tell)
   - Adjacent-strikes V/OI (sweep across multiple strikes)
   - Side concentration (which way are they betting?)
   - Stock-volume-without-price (accumulation pattern)

2. COIL SPRING (30%) — energy stored, not yet released
   - Range compression: stock 5d move < 8%
   - IV term inversion (front >> back = event imminent)
   - Today's price move LOW (< 3%) — catalyst hasn't fired
   - Tight bid-ask spread (liquid market)

3. EXPLOSIVE PHYSICS (20%) — same convexity math as V2
   - Gamma per dollar
   - Delta in sweet zone
   - Move-to-3x feasibility

A pre-breakout candidate is DISQUALIFIED if:
- Stock up/down > 10% in 5 days (already moved)
- Stock up/down > 4% today (catalyst already firing)
- IV > 300% (event fully priced in)

Lower base hit-rate than continuation plays. Bigger payoff when right.
"""

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
import numpy as np

from lottery_scanner import UNIVERSE, ALL_TICKERS, fetch_quote_data
from convexity_hunter import (
    fetch_options_full, build_chain_context,
    score_leverage_quality, move_to_multiplier, lognormal_prob_above,
)


# ============================================================
# PILLAR A — STEALTH FLOW (50%)
# ============================================================

def score_stealth_flow(contract, chain_ctx, stock_data):
    """Smart money positioning without the stock having moved yet."""
    vol = contract["volume"]
    oi = contract["oi"]
    side = contract["side"]

    # Sub 1: V/OI ratio — heavy weight
    if oi > 0:
        voi = vol / oi
        if voi >= 10:
            s_voi = 10
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
        s_voi = 8 if vol > 200 else 4 if vol > 50 else 1

    # Sub 2: Adjacent-strikes sweep
    expiration = contract["expiration"]
    same_side = chain_ctx.get(f"{side}_{expiration}", [])
    strike = contract["strike"]
    adjacent_unusual = 0
    for c in same_side:
        if c["strike"] == strike:
            continue
        if abs(c["strike"] - strike) / strike <= 0.10:
            adj_voi = c["volume"] / max(c["oi"], 1)
            if adj_voi > 1:
                adjacent_unusual += 1
    if adjacent_unusual >= 4:
        s_sweep = 10
    elif adjacent_unusual >= 2:
        s_sweep = 7
    elif adjacent_unusual >= 1:
        s_sweep = 4
    else:
        s_sweep = 1

    # Sub 3: Side concentration
    total_call = chain_ctx.get("total_call_vol", 0)
    total_put = chain_ctx.get("total_put_vol", 0)
    total = total_call + total_put
    if total > 0:
        share = (total_call if side == "CALL" else total_put) / total
        if share >= 0.80:
            s_skew = 10
        elif share >= 0.65:
            s_skew = 8
        elif share >= 0.55:
            s_skew = 6
        elif share >= 0.45:
            s_skew = 4
        else:
            s_skew = 2
    else:
        s_skew = 3

    # Sub 4: ACCUMULATION — stock volume up but price flat
    # The signature pre-breakout pattern: someone is loading up shares
    # without driving the price (HFT/algos slowly absorbing liquidity)
    vol_ratio = stock_data.get("volume_vs_avg", 1.0)
    abs_today = abs(stock_data.get("pct_change_today", 0))
    abs_5d = abs(stock_data.get("pct_change_5d", 0))
    # Higher score: high volume + low price movement
    if vol_ratio >= 2.0 and abs_today < 2 and abs_5d < 5:
        s_accum = 10  # Classic stealth accumulation
    elif vol_ratio >= 1.5 and abs_today < 3 and abs_5d < 8:
        s_accum = 8
    elif vol_ratio >= 1.2 and abs_today < 4:
        s_accum = 5
    elif vol_ratio >= 1.0:
        s_accum = 3
    else:
        s_accum = 1

    score = (s_voi * 0.40 + s_sweep * 0.25 + s_skew * 0.15 + s_accum * 0.20)
    return {
        "score": round(score, 2),
        "subs": {
            "strike_voi": s_voi,
            "adjacent_sweep": s_sweep,
            "side_concentration": s_skew,
            "stealth_accumulation": s_accum,
        },
    }


# ============================================================
# PILLAR B — COIL SPRING (30%)
# ============================================================

def score_coil_spring(contract, chain_ctx, stock_data):
    """Energy stored = stock has been quiet, vol structure says event is coming."""

    pct_today = abs(stock_data.get("pct_change_today", 0))
    pct_5d = abs(stock_data.get("pct_change_5d", 0))

    # Sub 1: Range compression — quiet stock = energy stored
    # We WANT pct_5d to be LOW (3-8% sweet spot for "quietly setting up")
    if pct_5d <= 3:
        s_compression = 10  # Very tight coil
    elif pct_5d <= 5:
        s_compression = 9
    elif pct_5d <= 8:
        s_compression = 7
    elif pct_5d <= 12:
        s_compression = 4
    else:
        s_compression = 1  # Already moved — no coil left

    # Sub 2: Today's move — low = catalyst hasn't fired yet
    if pct_today <= 1:
        s_today = 10
    elif pct_today <= 2:
        s_today = 8
    elif pct_today <= 3:
        s_today = 6
    elif pct_today <= 4:
        s_today = 4
    else:
        s_today = 1  # Catalyst already firing — past the entry

    # Sub 3: IV term structure inversion — event priced in soon
    front_iv = chain_ctx.get("front_iv", 0)
    back_iv = chain_ctx.get("back_iv", 0)
    if front_iv > 0 and back_iv > 0:
        ratio = front_iv / back_iv
        if ratio >= 1.5:
            s_term = 10  # Strong inversion = imminent event
        elif ratio >= 1.25:
            s_term = 8
        elif ratio >= 1.10:
            s_term = 6
        elif ratio >= 1.0:
            s_term = 4
        else:
            s_term = 2  # Normal contango
    else:
        s_term = 4

    # Sub 4: Liquidity — tight spread = professional market makers active
    bid = contract["bid"]
    ask = contract["ask"]
    if bid > 0 and ask > 0:
        mid = (bid + ask) / 2
        spread_pct = (ask - bid) / max(mid, 0.01)
        if spread_pct <= 0.05:
            s_liq = 10
        elif spread_pct <= 0.10:
            s_liq = 8
        elif spread_pct <= 0.20:
            s_liq = 5
        else:
            s_liq = 2
    else:
        s_liq = 1

    score = (s_compression * 0.30 + s_today * 0.25
             + s_term * 0.30 + s_liq * 0.15)
    return {
        "score": round(score, 2),
        "subs": {
            "range_compression": s_compression,
            "no_move_today": s_today,
            "iv_term_structure": s_term,
            "liquidity": s_liq,
        },
    }


# ============================================================
# PILLAR C — EXPLOSIVE PHYSICS (20%)
# ============================================================
# Re-uses score_leverage_quality from convexity_hunter — same math


# ============================================================
# COMPOSITE
# ============================================================

def composite_pbs_score(stealth, coil, physics):
    """Pre-Breakout Score — weighted geometric mean."""
    A = stealth["score"]
    B = coil["score"]
    C = physics["score"]
    if A <= 0 or B <= 0 or C <= 0:
        return 0.0
    score = (A ** 0.50) * (B ** 0.30) * (C ** 0.20)
    return round(score, 2)


# ============================================================
# DISQUALIFIERS — pre-breakout MUST be quiet
# ============================================================

def passes_pre_breakout_filter(stock_data, contract):
    """Hard filters for pre-breakout candidates."""
    pct_5d = abs(stock_data.get("pct_change_5d", 0))
    pct_today = abs(stock_data.get("pct_change_today", 0))
    iv = contract.get("iv", 0)
    if iv > 5:
        iv_pct = iv  # already in % space
    else:
        iv_pct = iv * 100

    # Already moved too much in 5d
    if pct_5d > 10:
        return False
    # Catalyst already firing today
    if pct_today > 4:
        return False
    # IV too high = event fully priced
    if iv_pct > 300:
        return False
    return True


# ============================================================
# SCAN PIPELINE
# ============================================================

def scan_symbol_pre_breakout(client, symbol, max_dte=21, max_premium=2.50):
    """Pre-breakout scan for one symbol."""
    stock_data = fetch_quote_data(client, symbol)
    if not stock_data or stock_data["spot"] <= 0:
        return []

    # First-pass disqualifier at stock level
    pct_5d = abs(stock_data.get("pct_change_5d", 0))
    pct_today = abs(stock_data.get("pct_change_today", 0))
    if pct_5d > 10 or pct_today > 4:
        return []  # Already moved — skip entire ticker

    contracts = fetch_options_full(client, symbol, max_dte=max_dte)
    if not contracts:
        return []

    chain_ctx = build_chain_context(contracts)

    results = []
    for c in contracts:
        if c["mark"] <= 0 or c["mark"] > max_premium or c["mark"] < 0.10:
            continue
        if c["oi"] < 50 and c["volume"] < 100:
            continue
        if c["bid"] > 0 and c["ask"] > 0:
            spread_pct = (c["ask"] - c["bid"]) / max((c["bid"] + c["ask"]) / 2, 0.01)
            if spread_pct > 0.50:
                continue

        c["spot"] = stock_data["spot"]

        if not passes_pre_breakout_filter(stock_data, c):
            continue

        stealth = score_stealth_flow(c, chain_ctx, stock_data)
        coil = score_coil_spring(c, chain_ctx, stock_data)
        physics = score_leverage_quality(c)
        composite = composite_pbs_score(stealth, coil, physics)

        # Move-to-Nx feasibility
        ds_3x = move_to_multiplier(c["mark"], abs(c["delta"]), c["gamma"], 3)
        ds_5x = move_to_multiplier(c["mark"], abs(c["delta"]), c["gamma"], 5)
        ds_10x = move_to_multiplier(c["mark"], abs(c["delta"]), c["gamma"], 10)
        spot = stock_data["spot"]
        pct_3x = (ds_3x / spot * 100) if ds_3x else None
        pct_5x = (ds_5x / spot * 100) if ds_5x else None
        pct_10x = (ds_10x / spot * 100) if ds_10x else None
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
            "stealth": stealth,
            "coil": coil,
            "physics": physics,
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


def scan_universe_pre_breakout(client, tickers=None, max_dte=21, min_score=4.0,
                               max_premium=2.50, max_workers=5, progress_cb=None):
    """Pre-breakout scan across universe."""
    if tickers is None:
        tickers = ALL_TICKERS

    all_results = []
    completed = 0
    total = len(tickers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(scan_symbol_pre_breakout, client, t, max_dte, max_premium): t
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
