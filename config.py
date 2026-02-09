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
REFRESH_INTERVAL_SECONDS = 30
NUM_EXPIRY_COLUMNS = 5  # Show next N expiration dates as individual columns

# Market hours (Eastern Time)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0
