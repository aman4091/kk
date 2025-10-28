# Audio to Video Converter - Usage Guide

## 🎯 Overview

Standalone script that fetches enhanced audio links from Supabase database, downloads them from Gofile, and converts them to MP4 videos with black background.

**Features:**
- ✅ Auto-installs all Python dependencies
- ✅ Works on PC (Windows/Linux/macOS) and Android (Termux)
- ✅ Smart directory selection based on platform
- ✅ Numbered file output (1.mp4, 2.mp4, etc.)
- ✅ Skips existing file numbers
- ✅ Progress display in terminal
- ✅ Auto-cleanup of temp files

---

## 📱 Android (Termux) Setup

### Step 1: Install Termux
Download from F-Droid (NOT Google Play Store): https://f-droid.org/en/packages/com.termux/

### Step 2: Setup Storage Access
```bash
termux-setup-storage
```
Grant storage permission when prompted. This allows the script to save files to your phone's storage.

### Step 3: Install Dependencies
```bash
# Update packages
pkg update && pkg upgrade

# Install Python and FFmpeg
pkg install python ffmpeg

# Install git (optional, for cloning)
pkg install git
```

### Step 4: Get the Script
Copy `audio_to_video_converter.py` to your Termux home directory:
```bash
# Option 1: Use file manager to copy to ~/storage/shared then move
cp ~/storage/shared/audio_to_video_converter.py ~/

# Option 2: Direct download (if uploaded somewhere)
# wget <URL> -O audio_to_video_converter.py
```

### Step 5: Run the Script
```bash
python audio_to_video_converter.py
```

**Output Location (Android):**
- Files saved to: `~/storage/shared/AudioToVideo/`
- Access from file manager: Look for "AudioToVideo" folder
- Files: `1.mp4`, `2.mp4`, `3.mp4`, etc.

---

## 💻 PC Setup (Windows/Linux/macOS)

### Step 1: Install FFmpeg

**Windows:**
1. Download from https://ffmpeg.org/download.html
2. Extract and add to PATH

**Linux:**
```bash
sudo apt install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

### Step 2: Get the Script
Copy `audio_to_video_converter.py` to any directory.

### Step 3: Run the Script
```bash
python3 audio_to_video_converter.py
```

**Output Location (PC):**
- Files saved to: `./video/` (in same directory as script)
- Files: `1.mp4`, `2.mp4`, `3.mp4`, etc.

---

## 🚀 Usage

### First Time Run:
The script will automatically:
1. Install required Python packages (supabase, httpx, requests)
2. Detect your platform (Android/PC)
3. Create output directory
4. Connect to Supabase database
5. Fetch pending audio links
6. Download and convert each audio file
7. Delete processed links from database

### Terminal Output Example:
```
============================================================
  🎬 Audio to Video Converter
============================================================

🖥️  Platform: Android (Termux)
📂 Output directory: /data/data/com.termux/files/home/storage/shared/AudioToVideo

📋 Checking dependencies...
✅ FFmpeg found

✅ Output directory: /storage/emulated/0/AudioToVideo/
   Platform: Android (Termux)

📂 Scanning existing files...
✅ No existing MP4 files

🔌 Connecting to database...
✅ Connected to Supabase

📥 Fetching audio links from database...
✅ Found 5 pending audio links

🚀 Starting to process 5 audio links...

============================================================
Link 1/5 -> Output: 1.mp4
============================================================

Processing Audio #1
Link ID: 123
URL: https://gofile.io/d/...

📥 Downloading from Gofile...
   Progress: 100.0% (5242880/5242880 bytes)
✅ Downloaded: /storage/.../temp_1.wav

🎬 Converting to MP4 with black background...
✅ Converted to MP4: 1.mp4

🗑️ Deleting from database...
✅ Audio link deleted from database (ID: 123)
🗑️ Cleaned up temp file

✅ Successfully processed audio #1

[... continues for all links ...]

============================================================
  📊 Processing Complete!
============================================================

✅ Successful: 5/5
❌ Failed: 0/5

📂 Output directory: /storage/emulated/0/AudioToVideo/

📹 MP4 files: [1, 2, 3, 4, 5]
```

---

## 🔧 How It Works

### Workflow:
1. **Fetch Links:** Connects to Supabase and fetches all rows from `audio_links` table
2. **Download:** Uses Gofile API to download each audio file
3. **Convert:** Uses FFmpeg to create MP4 with black background (1280x720)
4. **Save:** Saves as numbered files, skipping existing numbers
5. **Cleanup:** Deletes link from database and removes temp files

### FFmpeg Command Used:
```bash
ffmpeg -f lavfi -i color=black:s=1280x720:r=1 \
       -i input.wav \
       -shortest \
       -c:v libx264 \
       -c:a aac \
       -b:a 192k \
       -pix_fmt yuv420p \
       output.mp4
```

---

## 📝 Notes

### File Naming:
- Script automatically finds the next available number
- If you have `1.mp4` and `3.mp4`, next file will be `2.mp4`
- You can manually delete files and the script will reuse those numbers

### Database:
- Links are automatically deleted after successful conversion
- If conversion fails, link stays in database for retry

### Storage:
- **Android:** Files in shared storage are accessible from any file manager
- **PC:** Files in `./video/` folder next to the script
- **Temp files:** Automatically cleaned up after each conversion

### Permissions (Android):
- Must run `termux-setup-storage` first time
- Grant storage permission when prompted
- Without permission, files save to Termux home directory only

---

## 🐛 Troubleshooting

### "FFmpeg not found"
**Android:**
```bash
pkg install ffmpeg
```

**PC:** Download and install from ffmpeg.org

### "Permission denied creating directory" (Android)
```bash
termux-setup-storage
# Re-run script after granting permission
```

### "No pending audio links in database"
- Bot hasn't processed any YouTube channels yet
- OR all links already downloaded and deleted

### "Supabase connection error"
- Check internet connection
- Credentials are hardcoded in script (should work automatically)

### "Download failed"
- Gofile link may be expired (usually 30 days)
- Check internet connection
- Link may be invalid

---

## 🔐 Security

**IMPORTANT:**
- This script contains hardcoded Supabase credentials
- Keep this file private (DO NOT share publicly)
- Already added to `.gitignore` to prevent Git commits
- Only you should have access to this file

---

## 📞 Support

For issues with:
- **Bot:** Check bot logs and Telegram messages
- **Script:** Check terminal output for error messages
- **FFmpeg:** Test with `ffmpeg -version`
- **Database:** Check Supabase dashboard for `audio_links` table

---

## ✅ Quick Checklist

### Android (Termux):
- [ ] Termux installed from F-Droid
- [ ] Ran `termux-setup-storage` and granted permission
- [ ] Installed: `pkg install python ffmpeg`
- [ ] Script copied to Termux directory
- [ ] Run: `python audio_to_video_converter.py`

### PC:
- [ ] Python 3.7+ installed
- [ ] FFmpeg installed and in PATH
- [ ] Script downloaded
- [ ] Run: `python3 audio_to_video_converter.py`
