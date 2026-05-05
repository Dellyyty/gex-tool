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
    # === Mega caps and high-beta majors ===
    "Mega_Cap_High_Beta": [
        "TSLA", "NVDA", "META", "NFLX", "AAPL", "GOOGL", "AMZN", "MSFT",
        "DIS", "AVGO", "ORCL", "CRM", "ADBE", "AMD", "QCOM",
    ],

    # === Semiconductors — full ladder ===
    "Semis_Mega": [
        "NVDA", "AMD", "AVGO", "TSM", "ASML", "MU", "QCOM", "TXN", "INTC",
    ],
    "Semis_Mid": [
        "SMCI", "ARM", "MRVL", "AMAT", "LRCX", "KLAC", "ON", "MCHP", "ADI",
        "MPWR", "NXPI", "STM", "ENTG", "COHR",
    ],
    "Semis_Small_Niche": [
        "WDC", "STX", "CRDO", "ALAB", "AEHR", "INDI", "POWI", "SITM",
        "SLAB", "SWKS", "QRVO", "WOLF", "ACMR", "AMBA", "VECO", "ICHR",
        "PI", "RMBS", "FORM", "ONTO", "CRUS", "DIOD", "KOPN",
    ],

    # === AI / data infra software ===
    "AI_Software_Mega": [
        "PLTR", "SNOW", "CRM", "ORCL",
    ],
    "AI_Software_Mid": [
        "MDB", "DDOG", "NET", "CRWD", "PANW", "ZS", "S", "OKTA", "FTNT",
        "GTLB", "ESTC", "CFLT", "MNDY", "TEAM", "WDAY",
    ],
    "AI_Pureplays_Small": [
        "AI", "BBAI", "SOUN", "TEM", "PATH", "PRCH", "VRSN", "DOCN",
        "INOD", "LMND", "NVTS", "GLBE", "RXRX", "CRNC",
    ],

    # === Crypto / mining / blockchain adjacent ===
    "Crypto_Adjacent": [
        "COIN", "MSTR", "MARA", "RIOT", "CLSK", "HOOD", "BITF", "HUT",
        "WULF", "CIFR", "CORZ", "IREN", "BTBT", "GREE", "CAN", "BTDR",
        "DGHI", "SOS", "NCTY", "BTCS", "EBON", "BFRG",
    ],

    # === Biotech — small/mid catalyst-driven (where SNDK-style moves live) ===
    "Biotech_Mega": [
        "LLY", "NVO", "JNJ", "MRK", "PFE", "ABBV", "AMGN", "GILD", "REGN",
        "VRTX", "BIIB",
    ],
    "Biotech_Mid_Hot": [
        "MRNA", "BNTX", "NVAX", "ALNY", "EXEL", "INCY", "BMRN", "NBIX",
        "UTHR", "RPRX", "NEUR", "SAREPTA", "SRPT", "GH", "VEEV",
    ],
    "Biotech_Small_Catalyst": [
        "CRSP", "EDIT", "NTLA", "BEAM", "VERV", "PRME", "SAVA", "OCGN",
        "INSM", "ARWR", "RVMD", "RYTM", "VKTX", "MDGL", "KRYS", "IONS",
        "PCVX", "ACAD", "DNLI", "MORF", "PTCT", "FOLD", "AXSM", "ARCT",
        "BHVN", "DAWN", "TARS", "CRBU", "RNA", "AURA", "TVTX", "GERN",
        "CVAC", "INVA", "HRMY", "VANI", "OPK", "INMD", "BCRX", "ANIP",
    ],
    "Biotech_Lottery": [
        "SAVA", "AVTX", "NVAX", "OCGN", "ENVB", "CYTK", "PHIO", "ATAI",
        "MNMD", "CMPS", "GHRS", "ATXS", "ABOS", "ADAG", "CABA", "TENX",
        "EVAX", "VBLT", "INSE", "KZIA", "OST", "KMPB",
    ],

    # === EV / clean transport ===
    "EV_Auto_Major": [
        "TSLA", "F", "GM", "STLA", "TM", "RACE", "HMC",
    ],
    "EV_Pureplays": [
        "RIVN", "LCID", "NIO", "XPEV", "LI", "ZK", "FSR", "WKHS", "MULN",
        "GOEV", "NKLA", "FFIE", "BLNK", "EVGO", "CHPT", "ADSE",
    ],
    "EV_Battery_Lithium": [
        "ALB", "SQM", "LTHM", "PLL", "LAC", "MP", "REE", "QS", "ENVX",
        "FREY", "MVST", "LICY", "AMPX", "DRMA",
    ],

    # === Recent IPOs / spinoffs / SPAC-graduates (the SNDK pattern!) ===
    "Recent_IPO_Spinoffs": [
        "SNDK", "ARM", "CART", "BIRK", "RDDT", "GEHC", "KVUE", "SOLV",
        "GTLB", "S", "TOST", "ABNB", "DASH", "RBLX", "RIVN", "AAOI",
        "ASTS", "JOBY", "ACHR", "EVTL", "ESLT", "RUM", "BBAI", "STAA",
    ],

    # === Memes / squeeze / retail ===
    "Memes_Squeeze": [
        "GME", "AMC", "BB", "KOSS", "BBBY", "ATER", "DJT", "RDDT", "HKD",
        "NEGG", "MMTLP", "AMTD", "WAVE", "MMAT", "BTU", "CRTD", "PRSO",
    ],

    # === M&A targets / takeover candidates ===
    "Recent_MA_Targets": [
        "U", "RBLX", "PINS", "SNAP", "ROKU", "ETSY", "EBAY", "PYPL",
        "CMA", "FRC", "PACW", "WAL", "DKNG", "RKT", "OPEN", "Z", "ZG",
        "COMP", "RDFN", "ACI", "KR", "CASY", "DG", "DLTR", "HOOD",
    ],

    # === Fintech / payments ===
    "Fintech": [
        "SQ", "PYPL", "SOFI", "AFRM", "UPST", "RKT", "OPEN", "LMND", "NU",
        "INTR", "STNE", "PAGS", "MELI", "GLOB", "HOOD", "COIN", "NRDS",
        "DAVE", "ROOT", "HIPO", "MBC", "FOUR", "FLYW",
    ],

    # === Software / SaaS — beyond AI labels ===
    "Software_SaaS": [
        "SHOP", "SQ", "ADBE", "INTU", "WDAY", "CRM", "NOW", "ADSK",
        "ANSS", "PTC", "CDNS", "SNPS", "U", "TWLO", "FSLY", "DOCN",
        "ESTC", "CFLT", "GTLB", "MNDY", "TEAM", "ASAN", "BOX", "DOCN",
        "OLO", "BL", "BLKB", "FROG", "JAMF", "RNG", "ZM",
    ],

    # === Cybersecurity ===
    "Cybersecurity": [
        "PANW", "CRWD", "ZS", "S", "NET", "OKTA", "FTNT", "FFIV", "CYBR",
        "QLYS", "VRNS", "TENB", "RPD", "CHKP", "OSPN", "SAIL",
    ],

    # === Cloud / data infra ===
    "Cloud_Data_Infra": [
        "DDOG", "MDB", "SNOW", "NET", "ESTC", "CFLT", "DOCN", "DBX", "BOX",
        "PSTG", "NTNX", "AKAM", "EQIX", "DLR", "VRT",
    ],

    # === Quantum / advanced compute ===
    "Quantum_Compute": [
        "IONQ", "RGTI", "QBTS", "QUBT", "NNDM", "ARQQ", "QMCO",
    ],

    # === Nuclear / uranium / SMR ===
    "Nuclear_Uranium": [
        "CCJ", "UEC", "UUUU", "NXE", "LEU", "OKLO", "SMR", "NNE", "VST",
        "TLN", "CEG", "BWXT", "URA", "URNM", "USA",
    ],

    # === Solar / clean energy ===
    "Solar_Clean": [
        "ENPH", "SEDG", "FSLR", "RUN", "ARRY", "NOVA", "MAXN", "CSIQ",
        "JKS", "DQ", "SPWR", "SHLS", "STEM", "PLUG", "FCEL", "BE", "BLDP",
        "BEEM", "AMPS",
    ],

    # === Space / aerospace / defense ===
    "Space_Aerospace": [
        "RKLB", "ASTS", "LUNR", "ASTR", "JOBY", "EVTL", "ACHR", "RDW",
        "PL", "MNTS", "BA", "LMT", "RTX", "NOC", "GD", "HII", "TXT",
        "TDG", "HEI", "AVAV", "KTOS", "BWXT",
    ],

    # === Cannabis ===
    "Cannabis": [
        "TLRY", "CGC", "CRON", "ACB", "SNDL", "MSOS", "GRWG", "VFF",
        "OGI", "CURLF", "GTBIF", "VRNOF", "TCNNF", "AYRWF", "AAWH",
    ],

    # === China ADRs (volatile, options-active) ===
    "China_ADRs": [
        "BABA", "JD", "PDD", "BIDU", "NIO", "XPEV", "LI", "TME", "BILI",
        "TAL", "EDU", "DIDI", "BEKE", "VIPS", "YMM", "TIGR", "FUTU",
        "ATAT", "ZH", "MOMO", "WB", "DOYU", "HUYA",
    ],

    # === Travel / leisure / hospitality ===
    "Travel_Leisure": [
        "ABNB", "BKNG", "EXPE", "TRIP", "MAR", "HLT", "H", "WH", "IHG",
        "CCL", "NCLH", "RCL", "VIK", "DAL", "AAL", "UAL", "LUV", "ALK",
        "JBLU", "SAVE", "ULCC", "MESA",
    ],

    # === Restaurants / consumer hot ===
    "Restaurants_Consumer": [
        "MCD", "SBUX", "CMG", "DASH", "UBER", "SHAK", "WING", "CAVA",
        "TXRH", "CAKE", "EAT", "DPZ", "PZZA", "QSR", "WEN", "JACK",
        "DRI", "LOCO", "BJ", "BROS", "PLAY", "FWRG", "DNUT",
    ],

    # === Gaming / sports betting ===
    "Gaming_Betting": [
        "DKNG", "PENN", "BYD", "MGM", "WYNN", "LVS", "CZR", "FLUT",
        "RSI", "GENI", "SRAD", "SEAT", "MNKD", "MNRD", "EDR", "MSGS",
    ],

    # === Real estate / mortgage ===
    "Real_Estate_Hot": [
        "RKT", "OPEN", "Z", "ZG", "COMP", "RDFN", "EXPI", "PSA", "EXR",
        "AMT", "SBAC", "CCI", "DLR", "EQIX", "INVH", "AMH", "EQR", "AVB",
    ],

    # === Energy / oil / gas (volatile) ===
    "Energy_Volatile": [
        "OXY", "DVN", "MRO", "FANG", "PXD", "MPC", "SLB", "HAL", "BKR",
        "OII", "WTI", "RIG", "BORR", "TUSK", "TDW", "CRC", "PR", "MGY",
        "CEIX", "BTU", "ARCH", "AMR", "HCC", "FCEL",
    ],

    # === Industrials / cyclicals ===
    "Industrial_Cyclical": [
        "BA", "CAT", "DE", "HON", "GE", "MMM", "ETN", "EMR", "ITW",
        "PH", "ROK", "CMI", "PCAR", "LUV", "XPO", "CHRW", "JBHT", "ARCB",
        "HUBG", "WERN", "LSTR", "GBX", "TRN",
    ],

    # === Speculative lottery / former hype ===
    "Speculative_Lottery": [
        "SPCE", "NKLA", "PLUG", "FCEL", "BLDP", "WKHS", "GOEV", "MULN",
        "SIRI", "SNDL", "FFIE", "GREE", "AMPX", "DOMA", "REKR", "UAVS",
        "NXTC", "GMVD", "BBLG", "AGRI", "CRTD", "HCWB",
    ],

    # === 3D printing / advanced manufacturing ===
    "3D_Printing_AdvMfg": [
        "DDD", "SSYS", "DM", "VLD", "MKFG", "NNDM", "VJET", "XMTR", "ARCT",
        "SPNS", "AOSL", "VLO", "CDXC",
    ],

    # === ETFs that move (leveraged + thematic) ===
    "ETF_Leveraged_Thematic": [
        "TQQQ", "SQQQ", "SOXL", "SOXS", "TNA", "TZA", "FAS", "FAZ",
        "LABU", "LABD", "TMF", "TMV", "BOIL", "KOLD", "JNUG", "JDST",
        "GUSH", "DRIP", "SPXL", "SPXS", "URTY", "SRTY", "WEBL", "WEBS",
        "ARKK", "ARKG", "ARKF", "ARKW", "BITX", "BITI",
    ],
}

# Flattened deduplicated list
ALL_TICKERS = sorted(set(t for sector in UNIVERSE.values() for t in sector))


# Curated sector presets for quick-select
SECTOR_PRESETS = {
    "All sectors": list(UNIVERSE.keys()),
    "Niche / small-cap only (skip mega caps)": [
        s for s in UNIVERSE.keys()
        if s not in ("Mega_Cap_High_Beta", "Semis_Mega", "AI_Software_Mega",
                     "Biotech_Mega", "EV_Auto_Major")
    ],
    "Lottery focus (biotech + crypto + memes + IPOs)": [
        "Biotech_Small_Catalyst", "Biotech_Lottery", "Crypto_Adjacent",
        "Memes_Squeeze", "Recent_IPO_Spinoffs", "Speculative_Lottery",
        "Quantum_Compute", "Cannabis",
    ],
    "Hot momentum (semis + AI + nuclear + space)": [
        "Semis_Small_Niche", "Semis_Mid", "AI_Pureplays_Small",
        "Nuclear_Uranium", "Space_Aerospace", "Quantum_Compute",
    ],
    "Catalyst-driven (biotech + earnings + China)": [
        "Biotech_Small_Catalyst", "Biotech_Mid_Hot", "Biotech_Lottery",
        "China_ADRs", "Recent_IPO_Spinoffs",
    ],
}


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
