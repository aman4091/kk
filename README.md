# 🤖 F5-TTS YouTube Channel Automation Bot

Complete Telegram bot for automated YouTube channel processing with F5-TTS voice generation, Supabase database integration, and multi-chat support.

## ✨ Features

### 🎯 Core Features
- **YouTube Channel Processing**: Automatically fetch top 6 videos (>10 min, sorted by views)
- **Smart Transcript Extraction**: Supadata API with automatic key rotation
- **AI Processing**: 7000-char chunking with DeepSeek API
- **Voice Generation**: F5-TTS for high-quality audio
- **Multi-Chat Support**: Aman & Anu chats configured
- **Global File Naming**: Sequential counter (1_raw.wav, 2_raw.wav, etc.)
- **15-Day Cooldown**: Videos won't repeat for 15 days
- **Database Persistence**: Supabase integration for all data

### 🔑 API Key Management
- Multiple Supadata keys with auto-rotation
- YouTube Data API v3 integration
- DeepSeek API for text processing
- All keys stored in Supabase database

---

## 🚀 Quick Start (Vast.ai)

### Step 1: Clone Repository

```bash
cd /workspace
git clone https://github.com/aman4091/kk.git
cd kk
```

### Step 2: Run Setup Script

```bash
python3 k.py
```

**That's it!** The script will:
- ✅ Auto-detect it's running in `/workspace/kk/`
- ✅ Install all dependencies (including new ones: supabase, httpx, isodate)
- ✅ Create `f5-automation/` directory
- ✅ Clone and setup F5-TTS
- ✅ Start the bot

---

## 📋 Setup Instructions

### 1. Create Supabase Project

1. Go to https://supabase.com
2. Create new project
3. Copy Project URL and Anon Key
4. In SQL Editor, run this schema:

```sql
-- API Keys Table
CREATE TABLE IF NOT EXISTS api_keys (
    id BIGSERIAL PRIMARY KEY,
    key_type TEXT NOT NULL CHECK (key_type IN ('youtube', 'supadata', 'deepseek')),
    api_key TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used TIMESTAMPTZ DEFAULT NOW(),
    usage_count INTEGER DEFAULT 0
);

-- YouTube Channels Table
CREATE TABLE IF NOT EXISTS youtube_channels (
    id BIGSERIAL PRIMARY KEY,
    channel_url TEXT NOT NULL UNIQUE,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    videos_json JSONB,
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

-- Processed Videos Table
CREATE TABLE IF NOT EXISTS processed_videos (
    id BIGSERIAL PRIMARY KEY,
    video_id TEXT NOT NULL,
    video_url TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    processed_date TIMESTAMPTZ DEFAULT NOW(),
    chat_id TEXT NOT NULL,
    audio_counter INTEGER
);

CREATE INDEX IF NOT EXISTS idx_processed_videos_date
ON processed_videos (video_id, processed_date DESC);

-- Prompts Table
CREATE TABLE IF NOT EXISTS prompts (
    id BIGSERIAL PRIMARY KEY,
    prompt_type TEXT NOT NULL CHECK (prompt_type IN ('deepseek', 'youtube', 'channel')),
    prompt_text TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chat Configs Table
CREATE TABLE IF NOT EXISTS chat_configs (
    id BIGSERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL UNIQUE,
    chat_name TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Global Counter Table
CREATE TABLE IF NOT EXISTS global_counter (
    id INTEGER PRIMARY KEY DEFAULT 1,
    counter INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CHECK (id = 1)
);

INSERT INTO global_counter (id, counter) VALUES (1, 0)
ON CONFLICT (id) DO NOTHING;
```

### 2. Configure Bot via Telegram

Send these commands to your bot:

```
/set_supabase_url https://your-project.supabase.co
/set_supabase_key eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

/set_youtube_key AIzaSyBxxxxxxxxxxxxxx
/add_supadata_key sd_xxxxxxxxxx
/add_supadata_key sd_yyyyyyyyyy  (add multiple for rotation!)
/set_deepseek_key sk-xxxxxxxxxx

/set_channel_prompt Rewrite this content into engaging storytelling format

/list_keys  (check status)
```

### 3. Process YouTube Channel

Simply send a channel URL:
```
https://youtube.com/@examplechannel
```

Bot will automatically:
1. Detect it's a channel (not a video)
2. Fetch top 1000 videos (>10 min)
3. Select 6 unique videos (not processed in last 15 days)
4. Process each video → Generate audio → Upload to Gofile
5. Send all 12 audio links (6 videos × 2 variants)

---

## 📁 Project Structure

```
kk/
├── final_working_bot.py          # Main bot (modified)
├── k.py                          # Setup script (works in /workspace/kk/)
├── auto_setup_and_run_bot.py     # Alternative setup (works in /workspace/kk/)
│
├── supabase_client.py            # Database operations
├── transcribe_helper.py          # Supadata API integration
├── youtube_processor.py          # YouTube channel processing
│
├── requirements_new.txt          # New dependencies
├── .gitignore                    # Git ignore rules
├── README.md                     # This file
└── IMPLEMENTATION_COMPLETE.md    # Detailed implementation docs

After running k.py:
kk/
└── f5-automation/
    ├── F5-TTS/                   # Cloned F5-TTS repo
    ├── chunks/                   # Video processing chunks
    ├── input/
    ├── output/                   # Generated audio files
    ├── processed/
    ├── reference/
    ├── prompts/
    └── scripts/
```

---

## 🎯 Usage Examples

### YouTube Channel Processing
```
User: https://youtube.com/@TEDx

Bot: 📺 YouTube Channel Detected!
     🔍 Fetching top videos...
     ✅ Found 1000 videos (>10 min)
     🎯 Selecting 6 unique videos...

     📹 Video 1/6: "Amazing Talk"
     🔄 Processing transcript...
     ✅ Transcript: 45,230 chars
     🤖 Processing chunks: 1/7, 2/7, 3/7...
     🎵 Generating audio...

     🔗 1_raw.wav (28 MB)
     https://gofile.io/...

     🔗 1_enhanced.wav (32 MB)
     https://gofile.io/...

     [Repeat for videos 2-6]
```

### YouTube Video (Reference Audio)
```
User: https://youtube.com/watch?v=xxxxx

Bot: 🔗 YouTube video detected!
     🎵 Processing as Reference Audio...
     📥 Extracting audio → Cropping to 30s
     ✅ Reference audio updated!
```

---

## 🔧 Advanced Configuration

### Environment Variables (Optional)
These are auto-set, but you can override:

```bash
export DEEPSEEK_API_KEY="sk-xxxxx"
export SUPADATA_API_KEY="sd-xxxxx"
export SUPABASE_URL="https://xxxxx.supabase.co"
export SUPABASE_ANON_KEY="eyJhbGciOiJ..."
```

### Custom Prompts
```
/set_channel_prompt Transform this transcript into a captivating story with dramatic pauses and engaging narration
```

---

## 🐛 Troubleshooting

### Issue: "git clone" folder different from previous setup

**Old Setup**:
```
/workspace/
├── final_working_bot.py
├── k.py
└── auto_setup_and_run_bot.py
```

**New Setup** (after git clone):
```
/workspace/kk/
├── final_working_bot.py
├── k.py
└── auto_setup_and_run_bot.py
```

**Solution**: ✅ **Already handled!**

Both `k.py` and `auto_setup_and_run_bot.py` now use:
```python
script_dir = os.path.dirname(os.path.abspath(__file__))
```

This means they work from **any directory**:
- ✅ `/workspace/` (old way)
- ✅ `/workspace/kk/` (git clone way)
- ✅ `/home/user/mybot/` (custom location)

### Issue: Dependencies not installing

**Solution**:
```bash
cd /workspace/kk
pip install -r requirements_new.txt
# Or manually:
pip install supabase httpx isodate google-api-python-client
```

### Issue: Bot can't find files after git clone

**Solution**: Just run from the cloned directory:
```bash
cd /workspace/kk
python3 k.py
```

The scripts automatically detect their location and create `f5-automation/` in the same directory.

---

## 📊 File Naming Convention

Global counter persists in Supabase:

```
Video 1: 1_raw.wav, 1_enhanced.wav
Video 2: 2_raw.wav, 2_enhanced.wav
Video 3: 3_raw.wav, 3_enhanced.wav
...
Video 6: 6_raw.wav, 6_enhanced.wav
```

Next run continues from counter = 7.

---

## 🔒 Security Notes

### Files NOT pushed to Git (via .gitignore):
- ❌ `output/`, `processed/`, `reference/` directories
- ❌ `*.wav`, `*.mp3` audio files
- ❌ `bot_config.json` (contains credentials)
- ❌ `F5-TTS/` (cloned separately)
- ❌ `__pycache__/`, `*.pyc`

### Credentials Storage:
- API keys stored in Supabase (encrypted at rest)
- Bot token in code (consider environment variable)
- Use `.env` file for local development

---

## 🎊 Credits

- **F5-TTS**: https://github.com/SWivid/F5-TTS
- **Supabase**: https://supabase.com
- **YouTube Data API**: https://developers.google.com/youtube/v3
- **Supadata API**: https://supadata.ai

---

## 📞 Support

For issues or questions:
1. Check `IMPLEMENTATION_COMPLETE.md` for detailed docs
2. Review troubleshooting section above
3. Check bot logs for error messages
4. Verify all API keys: `/list_keys`

---

## 🚀 Quick Command Reference

```bash
# Clone and setup
git clone https://github.com/aman4091/kk.git
cd kk
python3 k.py

# Telegram commands
/set_supabase_url <url>
/set_supabase_key <key>
/set_youtube_key <key>
/add_supadata_key <key>
/set_deepseek_key <key>
/set_channel_prompt <text>
/list_keys
/settings

# Usage
Send: https://youtube.com/@channel  (process 6 videos)
Send: https://youtube.com/watch?v=xxx  (reference audio)
Send: <text script>  (generate audio)
```

---

**Status**: ✅ Production Ready
**Last Updated**: 2025-01-28
**Version**: 2.0 (YouTube Channel Automation)

🎉 **Happy Processing!** 🎉
