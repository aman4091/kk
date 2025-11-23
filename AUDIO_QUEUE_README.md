# Audio Queue System - Complete Documentation

## 📋 Table of Contents
- [Overview](#overview)
- [Problem Statement](#problem-statement)
- [Solution Architecture](#solution-architecture)
- [File Structure](#file-structure)
- [Database Schema](#database-schema)
- [Deployment Guide](#deployment-guide)
- [How It Works](#how-it-works)
- [Environment Variables](#environment-variables)
- [Troubleshooting](#troubleshooting)

---

## 🎯 Overview

**Audio Queue System** separates audio generation from the Telegram bot to enable:
- **Contabo Server**: Runs lightweight bot (no GPU/F5-TTS needed)
- **Vast.ai Worker**: Handles heavy GPU-based audio generation
- **Supabase Queue**: Coordinates work between bot and worker

### Key Benefits
✅ **Minimal Code Changes** - Existing code paths preserved, no breaking changes
✅ **Resource Optimization** - No GPU needed on Contabo, saves cost
✅ **Scalability** - Add more workers to handle load
✅ **Async Processing** - Users don't wait for audio generation
✅ **Automatic Notifications** - Users notified when audio is ready
✅ **Zero Video Pipeline Disruption** - Video worker continues unchanged

---

## 🔥 Problem Statement

### Before Audio Queue System:

**Setup:**
```
Contabo Server (24/7 bot)
├── Telegram Bot (final_working_bot.py)
├── F5-TTS Model (requires GPU - EXPENSIVE!)
├── Video Worker (local_video_worker.py)
└── Audio Generation (blocking, slow on CPU)
```

**Issues:**
1. ❌ **Expensive**: Contabo needs GPU or slow CPU-based generation
2. ❌ **Blocking**: User waits minutes for audio generation
3. ❌ **Resource Waste**: GPU idle when no audio generation
4. ❌ **No Scalability**: Can't add more workers easily

### After Audio Queue System:

**Setup:**
```
Contabo Server (24/7, lightweight)
├── Telegram Bot (final_working_bot.py)
│   ├── Receives scripts
│   ├── Queues audio jobs in Supabase
│   └── No F5-TTS needed!
└── Video Worker (local_video_worker.py)
    └── Processes videos as before

Vast.ai Worker (on-demand, GPU)
├── Audio Worker (audio_worker.py)
│   ├── Polls Supabase queue
│   ├── Generates audio with F5-TTS
│   ├── Uploads to Google Drive
│   └── Notifies user via Telegram
└── Auto-shutdown when idle
```

**Benefits:**
1. ✅ **Cost Effective**: Vast.ai GPU only when needed
2. ✅ **Non-Blocking**: Bot queues and continues immediately
3. ✅ **Resource Efficient**: Workers scale based on load
4. ✅ **Scalable**: Add multiple Vast.ai workers if needed

---

## 🏗️ Solution Architecture

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER WORKFLOW                            │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                   User sends script via Telegram
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CONTABO SERVER (24/7)                         │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  final_working_bot.py (Telegram Bot)                       │ │
│  │  ├── Receives script                                       │ │
│  │  ├── Calls: generate_audio_f5()                            │ │
│  │  │    └─► Redirects to: audio_queue_manager.create_job()  │ │
│  │  └── Returns: "✅ Audio job queued: abc123..."            │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                │                                 │
│                                ▼                                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  audio_queue_manager.py                                    │ │
│  │  ├── Creates job in Supabase                               │ │
│  │  ├── Stores: script, chat_id, metadata                     │ │
│  │  └── Returns: job_id                                       │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    SUPABASE (Queue Database)                     │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  audio_jobs table                                          │ │
│  │  ├── job_id: "abc123..."                                   │ │
│  │  ├── status: "pending"                                     │ │
│  │  ├── script_text: "..."                                    │ │
│  │  ├── chat_id: "-1002343932866"                             │ │
│  │  ├── channel_code: "BI" (if daily video)                   │ │
│  │  ├── audio_counter: 42                                     │ │
│  │  └── priority: 0                                           │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  audio_workers table                                       │ │
│  │  ├── worker_id: "vastai_12345"                             │ │
│  │  ├── status: "online"                                      │ │
│  │  ├── last_heartbeat: "2025-01-23 12:00:00"                 │ │
│  │  ├── jobs_completed: 42                                    │ │
│  │  └── vastai_instance_id: "12345"                           │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼ (Polls every 30s)
┌─────────────────────────────────────────────────────────────────┐
│                    VAST.AI WORKER (GPU, On-Demand)               │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  audio_worker.py                                           │ │
│  │  1. Polls Supabase for pending jobs                        │ │
│  │  2. Claims job atomically (status: pending → processing)   │ │
│  │  3. Downloads reference audio from GDrive (if needed)      │ │
│  │  4. Generates audio with F5-TTS:                           │ │
│  │     ├── Splits script into chunks (500 chars)              │ │
│  │     ├── Generates audio per chunk                          │ │
│  │     └── Concatenates segments                              │ │
│  │  5. Uploads audio to Google Drive                          │ │
│  │  6. Updates daily_video_tracking (if daily video)          │ │
│  │  7. Sends Telegram notification to user                    │ │
│  │  8. Marks job completed                                    │ │
│  │  9. Cleans up temp files                                   │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                   User receives Telegram notification:
                   "✅ Audio generation complete!
                    Video will be generated automatically."
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CONTABO SERVER (Video Worker)                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  local_video_worker.py (Already Running)                   │ │
│  │  ├── Detects new audio in daily_video_tracking             │ │
│  │  ├── Downloads audio + image from GDrive                   │ │
│  │  ├── Generates video with FFmpeg                           │ │
│  │  ├── Uploads to GDrive + Gofile                            │ │
│  │  └── Notifies user: "✅ Video ready!"                      │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                   User receives final video link
```

---

## 📁 File Structure

### New Files Created

#### 1. **audio_queue_manager.py** (Bot Side - Contabo)
**Purpose**: Queue management on bot side
**Location**: Runs on Contabo with `final_working_bot.py`
**Key Functions**:
- `create_audio_job()` - Creates new job in queue
- `_get_current_reference_audio_id()` - Gets reference audio from DB
- `sync_reference_audio_to_gdrive()` - Uploads reference audio to GDrive
- `get_job_status()` - Checks job status
- `get_pending_jobs_count()` - Returns pending jobs count

**Usage Example**:
```python
# In bot code
success, job_id = await self.audio_queue_manager.create_audio_job(
    script_text="This is the script to convert to audio",
    chat_id=-1002343932866,
    channel_code="BI",  # For daily videos
    video_number=1,
    priority=0
)
```

#### 2. **audio_worker.py** (Worker Side - Vast.ai)
**Purpose**: Audio generation worker
**Location**: Runs on Vast.ai GPU instance
**Key Functions**:
- `register_worker()` - Registers worker in DB
- `send_heartbeat()` - Updates worker status
- `get_pending_job()` - Fetches and claims jobs atomically
- `sync_reference_audio()` - Downloads reference audio from GDrive
- `generate_audio_f5()` - Generates audio with F5-TTS
- `upload_audio_to_gdrive()` - Uploads to GDrive
- `update_daily_video_tracking()` - Updates tracking table
- `send_telegram_notification()` - Notifies user
- `process_job()` - Main job processing pipeline

**Main Loop**:
```python
while True:
    # 1. Send heartbeat every N polls
    send_heartbeat()

    # 2. Get pending job (atomic claim)
    job = get_pending_job()

    if job:
        # 3. Process job
        await process_job(job)
    else:
        # 4. Sleep before next poll
        await asyncio.sleep(30)
```

#### 3. **supabase_audio_queue_schema.sql**
**Purpose**: Database schema for queue system
**Creates**:
- `audio_jobs` table - Queue of audio generation tasks
- `audio_workers` table - Registry of active workers
- `reference_audio_sync` table - Reference audio tracking
- Indexes for efficient querying
- Foreign key constraints
- Functions: `get_pending_audio_jobs()`, `cleanup_old_audio_jobs()`
- Trigger: Auto-mark old reference audios as not current

**Key Tables**:

**audio_jobs**:
```sql
job_id TEXT PRIMARY KEY
chat_id TEXT NOT NULL
status TEXT (pending/processing/completed/failed)
script_text TEXT NOT NULL
channel_code TEXT (BI, AFG, JIMMY, GYH, ANU, JM)
video_number INTEGER (1-4)
date DATE
audio_counter INTEGER
reference_audio_gdrive_id TEXT
audio_gdrive_id TEXT (output)
priority INTEGER DEFAULT 0
retry_count INTEGER DEFAULT 0
error_message TEXT
created_at TIMESTAMPTZ
processing_started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ
worker_id TEXT
```

**audio_workers**:
```sql
worker_id TEXT PRIMARY KEY
hostname TEXT NOT NULL
gpu_model TEXT
status TEXT (online/offline/busy)
last_heartbeat TIMESTAMPTZ
jobs_completed INTEGER
jobs_failed INTEGER
vastai_instance_id TEXT
avg_processing_time_seconds REAL
```

#### 4. **supabase_audio_queue_DROP.sql**
**Purpose**: Cleanup script to drop old tables
**Usage**: Run this FIRST if tables already exist, then run schema
**Drops**:
- Foreign key constraints
- Tables: audio_jobs, audio_workers, reference_audio_sync
- Functions and triggers

### Modified Files

#### 1. **final_working_bot.py** (MAIN CHANGES)

**Changes Made**:

##### A. Imports
```python
# Added
from audio_queue_manager import AudioQueueManager

# Commented out (not needed on Contabo)
# import torch
```

##### B. F5-TTS Initialization (Line ~1735)
```python
def init_f5_tts(self):
    """F5-TTS model initialize - DISABLED (using audio queue now)"""
    try:
        print("ℹ️  F5-TTS disabled on Contabo - using audio queue worker on Vastai")
        self.f5_model = None
        # F5-TTS will run on Vastai worker, not on this bot
        # from f5_tts.api import F5TTS
        # self.f5_model = F5TTS()
        print("✅ Audio queue mode enabled")
```

##### C. AudioQueueManager Initialization (Line ~200)
```python
# Initialize Audio Queue Manager
self.audio_queue_manager = None
try:
    if self.gdrive_manager is None:
        self.gdrive_manager = GDriveImageManager()
    if self.gdrive_manager and self.supabase.is_connected():
        self.audio_queue_manager = AudioQueueManager(self.supabase, self.gdrive_manager)
        print(f"✅ Audio queue manager initialized")
except Exception as e:
    print(f"⚠️ Audio queue manager initialization failed: {e}")
```

##### D. generate_audio_f5() Function (Line ~6323) - **MOST CRITICAL CHANGE**
```python
async def generate_audio_f5(self, script_text, chat_id=None, input_filename=None,
                           channel_shortform=None, audio_counter=None):
    """REDIRECTED TO AUDIO QUEUE - Audio generation now happens on Vastai worker"""
    try:
        print(f"🎙️  Audio queue mode - creating job...")
        print(f"📝 Script length: {len(script_text)} characters")

        # Create audio job in queue instead of generating locally
        success, job_id = await self.audio_queue_manager.create_audio_job(
            script_text=script_text,
            chat_id=chat_id,
            audio_counter=audio_counter,
            channel_shortform=channel_shortform,
            priority=0
        )

        if success:
            print(f"✅ Audio job queued: {job_id[:12]}...")
            # Return success but no local files (will be generated by worker)
            return True, f"queued:{job_id}"
        else:
            print(f"❌ Failed to queue audio job")
            return False, "Failed to create audio job in queue"

    except Exception as e:
        error_msg = f"Audio queue error: {str(e)}"
        print(f"❌ {error_msg}")
        return False, error_msg
```

**Original function renamed to**: `generate_audio_f5_LOCAL_DISABLED()` (preserved for reference)

##### E. Main Function Check (Line ~7864)
```python
# F5-TTS check disabled - we use audio queue now
# if not bot_instance.f5_model:
#     print("❌ F5-TTS initialization failed! Check installation.")
#     return

if bot_instance.f5_model:
    print("✅ Bot fully initialized with F5-TTS!")
else:
    print("✅ Bot fully initialized in QUEUE MODE (F5-TTS on Vastai worker)!")

# Check if audio queue manager is available
if not bot_instance.audio_queue_manager:
    print("⚠️  Audio queue manager not initialized - audio generation will fail!")
    print("   Make sure SUPABASE credentials are set in .env")
```

**Impact**: All existing calls to `generate_audio_f5()` now automatically use the queue without any code changes! This includes:
- YouTube transcript processing (line ~633)
- Channel-specific audio generation (line ~3055)
- Inline keyboard script selection (line ~5153)
- Script file processing from queue (line ~6105)
- Google Drive channel batch processing (line ~7012)

#### 2. **p.py** (Vast.ai Setup Script)

**Changes Made**:

##### Line 18: Documentation Update
```python
# Changed from:
9. ✅ Bot run karegi (final_working_bot.py)

# To:
9. ✅ Audio Worker run karegi (audio_worker.py) - processes audio queue from Vastai
```

##### Line 32: Usage Notes
```python
# Changed from:
- No need for k.py, auto_setup_and_run_bot.py, or final_working_bot.py upload!

# To:
- No need for k.py, auto_setup_and_run_bot.py, or other files - just p.py and audio_worker.py!
```

##### Line 458: Worker File Selection
```python
# Changed from:
bot_file = os.path.join(project_dir, "final_working_bot.py")

# To:
bot_file = os.path.join(project_dir, "audio_worker.py")
```

**Impact**: p.py now runs `audio_worker.py` instead of `final_working_bot.py` on Vast.ai

---

## 🗄️ Database Schema

### Tables Created in Supabase

#### 1. audio_jobs
**Purpose**: Queue of audio generation tasks

| Column | Type | Description |
|--------|------|-------------|
| job_id | TEXT (PK) | Unique job identifier (UUID) |
| chat_id | TEXT | Telegram chat ID for notifications |
| status | TEXT | pending, processing, completed, failed |
| script_text | TEXT | Full script to convert to audio |
| script_gdrive_id | TEXT | Optional GDrive script ID |
| channel_code | TEXT | BI, AFG, JIMMY, GYH, ANU, JM (daily videos) |
| video_number | INTEGER | 1-4 (daily videos) |
| date | DATE | Date for daily video tracking |
| audio_counter | INTEGER | Sequential counter for naming |
| channel_shortform | TEXT | Short channel name for batch |
| reference_audio_gdrive_id | TEXT | Reference audio to use |
| audio_gdrive_id | TEXT | Generated audio file ID (output) |
| gofile_link | TEXT | Optional Gofile link |
| created_at | TIMESTAMPTZ | Job creation time |
| processing_started_at | TIMESTAMPTZ | When worker claimed job |
| completed_at | TIMESTAMPTZ | When job finished |
| worker_id | TEXT | Which worker processed it |
| retry_count | INTEGER | Number of retries |
| error_message | TEXT | Error details if failed |
| priority | INTEGER | Higher = processed first |

**Indexes**:
- `idx_audio_jobs_status` - Fast status filtering
- `idx_audio_jobs_priority` - Priority-based ordering
- `idx_audio_jobs_chat_id` - Find jobs by user
- `idx_audio_jobs_date_channel` - Daily video lookup

#### 2. audio_workers
**Purpose**: Registry of active audio workers

| Column | Type | Description |
|--------|------|-------------|
| worker_id | TEXT (PK) | Unique worker identifier |
| hostname | TEXT | Server hostname |
| gpu_model | TEXT | GPU type (e.g., "RTX 4090") |
| status | TEXT | online, offline, busy |
| last_heartbeat | TIMESTAMPTZ | Last ping time |
| jobs_completed | INTEGER | Total completed jobs |
| jobs_failed | INTEGER | Total failed jobs |
| vastai_instance_id | TEXT | Vast.ai instance ID |
| avg_processing_time_seconds | REAL | Average job duration |
| current_job_id | TEXT | Currently processing job |
| created_at | TIMESTAMPTZ | Worker registration time |

**Indexes**:
- `idx_audio_workers_status` - Find online workers
- `idx_audio_workers_heartbeat` - Detect dead workers

#### 3. reference_audio_sync
**Purpose**: Tracks reference audio files synced to GDrive

| Column | Type | Description |
|--------|------|-------------|
| id | SERIAL (PK) | Auto-increment ID |
| gdrive_id | TEXT (UNIQUE) | Google Drive file ID |
| local_path | TEXT | Local file path |
| last_modified | TIMESTAMPTZ | Last update time |
| file_size_bytes | BIGINT | File size |
| uploaded_at | TIMESTAMPTZ | Upload timestamp |
| last_synced_at | TIMESTAMPTZ | Last sync time |
| is_current | BOOLEAN | Is this the active reference? |
| created_by | TEXT | Chat ID that uploaded |
| checksum | TEXT | SHA256 hash for integrity |

**Trigger**: Auto-marks old references as `is_current = FALSE` when new one is set

---

## 🚀 Deployment Guide

### Prerequisites

1. **Supabase Database**:
   - URL and anon key configured in `.env`
   - Tables created using schema

2. **Google Drive**:
   - Service account credentials (`token.pickle`)
   - Folder IDs for audio/video storage

3. **Telegram Bot**:
   - Bot token from @BotFather

### Step 1: Setup Supabase

```bash
# In Supabase SQL Editor:

# 1. Drop old tables (if exist)
# Run: supabase_audio_queue_DROP.sql

# 2. Create fresh schema
# Run: supabase_audio_queue_schema.sql

# 3. Verify tables created
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name LIKE 'audio_%';

# Should show:
# - audio_jobs
# - audio_workers
# - reference_audio_sync
```

### Step 2: Configure Environment Variables

**On Contabo (Bot)**:
```bash
# .env file
BOT_TOKEN=your_telegram_bot_token
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key

# Google Drive folders
GDRIVE_REFERENCE_AUDIO_FOLDER=folder_id_for_reference_audio
GDRIVE_VIDEO_OUTPUT_FOLDER=folder_id_for_audio_output
DAILY_VIDEO_PARENT_FOLDER=1ZKnCa-7ieNt3bLhI6f6mCZBmyAP0-dnF

# Other required vars
DEEPSEEK_API_KEY=your_key
GEMINI_API_KEY=your_key
```

**On Vast.ai (Worker)**:
```bash
# Add same vars to p.py or set in Vast.ai environment
BOT_TOKEN=your_telegram_bot_token
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_key
GDRIVE_REFERENCE_AUDIO_FOLDER=folder_id
GDRIVE_VIDEO_OUTPUT_FOLDER=folder_id
```

### Step 3: Deploy Contabo Bot

```bash
# On Contabo server
cd /path/to/project
git pull origin master

# Install dependencies (if not already)
pip install -r requirements.txt

# Run bot
python3 final_working_bot.py

# Expected output:
# ✅ Bot fully initialized in QUEUE MODE (F5-TTS on Vastai worker)!
# ✅ Audio queue manager initialized
```

### Step 4: Deploy Vast.ai Worker

```bash
# 1. Create Vast.ai instance with GPU (RTX 3090/4090 recommended)

# 2. Upload p.py to instance via Jupyter

# 3. Run setup script
python3 p.py

# This will:
# ✅ Clone repository from GitHub
# ✅ Install F5-TTS
# ✅ Setup Google Drive credentials
# ✅ Run audio_worker.py automatically

# Expected output:
# 🚀 Audio Worker Starting
# ✅ Worker registered in database
# 🔍 Checking for pending jobs...
```

### Step 5: Test the System

```bash
# 1. Send a script to Telegram bot

# 2. Bot should respond:
# "✅ Audio job queued: abc123..."
# "Worker will process and notify you when ready."

# 3. Check Supabase audio_jobs table:
SELECT job_id, status, created_at FROM audio_jobs ORDER BY created_at DESC LIMIT 5;

# 4. Worker should claim and process job (watch logs)

# 5. User receives notification:
# "✅ Audio generation complete!
#  Video will be generated automatically."

# 6. Video worker processes video automatically
```

---

## ⚙️ How It Works

### Workflow Step-by-Step

#### Phase 1: User Sends Script

```
User → Telegram → Bot receives script
                   ↓
                   generate_audio_f5() called
                   ↓
                   audio_queue_manager.create_audio_job()
                   ↓
                   Supabase: INSERT INTO audio_jobs
                   ↓
                   Bot responds: "✅ Queued: abc123..."
```

#### Phase 2: Worker Processes Queue

```
Audio Worker (Vast.ai) polls every 30s
    ↓
    SELECT * FROM audio_jobs WHERE status='pending' LIMIT 1
    ↓
    Found job? → Atomic claim:
                 UPDATE audio_jobs SET status='processing', worker_id='vastai_123'
                 WHERE job_id='abc123' AND status='pending'
    ↓
    Download reference audio from GDrive (if needed)
    ↓
    Generate audio with F5-TTS:
        1. Split script into 500-char chunks
        2. Generate audio per chunk
        3. Concatenate segments
        4. Save as WAV file
    ↓
    Upload audio to GDrive (organized folder)
    ↓
    Update daily_video_tracking table:
        SET audio_gdrive_id='gdrive_audio_id', status='audio_done'
    ↓
    Send Telegram notification to user
    ↓
    UPDATE audio_jobs SET status='completed', audio_gdrive_id='...'
    ↓
    Cleanup temp files
```

#### Phase 3: Video Worker Takes Over (Automatic)

```
Video Worker (already running on Contabo)
    ↓
    Polls daily_video_tracking table
    ↓
    Finds: status='audio_done' (new audio available)
    ↓
    Claims video job
    ↓
    Downloads audio + image from GDrive
    ↓
    Generates video with FFmpeg
    ↓
    Uploads to GDrive + Gofile
    ↓
    Notifies user: "✅ Video ready!"
```

### Atomic Job Claiming (Race Condition Prevention)

```sql
-- Multiple workers can run simultaneously without conflicts

-- Worker 1 and Worker 2 both find same pending job:
SELECT * FROM audio_jobs WHERE status='pending' LIMIT 1;
-- Both see: job_id='abc123'

-- Worker 1 tries to claim:
UPDATE audio_jobs
SET status='processing', worker_id='worker1'
WHERE job_id='abc123' AND status='pending';
-- ✅ SUCCESS - 1 row updated

-- Worker 2 tries to claim (milliseconds later):
UPDATE audio_jobs
SET status='processing', worker_id='worker2'
WHERE job_id='abc123' AND status='pending';
-- ❌ FAIL - 0 rows updated (status is now 'processing')

-- Worker 2 moves to next job or waits for next poll
```

### Error Handling & Retries

```python
# In audio_worker.py:

try:
    # Process job
    await process_job(job)
except Exception as e:
    # Mark as failed
    retry_count = job.get('retry_count', 0) + 1

    if retry_count >= 3:
        # Permanent failure
        status = 'failed'
        error_msg = f"Failed after 3 retries: {str(e)}"
    else:
        # Retry
        status = 'pending'
        error_msg = f"Retry {retry_count}/3: {str(e)}"

    # Update database
    supabase.update('audio_jobs', {
        'status': status,
        'error_message': error_msg,
        'retry_count': retry_count
    })

    # Notify user of failure
    await send_telegram_notification(chat_id, error_msg)
```

---

## 🔧 Environment Variables

### Required Variables

| Variable | Where | Description |
|----------|-------|-------------|
| `BOT_TOKEN` | Both | Telegram bot token from @BotFather |
| `SUPABASE_URL` | Both | Supabase project URL |
| `SUPABASE_ANON_KEY` | Both | Supabase anonymous key |
| `GDRIVE_REFERENCE_AUDIO_FOLDER` | Both | GDrive folder for reference audio |
| `GDRIVE_VIDEO_OUTPUT_FOLDER` | Both | GDrive folder for audio output |
| `DAILY_VIDEO_PARENT_FOLDER` | Both | Parent folder for organized videos |

### Optional Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CHUNK_SIZE` | 500 | Audio generation chunk size (chars) |
| `AUDIO_SPEED` | 1.0 | Audio playback speed |
| `WORKER_ID` | Auto | Custom worker identifier |
| `POLL_INTERVAL` | 30 | Seconds between queue checks |

---

## 🐛 Troubleshooting

### Bot Issues

#### "Audio queue manager not initialized"
```bash
# Check Supabase credentials
echo $SUPABASE_URL
echo $SUPABASE_ANON_KEY

# Verify Supabase connection
python3 -c "from supabase_client import SupabaseClient; c = SupabaseClient(); print(c.is_connected())"
```

#### "F5-TTS initialization failed"
```bash
# This is EXPECTED on Contabo - ignore it
# Bot should show: "✅ Bot fully initialized in QUEUE MODE"
```

### Worker Issues

#### "No pending jobs found"
```bash
# Check if bot is actually creating jobs
# In Supabase SQL Editor:
SELECT * FROM audio_jobs ORDER BY created_at DESC LIMIT 5;

# Should see jobs with status='pending'
```

#### "Failed to download reference audio"
```bash
# Check GDrive folder ID
echo $GDRIVE_REFERENCE_AUDIO_FOLDER

# Verify folder exists and credentials work
python3 -c "from gdrive_manager import GDriveImageManager; g = GDriveImageManager(); print('✅ GDrive OK')"
```

#### Worker not showing in database
```bash
# Check audio_workers table
SELECT * FROM audio_workers;

# Should see worker registered with last_heartbeat updating
```

### Database Issues

#### Tables don't exist
```bash
# Drop and recreate
# Run: supabase_audio_queue_DROP.sql
# Then: supabase_audio_queue_schema.sql
```

#### Foreign key constraint errors
```bash
# Make sure you dropped old tables first!
# The schema creates tables WITHOUT foreign keys first,
# then adds them later to avoid circular dependencies
```

---

## 📊 Monitoring

### Check Queue Status
```sql
-- Pending jobs
SELECT COUNT(*) as pending FROM audio_jobs WHERE status='pending';

-- Processing jobs
SELECT COUNT(*) as processing FROM audio_jobs WHERE status='processing';

-- Completed jobs (last 24h)
SELECT COUNT(*) as completed FROM audio_jobs
WHERE status='completed'
AND completed_at > NOW() - INTERVAL '24 hours';

-- Failed jobs
SELECT job_id, error_message, retry_count FROM audio_jobs
WHERE status='failed'
ORDER BY created_at DESC;
```

### Check Worker Health
```sql
-- Active workers
SELECT worker_id, hostname, gpu_model, status, last_heartbeat
FROM audio_workers
WHERE status='online'
AND last_heartbeat > NOW() - INTERVAL '5 minutes';

-- Worker statistics
SELECT
    worker_id,
    jobs_completed,
    jobs_failed,
    ROUND(avg_processing_time_seconds, 2) as avg_time_sec
FROM audio_workers
ORDER BY jobs_completed DESC;
```

### Check Performance
```sql
-- Average processing time per job
SELECT
    AVG(EXTRACT(EPOCH FROM (completed_at - processing_started_at))) as avg_seconds
FROM audio_jobs
WHERE status='completed'
AND completed_at > NOW() - INTERVAL '24 hours';

-- Jobs by status (last 7 days)
SELECT
    status,
    COUNT(*) as count
FROM audio_jobs
WHERE created_at > NOW() - INTERVAL '7 days'
GROUP BY status;
```

---

## 🎓 Key Concepts

### Why Queue-Based Architecture?

**Traditional Approach** (Blocking):
```python
# User sends script
script = "This is a long script..."

# Bot generates audio (blocks for 2-5 minutes!)
audio = generate_audio_f5(script)  # User waits...

# Bot sends audio
send_audio(audio)
```

**Queue-Based Approach** (Non-Blocking):
```python
# User sends script
script = "This is a long script..."

# Bot queues job (instant!)
job_id = queue_audio_job(script)  # Returns immediately

# Bot responds
send_message(f"✅ Queued: {job_id}")  # User continues using bot

# Worker processes in background (2-5 minutes later)
# User gets notification when done
```

### Why Separate Bot and Worker?

| Aspect | Combined (Old) | Separated (New) |
|--------|---------------|-----------------|
| **GPU Requirement** | Always needed | Only worker |
| **Cost** | High (24/7 GPU) | Low (on-demand GPU) |
| **Scalability** | Limited | Add more workers |
| **User Experience** | Blocking | Non-blocking |
| **Resource Usage** | Inefficient | Efficient |

---

## 📝 Summary

### What Changed?
1. **Bot** (final_working_bot.py): No longer runs F5-TTS, queues jobs instead
2. **Worker** (audio_worker.py): New file, processes queue with GPU
3. **Database** (Supabase): New tables for queue coordination
4. **Setup** (p.py): Now runs worker instead of bot on Vast.ai

### What Stayed the Same?
✅ All existing code paths in bot
✅ Video worker (no changes)
✅ Daily video system
✅ Channel processing
✅ YouTube transcript processing
✅ User commands

### Key Benefits?
1. **Cost Savings**: No GPU needed on Contabo
2. **Better UX**: Users don't wait for audio generation
3. **Scalability**: Add workers as needed
4. **Reliability**: Jobs retry on failure
5. **Monitoring**: Track jobs in database

---

## 🔄 Migration Path

If you're running the old system and want to migrate:

1. **Backup**: Save current `.env` and database
2. **Deploy Schema**: Run Supabase SQL files
3. **Update Bot**: `git pull` and restart bot on Contabo
4. **Deploy Worker**: Upload `p.py` to Vast.ai and run
5. **Test**: Send a script and verify queue works
6. **Monitor**: Check Supabase tables for job flow

**Rollback**: If issues occur, revert to previous commit:
```bash
git log  # Find previous commit
git checkout <commit_hash>
python3 final_working_bot.py
```

---

## 📞 Support

- **GitHub Issues**: Report bugs or request features
- **Documentation**: This README + inline code comments
- **Database**: Check Supabase dashboard for queue status
- **Logs**: Check bot/worker console output for errors

---

**Generated**: 2025-01-23
**Version**: 1.0
**Status**: Production Ready ✅
