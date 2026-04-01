import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime
import pytz
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


# --- Close Direction Signal UI ---

def signal_badge_html(direction, confidence):
    """Large BUY/SELL/NEUTRAL badge with confidence percentage."""
    colors = {
        "BUY": {"bg": "#00c853", "border": "#00e676", "text": "#000"},
        "SELL": {"bg": "#ff1744", "border": "#ff5252", "text": "#fff"},
        "NEUTRAL": {"bg": "#555", "border": "#777", "text": "#fff"},
    }
    c = colors.get(direction, colors["NEUTRAL"])
    return f"""
    <div style="text-align: center; margin: 20px 0;">
        <div style="display: inline-block; background: {c['bg']}; border: 3px solid {c['border']};
            border-radius: 16px; padding: 20px 50px; box-shadow: 0 0 30px {c['bg']}44;">
            <div style="color: {c['text']}; font-size: 48px; font-weight: 900; letter-spacing: 4px;">{direction}</div>
            <div style="color: {c['text']}; font-size: 18px; opacity: 0.85; margin-top: 4px;">
                Confidence: {confidence:.0f}%
            </div>
        </div>
    </div>
    """


def single_card_html(key, comp):
    """Render a single signal component card."""
    icons = {
        "net_premium": "$",
        "gex_magnet": "M",
        "zero_dte_skew": "0D",
        "pc_ratio": "P/C",
    }
    norm = comp["normalized"]
    contrib = comp["contribution"]

    if norm > 0.1:
        bar_color = "#00c853"
        val_color = "#00e676"
    elif norm < -0.1:
        bar_color = "#ff1744"
        val_color = "#ff5252"
    else:
        bar_color = "#555"
        val_color = "#aaa"

    raw_val = comp["value"]
    if key == "net_premium":
        if abs(raw_val) >= 1_000_000:
            display_val = f"${raw_val / 1_000_000:+,.1f}M"
        elif abs(raw_val) >= 1_000:
            display_val = f"${raw_val / 1_000:+,.0f}K"
        else:
            display_val = f"${raw_val:+,.0f}"
    elif key == "gex_magnet":
        display_val = f"{raw_val:+.0f} pts"
    elif key == "zero_dte_skew":
        display_val = f"{raw_val:.1%}"
    elif key == "pc_ratio":
        display_val = f"{raw_val:.2f}"
    else:
        display_val = f"{raw_val:.2f}"

    bar_width = min(abs(norm) * 100, 100)

    return f"""<div style="background: #16213e; border: 1px solid #2a2a4a; border-radius: 10px;
        padding: 14px; text-align: center;">
        <div style="color: #888; font-size: 11px; text-transform: uppercase; letter-spacing: 1px;">{icons.get(key, '')} {comp['label']}</div>
        <div style="color: {val_color}; font-size: 22px; font-weight: bold; margin: 6px 0;">{display_val}</div>
        <div style="background: #1a1a2e; border-radius: 4px; height: 6px; margin: 6px 0; overflow: hidden;">
            <div style="background: {bar_color}; width: {bar_width}%; height: 100%; border-radius: 4px;"></div>
        </div>
        <div style="color: #666; font-size: 11px;">Weight: {comp['weight']:.0%} | Contrib: {contrib:+.3f}</div>
    </div>"""


def create_premium_flow_chart(premium_history):
    """Plotly line chart of cumulative net premium flow over the session."""
    if not premium_history:
        fig = go.Figure()
        fig.update_layout(
            title="Net Premium Flow",
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font=dict(color="#999"),
            height=300,
            annotations=[dict(text="Waiting for data...", x=0.5, y=0.5,
                            xref="paper", yref="paper", showarrow=False,
                            font=dict(color="#555", size=16))],
        )
        return fig

    timestamps = [h[0] for h in premium_history]
    values = [h[1] for h in premium_history]
    # Scale to millions
    values_m = [v / 1_000_000 for v in values]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps, y=values_m,
        mode="lines+markers",
        line=dict(color="#00b4d8", width=2),
        marker=dict(size=4, color="#00b4d8"),
        fill="tozeroy",
        fillcolor="rgba(0, 180, 216, 0.1)",
    ))

    fig.add_hline(y=0, line_dash="dash", line_color="#555", line_width=1)

    fig.update_layout(
        title=dict(text="Net Premium Flow ($M)", font=dict(size=13, color="#999")),
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        font=dict(color="#999", size=10),
        xaxis=dict(gridcolor="#1a1a2e", tickformat="%H:%M"),
        yaxis=dict(gridcolor="#1a1a2e", title="$M"),
        height=300,
        margin=dict(l=50, r=20, t=35, b=30),
        showlegend=False,
    )
    return fig


def create_signal_history_chart(signal_history):
    """Plotly line chart of composite score over time."""
    if not signal_history:
        fig = go.Figure()
        fig.update_layout(
            title="Composite Signal",
            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
            font=dict(color="#999"),
            height=300,
            annotations=[dict(text="Waiting for data...", x=0.5, y=0.5,
                            xref="paper", yref="paper", showarrow=False,
                            font=dict(color="#555", size=16))],
        )
        return fig

    timestamps = [h[0] for h in signal_history]
    scores = [h[1] for h in signal_history]

    # Color segments by sign
    colors = ["#00c853" if s > 0 else "#ff1744" if s < 0 else "#555" for s in scores]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=timestamps, y=scores,
        mode="lines+markers",
        line=dict(color="#c0a0ff", width=2),
        marker=dict(size=5, color=colors),
    ))

    # Threshold bands
    from config import SIGNAL_THRESHOLD
    fig.add_hline(y=SIGNAL_THRESHOLD, line_dash="dot", line_color="rgba(0,200,83,0.4)", line_width=1,
                  annotation_text="BUY", annotation_font_color="#00c853")
    fig.add_hline(y=-SIGNAL_THRESHOLD, line_dash="dot", line_color="rgba(255,23,68,0.4)", line_width=1,
                  annotation_text="SELL", annotation_font_color="#ff1744")
    fig.add_hline(y=0, line_dash="dash", line_color="#555", line_width=1)

    fig.update_layout(
        title=dict(text="Composite Signal Score", font=dict(size=13, color="#999")),
        plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
        font=dict(color="#999", size=10),
        xaxis=dict(gridcolor="#1a1a2e", tickformat="%H:%M"),
        yaxis=dict(gridcolor="#1a1a2e", range=[-1.1, 1.1], title="Score"),
        height=300,
        margin=dict(l=50, r=20, t=35, b=30),
        showlegend=False,
    )
    return fig


def close_alert_html():
    """Alert banner for the 3:30-4:00 PM ET MOC trading window."""
    eastern = pytz.timezone("US/Eastern")
    now = datetime.now(eastern)
    hour, minute = now.hour, now.minute

    if not (15 <= hour <= 15 and 30 <= minute <= 59) and not (hour == 16 and minute == 0):
        return ""

    if 45 <= minute <= 55:
        # Peak alert window
        urgency = "ENTRY WINDOW"
        bg = "linear-gradient(135deg, #ff6f00, #ff8f00)"
        border_color = "#ffab00"
        pulse = "animation: pulse 1.5s ease-in-out infinite;"
    else:
        urgency = "MOC WATCH"
        bg = "linear-gradient(135deg, #1a237e, #283593)"
        border_color = "#5c6bc0"
        pulse = ""

    return f"""
    <style>
        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.7; }}
        }}
    </style>
    <div style="background: {bg}; border: 2px solid {border_color}; border-radius: 10px;
        padding: 12px 20px; margin: 10px 0; text-align: center; {pulse}">
        <span style="color: #fff; font-size: 16px; font-weight: bold; letter-spacing: 2px;">
            {urgency} — {now.strftime('%H:%M')} ET
        </span>
    </div>
    """


# --- Contract Scanner UI ---

def scanner_alert_banner_html(scan_result):
    """Pulsing alert banner when scanner triggers are active."""
    if not scan_result["alert_active"]:
        return ""

    alert_type = scan_result["alert_type"]
    lean = scan_result["lean"]

    styles = {
        "COMPOSITE": ("linear-gradient(135deg, #ff6f00, #e65100)", "#ffab00", "COMPOSITE ALERT"),
        "VOLUME_SPIKE": ("linear-gradient(135deg, #1b5e20, #2e7d32)", "#66bb6a", "VOLUME SPIKE"),
        "GAMMA_SETUP": ("linear-gradient(135deg, #4a148c, #6a1b9a)", "#ab47bc", "GAMMA SETUP"),
        "TIME_WINDOW": ("linear-gradient(135deg, #0d47a1, #1565c0)", "#42a5f5", "TIME WINDOW"),
    }
    bg, border, label = styles.get(alert_type, styles["TIME_WINDOW"])
    reasons = " | ".join(scan_result["alert_reasons"])

    lean_text = ""
    if lean != "NEUTRAL":
        lean_color = "#00c853" if lean == "CALLS" else "#ff1744"
        lean_text = f' — Leaning <span style="color:{lean_color};">{lean}</span>'

    return f"""
    <style>@keyframes scanner-pulse {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.7; }} }}</style>
    <div style="background:{bg}; border:2px solid {border}; border-radius:10px;
        padding:14px 20px; margin:10px 0; text-align:center;
        animation:scanner-pulse 1.5s ease-in-out infinite;">
        <div style="color:#fff; font-size:18px; font-weight:bold; letter-spacing:2px;">
            {label}{lean_text}</div>
        <div style="color:rgba(255,255,255,0.7); font-size:12px; margin-top:6px;">{reasons}</div>
    </div>"""


def scanner_lean_badge_html(scan_result):
    """Signal lean badge — shows which direction flow favors."""
    lean = scan_result["lean"]
    reason = scan_result["lean_reason"]

    if lean == "CALLS":
        bg, border, tc = "#00c853", "#00e676", "#000"
        label = "FLOW LEANS CALLS"
    elif lean == "PUTS":
        bg, border, tc = "#ff1744", "#ff5252", "#fff"
        label = "FLOW LEANS PUTS"
    else:
        bg, border, tc = "#555", "#777", "#fff"
        label = "NO CLEAR LEAN"

    return f"""
    <div style="text-align:center; margin:12px 0;">
        <div style="display:inline-block; background:{bg}; border:2px solid {border};
            border-radius:12px; padding:10px 30px; box-shadow:0 0 15px {bg}33;">
            <div style="color:{tc}; font-size:22px; font-weight:900; letter-spacing:2px;">
                {label}</div>
            <div style="color:{tc}; font-size:12px; opacity:0.85; margin-top:2px;">{reason}</div>
        </div>
    </div>"""


def scanner_timing_html(timing_window):
    """Timing window status indicator."""
    eastern = pytz.timezone("US/Eastern")
    now = datetime.now(eastern)
    time_str = now.strftime("%H:%M ET")

    if timing_window:
        return f"""
        <div style="background:linear-gradient(135deg,#1a237e,#283593);
            border:2px solid #5c6bc0; border-radius:8px; padding:10px;
            text-align:center; margin:8px 0;">
            <span style="color:#90caf9; font-size:11px; text-transform:uppercase;
                letter-spacing:2px;">ACTIVE WINDOW</span>
            <div style="color:#fff; font-size:18px; font-weight:bold; margin:4px 0;">
                {timing_window['name']}</div>
            <div style="color:#90caf9; font-size:12px;">
                {timing_window['start']} - {timing_window['end']} ET (Now: {time_str})</div>
        </div>"""
    else:
        return f"""
        <div style="background:#16213e; border:1px solid #2a2a4a; border-radius:8px;
            padding:10px; text-align:center; margin:8px 0;">
            <span style="color:#555; font-size:11px; text-transform:uppercase;
                letter-spacing:2px;">NO ACTIVE WINDOW</span>
            <div style="color:#888; font-size:13px; margin-top:4px;">
                Next: 9:45 AM or 12:45 PM ET | Now: {time_str}</div>
        </div>"""


def scanner_summary_cards_html(scan_result):
    """Summary metric cards for scanner tab — shows best of each side."""
    summary = scan_result["scan_summary"]
    calls = scan_result["calls"]
    puts = scan_result["puts"]

    call_score = calls[0]["score"] if calls else 0
    call_strike = calls[0]["strike"] if calls else 0
    put_score = puts[0]["score"] if puts else 0
    put_strike = puts[0]["strike"] if puts else 0

    def score_color(s):
        return "#00c853" if s >= 70 else "#ffc107" if s >= 50 else "#ff5252"

    cards = [
        ("Best Call", f"{call_strike:,.0f}" if call_strike else "--",
         f"Score: {call_score:.0f}", score_color(call_score)),
        ("Best Put", f"{put_strike:,.0f}" if put_strike else "--",
         f"Score: {put_score:.0f}", score_color(put_score)),
        ("0DTE Found", f"{summary.get('call_candidates', 0)}C / {summary.get('put_candidates', 0)}P",
         f"of {summary.get('total_0dte', 0)} total", "#90caf9"),
        ("Price Range", summary.get("price_range", ""),
         "target: $400-$550", "#aaa"),
    ]

    html = '<div style="display:flex; gap:10px; margin:12px 0;">'
    for label, value, sub, color in cards:
        html += f"""<div style="flex:1; background:#16213e; border:1px solid #2a2a4a;
            border-radius:10px; padding:12px; text-align:center;">
            <div style="color:#666; font-size:10px; text-transform:uppercase;
                letter-spacing:2px;">{label}</div>
            <div style="color:{color}; font-size:22px; font-weight:bold; margin:4px 0;">
                {value}</div>
            <div style="color:#555; font-size:11px;">{sub}</div>
        </div>"""
    html += '</div>'
    return html


def scanner_contracts_table_html(contracts, direction):
    """Styled table of scored contracts — compact for side-by-side layout."""
    from config import SCANNER_GAMMA_DELTA_THRESHOLD

    dir_label = "CALLS" if direction == "CALLS" else "PUTS"
    hc = "#00c853" if direction == "CALLS" else "#ff1744"

    if not contracts:
        return f"""<div style="background:#16213e; border:1px solid #2a2a4a;
            border-radius:10px; padding:20px; text-align:center; margin:8px 0;">
            <div style="color:{hc}; font-size:13px; font-weight:bold;
                text-transform:uppercase; letter-spacing:2px; margin-bottom:8px;">
                {dir_label}</div>
            <div style="color:#888; font-size:13px;">No 0DTE contracts in range</div>
        </div>"""

    # Use unique class name per direction to avoid CSS collisions
    cls = f"sc-{direction.lower()}"

    html = f"""
    <style>
    .{cls} {{ border-collapse:collapse; width:100%;
        font-family:'Consolas','Courier New',monospace; font-size:12px; }}
    .{cls} th {{ background:#1a1a2e; color:{hc}; padding:6px 6px;
        text-align:center; border-bottom:2px solid {hc}44;
        font-size:10px; text-transform:uppercase; letter-spacing:1px; }}
    .{cls} td {{ padding:5px 6px; text-align:right;
        border-bottom:1px solid rgba(255,255,255,0.05); white-space:nowrap; }}
    .{cls} tr:hover td {{ filter:brightness(1.2); }}
    </style>
    <div style="color:{hc}; font-size:13px; font-weight:bold; text-transform:uppercase;
        letter-spacing:2px; text-align:center; margin:8px 0 4px;">{dir_label}</div>
    <table class="{cls}">
    <thead><tr>
        <th>Strike</th><th>Mark</th><th>G/D</th>
        <th>Vol</th><th>IV</th><th>Score</th>
    </tr></thead><tbody>"""

    for i, c in enumerate(contracts):
        rank = i + 1
        score = c["score"]
        if score >= 70:
            sc_bg, sc_c = "rgba(0,200,83,0.25)", "#00c853"
        elif score >= 50:
            sc_bg, sc_c = "rgba(255,193,7,0.2)", "#ffc107"
        else:
            sc_bg, sc_c = "rgba(255,23,68,0.15)", "#ff5252"

        row_bg = "rgba(255,255,255,0.03)" if rank == 1 else "transparent"
        gd = c["gamma_delta_ratio"]
        gd_color = "#00e676" if gd > SCANNER_GAMMA_DELTA_THRESHOLD else "#aaa"
        vol_color = "#ffab00" if c["volume"] > c.get("avg_volume", 0) * 2 else "#aaa"

        html += f"""<tr style="background:{row_bg};">
            <td style="color:#fff; font-weight:bold; text-align:center;">{c['strike']:,.0f}</td>
            <td style="color:#fff;">${c['mark']:.2f}</td>
            <td style="color:{gd_color};">{gd:.4f}</td>
            <td style="color:{vol_color};">{c['volume']:,}</td>
            <td style="color:#aaa;">{c['iv']:.0%}</td>
            <td style="background:{sc_bg}; color:{sc_c}; font-weight:bold;
                font-size:14px; text-align:center;">{score:.0f}</td>
        </tr>"""

    html += "</tbody></table>"
    return html


def scanner_score_breakdown_html(contract):
    """Compact score breakdown bars for top contract — fits in half-width."""
    if not contract or "score_components" not in contract:
        return ""

    components = contract["score_components"]
    labels = {
        "gamma_accel": ("Gamma", "30%"),
        "volume_activity": ("Vol", "25%"),
        "spread_tight": ("Sprd", "20%"),
        "iv_room": ("IV", "15%"),
        "distance_otm": ("OTM", "10%"),
    }

    rows = ""
    for key, (label, weight) in labels.items():
        val = components.get(key, 0)
        if val >= 70:
            bar_c = "#00c853"
        elif val >= 40:
            bar_c = "#ffc107"
        else:
            bar_c = "#ff1744"

        rows += f"""<div style="display:flex; align-items:center; gap:6px; margin:3px 0;">
            <div style="color:#666; font-size:10px; width:36px; text-align:right;
                text-transform:uppercase;">{label}</div>
            <div style="flex:1; background:#1a1a2e; border-radius:3px; height:6px;
                overflow:hidden;">
                <div style="background:{bar_c}; width:{min(val,100)}%;
                    height:100%; border-radius:3px;"></div></div>
            <div style="color:{bar_c}; font-size:11px; font-weight:bold;
                width:24px; text-align:right;">{val:.0f}</div>
        </div>"""

    return f"""<div style="background:#16213e; border:1px solid #2a2a4a;
        border-radius:8px; padding:8px 10px; margin:8px 0;">{rows}</div>"""
