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


# ========== BRRRR TAB ==========

def brrrr_signal_html(signal):
    """Big directional signal — the centerpiece of the BRRRR tab."""
    direction = signal["direction"]
    confidence = signal["confidence"]
    score = signal["composite_score"]

    if direction == "BUY":
        bg = "linear-gradient(135deg, #004d25, #00c853)"
        border = "#00e676"
        label = "BUY CALLS"
        icon = "&#9650;"  # ▲
        glow = "0 0 40px rgba(0,200,83,0.4), 0 0 80px rgba(0,200,83,0.15)"
    elif direction == "SELL":
        bg = "linear-gradient(135deg, #4d0011, #ff1744)"
        border = "#ff5252"
        label = "BUY PUTS"
        icon = "&#9660;"  # ▼
        glow = "0 0 40px rgba(255,23,68,0.4), 0 0 80px rgba(255,23,68,0.15)"
    else:
        bg = "linear-gradient(135deg, #2a2a3a, #444)"
        border = "#666"
        label = "WAIT"
        icon = "&#9644;"  # ▬
        glow = "none"

    return f"""
    <div style="text-align:center; margin:16px 0;">
        <div style="display:inline-block; background:{bg}; border:3px solid {border};
            border-radius:20px; padding:24px 60px; box-shadow:{glow};">
            <div style="color:#fff; font-size:48px; font-weight:900; letter-spacing:4px;
                text-shadow:0 2px 10px rgba(0,0,0,0.5);">
                {icon} {label}</div>
            <div style="color:rgba(255,255,255,0.8); font-size:16px; margin-top:6px;">
                Score: {score:+.4f}</div>
        </div>
    </div>"""


def brrrr_confidence_meter_html(confidence):
    """Visual confidence meter with conviction guide."""
    # Determine tier
    if confidence >= 65:
        tier = "HIGH CONVICTION"
        tier_desc = "Full size — strong edge"
        tier_color = "#00c853"
        tier_bg = "rgba(0,200,83,0.15)"
    elif confidence >= 45:
        tier = "MODERATE"
        tier_desc = "Standard size"
        tier_color = "#ffc107"
        tier_bg = "rgba(255,193,7,0.1)"
    elif confidence >= 25:
        tier = "SPECULATIVE"
        tier_desc = "Small size only"
        tier_color = "#ff9800"
        tier_bg = "rgba(255,152,0,0.1)"
    else:
        tier = "NO EDGE"
        tier_desc = "Sit on hands"
        tier_color = "#ff1744"
        tier_bg = "rgba(255,23,68,0.1)"

    # Build tick marks for the meter
    ticks = ""
    for pct in [0, 25, 45, 65, 100]:
        ticks += f"""<div style="position:absolute; left:{pct}%; top:-14px;
            transform:translateX(-50%); color:#555; font-size:9px;">{pct}</div>"""

    # Color segments on the bar
    segments = f"""
    <div style="position:absolute; left:0; width:25%; height:100%;
        background:#ff1744; border-radius:4px 0 0 4px; opacity:0.3;"></div>
    <div style="position:absolute; left:25%; width:20%; height:100%;
        background:#ff9800; opacity:0.3;"></div>
    <div style="position:absolute; left:45%; width:20%; height:100%;
        background:#ffc107; opacity:0.3;"></div>
    <div style="position:absolute; left:65%; width:35%; height:100%;
        background:#00c853; border-radius:0 4px 4px 0; opacity:0.3;"></div>"""

    fill_pct = min(confidence, 100)

    return f"""
    <div style="background:#16213e; border:1px solid #2a2a4a; border-radius:12px;
        padding:20px 24px; margin:12px 0;">
        <div style="display:flex; justify-content:space-between; align-items:center;
            margin-bottom:12px;">
            <div style="color:#888; font-size:12px; text-transform:uppercase;
                letter-spacing:2px;">Confidence</div>
            <div style="background:{tier_bg}; border:1px solid {tier_color};
                border-radius:6px; padding:4px 12px;">
                <span style="color:{tier_color}; font-size:14px; font-weight:bold;">
                    {tier}</span>
                <span style="color:#888; font-size:11px; margin-left:6px;">{tier_desc}</span>
            </div>
        </div>
        <div style="position:relative; background:#1a1a2e; border-radius:4px;
            height:12px; margin-top:20px; overflow:visible;">
            {segments}
            <div style="position:absolute; left:0; width:{fill_pct}%; height:100%;
                background:{tier_color}; border-radius:4px; opacity:0.8;
                transition:width 0.3s;"></div>
            <div style="position:absolute; left:{fill_pct}%; top:-4px;
                transform:translateX(-50%); width:4px; height:20px;
                background:#fff; border-radius:2px;
                box-shadow:0 0 6px {tier_color};"></div>
            {ticks}
        </div>
        <div style="text-align:center; margin-top:16px;">
            <span style="color:{tier_color}; font-size:28px; font-weight:bold;">
                {confidence:.0f}%</span>
        </div>
    </div>"""


def brrrr_conviction_guide_html():
    """Static conviction guide showing what each tier means."""
    tiers = [
        ("#ff1744", "0-24%", "NO EDGE", "Don't trade. Signal too weak."),
        ("#ff9800", "25-44%", "SPECULATIVE", "Small size if you must. Accept the risk."),
        ("#ffc107", "45-64%", "MODERATE", "Standard position. Flow supports direction."),
        ("#00c853", "65%+", "HIGH CONVICTION", "Full size. Multiple signals aligned."),
    ]

    rows = ""
    for color, pct_range, tier, desc in tiers:
        rows += f"""<div style="display:flex; align-items:center; gap:10px; padding:6px 0;
            border-bottom:1px solid rgba(255,255,255,0.04);">
            <div style="width:8px; height:8px; border-radius:50%;
                background:{color}; flex-shrink:0;"></div>
            <div style="color:{color}; font-size:12px; font-weight:bold;
                width:50px;">{pct_range}</div>
            <div style="color:#ccc; font-size:12px; font-weight:600;
                width:120px;">{tier}</div>
            <div style="color:#888; font-size:11px;">{desc}</div>
        </div>"""

    return f"""
    <div style="background:#16213e; border:1px solid #2a2a4a; border-radius:12px;
        padding:16px; margin:12px 0;">
        <div style="color:#888; font-size:11px; text-transform:uppercase;
            letter-spacing:2px; margin-bottom:8px;">Conviction Guide</div>
        {rows}
    </div>"""


def brrrr_strikes_html(contracts, direction, spot_price):
    """Show top 3 strikes for the chosen direction — simple and actionable."""
    hc = "#00c853" if direction == "CALLS" else "#ff1744"
    dir_label = "CALL" if direction == "CALLS" else "PUT"

    if not contracts:
        return f"""
        <div style="background:#16213e; border:1px solid #2a2a4a; border-radius:12px;
            padding:24px; text-align:center; margin:12px 0;">
            <div style="color:#888; font-size:14px;">No 0DTE {dir_label.lower()}s in $4-$5.50 range</div>
        </div>"""

    top3 = contracts[:3]

    cards = ""
    for i, c in enumerate(top3):
        rank = i + 1
        strike = c["strike"]
        mark = c["mark"]
        cost = mark * 100

        # Distance from ATM
        if direction == "CALLS":
            dist = strike - spot_price
            dist_label = f"{dist:+.0f} pts OTM" if dist > 0 else f"{abs(dist):.0f} pts ITM"
        else:
            dist = spot_price - strike
            dist_label = f"{dist:+.0f} pts OTM" if dist > 0 else f"{abs(dist):.0f} pts ITM"

        # Potential (3x and 5x targets)
        target_3x = mark * 3
        target_5x = mark * 5

        # Visual emphasis — #1 is highlighted
        if rank == 1:
            card_bg = f"linear-gradient(135deg, #16213e, {hc}15)"
            card_border = hc
            strike_size = "28px"
            label_text = "TOP PICK"
        else:
            card_bg = "#16213e"
            card_border = "#2a2a4a"
            strike_size = "22px"
            label_text = f"#{rank}"

        cards += f"""
        <div style="background:{card_bg}; border:1px solid {card_border};
            border-radius:12px; padding:16px; margin:8px 0;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="color:{hc}; font-size:10px; font-weight:bold;
                        text-transform:uppercase; letter-spacing:2px;">{label_text}</div>
                    <div style="color:#fff; font-size:{strike_size}; font-weight:bold;
                        margin:4px 0;">{strike:,.0f} {dir_label}</div>
                    <div style="color:#888; font-size:12px;">{dist_label}</div>
                </div>
                <div style="text-align:right;">
                    <div style="color:#fff; font-size:20px; font-weight:bold;">
                        ${mark:.2f}</div>
                    <div style="color:#888; font-size:11px;">${cost:,.0f} per contract</div>
                </div>
            </div>
            <div style="display:flex; gap:12px; margin-top:10px;
                border-top:1px solid rgba(255,255,255,0.06); padding-top:10px;">
                <div style="flex:1; text-align:center;">
                    <div style="color:#555; font-size:10px;">BID/ASK</div>
                    <div style="color:#aaa; font-size:12px;">
                        ${c['bid']:.2f} / ${c['ask']:.2f}</div>
                </div>
                <div style="flex:1; text-align:center;">
                    <div style="color:#555; font-size:10px;">3X TARGET</div>
                    <div style="color:#ffc107; font-size:12px; font-weight:bold;">
                        ${target_3x:.2f}</div>
                </div>
                <div style="flex:1; text-align:center;">
                    <div style="color:#555; font-size:10px;">5X TARGET</div>
                    <div style="color:#00e676; font-size:12px; font-weight:bold;">
                        ${target_5x:.2f}</div>
                </div>
                <div style="flex:1; text-align:center;">
                    <div style="color:#555; font-size:10px;">VOL</div>
                    <div style="color:#aaa; font-size:12px;">{c['volume']:,}</div>
                </div>
            </div>
        </div>"""

    return cards


def brrrr_signal_components_html(signal):
    """Compact view of what's driving the signal — horizontal bars."""
    components = signal["components"]

    rows = ""
    for key, comp in components.items():
        label = comp["label"]
        norm = comp["normalized"]
        weight_pct = comp["weight"] * 100

        # Color based on direction
        if norm > 0.1:
            bar_c = "#00c853"
            direction = "right"
        elif norm < -0.1:
            bar_c = "#ff1744"
            direction = "left"
        else:
            bar_c = "#555"
            direction = "right"

        bar_width = abs(norm) * 50  # max 50% of bar width (centered)

        rows += f"""<div style="display:flex; align-items:center; gap:8px; margin:6px 0;">
            <div style="color:#888; font-size:11px; width:110px; text-align:right;">{label}</div>
            <div style="flex:1; height:8px; background:#1a1a2e; border-radius:4px;
                position:relative; overflow:hidden;">
                <div style="position:absolute; left:50%; top:0; width:1px; height:100%;
                    background:#333;"></div>"""

        if direction == "right":
            rows += f"""<div style="position:absolute; left:50%; width:{bar_width}%;
                height:100%; background:{bar_c}; border-radius:0 4px 4px 0;"></div>"""
        else:
            rows += f"""<div style="position:absolute; right:50%; width:{bar_width}%;
                height:100%; background:{bar_c}; border-radius:4px 0 0 4px;"></div>"""

        rows += f"""</div>
            <div style="color:{bar_c}; font-size:11px; font-weight:bold;
                width:40px; text-align:right;">{norm:+.2f}</div>
            <div style="color:#555; font-size:10px; width:30px;">{weight_pct:.0f}%</div>
        </div>"""

    return f"""
    <div style="background:#16213e; border:1px solid #2a2a4a; border-radius:12px;
        padding:14px 16px; margin:12px 0;">
        <div style="color:#888; font-size:11px; text-transform:uppercase;
            letter-spacing:2px; margin-bottom:8px;">Signal Breakdown</div>
        <div style="display:flex; justify-content:center; gap:24px; margin-bottom:6px;">
            <span style="color:#ff1744; font-size:10px;">&#9668; PUTS</span>
            <span style="color:#00c853; font-size:10px;">CALLS &#9658;</span>
        </div>
        {rows}
    </div>"""


# ========== FACTOR 2 TAB ==========

def factor2_signal_html(signal_v2):
    """Big directional signal for Factor 2 — same style as BRRRR."""
    direction = signal_v2["direction"]
    confidence = signal_v2["confidence"]
    score = signal_v2["composite_score"]

    if direction == "BUY":
        bg = "linear-gradient(135deg, #004d25, #00c853)"
        border = "#00e676"
        label = "BUY CALLS"
        icon = "&#9650;"
        glow = "0 0 40px rgba(0,200,83,0.4), 0 0 80px rgba(0,200,83,0.15)"
    elif direction == "SELL":
        bg = "linear-gradient(135deg, #4d0011, #ff1744)"
        border = "#ff5252"
        label = "BUY PUTS"
        icon = "&#9660;"
        glow = "0 0 40px rgba(255,23,68,0.4), 0 0 80px rgba(255,23,68,0.15)"
    else:
        bg = "linear-gradient(135deg, #2a2a3a, #444)"
        border = "#666"
        label = "WAIT"
        icon = "&#9644;"
        glow = "none"

    return f"""
    <div style="text-align:center; margin:16px 0;">
        <div style="display:inline-block; background:{bg}; border:3px solid {border};
            border-radius:20px; padding:24px 60px; box-shadow:{glow};">
            <div style="color:#fff; font-size:48px; font-weight:900; letter-spacing:4px;
                text-shadow:0 2px 10px rgba(0,0,0,0.5);">
                {icon} {label}</div>
            <div style="color:rgba(255,255,255,0.8); font-size:16px; margin-top:6px;">
                Score: {score:+.4f} | Factor 2 Engine</div>
        </div>
    </div>"""


def factor2_confidence_html(confidence):
    """Confidence meter with adjusted tiers for Factor 2."""
    if confidence >= 40:
        tier = "FULL SIZE"
        tier_desc = "3-5 contracts — strong alignment"
        tier_color = "#00c853"
    elif confidence >= 25:
        tier = "STANDARD"
        tier_desc = "2-3 contracts — flow supports"
        tier_color = "#ffc107"
    elif confidence >= 10:
        tier = "SMALL SPEC"
        tier_desc = "1-2 contracts — slight lean"
        tier_color = "#ff9800"
    else:
        tier = "SKIP"
        tier_desc = "Signals conflicting"
        tier_color = "#ff1744"

    fill = min(confidence, 50) * 2  # Scale 0-50% to 0-100% bar width

    return f"""
    <div style="background:#16213e; border:1px solid #2a2a4a; border-radius:12px;
        padding:20px; margin:12px 0;">
        <div style="display:flex; justify-content:space-between; align-items:center;
            margin-bottom:12px;">
            <div>
                <span style="color:{tier_color}; font-size:32px; font-weight:bold;">
                    {confidence:.0f}%</span>
                <span style="color:#888; font-size:14px; margin-left:8px;">confidence</span>
            </div>
            <div style="background:rgba(0,0,0,0.3); border:1px solid {tier_color};
                border-radius:6px; padding:4px 14px;">
                <span style="color:{tier_color}; font-size:14px; font-weight:bold;">
                    {tier}</span>
            </div>
        </div>
        <div style="background:#1a1a2e; border-radius:4px; height:10px; overflow:hidden;">
            <div style="background:{tier_color}; width:{fill}%; height:100%;
                border-radius:4px; transition:width 0.3s;"></div>
        </div>
        <div style="color:#888; font-size:11px; margin-top:6px;">{tier_desc}</div>
        <div style="display:flex; justify-content:space-between; margin-top:4px;">
            <span style="color:#ff1744; font-size:9px;">0% SKIP</span>
            <span style="color:#ff9800; font-size:9px;">10% SPEC</span>
            <span style="color:#ffc107; font-size:9px;">25% STD</span>
            <span style="color:#00c853; font-size:9px;">40%+ FULL</span>
        </div>
    </div>"""


def factor2_breakdown_html(signal_v2):
    """Signal component breakdown for Factor 2 — horizontal tug-of-war bars."""
    components = signal_v2["components"]

    rows = ""
    for key, comp in components.items():
        label = comp["label"]
        norm = comp["normalized"]
        weight_pct = comp["weight"] * 100

        if norm > 0.1:
            bar_c = "#00c853"
        elif norm < -0.1:
            bar_c = "#ff1744"
        else:
            bar_c = "#555"

        bar_width = abs(norm) * 50

        if norm >= 0:
            bar_pos = f"left:50%; width:{bar_width}%; border-radius:0 4px 4px 0;"
        else:
            bar_pos = f"right:50%; width:{bar_width}%; border-radius:4px 0 0 4px;"

        rows += f"""<div style="display:flex; align-items:center; gap:8px; margin:8px 0;">
            <div style="color:#888; font-size:12px; width:120px; text-align:right;
                font-weight:500;">{label}</div>
            <div style="flex:1; height:10px; background:#1a1a2e; border-radius:4px;
                position:relative;">
                <div style="position:absolute; left:50%; top:0; width:1px; height:100%;
                    background:#333;"></div>
                <div style="position:absolute; {bar_pos}
                    height:100%; background:{bar_c};"></div>
            </div>
            <div style="color:{bar_c}; font-size:12px; font-weight:bold;
                width:44px; text-align:right;">{norm:+.2f}</div>
            <div style="color:#555; font-size:10px; width:30px;">{weight_pct:.0f}%</div>
        </div>"""

    return f"""
    <div style="background:#16213e; border:1px solid #2a2a4a; border-radius:12px;
        padding:16px 18px; margin:12px 0;">
        <div style="color:#888; font-size:11px; text-transform:uppercase;
            letter-spacing:2px; margin-bottom:6px;">Factor 2 Breakdown</div>
        <div style="display:flex; justify-content:center; gap:24px; margin-bottom:8px;">
            <span style="color:#ff1744; font-size:10px;">&#9668; BEARISH</span>
            <span style="color:#00c853; font-size:10px;">BULLISH &#9658;</span>
        </div>
        {rows}
    </div>"""


def factor2_flip_badge_html(flip_level, spot_price):
    """Show the GEX flip level relative to spot."""
    if flip_level is None:
        return ""

    distance = spot_price - flip_level
    above = distance > 0

    if above:
        regime_label = "ABOVE FLIP"
        regime_desc = "Positive gamma — dealers dampen moves (mean-reverting)"
        color = "#00c853"
        icon = "&#9650;"
    else:
        regime_label = "BELOW FLIP"
        regime_desc = "Negative gamma — dealers amplify moves (trending)"
        color = "#ff1744"
        icon = "&#9660;"

    return f"""
    <div style="background:#16213e; border:1px solid #2a2a4a; border-radius:12px;
        padding:14px; margin:12px 0; text-align:center;">
        <div style="color:#888; font-size:10px; text-transform:uppercase;
            letter-spacing:2px;">GEX Flip Level</div>
        <div style="color:#fff; font-size:24px; font-weight:bold; margin:4px 0;">
            {flip_level:,.1f}</div>
        <div style="color:{color}; font-size:13px; font-weight:bold;">
            {icon} {regime_label} ({distance:+.1f} pts)</div>
        <div style="color:#888; font-size:11px; margin-top:4px;">{regime_desc}</div>
    </div>"""


# ========== 0 GAMMA TAB ==========

def zero_gamma_header_html(flip_level, spot_price):
    """Big 0-gamma display — the centerpiece."""
    if flip_level is None:
        return """
        <div style="background:#16213e; border:1px solid #2a2a4a; border-radius:16px;
            padding:40px; text-align:center; margin:16px 0;">
            <div style="color:#888; font-size:18px;">No GEX crossover detected</div>
            <div style="color:#555; font-size:13px; margin-top:8px;">
                All strikes have same-sign GEX</div>
        </div>"""

    distance = spot_price - flip_level
    above = distance > 0

    if above:
        zone_color = "#00c853"
        zone_label = "POSITIVE GAMMA ZONE"
        zone_desc = "Dealers BUY dips, SELL rips — mean-reverting, range-bound"
        zone_glow = "0 0 40px rgba(0,200,83,0.3)"
    else:
        zone_color = "#ff1744"
        zone_label = "NEGATIVE GAMMA ZONE"
        zone_desc = "Dealers SELL dips, BUY rips — trending, explosive moves"
        zone_glow = "0 0 40px rgba(255,23,68,0.3)"

    pct_dist = abs(distance) / spot_price * 100

    return f"""
    <div style="text-align:center; margin:16px 0;">
        <div style="display:inline-block; background:#16213e; border:3px solid {zone_color};
            border-radius:20px; padding:24px 40px; box-shadow:{zone_glow};">
            <div style="color:{zone_color}; font-size:14px; font-weight:bold;
                text-transform:uppercase; letter-spacing:3px;">{zone_label}</div>
            <div style="margin:16px 0;">
                <span style="color:#888; font-size:14px;">0 Gamma Level</span>
                <div style="color:#fff; font-size:42px; font-weight:900;
                    text-shadow:0 0 20px {zone_color}44;">{flip_level:,.1f}</div>
            </div>
            <div style="display:flex; justify-content:center; gap:30px; margin-top:8px;">
                <div>
                    <div style="color:#888; font-size:10px; text-transform:uppercase;">SPX Now</div>
                    <div style="color:#fff; font-size:18px; font-weight:bold;">{spot_price:,.2f}</div>
                </div>
                <div>
                    <div style="color:#888; font-size:10px; text-transform:uppercase;">Distance</div>
                    <div style="color:{zone_color}; font-size:18px; font-weight:bold;">
                        {distance:+.1f} pts</div>
                </div>
                <div>
                    <div style="color:#888; font-size:10px; text-transform:uppercase;">% Away</div>
                    <div style="color:{zone_color}; font-size:18px; font-weight:bold;">
                        {pct_dist:.2f}%</div>
                </div>
            </div>
        </div>
    </div>
    <div style="text-align:center; color:#888; font-size:12px; margin-top:4px;">
        {zone_desc}</div>"""


def zero_gamma_stats_html(regime_info, spot_price):
    """Stats cards for the 0 gamma tab."""
    total = regime_info.get("total_gex", 0)
    pos = regime_info.get("positive_gex", 0)
    neg = regime_info.get("negative_gex", 0)
    max_strike = regime_info.get("max_gex_strike", 0)
    regime = regime_info.get("regime", "UNKNOWN")

    regime_color = "#00c853" if regime == "POSITIVE" else "#ff1744"

    from gex_calculator import format_gex_value

    cards = [
        ("Net GEX", format_gex_value(total), regime, regime_color),
        ("Positive GEX", format_gex_value(pos), "Call-dominant strikes", "#00c853"),
        ("Negative GEX", format_gex_value(neg), "Put-dominant strikes", "#ff1744"),
        ("GEX Magnet", f"{max_strike:,.0f}" if max_strike else "--",
         f"{max_strike - spot_price:+.0f} pts from spot" if max_strike else "", "#90caf9"),
    ]

    html = '<div style="display:flex; gap:10px; margin:16px 0;">'
    for label, value, sub, color in cards:
        html += f"""<div style="flex:1; background:#16213e; border:1px solid #2a2a4a;
            border-radius:10px; padding:14px; text-align:center;">
            <div style="color:#666; font-size:10px; text-transform:uppercase;
                letter-spacing:2px;">{label}</div>
            <div style="color:{color}; font-size:22px; font-weight:bold; margin:6px 0;">
                {value}</div>
            <div style="color:#555; font-size:11px;">{sub}</div>
        </div>"""
    html += '</div>'
    return html


def zero_gamma_explanation_html():
    """Static explanation of what 0 gamma means."""
    return """
    <div style="background:#16213e; border:1px solid #2a2a4a; border-radius:12px;
        padding:16px; margin:12px 0;">
        <div style="color:#888; font-size:11px; text-transform:uppercase;
            letter-spacing:2px; margin-bottom:10px;">How to Use This</div>
        <div style="display:flex; gap:16px;">
            <div style="flex:1; border-right:1px solid #2a2a4a; padding-right:16px;">
                <div style="color:#00c853; font-size:13px; font-weight:bold;
                    margin-bottom:6px;">&#9650; SPX Above 0-Gamma</div>
                <div style="color:#aaa; font-size:11px; line-height:1.5;">
                    Dealers are long gamma. They buy when price drops, sell when it rises.
                    This <b style="color:#fff;">dampens</b> moves. Expect range-bound,
                    mean-reverting action. Fade moves, sell premium.</div>
            </div>
            <div style="flex:1; padding-left:16px;">
                <div style="color:#ff1744; font-size:13px; font-weight:bold;
                    margin-bottom:6px;">&#9660; SPX Below 0-Gamma</div>
                <div style="color:#aaa; font-size:11px; line-height:1.5;">
                    Dealers are short gamma. They sell when price drops, buy when it rises.
                    This <b style="color:#fff;">amplifies</b> moves. Expect trending,
                    explosive action. Ride momentum, buy 0DTE.</div>
            </div>
        </div>
    </div>"""


# ========== 0DTE GEX TAB ==========

def dte0_gex_header_html(flip_level, spot_price, info):
    """Big 0DTE header — GEX Magnet as the hero number, flip level secondary."""
    if not info or info.get("total_gex", 0) == 0:
        return """
        <div style="background:#16213e; border:1px solid #2a2a4a; border-radius:16px;
            padding:40px; text-align:center; margin:16px 0;">
            <div style="color:#888; font-size:18px;">No 0DTE contracts found</div>
            <div style="color:#555; font-size:13px; margin-top:8px;">
                Market may be closed or no same-day expiry available</div>
        </div>"""

    magnet = info.get("max_gex_strike")
    regime = info.get("regime", "UNKNOWN")
    zone_color = "#00c853" if regime == "POSITIVE" else "#ff1744"

    if magnet:
        mag_dist = magnet - spot_price
        mag_pct = abs(mag_dist) / spot_price * 100
        mag_dir = "above" if mag_dist > 0 else "below"
    else:
        mag_dist = 0
        mag_pct = 0
        mag_dir = ""

    # Flip level info (secondary)
    flip_html = ""
    if flip_level:
        flip_dist = spot_price - flip_level
        above_flip = flip_dist > 0
        flip_color = "#00c853" if above_flip else "#ff1744"
        flip_label = "ABOVE FLIP" if above_flip else "BELOW FLIP"
        flip_desc = "Dealers dampening — range-bound" if above_flip else "Dealers amplifying — explosive"

        flip_html = f"""
        <div style="display:flex; justify-content:center; gap:24px; margin-top:14px;
            padding-top:14px; border-top:1px solid rgba(255,255,255,0.08);">
            <div style="text-align:center;">
                <div style="color:#888; font-size:10px; text-transform:uppercase;">0DTE Flip Level</div>
                <div style="color:#ffc107; font-size:20px; font-weight:bold;">{flip_level:,.1f}</div>
            </div>
            <div style="text-align:center;">
                <div style="color:#888; font-size:10px; text-transform:uppercase;">Regime</div>
                <div style="color:{flip_color}; font-size:14px; font-weight:bold;
                    margin-top:4px;">{flip_label}</div>
                <div style="color:#888; font-size:10px;">{flip_desc}</div>
            </div>
            <div style="text-align:center;">
                <div style="color:#888; font-size:10px; text-transform:uppercase;">SPX to Flip</div>
                <div style="color:{flip_color}; font-size:20px; font-weight:bold;">
                    {flip_dist:+.1f} pts</div>
            </div>
        </div>"""
    else:
        flip_html = f"""
        <div style="text-align:center; margin-top:12px; padding-top:12px;
            border-top:1px solid rgba(255,255,255,0.08);">
            <span style="color:{zone_color}; font-size:12px; font-weight:bold;">
                All {regime} gamma — no flip level in 0DTE chain</span>
        </div>"""

    return f"""
    <div style="text-align:center; margin:16px 0;">
        <div style="display:inline-block; background:#16213e; border:3px solid #90caf9;
            border-radius:20px; padding:28px 50px;
            box-shadow:0 0 50px rgba(144,202,249,0.2);">
            <div style="color:#90caf9; font-size:14px; font-weight:bold;
                text-transform:uppercase; letter-spacing:3px;">0DTE GEX Magnet</div>
            <div style="color:#fff; font-size:52px; font-weight:900; margin:8px 0;
                text-shadow:0 0 30px rgba(144,202,249,0.3);">
                {magnet:,.0f}</div>
            <div style="display:flex; justify-content:center; gap:30px; margin-top:8px;">
                <div>
                    <div style="color:#888; font-size:10px; text-transform:uppercase;">SPX Now</div>
                    <div style="color:#fff; font-size:18px; font-weight:bold;">{spot_price:,.2f}</div>
                </div>
                <div>
                    <div style="color:#888; font-size:10px; text-transform:uppercase;">Distance</div>
                    <div style="color:#90caf9; font-size:18px; font-weight:bold;">
                        {mag_dist:+.0f} pts {mag_dir}</div>
                </div>
                <div>
                    <div style="color:#888; font-size:10px; text-transform:uppercase;">% Away</div>
                    <div style="color:#90caf9; font-size:18px; font-weight:bold;">
                        {mag_pct:.2f}%</div>
                </div>
            </div>
            {flip_html}
        </div>
    </div>
    <div style="text-align:center; color:#888; font-size:12px; margin-top:4px;">
        Price is pulled toward the magnet strike — highest 0DTE dealer gamma exposure</div>"""


def dte0_gex_stats_html(info, spot_price):
    """Stats cards for the 0DTE GEX tab — includes OI/volume and walls."""
    if not info:
        return ""

    from gex_calculator import format_gex_value

    total = info.get("total_gex", 0)
    regime = info.get("regime", "UNKNOWN")
    regime_color = "#00c853" if regime == "POSITIVE" else "#ff1744"
    call_wall = info.get("call_wall")
    put_wall = info.get("put_wall")
    max_strike = info.get("max_gex_strike")

    row1 = [
        ("0DTE Net GEX", format_gex_value(total), regime, regime_color),
        ("GEX Magnet", f"{max_strike:,.0f}" if max_strike else "--",
         f"{max_strike - spot_price:+.0f} pts" if max_strike else "", "#90caf9"),
        ("Call Wall", f"{call_wall:,.0f}" if call_wall else "--",
         f"{call_wall - spot_price:+.0f} pts (resistance)" if call_wall else "", "#00c853"),
        ("Put Wall", f"{put_wall:,.0f}" if put_wall else "--",
         f"{put_wall - spot_price:+.0f} pts (support)" if put_wall else "", "#ff1744"),
    ]

    total_call_oi = info.get("total_call_oi", 0)
    total_put_oi = info.get("total_put_oi", 0)
    total_call_vol = info.get("total_call_vol", 0)
    total_put_vol = info.get("total_put_vol", 0)
    pc_oi = total_put_oi / total_call_oi if total_call_oi > 0 else 0
    pc_vol = total_put_vol / total_call_vol if total_call_vol > 0 else 0

    row2 = [
        ("0DTE Call OI", f"{total_call_oi:,}", f"Vol: {total_call_vol:,}", "#00c853"),
        ("0DTE Put OI", f"{total_put_oi:,}", f"Vol: {total_put_vol:,}", "#ff1744"),
        ("P/C OI Ratio", f"{pc_oi:.2f}",
         "Bearish" if pc_oi > 1.2 else "Bullish" if pc_oi < 0.8 else "Neutral",
         "#ff1744" if pc_oi > 1.2 else "#00c853" if pc_oi < 0.8 else "#888"),
        ("P/C Vol Ratio", f"{pc_vol:.2f}",
         "Bearish" if pc_vol > 1.2 else "Bullish" if pc_vol < 0.8 else "Neutral",
         "#ff1744" if pc_vol > 1.2 else "#00c853" if pc_vol < 0.8 else "#888"),
    ]

    html = ""
    for row in [row1, row2]:
        html += '<div style="display:flex; gap:10px; margin:8px 0;">'
        for label, value, sub, color in row:
            html += f"""<div style="flex:1; background:#16213e; border:1px solid #2a2a4a;
                border-radius:10px; padding:12px; text-align:center;">
                <div style="color:#666; font-size:10px; text-transform:uppercase;
                    letter-spacing:1px;">{label}</div>
                <div style="color:{color}; font-size:20px; font-weight:bold; margin:4px 0;">
                    {value}</div>
                <div style="color:#555; font-size:11px;">{sub}</div>
            </div>"""
        html += '</div>'
    return html


def dte0_gex_vs_all_html(flip_0dte, flip_all, spot_price):
    """Compare 0DTE flip vs all-expiry flip — shows divergence."""
    if flip_0dte is None and flip_all is None:
        return ""

    dte0_str = f"{flip_0dte:,.1f}" if flip_0dte else "N/A"
    all_str = f"{flip_all:,.1f}" if flip_all else "N/A"

    if flip_0dte and flip_all:
        diff = flip_0dte - flip_all
        if abs(diff) < 5:
            note = "Aligned — both timeframes agree"
            note_color = "#00c853"
        elif diff > 0:
            note = f"0DTE flip is {diff:+.1f} pts ABOVE all-expiry — intraday more bullish"
            note_color = "#00c853"
        else:
            note = f"0DTE flip is {diff:+.1f} pts BELOW all-expiry — intraday more bearish"
            note_color = "#ff1744"
    else:
        note = "Cannot compare — one timeframe has no flip level"
        note_color = "#888"

    return f"""
    <div style="background:#16213e; border:1px solid #2a2a4a; border-radius:12px;
        padding:14px 18px; margin:12px 0;">
        <div style="color:#888; font-size:11px; text-transform:uppercase;
            letter-spacing:2px; margin-bottom:10px;">0DTE vs All-Expiry Flip</div>
        <div style="display:flex; gap:20px; justify-content:center; align-items:center;">
            <div style="text-align:center;">
                <div style="color:#ffc107; font-size:10px; text-transform:uppercase;">0DTE Flip</div>
                <div style="color:#ffc107; font-size:24px; font-weight:bold;">{dte0_str}</div>
            </div>
            <div style="color:#555; font-size:20px;">vs</div>
            <div style="text-align:center;">
                <div style="color:#90caf9; font-size:10px; text-transform:uppercase;">All-Expiry Flip</div>
                <div style="color:#90caf9; font-size:24px; font-weight:bold;">{all_str}</div>
            </div>
        </div>
        <div style="text-align:center; color:{note_color}; font-size:12px;
            margin-top:8px;">{note}</div>
    </div>"""
