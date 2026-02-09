import pandas as pd
import numpy as np
import plotly.graph_objects as go
from gex_calculator import format_gex_value


def get_magic_number(gex_table):
    """Find the 'magic number' — strike with highest positive 0-30 DTE GEX."""
    agg_col = [c for c in gex_table.columns if "DTE" in str(c)]
    if not agg_col:
        return None
    col = agg_col[0]
    data = gex_table[col]
    return {
        "magnet_strike": data.idxmax(),
        "magnet_value": data.max(),
        "repulsion_strike": data.idxmin(),
        "repulsion_value": data.min(),
    }


def magic_number_html(magic, spot_price):
    """Render the magic number callout."""
    if not magic:
        return ""
    magnet = magic["magnet_strike"]
    repulsion = magic["repulsion_strike"]
    distance_up = magnet - spot_price
    distance_down = spot_price - repulsion

    return f"""
    <div style="display: flex; gap: 16px; margin-bottom: 16px;">
        <div style="flex: 1; background: linear-gradient(135deg, #0a3d0a, #1a5c1a); border: 2px solid #00ff88;
            border-radius: 10px; padding: 16px; text-align: center;">
            <div style="color: #88ffaa; font-size: 12px; text-transform: uppercase; letter-spacing: 2px;">Upside Magnet</div>
            <div style="color: #00ff88; font-size: 38px; font-weight: bold; margin: 6px 0;">{magnet:,.0f}</div>
            <div style="color: #88ffaa; font-size: 13px;">GEX: {format_gex_value(magic['magnet_value'])} | {distance_up:+,.0f} pts</div>
        </div>
        <div style="flex: 0.5; background: #16213e; border: 1px solid #444; border-radius: 10px; padding: 16px; text-align: center;">
            <div style="color: #aaa; font-size: 12px; text-transform: uppercase; letter-spacing: 2px;">SPX Now</div>
            <div style="color: #fff; font-size: 32px; font-weight: bold; margin: 6px 0;">{spot_price:,.2f}</div>
        </div>
        <div style="flex: 1; background: linear-gradient(135deg, #3d0a0a, #5c1a1a); border: 2px solid #ff4444;
            border-radius: 10px; padding: 16px; text-align: center;">
            <div style="color: #ffaaaa; font-size: 12px; text-transform: uppercase; letter-spacing: 2px;">Downside Target</div>
            <div style="color: #ff4444; font-size: 38px; font-weight: bold; margin: 6px 0;">{repulsion:,.0f}</div>
            <div style="color: #ffaaaa; font-size: 13px;">GEX: {format_gex_value(magic['repulsion_value'])} | {-distance_down:+,.0f} pts</div>
        </div>
    </div>
    """


def style_gex_table(gex_table, spot_price):
    """Apply heatmap styling matching the reference screenshot exactly.

    Color scheme (matching sofortunegex):
    - Positive values: light warm yellow/cream background
    - Peak positive values (top ~15%): bright GREEN background
    - Negative values: light pink/salmon background
    - Peak negative values (top ~15%): deeper red/magenta background
    - Zero/empty: dark background
    - ATM row: bright yellow/gold across entire row
    - 0-30 DTE column: most vivid colors
    """
    if gex_table.empty:
        return "<p>No data available</p>"

    strikes = gex_table.index.tolist()
    # Exclude "Net Contracts" from display — that goes in the bar chart
    columns = [c for c in gex_table.columns if c != "Net Contracts"]

    atm_strike = min(strikes, key=lambda s: abs(s - spot_price))

    # Pre-compute global max/min for the 0-30 DTE column (for brightness reference)
    agg_col = [c for c in columns if "DTE" in str(c)]

    html = """
    <style>
    .gex-table {
        border-collapse: collapse;
        width: 100%;
        font-family: 'Consolas', 'Courier New', monospace;
        font-size: 13px;
        line-height: 1.4;
    }
    .gex-table th {
        background-color: #1a1a2e;
        color: #bbb;
        padding: 8px 12px;
        text-align: center;
        border-bottom: 2px solid #444;
        font-size: 12px;
        position: sticky;
        top: 0;
        z-index: 2;
    }
    .gex-table td {
        padding: 3px 10px;
        text-align: right;
        border-bottom: 1px solid rgba(255,255,255,0.05);
        white-space: nowrap;
        font-size: 13px;
    }
    .gex-table .strike-col {
        text-align: center;
        font-weight: bold;
        color: #ccc;
        background-color: #12121f;
        position: sticky;
        left: 0;
        z-index: 1;
        border-right: 1px solid #333;
        padding: 3px 14px;
    }
    .gex-table .atm-row td {
        border-top: 2px solid #c0a0ff;
        border-bottom: 2px solid #c0a0ff;
    }
    .gex-table .atm-strike {
        background-color: #d4c030 !important;
        color: #000 !important;
        font-size: 14px;
    }
    .gex-table tr:hover td {
        filter: brightness(1.15);
    }
    </style>
    """

    html += '<div style="overflow-x: auto; max-height: 850px; overflow-y: auto;">'
    html += '<table class="gex-table">'

    # Header
    html += '<thead><tr><th style="border-right: 1px solid #333;">Strike</th>'
    for col in columns:
        # Make 0-30 DTE header stand out
        if "DTE" in str(col):
            html += f'<th style="border-left: 2px solid #555; color: #fff;">{col}</th>'
        else:
            html += f"<th>{col}</th>"
    html += "</tr></thead>"

    # Body
    html += "<tbody>"
    for strike in strikes:
        is_atm = strike == atm_strike
        row_class = ' class="atm-row"' if is_atm else ""
        html += f"<tr{row_class}>"

        # Strike cell
        strike_class = "strike-col atm-strike" if is_atm else "strike-col"
        html += f'<td class="{strike_class}">{strike:,.2f}</td>'

        # Value cells
        for col in columns:
            val = gex_table.loc[strike, col]
            display = format_gex_value(val)
            is_agg = "DTE" in str(col)
            bg = _cell_color(val, gex_table, col, is_atm, is_agg)
            fg = _text_color(val, gex_table, col, is_atm, is_agg)
            border = "border-left: 2px solid #555;" if is_agg else ""
            html += f'<td style="background-color: {bg}; color: {fg}; {border}">{display}</td>'

        html += "</tr>"

    html += "</tbody></table></div>"
    return html


def _cell_color(val, gex_table, col, is_atm, is_agg):
    """Color scheme matching the reference: ONLY the peak values light up.

    Most cells are nearly dark/invisible. Only the top ~5% positive values
    get bright green, and only the top ~5% negative get bright red.
    The 0-30 DTE column is slightly more vivid.
    """
    if is_atm:
        if val == 0 or pd.isna(val):
            return "#7a7020"
        if val > 0:
            return "#8a8020"
        return "#6a4520"

    if val == 0 or pd.isna(val):
        return "#18182a"

    col_data = gex_table[col].replace(0, np.nan).dropna()
    if col_data.empty:
        return "#18182a"

    if val > 0:
        col_max = col_data.max()
        if col_max <= 0:
            return "#18182a"
        pct = min(val / col_max, 1.0)

        if is_agg and pct > 0.90:
            # BRIGHT GREEN — only the very top values in 0-30 DTE column
            t = (pct - 0.90) / 0.10
            return f"rgb({int(30 + 10*t)}, {int(130 + 50*t)}, {int(30 + 20*t)})"
        elif pct > 0.92:
            # BRIGHT GREEN — only THE peak in individual expiry columns
            t = (pct - 0.92) / 0.08
            return f"rgb({int(35 + 10*t)}, {int(120 + 40*t)}, {int(30 + 15*t)})"
        elif pct > 0.50:
            # Barely noticeable warm tint
            t = (pct - 0.50) / 0.42
            r = int(26 + 20 * t)
            g = int(26 + 18 * t)
            b = int(40 - 5 * t)
            return f"rgb({r}, {g}, {b})"
        else:
            # Nearly invisible — very faint warm tint
            t = pct / 0.50
            r = int(24 + 4 * t)
            g = int(24 + 4 * t)
            b = int(42 - 4 * t)
            return f"rgb({r}, {g}, {b})"

    else:  # negative
        col_min = col_data.min()
        if col_min >= 0:
            return "#18182a"
        pct = min(abs(val) / abs(col_min), 1.0)

        if is_agg and pct > 0.90:
            # BRIGHT RED — only the very top negative in 0-30 DTE
            t = (pct - 0.90) / 0.10
            return f"rgb({int(140 + 40*t)}, {int(30 + 5*t)}, {int(45 + 10*t)})"
        elif pct > 0.92:
            # BRIGHT RED — only THE peak negative in individual columns
            t = (pct - 0.92) / 0.08
            return f"rgb({int(130 + 40*t)}, {int(30 + 5*t)}, {int(40 + 10*t)})"
        elif pct > 0.50:
            # Barely noticeable pink tint
            t = (pct - 0.50) / 0.42
            r = int(26 + 18 * t)
            g = int(24 + 2 * t)
            b = int(40 - 2 * t)
            return f"rgb({r}, {g}, {b})"
        else:
            # Nearly invisible — very faint pink
            t = pct / 0.50
            r = int(24 + 4 * t)
            g = int(24 + 1 * t)
            b = int(42 - 2 * t)
            return f"rgb({r}, {g}, {b})"


def _text_color(val, gex_table, col, is_atm, is_agg):
    """Text color — dark on bright backgrounds, light on dark."""
    if is_atm:
        return "#000"
    if val == 0 or pd.isna(val):
        return "#555"

    col_data = gex_table[col].replace(0, np.nan).dropna()
    if col_data.empty:
        return "#ccc"

    if val > 0:
        col_max = col_data.max()
        pct = min(val / col_max, 1.0) if col_max > 0 else 0
        # Only dark text on the bright green peak cells
        if (is_agg and pct > 0.90) or pct > 0.92:
            return "#000"
        return "#ccc"
    else:
        col_min = col_data.min()
        pct = min(abs(val) / abs(col_min), 1.0) if col_min < 0 else 0
        # White text on bright red peak cells
        if (is_agg and pct > 0.90) or pct > 0.92:
            return "#fff"
        return "#ccc"


def create_gex_bar_chart(gex_by_strike, spot_price, net_contracts=None):
    """Create horizontal bar chart matching the reference — Net Contracts per strike.

    Uses numeric y-axis (strike prices) so the ATM line renders correctly.
    Green/teal bars right for positive, red/pink bars left for negative.
    Thick magenta horizontal line at ATM strike.
    """
    if gex_by_strike.empty:
        return go.Figure()

    # Use net_contracts for the bar chart (matching reference)
    data = net_contracts if net_contracts is not None else gex_by_strike
    # Sort ascending for proper y-axis (low strikes at bottom, high at top)
    data = data.sort_index(ascending=True)
    strikes = data.index.tolist()
    values = data.values

    # Scale to thousands for display (reference shows small numbers like -20, 26)
    values_k = values / 1000.0

    colors = ["rgba(0, 180, 140, 0.85)" if v >= 0 else "rgba(200, 50, 80, 0.85)" for v in values_k]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=strikes,  # numeric y-axis
        x=values_k,
        orientation="h",
        marker_color=colors,
        text=[f"{v:.0f}" if abs(v) >= 1 else "" for v in values_k],
        textposition="outside",
        textfont=dict(size=9, color="#aaa"),
        width=3.5,  # bar width in strike-price units
    ))

    # Magenta ATM line (thick, spanning full width — matching reference)
    x_min = min(values_k) * 1.3 if min(values_k) < 0 else -1
    x_max = max(values_k) * 1.3 if max(values_k) > 0 else 1
    fig.add_shape(
        type="line",
        x0=x_min, x1=x_max,
        y0=spot_price, y1=spot_price,
        line=dict(color="#c070ff", width=4),
    )
    fig.add_annotation(
        x=x_max * 0.7, y=spot_price,
        text=f"{spot_price:,.0f}",
        font=dict(color="#c070ff", size=11),
        showarrow=False, yshift=12,
    )

    fig.update_layout(
        title=dict(text="Net Contracts", font=dict(size=13, color="#999")),
        plot_bgcolor="#0e1117",
        paper_bgcolor="#0e1117",
        font=dict(color="#999", size=9),
        xaxis=dict(
            gridcolor="#1a1a2e",
            zerolinecolor="#555",
            zerolinewidth=1,
            tickfont=dict(size=9),
        ),
        yaxis=dict(
            gridcolor="#1a1a2e",
            tickfont=dict(size=9),
            dtick=5,  # tick every $5 to match strike increments
            range=[min(strikes) - 5, max(strikes) + 5],
        ),
        height=max(600, len(strikes) * 20),
        margin=dict(l=55, r=30, t=30, b=20),
        showlegend=False,
        bargap=0.1,
    )

    return fig


def market_status_html():
    """Return HTML badge for market open/closed status."""
    from datetime import datetime
    import pytz

    eastern = pytz.timezone("US/Eastern")
    now = datetime.now(eastern)
    weekday = now.weekday()

    is_weekday = weekday < 5
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)

    if is_weekday and market_open <= now <= market_close:
        return '<span style="background: #00c853; color: #000; padding: 4px 12px; border-radius: 4px; font-weight: bold;">MARKET OPEN</span>'
    else:
        return '<span style="background: #ff1744; color: #fff; padding: 4px 12px; border-radius: 4px; font-weight: bold;">MARKET CLOSED</span>'
