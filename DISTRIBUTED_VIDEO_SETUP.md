# Distributed Video Encoding Setup Guide

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ CLOUD (Vast.ai)                                             │
│ - F5-TTS Audio Generation                                   │
│ - Upload audio + image to Google Drive                      │
│ - Create job in Supabase queue                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
           ┌──────────────────────────┐
           │ Supabase + Google Drive  │
           │ (Job Queue)              │
           └──────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│ LOCAL PC (RTX 4060)                                         │
│ - Poll queue every 30 seconds                               │
│ - Download audio + image                                    │
│ - Encode video with FFmpeg (GPU)                            │
│ - Upload to Google Drive + Gofile                           │
│ - Send Telegram notification                                │
└─────────────────────────────────────────────────────────────┘
```

---

## Setup Steps

### Step 1: Create Google Drive Folders (5 minutes)

1. Go to Google Drive: https://drive.google.com
2. Create two new folders:
   - **`Video_Queue`** - For pending jobs (audio + image files)
   - **`Video_Output`** - For completed videos

3. Get folder IDs from URL:
   ```
   https://drive.google.com/drive/folders/1ABC123XYZ...
                                           ^^^^^^^^^^^ This is the folder ID
   ```

4. Update `p.py` (line 65-66):
   ```python
   "GDRIVE_VIDEO_QUEUE_FOLDER": "1ABC123...",   # Your Video_Queue folder ID
   "GDRIVE_VIDEO_OUTPUT_FOLDER": "1XYZ789...",  # Your Video_Output folder ID
   ```

---

### Step 2: Run Supabase SQL (Already Done ✅)

Tables created:
- ✅ `video_jobs` - Job queue
- ✅ `video_workers` - Worker status tracking

---

### Step 3: Setup Local PC Worker

#### 3.1. Install Dependencies (if needed)

```bash
cd "E:\audio\New folder"
pip install telegram python-telegram-bot google-api-python-client supabase httpx
```

#### 3.2. Test Worker Manually

```bash
python local_video_worker.py
```

Expected output:
```
🚀 Starting Local Video Worker
   Worker ID: YOUR-PC-NAME_RTX4060
   Hostname: YOUR-PC-NAME
   GPU: RTX 4060
   Poll interval: 30s

✅ Worker registered in database
⏳ No pending jobs. Waiting 30s... (poll #1)
```

Press Ctrl+C to stop.

#### 3.3. Install as Windows Service (Auto-start on boot)

1. Right-click `install_worker_service.bat`
2. Select **"Run as administrator"**
3. Wait for installation to complete

Service will:
- ✅ Auto-start when PC boots
- ✅ Run 24/7 in background
- ✅ Auto-restart if it crashes

#### 3.4. Manage Service

**Check status:**
```cmd
nssm status VideoWorker
```

**View logs:**
```
E:\audio\New folder\worker_stdout.log  (console output)
E:\audio\New folder\worker_stderr.log  (errors)
```

**Stop service:**
```cmd
nssm stop VideoWorker
```

**Start service:**
```cmd
nssm start VideoWorker
```

**Remove service:**
```cmd
nssm remove VideoWorker confirm
```

---

### Step 4: Update Cloud Bot (Vast.ai)

The bot code has already been updated with queue support.

**What changed:**
- After audio generation, instead of creating video immediately:
  1. Upload audio to `Video_Queue` folder
  2. Upload image to `Video_Queue` folder
  3. Create job in Supabase `video_jobs` table
  4. Send message: "🎵 Audio ready! Video queued for processing..."

---

### Step 5: Test End-to-End

#### On Vast.ai (Cloud):

1. Upload updated `p.py` with folder IDs
2. Run bot: `python3 p.py`
3. Send script or YouTube channel link to bot
4. Bot generates audio and creates job in queue

#### On Local PC:

1. Worker detects job (check `worker_stdout.log`)
2. Downloads audio + image from Google Drive
3. Encodes video with FFmpeg
4. Uploads video to Google Drive + Gofile
5. Sends Telegram notification with links

#### Expected Timeline:

- **Cloud (Vast.ai)**: 5-10 minutes for audio generation
- **Queue**: Instant (job created in database)
- **Local PC**:
  - Detection: Max 30 seconds (poll interval)
  - Download: 1-2 minutes
  - Encoding: 30-50 minutes for 50-min video
  - Upload: 5-10 minutes
  - **Total**: ~40-60 minutes from audio completion

---

## Monitoring

### Check Queue Status (Supabase)

```sql
-- Pending jobs count
SELECT COUNT(*) FROM video_jobs WHERE status = 'pending';

-- All jobs summary
SELECT status, COUNT(*) as count
FROM video_jobs
GROUP BY status;

-- Worker status
SELECT worker_id, status, last_heartbeat, jobs_completed, jobs_failed
FROM video_workers;

-- Failed jobs
SELECT job_id, error_message, retry_count
FROM video_jobs
WHERE status = 'failed'
ORDER BY created_at DESC;
```

### Check Worker Logs

```cmd
# Real-time log monitoring
tail -f E:\audio\New folder\worker_stdout.log

# Last 50 lines
Get-Content E:\audio\New folder\worker_stdout.log -Tail 50
```

---

## Troubleshooting

### Problem: Worker not detecting jobs

**Check:**
1. Service running? `nssm status VideoWorker`
2. Check logs: `worker_stderr.log`
3. Supabase connection? Check API keys in environment
4. Internet connection?

**Fix:**
```cmd
nssm restart VideoWorker
```

### Problem: Download fails from Google Drive

**Check:**
1. Folder IDs correct in `p.py`?
2. `token.pickle` file exists?
3. GDrive permissions OK?

**Fix:**
Regenerate Google Drive token:
```bash
python regenerate_gdrive_token.py
```

### Problem: Video encoding fails

**Check:**
1. FFmpeg installed? `ffmpeg -version`
2. NVIDIA GPU driver installed? `nvidia-smi`
3. Check error in `worker_stderr.log`

**Fix:**
Reinstall FFmpeg with GPU support

### Problem: Upload to Gofile fails

**Cause:** Gofile API rate limit or server down

**Fix:**
- Retry automatically (worker will retry 3 times)
- Google Drive link still works

---

## Performance

### Expected Encoding Times (RTX 4060)

| Video Length | Encoding Time | Speed     |
|--------------|---------------|-----------|
| 10 minutes   | 5-8 minutes   | 1.5x      |
| 30 minutes   | 15-20 minutes | 1.5-2x    |
| 50 minutes   | 30-40 minutes | 1.2-1.5x  |

**Factors:**
- GPU utilization: 50-70%
- CPU usage: 20-30% (subtitle generation)
- Disk I/O: Moderate

### Cost Savings

**Before (Cloud only):**
- Vast.ai GPU 24/7: $0.50/hour × 720 hours = **$360/month**
- Video encoding: Hangs at 70-76% ❌

**After (Distributed):**
- Vast.ai GPU (audio only): $0.50/hour × 60 hours = **$30/month**
- Local PC: Free (electricity ~$5/month)
- **Total: $35/month**
- **Savings: $325/month (90%)** 🎉

---

## FAQ

**Q: What if my PC is offline?**
A: Jobs accumulate in queue. When PC comes online, worker processes them automatically.

**Q: Can I run multiple workers?**
A: Yes! Install worker on multiple PCs. They'll share the queue.

**Q: How to prioritize urgent jobs?**
A: Update job priority in Supabase:
```sql
UPDATE video_jobs SET priority = 10 WHERE job_id = '12345';
```

**Q: Can I disable queue and use direct video generation?**
A: Yes, but it will hang on cloud. Queue system is recommended.

**Q: What happens if encoding fails?**
A: Auto-retry 3 times. After 3 failures, marked as 'failed' and stops retrying.

---

## Next Steps

1. ✅ Test with one job end-to-end
2. Monitor for 24 hours
3. Check worker stats in Supabase
4. Optimize if needed (e.g., faster encoding preset)

**Enjoy stable video encoding! 🎬🚀**
