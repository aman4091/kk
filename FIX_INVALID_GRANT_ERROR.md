# 🔧 Fix: invalid_grant Error - Google Drive

## Error

```
❌ Google Drive upload error: ('invalid_grant: Bad Request', {'error': 'invalid_grant', 'error_description': 'Bad Request'})
```

## What This Means

`invalid_grant` error occurs when:
- ✅ Token.pickle was found (`✅ Found token.pickle at: ../token.pickle`)
- ❌ But the OAuth token inside is **expired/revoked/invalid**

## Common Causes

1. **Token Expired**: OAuth access token expired (normal, should auto-refresh)
2. **Refresh Token Revoked**: User revoked access in Google Account settings
3. **Token Too Old**: Token not used for 6+ months (Google auto-revokes)
4. **Credentials Changed**: Client ID/secret was regenerated in Google Console

## Quick Fixes (Try in Order)

---

### ✅ FIX #1: Regenerate Token (Fastest)

On Vast.ai terminal:

```bash
cd /workspace/kk

# Method 1: Using Python script
python3 regenerate_gdrive_token.py

# Method 2: Quick one-liner (use YOUR credentials from p.py)
python3 -c "
import pickle, os
from google.oauth2.credentials import Credentials
creds = Credentials(
    token=None,
    refresh_token=os.getenv('GDRIVE_REFRESH_TOKEN'),  # From environment
    token_uri='https://oauth2.googleapis.com/token',
    client_id=os.getenv('GDRIVE_CLIENT_ID'),
    client_secret=os.getenv('GDRIVE_CLIENT_SECRET'),
    scopes=['https://www.googleapis.com/auth/drive']
)
with open('token.pickle', 'wb') as f:
    pickle.dump(creds, f)
print('✅ Token regenerated!')
"

# Note: Environment variables are set by p.py automatically

# Restart bot
pkill -f final_working_bot.py
cd f5-automation
python3 ../final_working_bot.py
```

**Expected:** Token refreshes automatically on first use.

---

### ✅ FIX #2: Fresh OAuth Flow (If Fix #1 Fails)

If refresh_token itself is revoked, you need a completely new token:

#### On Your Local PC (Windows):

```bash
cd E:\tts

# Create generate_token.py if not exists:
python generate_token.py
# Browser will open
# Login with Google account
# Allow drive access
# token.pickle will be created
```

#### Upload to Vast.ai:

```bash
# Upload new token.pickle to /workspace/kk/
# Via Jupyter Files interface or scp

# Restart bot
```

---

### ✅ FIX #3: Check Google Account Permissions

1. Go to: https://myaccount.google.com/permissions
2. Find: "F5-TTS Bot" or your app name
3. Check if access is still granted
4. If revoked, re-run OAuth flow (Fix #2)

---

## Why Did This Happen?

### Scenario 1: First Time Setup
- p.py created token.pickle from embedded refresh_token
- Refresh_token might be old/expired
- **Solution:** Regenerate token (Fix #1)

### Scenario 2: Token Not Used Regularly
- Google auto-revokes tokens after 6 months of inactivity
- **Solution:** Fresh OAuth (Fix #2)

### Scenario 3: Manual Revocation
- User revoked access in Google Account settings
- **Solution:** Fresh OAuth (Fix #2)

### Scenario 4: Credentials Rotated
- Client ID/secret changed in Google Console
- **Solution:** Update credentials.json and fresh OAuth

---

## Prevention

### Auto-Refresh Logic (Already in Bot)

The bot now includes automatic token refresh:

```python
# In final_working_bot.py
if creds and creds.expired and creds.refresh_token:
    try:
        print("🔄 Refreshing expired Google Drive token...")
        creds.refresh(Request())
        with open(token_file, 'wb') as token:
            pickle.dump(creds, token)
        print("✅ Token refreshed and saved")
    except Exception as refresh_error:
        print(f"❌ Token refresh failed: {refresh_error}")
        return None
```

### Regular Usage
- Use bot regularly (at least once a month)
- Keeps token active
- Prevents auto-revocation

---

## Complete OAuth Flow Script

If you need to generate token.pickle from scratch:

```python
# generate_token.py
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

SCOPES = ['https://www.googleapis.com/auth/drive']

# Run OAuth flow
flow = InstalledAppFlow.from_client_secrets_file(
    'credentials.json', SCOPES)
creds = flow.run_local_server(port=0)

# Save token
with open('token.pickle', 'wb') as token:
    pickle.dump(creds, token)

print('✅ token.pickle created!')
```

Run on your PC (where browser is available):
```bash
python generate_token.py
```

---

## Troubleshooting

### Error: "Token refresh failed"

**Cause:** Refresh token is invalid/revoked

**Solution:** Do fresh OAuth flow (Fix #2)

---

### Error: "credentials.json not found"

**Cause:** credentials.json missing or wrong location

**Solution:** p.py should create it automatically. Check:
```bash
ls -la /workspace/kk/credentials.json
```

---

### Error: "redirect_uri_mismatch"

**Cause:** OAuth flow running on different host

**Solution:** Run OAuth on local PC, not Vast.ai

---

## Testing After Fix

Send test message to bot:
```
Test audio generation
```

Expected log output:
```
✅ Found token.pickle at: ../token.pickle
🔄 Refreshing expired Google Drive token... (if expired)
✅ Token refreshed and saved
☁️ Uploading to Google Drive...
✅ Google Drive upload: generated_1234_raw.wav
   File ID: 1ABC...
   Link: https://drive.google.com/...
```

---

## Summary

| Error | Cause | Solution | Time |
|-------|-------|----------|------|
| invalid_grant | Expired token | Regenerate (Fix #1) | 1 min |
| invalid_grant | Revoked refresh_token | Fresh OAuth (Fix #2) | 5 min |
| Token not found | Missing file | Run p.py again | 10 min |

**Most Common:** Fix #1 works 90% of the time! ✅

---

## Quick Commands Reference

```bash
# Regenerate token (Vast.ai)
cd /workspace/kk
python3 regenerate_gdrive_token.py

# Check if token exists
ls -la token.pickle

# View token info (debug)
python3 -c "import pickle; print(pickle.load(open('token.pickle','rb')))"

# Restart bot
pkill -f final_working_bot.py
cd f5-automation && python3 ../final_working_bot.py
```

---

**TL;DR:** Run `python3 regenerate_gdrive_token.py` on Vast.ai, restart bot. Done! ✅
