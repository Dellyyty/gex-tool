"""Free data source using Yahoo Finance for SPX options data.

Provides OI from Yahoo Finance and calculates Greeks via Black-Scholes.
Works immediately — no API key needed.
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from scipy.stats import norm
from config import MAX_DTE


def fetch_options_chain_free():
    """Fetch SPX options chain from Yahoo Finance and calculate Greeks.

    Returns:
        tuple: (options_df, spot_price)
    """
    # Yahoo Finance uses ^SPX for S&P 500 index, but options are on ^SPX
    # SPX options are actually listed under ^SPX
    ticker = yf.Ticker("^SPX")

    # Get current price
    info = ticker.fast_info
    spot_price = info.get("lastPrice", 0) or info.get("previousClose", 0)
    if spot_price == 0:
        hist = ticker.history(period="1d")
        if not hist.empty:
            spot_price = hist["Close"].iloc[-1]

    if spot_price == 0:
        raise RuntimeError("Could not fetch SPX price")

    # Get available expiration dates
    expirations = ticker.options  # list of date strings "YYYY-MM-DD"

    # Filter to expirations within MAX_DTE
    today = datetime.now().date()
    max_date = today + timedelta(days=MAX_DTE)

    valid_exps = []
    for exp_str in expirations:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
        if today <= exp_date <= max_date:
            valid_exps.append(exp_str)

    if not valid_exps:
        return pd.DataFrame(), spot_price

    all_rows = []

    for exp_str in valid_exps:
        try:
            chain = ticker.option_chain(exp_str)
        except Exception:
            continue

        calls = chain.calls
        puts = chain.puts
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
        dte = (exp_date - today).days

        # Get all strikes present in either calls or puts
        all_strikes = sorted(set(calls["strike"].tolist() + puts["strike"].tolist()))

        for strike in all_strikes:
            call_row = calls[calls["strike"] == strike]
            put_row = puts[puts["strike"] == strike]

            call_oi = int(call_row["openInterest"].iloc[0]) if not call_row.empty and pd.notna(call_row["openInterest"].iloc[0]) else 0
            put_oi = int(put_row["openInterest"].iloc[0]) if not put_row.empty and pd.notna(put_row["openInterest"].iloc[0]) else 0
            call_iv = float(call_row["impliedVolatility"].iloc[0]) if not call_row.empty and pd.notna(call_row["impliedVolatility"].iloc[0]) else 0
            put_iv = float(put_row["impliedVolatility"].iloc[0]) if not put_row.empty and pd.notna(put_row["impliedVolatility"].iloc[0]) else 0
            call_vol = int(call_row["volume"].iloc[0]) if not call_row.empty and pd.notna(call_row["volume"].iloc[0]) else 0
            put_vol = int(put_row["volume"].iloc[0]) if not put_row.empty and pd.notna(put_row["volume"].iloc[0]) else 0

            # Calculate gamma from Black-Scholes
            T = max(dte / 365.0, 1 / 365.0)  # time in years, min 1 day
            call_gamma = _bs_gamma(spot_price, strike, T, call_iv) if call_iv > 0 else 0
            put_gamma = _bs_gamma(spot_price, strike, T, put_iv) if put_iv > 0 else 0

            # Calculate delta too
            call_delta = _bs_delta(spot_price, strike, T, call_iv, "call") if call_iv > 0 else 0
            put_delta = _bs_delta(spot_price, strike, T, put_iv, "put") if put_iv > 0 else 0

            all_rows.append({
                "strike": strike,
                "expiration": exp_str,
                "dte": dte,
                "call_OI": call_oi,
                "put_OI": put_oi,
                "call_gamma": call_gamma,
                "put_gamma": put_gamma,
                "call_delta": call_delta,
                "put_delta": put_delta,
                "call_volume": call_vol,
                "put_volume": put_vol,
            })

    if not all_rows:
        return pd.DataFrame(), spot_price

    options_df = pd.DataFrame(all_rows)
    options_df = options_df.sort_values(["strike", "expiration"], ascending=[False, True])
    options_df = options_df.reset_index(drop=True)

    return options_df, spot_price


def _bs_gamma(S, K, T, sigma, r=0.05):
    """Calculate Black-Scholes gamma (same for calls and puts).

    Args:
        S: spot price
        K: strike price
        T: time to expiry in years
        sigma: implied volatility
        r: risk-free rate (default 5%)
    """
    if sigma <= 0 or T <= 0 or S <= 0:
        return 0.0
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
        return gamma
    except (ZeroDivisionError, ValueError):
        return 0.0


def _bs_delta(S, K, T, sigma, option_type, r=0.05):
    """Calculate Black-Scholes delta.

    Args:
        S: spot price
        K: strike price
        T: time to expiry in years
        sigma: implied volatility
        option_type: "call" or "put"
        r: risk-free rate
    """
    if sigma <= 0 or T <= 0 or S <= 0:
        return 0.0
    try:
        d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
        if option_type == "call":
            return norm.cdf(d1)
        else:
            return norm.cdf(d1) - 1
    except (ZeroDivisionError, ValueError):
        return 0.0
