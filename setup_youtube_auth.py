"""
╔══════════════════════════════════════════════════════╗
║         setup_youtube_auth.py                        ║
║  Run this ONCE on your laptop to link your           ║
║  YouTube channel. Creates youtube_token.json         ║
║  which you then paste into GitHub Secrets.           ║
╚══════════════════════════════════════════════════════╝

Run with:  python setup_youtube_auth.py
"""

import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES         = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_SECRETS = "client_secret.json"
TOKEN_FILE     = "youtube_token.json"


def main():
    print("\n🔑  YouTube Channel Authorization")
    print("=" * 42)

    if not os.path.exists(CLIENT_SECRETS):
        print(f"""
❌  '{CLIENT_SECRETS}' not found!

Steps to get it:
  1. Go to https://console.cloud.google.com
  2. Select your YouTubeBot project
  3. APIs & Services → Credentials
  4. Create OAuth 2.0 Client ID → Desktop App
  5. Download the JSON → rename to 'client_secret.json'
  6. Place it in this same folder
  7. Run this script again
""")
        return

    print("\n🌐  Opening browser for Google sign-in...")
    print("    Sign in with the Google account that OWNS your YouTube channel.")
    print("    (This can be a different account from your Google Cloud account)\n")

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRETS, SCOPES)
    credentials = flow.run_local_server(port=0, prompt="consent")

    token_data = {
        "token":         credentials.token,
        "refresh_token": credentials.refresh_token,
        "token_uri":     credentials.token_uri,
        "client_id":     credentials.client_id,
        "client_secret": credentials.client_secret,
        "scopes":        list(credentials.scopes),
    }

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print(f"\n✅  Token saved to '{TOKEN_FILE}'")
    print()
    print("=" * 42)
    print("  NEXT STEP — Add to GitHub Secrets:")
    print("=" * 42)
    print(f"""
  1. Open '{TOKEN_FILE}' in Notepad
  2. Select All (Ctrl+A) and Copy everything
  3. Go to your GitHub repo →
     Settings → Secrets and variables → Actions
     → New repository secret
  4. Name:  YOUTUBE_TOKEN_JSON
     Value: (paste the file contents)
  5. Click Save secret
""")


if __name__ == "__main__":
    main()
