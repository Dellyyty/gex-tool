import schwabdev
from config import SCHWAB_APP_KEY, SCHWAB_APP_SECRET


def get_client():
    """Initialize and return an authenticated Schwab API client."""
    if not SCHWAB_APP_KEY or SCHWAB_APP_KEY == "your_app_key_here":
        raise ValueError(
            "Schwab API credentials not configured. "
            "Edit .env and set SCHWAB_APP_KEY and SCHWAB_APP_SECRET"
        )

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
