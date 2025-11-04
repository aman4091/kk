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

# Get credentials from p.py's embedded GDRIVE_TOKEN_INFO
# Since p.py is not in git, we extract from it if available
def get_credentials_from_ppy():
    """Try to extract credentials from p.py file"""
    import sys
    import importlib.util

    # Try to find p.py
    ppy_paths = ['../p.py', 'p.py', '/workspace/p.py']

    for path in ppy_paths:
        if os.path.exists(path):
            try:
                spec = importlib.util.spec_from_file_location("ppy_module", path)
                ppy = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(ppy)

                if hasattr(ppy, 'GDRIVE_TOKEN_INFO'):
                    return ppy.GDRIVE_TOKEN_INFO
            except Exception as e:
                print(f"⚠️ Could not load from {path}: {e}")

    return None

def main():
    print("\n" + "="*60)
    print("🔧 Google Drive Token Regenerator")
    print("="*60 + "\n")

    # Try to get credentials from p.py
    print("🔍 Looking for credentials...")
    GDRIVE_TOKEN_INFO = get_credentials_from_ppy()

    if not GDRIVE_TOKEN_INFO:
        print("❌ Could not find p.py or extract credentials!")
        print("\n⚠️ This script needs access to p.py file")
        print("\n💡 Solutions:")
        print("   1. Run this from same directory as p.py")
        print("   2. Or manually edit this script and add credentials")
        print("   3. Or set environment variables:")
        print("      export GDRIVE_REFRESH_TOKEN='your_token'")
        print("      export GDRIVE_CLIENT_ID='your_client_id'")
        print("      export GDRIVE_CLIENT_SECRET='your_secret'\n")
        return

    print("✅ Found credentials from p.py")

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
