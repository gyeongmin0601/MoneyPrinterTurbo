"""
YouTube OAuth 2.0 authentication helper.

Usage:
    python scripts/youtube_auth.py

This script guides you through the OAuth flow to get
a refresh token for YouTube video uploads.

Prerequisites:
1. Create a Google Cloud project
2. Enable YouTube Data API v3
3. Create OAuth 2.0 credentials (Desktop app type)
4. Download as client_secrets.json and place in project root
"""

import json
import os
import sys
import time

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
CLIENT_SECRETS_FILE = os.path.join(PROJECT_ROOT, "client_secrets.json")
TOKEN_FILE = os.path.join(PROJECT_ROOT, "youtube_oauth_token.json")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def main():
    if not os.path.exists(CLIENT_SECRETS_FILE):
        print("ERROR: client_secrets.json not found!")
        print()
        print("Steps to create it:")
        print("1. Go to https://console.cloud.google.com/apis/credentials")
        print("2. Create OAuth 2.0 Client ID (Desktop application)")
        print("3. Download the JSON file")
        print(f"4. Save it as: {CLIENT_SECRETS_FILE}")
        sys.exit(1)

    with open(CLIENT_SECRETS_FILE, "r") as f:
        data = json.load(f)
        secrets = data.get("installed") or data.get("web")

    if not secrets:
        print("ERROR: Invalid client_secrets.json format")
        sys.exit(1)

    client_id = secrets["client_id"]
    client_secret = secrets["client_secret"]

    scope = " ".join(SCOPES)
    auth_url = (
        f"https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={client_id}"
        f"&redirect_uri=urn:ietf:wg:oauth:2.0:oob"
        f"&response_type=code"
        f"&scope={scope}"
        f"&access_type=offline"
        f"&prompt=consent"
    )

    print()
    print("=" * 60)
    print("YouTube OAuth 2.0 Authentication")
    print("=" * 60)
    print()
    print("1. Open this URL in your browser:")
    print()
    print(f"   {auth_url}")
    print()
    print("2. Sign in with your Google account")
    print("3. Grant permission to upload videos")
    print("4. Copy the authorization code")
    print()

    auth_code = input("Paste the authorization code here: ").strip()

    if not auth_code:
        print("ERROR: No code provided")
        sys.exit(1)

    print()
    print("Exchanging code for token...")

    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": auth_code,
            "grant_type": "authorization_code",
            "redirect_uri": "urn:ietf:wg:oauth:2.0:oob",
        },
        timeout=30,
    )

    if resp.status_code != 200:
        print(f"ERROR: Token exchange failed: {resp.text}")
        sys.exit(1)

    token_data = resp.json()
    token_data["expires_at"] = time.time() + token_data.get("expires_in", 3600)

    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f, indent=2)

    print()
    print("SUCCESS! Authentication complete.")
    print(f"Token saved to: {TOKEN_FILE}")
    print()
    print("You can now use the YouTube upload API.")
    print("The token will auto-refresh when needed.")


if __name__ == "__main__":
    main()
