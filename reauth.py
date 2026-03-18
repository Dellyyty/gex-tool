"""Quick script to re-authenticate with Schwab and save new tokens."""
import base64, datetime, requests, sqlite3, urllib.parse, os, webbrowser
from dotenv import load_dotenv

load_dotenv()
app_key = os.getenv("SCHWAB_APP_KEY")
app_secret = os.getenv("SCHWAB_APP_SECRET")

auth_url = f"https://api.schwabapi.com/v1/oauth/authorize?client_id={app_key}&redirect_uri=https://127.0.0.1"
print(f"Opening browser to Schwab login...")
webbrowser.open(auth_url)

url = input("\nAfter logging in, paste the FULL callback URL here (be quick, ~30s): ")
code = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("code", [None])[0]
if not code:
    print("ERROR: Could not extract auth code from URL")
    exit(1)

print("Exchanging auth code for tokens...")
headers = {
    "Authorization": f"Basic {base64.b64encode(f'{app_key}:{app_secret}'.encode()).decode()}",
    "Content-Type": "application/x-www-form-urlencoded",
}
resp = requests.post(
    "https://api.schwabapi.com/v1/oauth/token",
    headers=headers,
    data={"grant_type": "authorization_code", "code": code, "redirect_uri": "https://127.0.0.1"},
    timeout=30,
)

if resp.ok:
    td = resp.json()
    now = datetime.datetime.now(datetime.timezone.utc)
    conn = sqlite3.connect(os.path.expanduser("~/.schwabdev/tokens.db"))
    conn.execute("DELETE FROM schwabdev")
    conn.execute(
        "INSERT INTO schwabdev (access_token_issued, refresh_token_issued, access_token, refresh_token, id_token, expires_in, token_type, scope) VALUES (?,?,?,?,?,?,?,?)",
        (now.isoformat(), now.isoformat(), td["access_token"], td["refresh_token"], td.get("id_token", ""), td.get("expires_in", 1800), td.get("token_type", "Bearer"), td.get("scope", "api")),
    )
    conn.commit()
    conn.close()
    expires = (now + datetime.timedelta(days=7)).strftime("%b %d")
    print(f"\nDone! Tokens saved. Refresh token valid until {expires}.")
else:
    print(f"\nERROR: {resp.status_code} - {resp.text}")
