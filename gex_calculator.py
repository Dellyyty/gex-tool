import pandas as pd
import numpy as np
from config import AGGREGATE_DTE, NUM_EXPIRY_COLUMNS


def calculate_gex(options_df, spot_price):
    """Calculate Net Gamma Exposure per strike per expiration.

    GEX formula (dealer perspective):
        call_gex = call_OI × call_gamma × 100
        put_gex  = -put_OI × put_gamma × 100
        net_gex  = call_gex + put_gex

    Returns:
        tuple: (gex_table, gex_by_strike, net_contracts_by_strike)
            - gex_table: DataFrame pivot — rows=strikes, columns=expiration dates + "0-30 DTE"
            - gex_by_strike: Series — net GEX per strike
            - net_contracts_by_strike: Series — net OI per strike (for bar chart)
    """
    if options_df.empty:
        return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype=float)

    df = options_df.copy()

    # Core GEX calculation (OI × Gamma × 100, no spot multiplication)
    df["call_gex"] = df["call_OI"] * df["call_gamma"] * 100
    df["put_gex"] = -df["put_OI"] * df["put_gamma"] * 100
    df["net_gex"] = df["call_gex"] + df["put_gex"]

    # Net contracts (call OI - put OI) per strike
    df["net_contracts"] = df["call_OI"] - df["put_OI"]

    # Pick the next N expiration dates for individual columns
    unique_exps = sorted(df["expiration"].unique())
    display_exps = unique_exps[:NUM_EXPIRY_COLUMNS]

    # Pivot: rows=strike, columns=expiration, values=net_gex
    pivot = df.pivot_table(
        index="strike",
        columns="expiration",
        values="net_gex",
        aggfunc="sum",
    )

    # Keep only the display expiration columns
    pivot = pivot.reindex(columns=display_exps)

    # Aggregate column: 0-30 DTE
    within_agg = df[df["dte"] <= AGGREGATE_DTE]
    agg_by_strike = within_agg.groupby("strike")["net_gex"].sum()
    pivot[f"0-{AGGREGATE_DTE} DTE"] = agg_by_strike

    # Net contracts per strike (summed across all expirations)
    net_contracts = df.groupby("strike")["net_contracts"].sum()

    # Total GEX per strike (for bar chart)
    gex_by_strike = df.groupby("strike")["net_gex"].sum()

    # Sort strikes descending (high on top)
    pivot = pivot.sort_index(ascending=False)
    gex_by_strike = gex_by_strike.sort_index(ascending=False)
    net_contracts = net_contracts.sort_index(ascending=False)

    # Add net contracts column
    pivot["Net Contracts"] = net_contracts

    # Replace NaN with dash for display
    pivot = pivot.fillna(0)

    return pivot, gex_by_strike, net_contracts


def format_gex_value(val):
    """Format GEX value for display (e.g., 571200 → '571.2k')."""
    if val == 0 or pd.isna(val):
        return "-"
    abs_val = abs(val)
    if abs_val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M"
    elif abs_val >= 1_000:
        return f"{val / 1_000:.1f}k"
    else:
        return f"{val:.0f}"
