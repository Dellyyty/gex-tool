import pandas as pd
from datetime import datetime, timedelta
from config import SYMBOL, MAX_DTE, STRIKE_INCREMENT, DEFAULT_STRIKES_ABOVE_ATM, DEFAULT_STRIKES_BELOW_ATM


def _get_spot_price_for_strikes(client):
    """Get spot price to calculate strike range."""
    response = client.quote(SYMBOL)
    if response.ok:
        data = response.json()
        symbol_data = data.get(SYMBOL, {})
        quote = symbol_data.get("quote", symbol_data)
        return quote.get("lastPrice", quote.get("last", quote.get("mark", 0)))
    return 0


def fetch_options_chain(client):
    """Fetch SPX options chain with Greeks and OI from Schwab API.

    Returns:
        tuple: (options_df, spot_price)
            - options_df: DataFrame with columns:
                strike, expiration, call_OI, put_OI, call_gamma, put_gamma,
                call_delta, put_delta, call_volume, put_volume, dte
            - spot_price: current underlying price
    """
    today = datetime.now()
    to_date = today + timedelta(days=MAX_DTE)

    # Get spot price first to limit strike range
    spot = _get_spot_price_for_strikes(client)
    strike_range = max(DEFAULT_STRIKES_ABOVE_ATM, DEFAULT_STRIKES_BELOW_ATM) * STRIKE_INCREMENT
    strike_from = spot - strike_range - 50 if spot > 0 else None
    strike_to = spot + strike_range + 50 if spot > 0 else None

    response = client.option_chains(
        symbol=SYMBOL,
        contractType="ALL",
        includeUnderlyingQuote=True,
        fromDate=today.strftime("%Y-%m-%d"),
        toDate=to_date.strftime("%Y-%m-%d"),
        strikeCount=45,
    )

    if not response.ok:
        raise RuntimeError(
            f"Schwab API error {response.status_code}: {response.text}"
        )

    data = response.json()

    # Extract spot price from underlying quote
    spot_price = data.get("underlyingPrice", 0)
    if spot_price == 0:
        underlying = data.get("underlying", {})
        spot_price = underlying.get("last", underlying.get("mark", underlying.get("close", 0)))

    # Parse call and put maps into a unified DataFrame
    calls = _parse_exp_date_map(data.get("callExpDateMap", {}), "CALL")
    puts = _parse_exp_date_map(data.get("putExpDateMap", {}), "PUT")

    # Merge calls and puts on (strike, expiration)
    if calls.empty and puts.empty:
        return pd.DataFrame(), spot_price

    if calls.empty:
        options_df = puts.rename(columns={
            "openInterest": "put_OI", "gamma": "put_gamma",
            "delta": "put_delta", "volume": "put_volume",
            "mark": "put_mark", "bid": "put_bid", "ask": "put_ask",
            "theta": "put_theta", "vega": "put_vega",
            "impliedVolatility": "put_iv",
        })
        options_df[["call_OI", "call_gamma", "call_delta", "call_volume",
                     "call_mark", "call_bid", "call_ask", "call_theta",
                     "call_vega", "call_iv"]] = 0
    elif puts.empty:
        options_df = calls.rename(columns={
            "openInterest": "call_OI", "gamma": "call_gamma",
            "delta": "call_delta", "volume": "call_volume",
            "mark": "call_mark", "bid": "call_bid", "ask": "call_ask",
            "theta": "call_theta", "vega": "call_vega",
            "impliedVolatility": "call_iv",
        })
        options_df[["put_OI", "put_gamma", "put_delta", "put_volume",
                     "put_mark", "put_bid", "put_ask", "put_theta",
                     "put_vega", "put_iv"]] = 0
    else:
        calls = calls.rename(columns={
            "openInterest": "call_OI", "gamma": "call_gamma",
            "delta": "call_delta", "volume": "call_volume",
            "mark": "call_mark", "bid": "call_bid", "ask": "call_ask",
            "theta": "call_theta", "vega": "call_vega",
            "impliedVolatility": "call_iv",
        })
        puts = puts.rename(columns={
            "openInterest": "put_OI", "gamma": "put_gamma",
            "delta": "put_delta", "volume": "put_volume",
            "mark": "put_mark", "bid": "put_bid", "ask": "put_ask",
            "theta": "put_theta", "vega": "put_vega",
            "impliedVolatility": "put_iv",
        })
        options_df = pd.merge(
            calls, puts,
            on=["strike", "expiration", "dte"],
            how="outer",
        ).fillna(0)

    # Sort by strike descending (high strikes on top, like the screenshot)
    options_df = options_df.sort_values(["strike", "expiration"], ascending=[False, True])
    options_df = options_df.reset_index(drop=True)

    return options_df, spot_price


def _parse_exp_date_map(exp_date_map, option_type):
    """Parse callExpDateMap or putExpDateMap into a flat DataFrame."""
    rows = []
    for exp_key, strikes_dict in exp_date_map.items():
        # exp_key format: "YYYY-MM-DD:DTE"
        parts = exp_key.split(":")
        exp_date = parts[0]
        dte = int(parts[1]) if len(parts) > 1 else 0

        for strike_key, contracts in strikes_dict.items():
            for contract in contracts:
                rows.append({
                    "strike": float(contract.get("strikePrice", strike_key)),
                    "expiration": exp_date,
                    "dte": contract.get("daysToExpiration", dte),
                    "openInterest": contract.get("openInterest", 0),
                    "gamma": contract.get("gamma", 0.0),
                    "delta": contract.get("delta", 0.0),
                    "volume": contract.get("totalVolume", 0),
                    "mark": contract.get("mark", 0.0),
                    "bid": contract.get("bid", 0.0),
                    "ask": contract.get("ask", 0.0),
                    "theta": contract.get("theta", 0.0),
                    "vega": contract.get("vega", 0.0),
                    "impliedVolatility": contract.get("impliedVolatility", 0.0),
                })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    # Ensure numeric types
    for col in ["strike", "openInterest", "gamma", "delta", "volume", "dte", "mark",
                "bid", "ask", "theta", "vega", "impliedVolatility"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df


def get_spot_price(client):
    """Fetch current SPX spot price."""
    response = client.quote(SYMBOL)
    if not response.ok:
        raise RuntimeError(f"Quote error {response.status_code}: {response.text}")
    data = response.json()
    # Response structure: {"$SPX": {"quote": {"lastPrice": ...}}}
    symbol_data = data.get(SYMBOL, {})
    quote = symbol_data.get("quote", symbol_data)
    return quote.get("lastPrice", quote.get("last", quote.get("mark", 0)))
