#!/usr/bin/env python3
"""
Regenerate Google Drive token.pickle
====================================

Use this script when you get "invalid_grant" error.

USAGE:
------
1. On Vast.ai terminal:
   python3 regenerate_gdrive_token.py

2. It will recreate token.pickle from refresh_token
"""

import os
import pickle
from google.oauth2.credentials import Credentials

# Your Google OAuth credentials (from environment or p.py)
# DO NOT hardcode credentials in git! Use environment variables:
GDRIVE_TOKEN_INFO = {
    "refresh_token": os.getenv("GDRIVE_REFRESH_TOKEN", "YOUR_REFRESH_TOKEN_HERE"),
    "client_id": os.getenv("GDRIVE_CLIENT_ID", "YOUR_CLIENT_ID_HERE"),
    "client_secret": os.getenv("GDRIVE_CLIENT_SECRET", "YOUR_CLIENT_SECRET_HERE"),
    "scopes": ["https://www.googleapis.com/auth/drive"]
}

def main():
    print("\n" + "="*60)
    print("🔧 Google Drive Token Regenerator")
    print("="*60 + "\n")

    # Check if token.pickle exists
    if os.path.exists('token.pickle'):
        backup = 'token.pickle.backup'
        os.rename('token.pickle', backup)
        print(f"✅ Backed up existing token.pickle to {backup}")

    # Create new credentials object
    print("🔑 Creating new credentials from refresh_token...")
    try:
        creds = Credentials(
            token=None,
            refresh_token=GDRIVE_TOKEN_INFO["refresh_token"],
            token_uri="https://oauth2.googleapis.com/token",
            client_id=GDRIVE_TOKEN_INFO["client_id"],
            client_secret=GDRIVE_TOKEN_INFO["client_secret"],
            scopes=GDRIVE_TOKEN_INFO["scopes"]
        )

        # Save to token.pickle
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

        print("✅ New token.pickle created successfully!")
        print(f"📁 Location: {os.path.abspath('token.pickle')}")

        # Test token validity
        print("\n🔍 Testing token...")
        from google.auth.transport.requests import Request

        if creds.expired and creds.refresh_token:
            print("🔄 Token expired, refreshing...")
            creds.refresh(Request())

            # Save refreshed token
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
            print("✅ Token refreshed successfully!")

        if creds.valid:
            print("✅ Token is VALID and ready to use!")
            print("\n📋 Next Steps:")
            print("   1. Restart your bot")
            print("   2. Google Drive upload should work now")
        else:
            print("❌ Token is INVALID!")
            print("\n⚠️ This means:")
            print("   1. Refresh token has been revoked")
            print("   2. You need to do fresh OAuth flow")
            print("   3. Run OAuth script on your local PC")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("\n⚠️ Possible causes:")
        print("   1. refresh_token is revoked/expired")
        print("   2. client_id or client_secret changed")
        print("   3. Network connection issue")
        print("\n💡 Solution:")
        print("   Generate new token.pickle using OAuth flow on local PC")

    print("\n" + "="*60)
    print("🏁 Done!")
    print("="*60 + "\n")

if __name__ == "__main__":
    main()
