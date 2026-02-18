import os
import schwabdev
from config import SCHWAB_APP_KEY, SCHWAB_APP_SECRET


def get_client():
    """Initialize and return an authenticated Schwab API client.

    Locally: uses schwabdev with interactive OAuth (browser + token DB).
    On cloud: uses lightweight CloudClient with direct token refresh (no browser/input).
    """
    if not SCHWAB_APP_KEY or SCHWAB_APP_KEY == "your_app_key_here":
        raise ValueError(
            "Schwab API credentials not configured. "
            "Edit .env and set SCHWAB_APP_KEY and SCHWAB_APP_SECRET"
        )

    refresh_token = os.getenv("SCHWAB_REFRESH_TOKEN")

    if refresh_token:
        # Cloud mode: use direct HTTP client (no interactive auth)
        from schwab_client_cloud import CloudClient
        return CloudClient(
            app_key=SCHWAB_APP_KEY,
            app_secret=SCHWAB_APP_SECRET,
            refresh_token=refresh_token,
        )

    # Local mode: use schwabdev with interactive OAuth
    client = schwabdev.Client(
        app_key=SCHWAB_APP_KEY,
        app_secret=SCHWAB_APP_SECRET,
        callback_url="https://127.0.0.1",
    )
    return client


if __name__ == "__main__":
    c = get_client()
    resp = c.quote("$SPX")
    print(resp.json())
