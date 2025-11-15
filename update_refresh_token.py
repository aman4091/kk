#!/usr/bin/env python3
"""
Auto-update refresh token in p.py from token.pickle

Usage:
1. Run your auth script to generate token.pickle
2. Run this script: python update_refresh_token.py
3. It will automatically update p.py with new refresh token
"""

import pickle
import re
import os

def extract_refresh_token():
    """Extract refresh token from token.pickle"""
    try:
        with open('token.pickle', 'rb') as f:
            creds = pickle.load(f)

        if not creds or not creds.refresh_token:
            print("❌ No refresh token found in token.pickle")
            return None

        print(f"✅ Extracted refresh token: {creds.refresh_token[:50]}...")
        return creds.refresh_token
    except FileNotFoundError:
        print("❌ token.pickle not found!")
        print("   Please run your auth script first to generate token.pickle")
        return None
    except Exception as e:
        print(f"❌ Error reading token.pickle: {e}")
        return None

def update_p_py(new_refresh_token):
    """Update refresh token in p.py"""
    p_py_path = 'p.py'

    if not os.path.exists(p_py_path):
        print(f"❌ p.py not found at: {os.path.abspath(p_py_path)}")
        return False

    try:
        # Read p.py
        with open(p_py_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Find and replace refresh_token
        pattern = r'("refresh_token":\s*")[^"]+(")'
        replacement = r'\g<1>' + new_refresh_token + r'\g<2>'

        new_content = re.sub(pattern, replacement, content)

        if new_content == content:
            print("⚠️ No changes made - refresh_token pattern not found in p.py")
            return False

        # Write back to p.py
        with open(p_py_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        print(f"✅ Updated p.py with new refresh token")
        print(f"📝 File: {os.path.abspath(p_py_path)}")
        return True

    except Exception as e:
        print(f"❌ Error updating p.py: {e}")
        return False

def main():
    print("🔄 Google Drive Refresh Token Updater\n")

    # Step 1: Extract refresh token from token.pickle
    print("Step 1: Reading token.pickle...")
    refresh_token = extract_refresh_token()

    if not refresh_token:
        print("\n❌ Failed to extract refresh token")
        print("\nℹ️  Steps to fix:")
        print("   1. Run your auth script to generate fresh token.pickle")
        print("   2. Run this script again: python update_refresh_token.py")
        return

    # Step 2: Update p.py
    print("\nStep 2: Updating p.py...")
    success = update_p_py(refresh_token)

    if success:
        print("\n✅ SUCCESS! Refresh token updated in p.py")
        print("\nℹ️  Note: p.py is in .gitignore, so this won't be committed")
        print("   The new token will be used next time you run p.py on Vast.ai")
    else:
        print("\n❌ Failed to update p.py")

if __name__ == '__main__':
    main()
