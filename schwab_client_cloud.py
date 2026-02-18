"""Cloud-safe Schwab API client.

Drop-in replacement for schwabdev.Client that manages OAuth tokens
directly via HTTP — no interactive browser/input() prompts.
Works on Streamlit Cloud, Render, Railway, or any headless server.

Requires environment variables:
    SCHWAB_APP_KEY, SCHWAB_APP_SECRET, SCHWAB_REFRESH_TOKEN
"""

import base64
import datetime
import logging
import os
import threading
import urllib.parse
import requests

logger = logging.getLogger("SchwabCloud")


class CloudClient:
    """Minimal Schwab API client for cloud deployments."""

    _base_url = "https://api.schwabapi.com"
    _token_url = "https://api.schwabapi.com/v1/oauth/token"

    def __init__(self, app_key: str, app_secret: str, refresh_token: str, timeout: int = 10):
        self._app_key = app_key
        self._app_secret = app_secret
        self._refresh_token = refresh_token
        self._access_token = None
        self._token_expiry = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
        self._lock = threading.Lock()
        self._timeout = timeout
        self._session = requests.Session()

        # Get initial access token
        self._refresh_access_token()

    def _auth_header(self) -> str:
        """Base64 encoded app_key:app_secret for OAuth."""
        creds = f"{self._app_key}:{self._app_secret}"
        return base64.b64encode(creds.encode()).decode()

    def _refresh_access_token(self):
        """Use refresh token to get a new access token."""
        with self._lock:
            resp = requests.post(
                self._token_url,
                headers={
                    "Authorization": f"Basic {self._auth_header()}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                },
                timeout=30,
            )

            if not resp.ok:
                logger.error(f"Token refresh failed: {resp.status_code} {resp.text}")
                raise RuntimeError(
                    f"Schwab token refresh failed ({resp.status_code}). "
                    "The refresh token may have expired (7-day limit). "
                    "Re-authenticate locally and update SCHWAB_REFRESH_TOKEN."
                )

            data = resp.json()
            self._access_token = data["access_token"]
            # Update refresh token if Schwab returned a new one
            if "refresh_token" in data:
                self._refresh_token = data["refresh_token"]
            expires_in = data.get("expires_in", 1800)
            self._token_expiry = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=expires_in - 60)
            self._session.headers["Authorization"] = f"Bearer {self._access_token}"
            logger.info("Access token refreshed successfully")

    def _ensure_token(self):
        """Refresh access token if expired."""
        now = datetime.datetime.now(datetime.timezone.utc)
        if now >= self._token_expiry:
            self._refresh_access_token()

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        self._ensure_token()
        return self._session.request(
            method, f"{self._base_url}{path}", timeout=self._timeout, **kwargs
        )

    def quote(self, symbol_id: str, fields: str = None) -> requests.Response:
        params = {"fields": fields} if fields else {}
        return self._request(
            "GET",
            f"/marketdata/v1/{urllib.parse.quote(symbol_id, safe='')}/quotes",
            params=params,
        )

    def option_chains(self, symbol: str, contractType=None, strikeCount=None,
                      includeUnderlyingQuote=None, fromDate=None, toDate=None,
                      **kwargs) -> requests.Response:
        params = {
            "symbol": symbol,
            "contractType": contractType,
            "strikeCount": strikeCount,
            "includeUnderlyingQuote": includeUnderlyingQuote,
            "fromDate": fromDate,
            "toDate": toDate,
        }
        # Remove None values
        params = {k: v for k, v in params.items() if v is not None}
        return self._request("GET", "/marketdata/v1/chains", params=params)
