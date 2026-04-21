"""
Run this ONCE locally to generate token.json and print the base64 value
you need to set as GOOGLE_TOKEN_JSON on Railway.

Usage:
    python auth_setup.py
"""

import base64
import json
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/calendar"]

def main():
    creds_path = Path("credentials.json")
    if not creds_path.exists():
        print("ERROR: credentials.json not found in current directory.")
        print("Download it from Google Cloud Console → APIs & Services → Credentials.")
        return

    print("Opening browser for Google OAuth…")
    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    creds = flow.run_local_server(port=0)

    token_path = Path("token.json")
    token_path.write_text(creds.to_json())
    print(f"\n✅ token.json saved to {token_path.resolve()}\n")

    b64 = base64.b64encode(token_path.read_bytes()).decode()
    print("=" * 60)
    print("GOOGLE_TOKEN_JSON value to paste into Railway env vars:")
    print("=" * 60)
    print(b64)
    print("=" * 60)

if __name__ == "__main__":
    main()
