import os
import sqlite3
import schwabdev
from config import SCHWAB_APP_KEY, SCHWAB_APP_SECRET


def _seed_tokens_from_secrets():
    """On Streamlit Cloud, pre-seed the schwabdev token DB from Streamlit secrets.

    This avoids the interactive OAuth browser flow that can't run on a remote server.
    Tokens are stored in Streamlit secrets and written to the SQLite DB before
    schwabdev.Client is created so it finds existing tokens and skips the auth prompt.
    """
    try:
        import streamlit as st
        refresh_token = st.secrets.get("SCHWAB_REFRESH_TOKEN")
        access_token = st.secrets.get("SCHWAB_ACCESS_TOKEN")
        id_token = st.secrets.get("SCHWAB_ID_TOKEN", "")
        rt_issued = st.secrets.get("SCHWAB_RT_ISSUED")
        at_issued = st.secrets.get("SCHWAB_AT_ISSUED")
    except Exception:
        return  # Not on Streamlit Cloud or no secrets configured

    if not refresh_token or not at_issued:
        return  # Secrets not configured, let schwabdev handle auth normally

    db_path = os.path.expanduser("~/.schwabdev/tokens.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS schwabdev (
            access_token_issued TEXT NOT NULL,
            refresh_token_issued TEXT NOT NULL,
            access_token TEXT NOT NULL,
            refresh_token TEXT NOT NULL,
            id_token TEXT NOT NULL,
            expires_in INTEGER,
            token_type TEXT,
            scope TEXT
        );
    """)

    # Only seed if the DB is empty (no existing tokens)
    existing = cur.execute("SELECT COUNT(*) FROM schwabdev").fetchone()[0]
    if existing == 0:
        cur.execute(
            "INSERT INTO schwabdev VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (at_issued, rt_issued, access_token, refresh_token, id_token, 1800, "Bearer", "api"),
        )
        conn.commit()
    conn.close()


def get_client():
    """Initialize and return an authenticated Schwab API client."""
    if not SCHWAB_APP_KEY or SCHWAB_APP_KEY == "your_app_key_here":
        raise ValueError(
            "Schwab API credentials not configured. "
            "Edit .env and set SCHWAB_APP_KEY and SCHWAB_APP_SECRET"
        )

    # On Streamlit Cloud, seed token DB from secrets before creating client
    _seed_tokens_from_secrets()

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
