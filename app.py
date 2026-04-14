import streamlit as st
import time
from datetime import datetime
import pytz

st.set_page_config(
    page_title="GEX Tool — Gamma Exposure Dashboard",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Dark theme CSS
st.markdown("""
<style>
    .stApp { background-color: #0e1117; }
    .block-container { padding-top: 2.5rem; padding-left: 1rem; padding-right: 1rem; }
    div[data-testid="stSidebarContent"] { background-color: #16213e; }
</style>
""", unsafe_allow_html=True)

from gex_calculator import calculate_gex
from close_signal import calculate_close_signal
from contract_scanner import scan_contracts
from signal_v2 import calculate_signal_v2, find_gex_flip_level, calculate_0dte_gex
from ui_components import (
    style_gex_table, create_gex_bar_chart, market_status_html,
    signal_badge_html, single_card_html,
    create_premium_flow_chart, create_signal_history_chart, close_alert_html,
    scanner_alert_banner_html, scanner_lean_badge_html,
    scanner_timing_html, scanner_contracts_table_html,
    scanner_score_breakdown_html, scanner_summary_cards_html,
    brrrr_signal_html, brrrr_confidence_meter_html,
    brrrr_conviction_guide_html, brrrr_strikes_html,
    brrrr_signal_components_html,
    factor2_signal_html, factor2_confidence_html,
    factor2_breakdown_html, factor2_flip_badge_html,
    zero_gamma_header_html, zero_gamma_stats_html,
    zero_gamma_explanation_html,
    dte0_gex_header_html, dte0_gex_stats_html, dte0_gex_vs_all_html,
)
from config import (
    DATA_SOURCE, DEFAULT_STRIKES_ABOVE_ATM, DEFAULT_STRIKES_BELOW_ATM,
    REFRESH_INTERVAL_SECONDS, MAX_DTE, STRIKE_INCREMENT,
)

# --- Initialize session state for signal history ---
if "signal_history" not in st.session_state:
    st.session_state.signal_history = []
if "premium_history" not in st.session_state:
    st.session_state.premium_history = []
if "price_history" not in st.session_state:
    st.session_state.price_history = []
if "last_reset_date" not in st.session_state:
    st.session_state.last_reset_date = None

# Reset history on new trading day
eastern = pytz.timezone("US/Eastern")
now_et = datetime.now(eastern)
today_str = now_et.strftime("%Y-%m-%d")
if st.session_state.last_reset_date != today_str:
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    if now_et >= market_open:
        st.session_state.signal_history = []
        st.session_state.premium_history = []
        st.session_state.price_history = []
        st.session_state.last_reset_date = today_str

# --- Sidebar (matching reference layout) ---
with st.sidebar:
    st.markdown(f"**{datetime.now().strftime('%a %b %d, %H:%M:%S')}**")

    st.markdown("---")
    display_symbol = "SPX"
    st.markdown(f"## {display_symbol}")

    # Data source indicator
    if DATA_SOURCE == "schwab":
        st.success("Data: Schwab API (Real-time)")
    else:
        st.info("Data: Yahoo Finance (Free)")

    strikes_above = st.slider("Strikes Above ATM", 5, 40, DEFAULT_STRIKES_ABOVE_ATM)
    strikes_below = st.slider("Strikes Below ATM", 5, 40, DEFAULT_STRIKES_BELOW_ATM)

    total_strikes = strikes_above + strikes_below + 1
    st.info(f"Total: {total_strikes} strikes | Up to {MAX_DTE} days")

    auto_refresh = st.checkbox("Auto-refresh every 30s", value=False)
    manual_refresh = st.button("Manual Refresh Now")

    st.markdown("---")
    st.markdown(market_status_html(), unsafe_allow_html=True)

    # TradingView mini chart embed
    st.markdown("---")
    st.markdown("#### Live Chart")
    tradingview_html = """
    <!-- TradingView Widget BEGIN -->
    <div class="tradingview-widget-container" style="height:300px;width:100%">
      <div class="tradingview-widget-container__widget" style="height:100%;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js" async>
      {
        "autosize": true,
        "symbol": "CBOE:SPX",
        "interval": "1",
        "timezone": "America/New_York",
        "theme": "dark",
        "style": "1",
        "locale": "en",
        "hide_top_toolbar": true,
        "hide_legend": false,
        "save_image": false,
        "calendar": false,
        "support_host": "https://www.tradingview.com"
      }
      </script>
    </div>
    <!-- TradingView Widget END -->
    """
    st.components.v1.html(tradingview_html, height=350)

# --- Data fetching based on source ---
if DATA_SOURCE == "schwab":
    from schwab_auth import get_client
    from data_fetcher import fetch_options_chain

    @st.cache_resource
    def init_client():
        return get_client()

    try:
        client = init_client()
    except ValueError as e:
        st.error(str(e))
        st.stop()

    @st.cache_data(ttl=REFRESH_INTERVAL_SECONDS)
    def load_data_schwab(_client, _refresh_key):
        return fetch_options_chain(_client)

    refresh_key = time.time() if manual_refresh else int(time.time() // REFRESH_INTERVAL_SECONDS)

    with st.spinner("Fetching options data from Schwab..."):
        try:
            options_df, spot_price = load_data_schwab(client, refresh_key)
        except Exception as e:
            st.error(f"Error fetching data: {e}")
            st.stop()

else:
    # Free data source (Yahoo Finance)
    from data_fetcher_free import fetch_options_chain_free

    @st.cache_data(ttl=REFRESH_INTERVAL_SECONDS)
    def load_data_free(_refresh_key):
        return fetch_options_chain_free()

    refresh_key = time.time() if manual_refresh else int(time.time() // REFRESH_INTERVAL_SECONDS)

    with st.spinner("Fetching options data from Yahoo Finance..."):
        try:
            options_df, spot_price = load_data_free(refresh_key)
        except Exception as e:
            st.error(f"Error fetching data: {e}")
            st.stop()

if options_df.empty:
    st.warning("No options data returned. Market may be closed or symbol invalid.")
    st.stop()

# --- SPX price header ---
st.markdown(
    f'<div style="display:flex; align-items:baseline; gap:16px;">'
    f'<span style="color:#ccc; font-size:16px;">SPX</span>'
    f'<span style="color:#fff; font-size:28px; font-weight:bold;">${spot_price:,.2f}</span>'
    f'<span style="color:#666; font-size:12px;">Last refresh: {datetime.now().strftime("%H:%M:%S")}</span>'
    f'</div>',
    unsafe_allow_html=True,
)

# Filter strikes around ATM
atm_strike = round(spot_price / STRIKE_INCREMENT) * STRIKE_INCREMENT
min_strike = atm_strike - (strikes_below * STRIKE_INCREMENT)
max_strike = atm_strike + (strikes_above * STRIKE_INCREMENT)

filtered_df = options_df[
    (options_df["strike"] >= min_strike) & (options_df["strike"] <= max_strike)
].copy()

# Calculate GEX
gex_table, gex_by_strike, net_contracts = calculate_gex(filtered_df, spot_price)

if gex_table.empty:
    st.warning("No GEX data to display for the selected range.")
    st.stop()

# --- Calculate signals BEFORE tabs ---
signal = calculate_close_signal(options_df, spot_price, gex_by_strike)

# Track price history for momentum signal
now_ts = datetime.now()
st.session_state.price_history.append((now_ts, spot_price))
if len(st.session_state.price_history) > 500:
    st.session_state.price_history = st.session_state.price_history[-500:]

# Factor 2 signal
signal_v2 = calculate_signal_v2(options_df, spot_price, gex_by_strike, st.session_state.price_history)

# 0 Gamma data (all expiry)
flip_level, regime_info = find_gex_flip_level(gex_by_strike)

# 0DTE-only GEX
flip_0dte, info_0dte = calculate_0dte_gex(options_df, spot_price)
st.session_state.signal_history.append(
    (now_ts, signal["composite_score"], signal["components"])
)
st.session_state.premium_history.append(
    (now_ts, signal["net_premium"])
)
if len(st.session_state.signal_history) > 500:
    st.session_state.signal_history = st.session_state.signal_history[-500:]
if len(st.session_state.premium_history) > 500:
    st.session_state.premium_history = st.session_state.premium_history[-500:]

# === TABBED LAYOUT ===
tab_gex, tab_0dte_gex, tab_signal, tab_scanner, tab_brrrr, tab_factor2, tab_zgamma = st.tabs([
    "GEX Dashboard", "0DTE GEX", "Close Direction", "Contract Scanner", "BRRRR", "Factor 2", "0 Gamma"
])

# --- GEX Dashboard Tab (original content) ---
with tab_gex:
    col_table, col_chart = st.columns([3, 1.5])

    with col_table:
        html = style_gex_table(gex_table, spot_price)
        st.markdown(html, unsafe_allow_html=True)

    with col_chart:
        fig = create_gex_bar_chart(gex_by_strike, spot_price, net_contracts=net_contracts)
        st.plotly_chart(fig, use_container_width=True)

# --- Close Direction Tab ---
with tab_signal:
    # 3:45 PM alert banner
    alert = close_alert_html()
    if alert:
        st.markdown(alert, unsafe_allow_html=True)

    # Signal badge
    st.markdown(
        signal_badge_html(signal["direction"], signal["confidence"]),
        unsafe_allow_html=True,
    )

    # Composite score text
    score = signal["composite_score"]
    score_color = "#00c853" if score > 0 else "#ff1744" if score < 0 else "#888"
    st.markdown(
        f'<div style="text-align:center; color:{score_color}; font-size:14px; margin-bottom:16px;">'
        f'Composite Score: {score:+.4f}</div>',
        unsafe_allow_html=True,
    )

    # Component cards — one per column for reliable rendering
    card_cols = st.columns(4)
    for i, (key, comp) in enumerate(signal["components"].items()):
        with card_cols[i]:
            st.markdown(single_card_html(key, comp), unsafe_allow_html=True)

    # Charts side by side
    col_prem, col_sig = st.columns(2)

    with col_prem:
        fig_prem = create_premium_flow_chart(st.session_state.premium_history)
        st.plotly_chart(fig_prem, use_container_width=True)

    with col_sig:
        fig_sig = create_signal_history_chart(st.session_state.signal_history)
        st.plotly_chart(fig_sig, use_container_width=True)

    n_points = len(st.session_state.signal_history)
    st.markdown(
        f'<div style="text-align:center; color:#555; font-size:11px;">'
        f'{n_points} data point{"s" if n_points != 1 else ""} this session</div>',
        unsafe_allow_html=True,
    )

# --- Contract Scanner Tab ---
with tab_scanner:
    scan_result = scan_contracts(options_df, spot_price, signal)

    # Alert banner (if active)
    alert_html = scanner_alert_banner_html(scan_result)
    if alert_html:
        st.markdown(alert_html, unsafe_allow_html=True)

    # Lean badge
    st.markdown(scanner_lean_badge_html(scan_result), unsafe_allow_html=True)

    # Timing window + summary cards
    col_timing, col_summary = st.columns([1, 3])
    with col_timing:
        st.markdown(scanner_timing_html(scan_result["timing_window"]), unsafe_allow_html=True)
    with col_summary:
        st.markdown(scanner_summary_cards_html(scan_result), unsafe_allow_html=True)

    # Contracts tables — BOTH sides, side by side
    col_calls, col_puts = st.columns(2)

    with col_calls:
        st.markdown(
            scanner_contracts_table_html(scan_result["calls"], "CALLS"),
            unsafe_allow_html=True,
        )
        if scan_result["calls"]:
            st.markdown(
                '<div style="color:#888; font-size:11px; margin-top:12px; '
                'text-transform:uppercase; letter-spacing:2px;">'
                'Score Breakdown — Top Call</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                scanner_score_breakdown_html(scan_result["calls"][0]),
                unsafe_allow_html=True,
            )

    with col_puts:
        st.markdown(
            scanner_contracts_table_html(scan_result["puts"], "PUTS"),
            unsafe_allow_html=True,
        )
        if scan_result["puts"]:
            st.markdown(
                '<div style="color:#888; font-size:11px; margin-top:12px; '
                'text-transform:uppercase; letter-spacing:2px;">'
                'Score Breakdown — Top Put</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                scanner_score_breakdown_html(scan_result["puts"][0]),
                unsafe_allow_html=True,
            )

    # Alert reasons
    if scan_result["alert_reasons"]:
        reasons_text = " | ".join(scan_result["alert_reasons"])
        st.markdown(
            f'<div style="color:#555; font-size:11px; text-align:center; '
            f'margin-top:12px;">Triggers: {reasons_text}</div>',
            unsafe_allow_html=True,
        )

# --- BRRRR Tab ---
with tab_brrrr:
    # Big directional signal
    st.markdown(brrrr_signal_html(signal), unsafe_allow_html=True)

    # Confidence meter + conviction guide side by side
    col_meter, col_guide = st.columns([3, 2])
    with col_meter:
        st.markdown(brrrr_confidence_meter_html(signal["confidence"]), unsafe_allow_html=True)
    with col_guide:
        st.markdown(brrrr_conviction_guide_html(), unsafe_allow_html=True)

    # Signal component breakdown
    st.markdown(brrrr_signal_components_html(signal), unsafe_allow_html=True)

    # Determine which side to show strikes for
    scan_result = scan_contracts(options_df, spot_price, signal)

    if signal["direction"] == "BUY":
        pick_dir = "CALLS"
        pick_contracts = scan_result["calls"]
    elif signal["direction"] == "SELL":
        pick_dir = "PUTS"
        pick_contracts = scan_result["puts"]
    else:
        # NEUTRAL — show whichever side has higher top score
        call_top = scan_result["calls"][0]["score"] if scan_result["calls"] else 0
        put_top = scan_result["puts"][0]["score"] if scan_result["puts"] else 0
        if call_top >= put_top and scan_result["calls"]:
            pick_dir = "CALLS"
            pick_contracts = scan_result["calls"]
        elif scan_result["puts"]:
            pick_dir = "PUTS"
            pick_contracts = scan_result["puts"]
        else:
            pick_dir = "CALLS"
            pick_contracts = []

    if signal["direction"] == "NEUTRAL":
        st.markdown(
            '<div style="text-align:center; color:#888; font-size:13px; margin:8px 0;">'
            'Signal is NEUTRAL — showing best available strikes. '
            '<span style="color:#ff9800; font-weight:bold;">Wait for conviction before entering.</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        f'<div style="color:#888; font-size:12px; text-transform:uppercase; '
        f'letter-spacing:2px; text-align:center; margin:16px 0 4px;">'
        f'Top Strikes to Watch</div>',
        unsafe_allow_html=True,
    )
    st.markdown(brrrr_strikes_html(pick_contracts, pick_dir, spot_price), unsafe_allow_html=True)

# --- Factor 2 Tab ---
with tab_factor2:
    # Big signal
    st.markdown(factor2_signal_html(signal_v2), unsafe_allow_html=True)

    # Confidence + Flip badge side by side
    col_conf, col_flip = st.columns([3, 2])
    with col_conf:
        st.markdown(factor2_confidence_html(signal_v2["confidence"]), unsafe_allow_html=True)
    with col_flip:
        st.markdown(
            factor2_flip_badge_html(signal_v2.get("flip_level"), spot_price),
            unsafe_allow_html=True,
        )

    # Factor breakdown
    st.markdown(factor2_breakdown_html(signal_v2), unsafe_allow_html=True)

    # Top strikes (reuse scan_contracts data)
    scan_for_f2 = scan_contracts(options_df, spot_price, signal)

    if signal_v2["direction"] == "BUY":
        f2_dir = "CALLS"
        f2_contracts = scan_for_f2["calls"]
    elif signal_v2["direction"] == "SELL":
        f2_dir = "PUTS"
        f2_contracts = scan_for_f2["puts"]
    else:
        call_top = scan_for_f2["calls"][0]["score"] if scan_for_f2["calls"] else 0
        put_top = scan_for_f2["puts"][0]["score"] if scan_for_f2["puts"] else 0
        if call_top >= put_top and scan_for_f2["calls"]:
            f2_dir = "CALLS"
            f2_contracts = scan_for_f2["calls"]
        elif scan_for_f2["puts"]:
            f2_dir = "PUTS"
            f2_contracts = scan_for_f2["puts"]
        else:
            f2_dir = "CALLS"
            f2_contracts = []

    if signal_v2["direction"] == "NEUTRAL":
        st.markdown(
            '<div style="text-align:center; color:#888; font-size:13px; margin:8px 0;">'
            'Signal is NEUTRAL — showing best available. '
            '<span style="color:#ff9800; font-weight:bold;">Wait for conviction.</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div style="color:#888; font-size:12px; text-transform:uppercase; '
        'letter-spacing:2px; text-align:center; margin:16px 0 4px;">'
        'Top Strikes</div>',
        unsafe_allow_html=True,
    )
    st.markdown(brrrr_strikes_html(f2_contracts, f2_dir, spot_price), unsafe_allow_html=True)

# --- 0 Gamma Tab ---
with tab_zgamma:
    # Big 0-gamma display
    st.markdown(zero_gamma_header_html(flip_level, spot_price), unsafe_allow_html=True)

    # Stats cards
    st.markdown(zero_gamma_stats_html(regime_info, spot_price), unsafe_allow_html=True)

    # GEX by strike chart — horizontal bars with zero-cross highlighted
    if "gex_by_strike" in regime_info and not regime_info["gex_by_strike"].empty:
        import plotly.graph_objects as go_fig

        gex_data = regime_info["gex_by_strike"]
        strikes = gex_data.index.values
        values = gex_data.values

        colors = ["rgba(0,200,83,0.7)" if v > 0 else "rgba(255,23,68,0.7)" for v in values]

        fig_gex = go_fig.Figure()
        fig_gex.add_trace(go_fig.Bar(
            y=strikes, x=values, orientation="h",
            marker_color=colors,
            hovertemplate="Strike: %{y}<br>GEX: %{x:,.0f}<extra></extra>",
        ))

        # Add zero line
        fig_gex.add_vline(x=0, line_color="#555", line_width=1)

        # Add flip level line
        if flip_level:
            fig_gex.add_hline(
                y=flip_level, line_color="#ffc107", line_width=2,
                line_dash="dash",
                annotation_text=f"0-Gamma: {flip_level:,.1f}",
                annotation_position="top right",
                annotation_font_color="#ffc107",
            )

        # Add spot price line
        fig_gex.add_hline(
            y=spot_price, line_color="#90caf9", line_width=2,
            annotation_text=f"SPX: {spot_price:,.1f}",
            annotation_position="bottom right",
            annotation_font_color="#90caf9",
        )

        fig_gex.update_layout(
            title=dict(text="GEX by Strike", font=dict(color="#888", size=14)),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#aaa"),
            height=500,
            margin=dict(l=60, r=20, t=40, b=20),
            xaxis=dict(gridcolor="rgba(255,255,255,0.05)", zeroline=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)", zeroline=False),
            showlegend=False,
        )

        st.plotly_chart(fig_gex, use_container_width=True)

    # Explanation
    st.markdown(zero_gamma_explanation_html(), unsafe_allow_html=True)

# --- 0DTE GEX Tab ---
with tab_0dte_gex:
    # Big 0DTE flip display
    st.markdown(dte0_gex_header_html(flip_0dte, spot_price, info_0dte), unsafe_allow_html=True)

    # Stats cards (OI, volume, walls)
    st.markdown(dte0_gex_stats_html(info_0dte, spot_price), unsafe_allow_html=True)

    # 0DTE vs All-expiry flip comparison
    st.markdown(dte0_gex_vs_all_html(flip_0dte, flip_level, spot_price), unsafe_allow_html=True)

    # 0DTE GEX by strike chart
    if info_0dte and "gex_by_strike" in info_0dte and not info_0dte["gex_by_strike"].empty:
        import plotly.graph_objects as go_0dte

        gex_data = info_0dte["gex_by_strike"]
        strikes = gex_data.index.values
        values = gex_data.values

        colors = ["rgba(0,200,83,0.7)" if v > 0 else "rgba(255,23,68,0.7)" for v in values]

        fig_0dte = go_0dte.Figure()
        fig_0dte.add_trace(go_0dte.Bar(
            y=strikes, x=values, orientation="h",
            marker_color=colors,
            hovertemplate="Strike: %{y}<br>GEX: %{x:,.0f}<extra></extra>",
        ))

        fig_0dte.add_vline(x=0, line_color="#555", line_width=1)

        if flip_0dte:
            fig_0dte.add_hline(
                y=flip_0dte, line_color="#ffc107", line_width=2,
                line_dash="dash",
                annotation_text=f"0DTE Flip: {flip_0dte:,.1f}",
                annotation_position="top right",
                annotation_font_color="#ffc107",
            )

        fig_0dte.add_hline(
            y=spot_price, line_color="#90caf9", line_width=2,
            annotation_text=f"SPX: {spot_price:,.1f}",
            annotation_position="bottom right",
            annotation_font_color="#90caf9",
        )

        # Also show all-expiry flip for comparison
        if flip_level and flip_level != flip_0dte:
            fig_0dte.add_hline(
                y=flip_level, line_color="#90caf9", line_width=1,
                line_dash="dot",
                annotation_text=f"All-Exp Flip: {flip_level:,.1f}",
                annotation_position="top left",
                annotation_font_color="#90caf944",
            )

        fig_0dte.update_layout(
            title=dict(text="0DTE GEX by Strike", font=dict(color="#888", size=14)),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#aaa"),
            height=500,
            margin=dict(l=60, r=20, t=40, b=20),
            xaxis=dict(gridcolor="rgba(255,255,255,0.05)", zeroline=False),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)", zeroline=False),
            showlegend=False,
        )

        st.plotly_chart(fig_0dte, use_container_width=True)

    # Explanation
    st.markdown(zero_gamma_explanation_html(), unsafe_allow_html=True)

# Auto-refresh logic
if auto_refresh:
    time.sleep(REFRESH_INTERVAL_SECONDS)
    st.rerun()
