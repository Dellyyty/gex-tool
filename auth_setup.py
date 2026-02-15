"""One-time auth setup for Schwab API. Run this interactively."""
import schwabdev
from config import SCHWAB_APP_KEY, SCHWAB_APP_SECRET

print("Starting Schwab authentication...")
print("A browser window will open. Log in, authorize, then copy the FULL URL from the address bar.")
print("You have 30 seconds to paste it back here!\n")

client = schwabdev.Client(
    app_key=SCHWAB_APP_KEY,
    app_secret=SCHWAB_APP_SECRET,
    callback_url="https://127.0.0.1",
)
print("\nAuth successful! Tokens saved. You can now run the Streamlit app.")
