import os
from dotenv import load_dotenv

load_dotenv()

# Data source: "free" (Yahoo Finance) or "schwab" (Schwab API)
# Use "free" while waiting for Schwab approval, switch to "schwab" later
DATA_SOURCE = os.getenv("DATA_SOURCE", "free")

# Schwab API (only needed if DATA_SOURCE="schwab")
SCHWAB_APP_KEY = os.getenv("SCHWAB_APP_KEY")
SCHWAB_APP_SECRET = os.getenv("SCHWAB_APP_SECRET")

# SPX Options
SYMBOL = "$SPX"
STRIKE_INCREMENT = 5
DEFAULT_STRIKES_ABOVE_ATM = 20
DEFAULT_STRIKES_BELOW_ATM = 20
MAX_DTE = 65  # Maximum days to expiration to include
AGGREGATE_DTE = 30  # DTE range for the aggregate column

# Dashboard
REFRESH_INTERVAL_SECONDS = 20
NUM_EXPIRY_COLUMNS = 5  # Show next N expiration dates as individual columns

# Market hours (Eastern Time)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0

# Close Direction Signal
SIGNAL_WEIGHTS = {
    "net_premium": 0.35,
    "gex_magnet": 0.25,
    "zero_dte_skew": 0.25,
    "pc_ratio": 0.15,
}
SIGNAL_THRESHOLD = 0.3        # |score| > this = BUY/SELL
ALERT_TIME_HOUR = 15          # 3:45 PM ET alert
ALERT_TIME_MINUTE = 45

# Contract Scanner
SCANNER_PRICE_MIN = 4.00        # Min contract mark price ($)
SCANNER_PRICE_MAX = 5.50        # Max contract mark price ($)
SCANNER_MAX_DTE = 0             # Only 0DTE contracts
SCANNER_TOP_N = 5               # Show top N scored contracts

SCANNER_WEIGHTS = {
    "gamma_accel": 0.30,         # gamma/delta ratio (acceleration potential)
    "volume_activity": 0.25,     # volume/OI ratio (smart money signal)
    "spread_tight": 0.20,       # bid-ask tightness (execution quality)
    "iv_room": 0.15,            # low IV = room for vega expansion
    "distance_otm": 0.10,       # slightly OTM preferred
}

SCANNER_VOLUME_SPIKE_MULTIPLIER = 2.0
SCANNER_GAMMA_DELTA_THRESHOLD = 0.04
SCANNER_CONFIDENCE_THRESHOLD = 20.0

SCANNER_WINDOWS = [
    {"name": "Morning Session", "start_hour": 10, "start_min": 0, "end_hour": 12, "end_min": 0},
    {"name": "Afternoon Session", "start_hour": 13, "start_min": 0, "end_hour": 16, "end_min": 0},
]
