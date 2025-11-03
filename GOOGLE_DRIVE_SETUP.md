# Google Drive Integration Setup

## Overview
Bot automatically uploads generated audio files to Google Drive after uploading to Gofile.

## Prerequisites
1. Google Cloud Console account
2. Google Drive API enabled
3. OAuth 2.0 credentials

---

## Step 1: Create Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create new project or select existing
3. Enable **Google Drive API**:
   - Navigate to "APIs & Services" → "Library"
   - Search for "Google Drive API"
   - Click "Enable"

---

## Step 2: Create OAuth 2.0 Credentials

1. Go to "APIs & Services" → "Credentials"
2. Click "Create Credentials" → "OAuth client ID"
3. Application type: **Desktop app**
4. Name: `F5-TTS Bot` (or any name)
5. Click "Create"
6. Download JSON file → Rename to `credentials.json`

---

## Step 3: Generate token.pickle

### On Your Local PC:

```bash
pip install google-auth-oauthlib google-api-python-client

python3 << EOF
from google_auth_oauthlib.flow import InstalledAppFlow
import pickle

SCOPES = ['https://www.googleapis.com/auth/drive.file']

flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
creds = flow.run_local_server(port=0)

with open('token.pickle', 'wb') as token:
    pickle.dump(creds, token)

print("✅ token.pickle created!")
EOF
```

This will:
- Open browser for Google authentication
- Generate `token.pickle` file

---

## Step 4: Upload Files to Vast.ai

Upload both files to `/workspace/kk/`:
```bash
# In Vast.ai terminal:
cd /workspace/kk

# Upload via SCP or paste content directly
```

**Files needed:**
- `credentials.json`
- `token.pickle`

---

## Step 5: Set Folder ID (Optional)

Get Google Drive folder ID from folder URL:
```
https://drive.google.com/drive/folders/1y-Af4T5pAvgqV2gyvN9zhSPdvZzUcFyi
                                          ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
                                          This is your FOLDER_ID
```

Set in environment:
```bash
export GDRIVE_FOLDER_LONG='1y-Af4T5pAvgqV2gyvN9zhSPdvZzUcFyi'
```

Or add to `p.py` in `ENV_VARS` dict.

---

## Verification

Bot logs will show:
```
✅ Uploaded to Google Drive: 11.wav
   Link: https://drive.google.com/file/d/xxxxx/view
```

---

## Troubleshooting

### Error: "token.pickle not found"
- Make sure file is in `/workspace/kk/`
- Check file permissions: `chmod 644 token.pickle`

### Error: "credentials expired"
- Delete `token.pickle`
- Re-run authentication script
- Upload new `token.pickle`

### Error: "Import error: google-api-python-client"
```bash
pip install google-api-python-client google-auth
```

---

## Security Notes

⚠️ **IMPORTANT:**
- `credentials.json` and `token.pickle` contain sensitive data
- Both files are in `.gitignore` (won't be pushed to GitHub)
- Keep these files secure
- Never share publicly

✅ **Safe to share:**
- `p.py` (setup script - no credentials hardcoded)
- `final_working_bot.py` (reads from pickle files)

---

## Optional: Auto-Upload Without Folder ID

If `GDRIVE_FOLDER_LONG` is not set:
- Files upload to "My Drive" root
- Still works, just not organized

To disable Google Drive upload completely:
- Remove `token.pickle` file
- Bot will skip upload (non-blocking)
