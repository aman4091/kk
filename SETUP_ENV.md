# Environment Variables Setup Guide

All API keys and confidential data must be set as environment variables before running the bot.

## Required Environment Variables

### Telegram Bot
```bash
export BOT_TOKEN='your_telegram_bot_token_here'
export CHAT_ID='your_default_chat_id'
```

### DeepSeek API
```bash
export DEEPSEEK_API_KEY='your_deepseek_api_key'
```

### Supadata API (YouTube Transcript)
```bash
export SUPADATA_API_KEY='your_supadata_api_key'
# Add more keys via /add_supadata_key command in Telegram
```

### Supabase Database (YouTube Channel Automation)
```bash
export SUPABASE_URL='https://xxxxx.supabase.co'
export SUPABASE_ANON_KEY='eyJhbGciOi...'
```

### YouTube Data API v3
```bash
export YOUTUBE_API_KEY='AIzaSy...'
```

### Google Drive (Optional)
```bash
export GDRIVE_FOLDER_LONG='your_gdrive_folder_id'
export GDRIVE_FOLDER_SHORT='your_gdrive_folder_id'
```

### Telegram Channels (Optional)
```bash
export IMAGE_SHORTS_CHAT_ID='-1002343932866'
export IMAGE_LONG_CHAT_ID='-1002498893774'
export CHANNEL_IDS='-1002498893774,-1002343932866'  # Comma-separated
```

---

## Setup in Vast.ai

### Method 1: Direct Export (Session Only)
```bash
export BOT_TOKEN='8274226808:AAH0...'
export DEEPSEEK_API_KEY='sk-299e2e942ec1...'
export SUPADATA_API_KEY='sd_a3a69115625b...'
export SUPABASE_URL='https://zrczbdkighpnzenjdsbi.supabase.co'
export SUPABASE_ANON_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6...'
export YOUTUBE_API_KEY='AIzaSyCFEQBb2_98ods5...'
export CHAT_ID='447705580'
export IMAGE_SHORTS_CHAT_ID='-1002343932866'
export IMAGE_LONG_CHAT_ID='-1002498893774'
export GDRIVE_FOLDER_LONG='1y-Af4T5pAvgqV2gyvN9zhSPdvZzUcFyi'
export GDRIVE_FOLDER_SHORT='1JdJCYDXLWjAz1091zs_Pnev3FuK3Ftex'

python3 k.py
```

### Method 2: .bashrc (Persistent)
```bash
nano ~/.bashrc

# Add at the end:
export BOT_TOKEN='your_token'
export DEEPSEEK_API_KEY='your_key'
# ... add all other variables ...

source ~/.bashrc
python3 k.py
```

### Method 3: .env File (Recommended)
```bash
cd /workspace/kk

# Create .env file
nano .env

# Add variables (without 'export'):
BOT_TOKEN=your_token_here
DEEPSEEK_API_KEY=your_key_here
SUPADATA_API_KEY=your_key_here
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_ANON_KEY=eyJhbGci...
YOUTUBE_API_KEY=AIzaSy...
CHAT_ID=447705580
IMAGE_SHORTS_CHAT_ID=-1002343932866
IMAGE_LONG_CHAT_ID=-1002498893774
GDRIVE_FOLDER_LONG=1y-Af4T5pAvgqV2gyvN9zhSPdvZzUcFyi
GDRIVE_FOLDER_SHORT=1JdJCYDXLWjAz1091zs_Pnev3FuK3Ftex

# Save and run
python3 k.py
```

---

## Verify Setup

After setting environment variables, verify with:
```bash
echo $BOT_TOKEN
echo $DEEPSEEK_API_KEY
echo $SUPABASE_URL
```

If empty, variables are not set correctly.

---

## Security Notes

- ✅ **DO NOT** commit `.env` file to Git (already in `.gitignore`)
- ✅ **DO NOT** share API keys publicly
- ✅ Use different keys for development and production
- ✅ Rotate keys periodically for security

---

## Troubleshooting

**Error: `BOT_TOKEN environment variable is required`**
- Solution: Set `BOT_TOKEN` via `export` or `.env` file

**Error: `Supabase not connected`**
- Check `SUPABASE_URL` and `SUPABASE_ANON_KEY` are set correctly
- Verify URL format: `https://xxxxx.supabase.co`

**Error: `No YouTube API key found`**
- Set `YOUTUBE_API_KEY` via environment or use `/set_youtube_key` command in Telegram
