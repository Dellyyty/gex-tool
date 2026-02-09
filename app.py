import streamlit as st
import time
from datetime import datetime

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
from ui_components import style_gex_table, create_gex_bar_chart, market_status_html
from config import (
    DATA_SOURCE, DEFAULT_STRIKES_ABOVE_ATM, DEFAULT_STRIKES_BELOW_ATM,
    REFRESH_INTERVAL_SECONDS, MAX_DTE, STRIKE_INCREMENT,
)

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

# --- SPX price header (matching reference: "SPX  $6,932.30" at top) ---
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

# --- Layout: table on left, bar chart on right (matching reference) ---
col_table, col_chart = st.columns([3, 1.5])

with col_table:
    html = style_gex_table(gex_table, spot_price)
    st.markdown(html, unsafe_allow_html=True)

with col_chart:
    fig = create_gex_bar_chart(gex_by_strike, spot_price, net_contracts=net_contracts)
    st.plotly_chart(fig, use_container_width=True)

# Auto-refresh logic
if auto_refresh:
    time.sleep(REFRESH_INTERVAL_SECONDS)
    st.rerun()
