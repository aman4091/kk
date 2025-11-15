#!/usr/bin/env python3
"""
Google Drive Token Refresher
Run this to get a fresh token when expired
"""

import json
import pickle
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ['https://www.googleapis.com/auth/drive']

# Your credentials
CREDENTIALS_JSON = {
    "installed": {
        "client_id": "25612659305-rkqp1n8gt5jgpde15v82ubg53qh8h2st.apps.googleusercontent.com",
        "project_id": "f5-bot-images",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_secret": "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",
        "redirect_uris": ["http://localhost"]
    }
}

def refresh_token():
    """Refresh or create new Google Drive token"""
    creds = None

    # Try to load existing token
    try:
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)
            print("✅ Loaded existing token.pickle")
    except FileNotFoundError:
        print("⚠️ token.pickle not found")

    # If no valid credentials, refresh or get new ones
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("🔄 Refreshing expired token...")
            try:
                creds.refresh(Request())
                print("✅ Token refreshed successfully!")
            except Exception as e:
                print(f"❌ Refresh failed: {e}")
                print("🔐 Starting fresh OAuth flow...")
                creds = None

        if not creds:
            # Save credentials.json
            with open('credentials.json', 'w') as f:
                json.dump(CREDENTIALS_JSON, f)

            print("\n🌐 Opening browser for authentication...")
            print("📝 Please authorize the application in your browser")

            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
            print("✅ New token generated!")

        # Save the credentials
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)
            print("💾 Saved to token.pickle")
    else:
        print("✅ Token is still valid!")

    # Print token info for p.py
    print("\n" + "="*60)
    print("📋 Token Info (copy to p.py):")
    print("="*60)
    print(f"refresh_token: {creds.refresh_token}")
    print(f"client_id: {creds.client_id}")
    print(f"client_secret: {creds.client_secret}")
    print(f"token_uri: {creds.token_uri}")
    print("="*60)

    return creds

if __name__ == '__main__':
    print("🚀 Google Drive Token Refresher\n")
    refresh_token()
    print("\n✅ Done!")
