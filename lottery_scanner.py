"""Lottery Scanner — finds explosive option contracts across a wide ticker universe.

Hunts for $50-$150 contracts (0-14 DTE) on stocks showing the unusual-options-flow
pattern that often precedes SNDK-style 10x-50x runs. Scans both calls and puts.

Composite score (1-10) is anchored on historical lottery-ticket setups. NOT a
probability — high score means "this matches the pattern" not "this will pay off."
Most lottery tickets expire worthless. Position size accordingly.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


# ============================================================
# Universe — curated ~120 high-momentum tickers across sectors.
# These are stocks that historically produce the SNDK-style runs:
# biotech catalysts, semis/AI cycles, M&A rumors, meme squeezes.
# ============================================================

UNIVERSE = {
    "Semis_AI_Hardware": [
        "NVDA", "AMD", "AVGO", "SMCI", "ARM", "MU", "MRVL", "TSM", "INTC",
        "ASML", "AMAT", "LRCX", "KLAC", "ON", "QCOM", "TXN", "MCHP", "ADI",
        "WDC", "STX", "CRDO", "ALAB", "ASTS",
    ],
    "AI_Software": [
        "PLTR", "SNOW", "MDB", "DDOG", "NET", "CRWD", "PATH", "AI", "BBAI",
        "SOUN", "TEM", "DOCN", "PANW", "ZS", "S", "OKTA",
    ],
    "Crypto_Adjacent": [
        "COIN", "MSTR", "MARA", "RIOT", "CLSK", "HOOD", "BITF", "HUT",
        "WULF", "CIFR", "CORZ", "IREN",
    ],
    "Biotech_Pharma": [
        "MRNA", "BNTX", "NVAX", "BIIB", "REGN", "VRTX", "GILD", "AMGN",
        "CRSP", "EDIT", "NTLA", "BEAM", "SAVA", "OCGN", "SRPT", "PFE",
        "LLY", "NVO", "ALNY", "MRK", "JNJ", "ABBV",
    ],
    "EV_Auto": [
        "TSLA", "RIVN", "LCID", "NIO", "XPEV", "LI", "F", "GM", "FSR",
        "QS", "CHPT", "BLNK",
    ],
    "Memes_Squeeze": [
        "GME", "AMC", "BB", "KOSS", "BBBY", "ATER", "DJT", "RDDT",
    ],
    "Recent_M&A_Targets": [
        "U", "RBLX", "PINS", "SNAP", "ROKU", "SHOP", "LYFT", "UBER",
        "AFRM", "SOFI", "UPST", "RKT", "SQ", "PYPL",
    ],
    "Mega_Cap_High_Beta": [
        "TSLA", "NVDA", "META", "NFLX", "AAPL", "GOOGL", "AMZN", "MSFT",
        "DIS", "BABA", "JD", "PDD",
    ],
    "Speculative_Lottery": [
        "SPCE", "NKLA", "PLUG", "FCEL", "BLDP", "WKHS", "GOEV", "MULN",
        "SIRI", "SNDL",
    ],
    "Industrial_Hot": [
        "BA", "CAT", "UBER", "DAL", "AAL", "UAL", "CCL", "NCLH",
    ],
    "Energy_Volatile": [
        "OXY", "DVN", "MRO", "FANG", "PXD", "MPC", "SLB", "HAL",
    ],
    "Recent_IPO_Volatile": [
        "ARM", "CART", "BIRK", "INSTA", "RDDT", "ASTR", "JOBY", "EVTL",
    ],
}

# Flattened deduplicated list
ALL_TICKERS = sorted(set(t for sector in UNIVERSE.values() for t in sector))


# ============================================================
# Scoring weights — tuned for lottery-ticket pattern matching
# ============================================================
WEIGHTS = {
    "voi": 0.20,           # Volume / Open Interest — unusual options flow
    "iv_extreme": 0.15,    # IV percentile — market expects move
    "stock_momentum": 0.15, # Multi-day breakout vs range
    "stock_volume": 0.15,  # Today's volume vs avg — unusual stock activity
    "otm_sweet": 0.10,     # 3-15% OTM = explosive zone
    "premium_fit": 0.10,   # Within $50-$150 budget zone
    "side_skew": 0.10,     # Heavy directional positioning
    "liquidity": 0.05,     # Tight bid-ask + minimum OI
}


def _score_premium(mark):
    """Score how well the contract fits the $50-$150 sweet spot."""
    cost = mark * 100
    if 50 <= cost <= 150:
        return 10  # Sweet spot
    elif 30 <= cost < 50:
        return 7   # Slightly cheap (might be too far OTM)
    elif 150 < cost <= 250:
        return 6   # Slightly expensive but still affordable
    elif 20 <= cost < 30:
        return 4   # Very cheap (low probability)
    elif 250 < cost <= 400:
        return 3   # Above range
    else:
        return 0   # Outside window


def _score_voi(volume, oi):
    """Volume/OI ratio — the cleanest unusual-activity tell."""
    if oi <= 0:
        return 8 if volume > 100 else 3  # New strike with volume = interesting
    ratio = volume / max(oi, 1)
    if ratio >= 5:
        return 10
    elif ratio >= 2:
        return 8
    elif ratio >= 1:
        return 6
    elif ratio >= 0.5:
        return 4
    elif ratio >= 0.2:
        return 2
    return 1


def _score_iv(iv):
    """High IV = market is pricing in a big move. Multiply by 100 if it's a fraction."""
    if iv < 1:
        iv = iv * 100  # Convert from decimal to percent
    if iv >= 200:
        return 10
    elif iv >= 120:
        return 8
    elif iv >= 80:
        return 6
    elif iv >= 50:
        return 4
    elif iv >= 30:
        return 2
    return 1


def _score_stock_momentum(stock_data):
    """Stock breaking out (or down) of recent range = setup for continuation."""
    pct_5d = abs(stock_data.get("pct_change_5d", 0))
    pct_today = abs(stock_data.get("pct_change_today", 0))

    score = 0
    if pct_5d >= 15:
        score += 6
    elif pct_5d >= 8:
        score += 4
    elif pct_5d >= 4:
        score += 2

    if pct_today >= 5:
        score += 4
    elif pct_today >= 3:
        score += 3
    elif pct_today >= 1.5:
        score += 2
    return min(score, 10)


def _score_stock_volume(stock_data):
    """Unusual stock volume vs average — confirms the move has fuel."""
    ratio = stock_data.get("volume_vs_avg", 1.0)
    if ratio >= 3:
        return 10
    elif ratio >= 2:
        return 8
    elif ratio >= 1.5:
        return 6
    elif ratio >= 1.1:
        return 4
    return 2


def _score_otm(strike, spot, side):
    """Sweet spot for explosive moves: 3-15% OTM."""
    if spot <= 0:
        return 0
    if side == "CALL":
        otm_pct = (strike - spot) / spot * 100
    else:
        otm_pct = (spot - strike) / spot * 100

    if 3 <= otm_pct <= 12:
        return 10  # Sweet spot
    elif 12 < otm_pct <= 20:
        return 7   # Further OTM, bigger payoff but lower prob
    elif 0 <= otm_pct < 3:
        return 6   # Near ATM
    elif -3 < otm_pct < 0:
        return 5   # Slightly ITM
    elif 20 < otm_pct <= 30:
        return 4   # Very far OTM
    else:
        return 1


def _score_side_skew(call_vol, put_vol, side):
    """Heavy positioning in chosen direction = conviction."""
    total = call_vol + put_vol
    if total == 0:
        return 3
    if side == "CALL":
        skew = call_vol / total
    else:
        skew = put_vol / total

    if skew >= 0.80:
        return 10
    elif skew >= 0.65:
        return 8
    elif skew >= 0.55:
        return 6
    elif skew >= 0.45:
        return 4
    return 2


def _score_liquidity(bid, ask, oi, volume):
    """Tight spread + minimum OI = you can actually exit."""
    if oi < 50 and volume < 100:
        return 0  # Disqualify — can't exit
    if bid <= 0 or ask <= 0:
        return 1
    mid = (bid + ask) / 2
    spread_pct = (ask - bid) / max(mid, 0.01)
    if spread_pct <= 0.05:
        return 10
    elif spread_pct <= 0.10:
        return 8
    elif spread_pct <= 0.20:
        return 5
    elif spread_pct <= 0.35:
        return 3
    return 1


def score_contract(contract, side, stock_data):
    """Score a single contract 0-10 with factor breakdown.

    contract: dict with keys: strike, mark, bid, ask, volume, oi, iv, dte, expiration
    side: 'CALL' or 'PUT'
    stock_data: dict with keys: spot, pct_change_today, pct_change_5d,
                volume_vs_avg, call_vol_today, put_vol_today
    """
    spot = stock_data.get("spot", 0)
    if spot <= 0:
        return None

    factors = {
        "premium_fit": _score_premium(contract["mark"]),
        "voi": _score_voi(contract["volume"], contract["oi"]),
        "iv_extreme": _score_iv(contract["iv"]),
        "stock_momentum": _score_stock_momentum(stock_data),
        "stock_volume": _score_stock_volume(stock_data),
        "otm_sweet": _score_otm(contract["strike"], spot, side),
        "side_skew": _score_side_skew(
            stock_data.get("call_vol_today", 0),
            stock_data.get("put_vol_today", 0),
            side,
        ),
        "liquidity": _score_liquidity(
            contract["bid"], contract["ask"],
            contract["oi"], contract["volume"],
        ),
    }

    # Hard disqualifiers
    if factors["premium_fit"] == 0 or factors["liquidity"] == 0:
        return None

    composite = sum(factors[k] * WEIGHTS[k] for k in factors)
    return {"score": round(composite, 2), "factors": factors}


# ============================================================
# Schwab data fetchers for arbitrary symbols
# ============================================================

def fetch_quote_data(client, symbol):
    """Fetch quote + price history for a single symbol. Returns stock_data dict."""
    try:
        # Current quote
        q = client.quote(symbol)
        if not q.ok:
            return None
        qd = q.json().get(symbol, {})
        quote = qd.get("quote", qd)
        regular = qd.get("regular", {})

        spot = quote.get("lastPrice", quote.get("mark", 0))
        prev_close = quote.get("closePrice", quote.get("regularMarketLastPrice", spot))
        today_vol = quote.get("totalVolume", quote.get("volume", 0))
        avg_vol = quote.get("averageVolume", quote.get("avg10DaysVolume", today_vol))

        pct_today = ((spot - prev_close) / max(prev_close, 0.01)) * 100 if prev_close else 0

        # 5-day price change via price_history (Schwab endpoint)
        try:
            ph = client.price_history(
                symbol=symbol,
                periodType="day",
                period=10,
                frequencyType="daily",
                frequency=1,
            )
            if ph.ok:
                candles = ph.json().get("candles", [])
                if len(candles) >= 5:
                    five_days_ago = candles[-6]["close"] if len(candles) >= 6 else candles[0]["close"]
                    pct_5d = ((spot - five_days_ago) / max(five_days_ago, 0.01)) * 100
                else:
                    pct_5d = pct_today
            else:
                pct_5d = pct_today
        except Exception:
            pct_5d = pct_today

        return {
            "symbol": symbol,
            "spot": spot,
            "pct_change_today": pct_today,
            "pct_change_5d": pct_5d,
            "volume": today_vol,
            "avg_volume": avg_vol,
            "volume_vs_avg": today_vol / max(avg_vol, 1) if avg_vol else 1.0,
        }
    except Exception:
        return None


def fetch_options_short_dated(client, symbol, max_dte=14):
    """Fetch options chain for a symbol, limited to short-dated expiries."""
    try:
        today = datetime.now()
        to_date = today + timedelta(days=max_dte)
        resp = client.option_chains(
            symbol=symbol,
            contractType="ALL",
            includeUnderlyingQuote=False,
            fromDate=today.strftime("%Y-%m-%d"),
            toDate=to_date.strftime("%Y-%m-%d"),
            strikeCount=40,
        )
        if not resp.ok:
            return None, None
        data = resp.json()

        call_total_vol = 0
        put_total_vol = 0
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
                        vol = c.get("totalVolume", 0)
                        if side == "CALL":
                            call_total_vol += vol
                        else:
                            put_total_vol += vol
                        contracts.append({
                            "side": side,
                            "strike": float(c.get("strikePrice", strike_key)),
                            "expiration": exp_date,
                            "dte": c.get("daysToExpiration", dte),
                            "mark": float(c.get("mark", 0)),
                            "bid": float(c.get("bid", 0)),
                            "ask": float(c.get("ask", 0)),
                            "volume": int(vol),
                            "oi": int(c.get("openInterest", 0)),
                            "iv": float(c.get("volatility", 0)),
                            "delta": float(c.get("delta", 0)),
                        })

        return contracts, {"call_vol": call_total_vol, "put_vol": put_total_vol}
    except Exception:
        return None, None


def scan_one_symbol(client, symbol, max_dte=14, max_premium=2.50):
    """Full scan pipeline for a single symbol. Returns list of scored contracts."""
    stock_data = fetch_quote_data(client, symbol)
    if not stock_data or stock_data["spot"] <= 0:
        return []

    contracts, vol_summary = fetch_options_short_dated(client, symbol, max_dte=max_dte)
    if not contracts:
        return []

    stock_data["call_vol_today"] = vol_summary["call_vol"]
    stock_data["put_vol_today"] = vol_summary["put_vol"]

    results = []
    for c in contracts:
        if c["mark"] <= 0 or c["mark"] > max_premium:
            continue
        scored = score_contract(c, c["side"], stock_data)
        if scored is None:
            continue

        # Calc upside scenarios — what if stock moves 5%, 10%, 20% in chosen dir
        spot = stock_data["spot"]
        delta = abs(c["delta"]) if c["delta"] else 0.3
        # Rough non-linear estimate: gamma kicks in as we go ITM
        target_5pct = c["mark"] * (1 + delta * 5 * 1.5)  # 5% move with gamma boost
        target_10pct = c["mark"] * (1 + delta * 10 * 2.5)  # 10% move bigger boost
        target_20pct = c["mark"] * (1 + delta * 20 * 4.0)  # 20% move parabolic

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
            "spot": stock_data["spot"],
            "pct_today": stock_data["pct_change_today"],
            "pct_5d": stock_data["pct_change_5d"],
            "vol_vs_avg": stock_data["volume_vs_avg"],
            "score": scored["score"],
            "factors": scored["factors"],
            "target_5pct": target_5pct * 100,    # dollar value per contract
            "target_10pct": target_10pct * 100,
            "target_20pct": target_20pct * 100,
        })

    return results


def scan_universe(client, tickers=None, max_dte=14, min_score=6.0,
                  max_premium=2.50, max_workers=5, progress_cb=None):
    """Scan a list of tickers in parallel. Returns ranked list of contracts."""
    if tickers is None:
        tickers = ALL_TICKERS

    all_results = []
    completed = 0
    total = len(tickers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(scan_one_symbol, client, t, max_dte, max_premium): t
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

    # Filter and rank
    qualified = [r for r in all_results if r["score"] >= min_score]
    qualified.sort(key=lambda x: x["score"], reverse=True)
    return qualified
