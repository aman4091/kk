# Daily Video Organization System - Implementation Guide

## ✅ Completed Components

### 1. **Database Schema** (`sql/daily_video_tracking.sql`)
- ✅ `daily_video_tracking` table created
- ✅ `thumbnail_queue` table created
- ✅ Helper functions and views added
- ✅ Indexes for performance

**Action Required:** Run this SQL in Supabase dashboard to create tables.

### 2. **Supabase Client** (`supabase_client.py`)
- ✅ `create_video_tracking()` - Create new video entry
- ✅ `update_video_tracking()` - Update tracking status
- ✅ `get_video_tracking()` - Get video by date/channel/number
- ✅ `get_next_video_number()` - Get next available slot (1-4)
- ✅ `get_incomplete_videos()` - Find missing items
- ✅ `get_date_completion_stats()` - Completion percentage
- ✅ `add_thumbnail_to_queue()` - Queue thumbnail
- ✅ `get_pending_thumbnails()` - Get unprocessed thumbnails
- ✅ `mark_thumbnail_processed()` - Mark as done
- ✅ `find_video_for_thumbnail()` - Match thumbnail to video
- ✅ `get_old_videos()` - Get videos for cleanup

### 3. **GDrive Manager** (`gdrive_manager.py`)
- ✅ `create_folder()` - Create new folder
- ✅ `folder_exists()` - Check if folder exists
- ✅ `get_or_create_folder()` - Smart folder creation
- ✅ `copy_file()` - Copy file between folders
- ✅ `upload_text_file()` - Upload script as text
- ✅ `upload_file()` - Upload any file
- ✅ `delete_folder()` - Delete old folders

### 4. **Organizer Module** (`daily_video_organizer.py`)
- ✅ `create_folder_structure()` - Create date/channel/video_X hierarchy
- ✅ `organize_audio()` - Copy audio + script to organized folder
- ✅ `organize_video()` - Copy video + delete original
- ✅ `process_thumbnail_queue()` - Background thumbnail processor
- ✅ `cleanup_old_videos()` - Delete 7+ day old videos

### 5. **Environment Variables** (`.env`)
- ✅ `DAILY_VIDEO_PARENT_FOLDER` - Parent folder ID
- ✅ `MONITOR_BOT_TOKEN` - Monitoring bot token
- ✅ `MONITOR_CHAT_ID` - Notification chat ID

### 6. **Safety Measures**
- ✅ p.py added to `.gitignore` (line 67)
- ✅ Backup branch created: `backup-pre-organizer`
- ✅ Pushed to remote: `origin/backup-pre-organizer`

---

## 🚧 Remaining Integration Work

### Step 1: Bot Integration (final_working_bot.py)

#### A. Add Imports (Top of file, around line 30)
```python
from daily_video_organizer import create_organizer
from datetime import timedelta
```

#### B. Initialize Organizer in `__init__` (around line 177)
```python
# After: self.gdrive_manager = None
# Add:
self.video_organizer = None
if self.gdrive_manager and self.supabase.is_connected():
    self.video_organizer = create_organizer(self.supabase, self.gdrive_manager)
```

#### C. Enhance `handle_text()` Method (around line 7242)

Find the existing `handle_text` method and wrap script detection:

```python
async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages - check for scripts"""
    text = update.message.text
    chat_id = update.effective_chat.id

    # Check if this looks like a script (> 100 chars, not a command)
    if len(text) > 100 and not text.startswith('/'):
        # This might be a script - show channel selection
        await self.handle_script_submission(update, context, text)
        return

    # ... existing code for other text handling ...
```

#### D. Add New Method: `handle_script_submission()`

Add this new method (around line 500, after other handlers):

```python
async def handle_script_submission(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle script submission - show inline keyboard for channel selection
    """
    try:
        script_text = update.message.text

        # Store script in user context
        context.user_data['pending_script'] = script_text
        context.user_data['script_message_id'] = update.message.message_id

        # Create inline keyboard with 6 channels
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup

        keyboard = [
            [
                InlineKeyboardButton("BI", callback_data="channel_BI"),
                InlineKeyboardButton("AFG", callback_data="channel_AFG"),
                InlineKeyboardButton("JIMMY", callback_data="channel_JIMMY")
            ],
            [
                InlineKeyboardButton("GYH", callback_data="channel_GYH"),
                InlineKeyboardButton("ANU", callback_data="channel_ANU"),
                InlineKeyboardButton("JM", callback_data="channel_JM")
            ]
        ]

        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "📝 Script received! Select channel:",
            reply_markup=reply_markup
        )

    except Exception as e:
        print(f"❌ Script submission error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")
```

#### E. Add Callback Handler: `handle_channel_selection()`

Add this new method:

```python
async def handle_channel_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle channel selection from inline keyboard
    """
    try:
        query = update.callback_query
        await query.answer()

        # Extract channel code
        if not query.data.startswith('channel_'):
            return

        channel_code = query.data.replace('channel_', '')  # BI, AFG, etc

        # Get script from context
        script_text = context.user_data.get('pending_script')
        if not script_text:
            await query.edit_message_text("❌ Script not found. Please send script again.")
            return

        # Get tomorrow's date
        from datetime import datetime, timedelta
        tomorrow = (datetime.now() + timedelta(days=1)).date()

        # Get next available video number
        video_num = self.supabase.get_next_video_number(tomorrow, channel_code)

        if video_num > 4:
            await query.edit_message_text(
                f"❌ {channel_code} is full for {tomorrow}!\n"
                f"All 4 video slots are taken."
            )
            return

        # Create tracking entry
        tracking_id = self.supabase.create_video_tracking(
            tomorrow, channel_code, video_num, script_text
        )

        if not tracking_id:
            await query.edit_message_text("❌ Database error. Please try again.")
            return

        # Store tracking info
        context.user_data['current_tracking_id'] = tracking_id
        context.user_data['current_channel'] = channel_code
        context.user_data['current_video_num'] = video_num
        context.user_data['current_date'] = tomorrow

        await query.edit_message_text(
            f"✅ Processing **{channel_code} video {video_num}** for {tomorrow}\n\n"
            f"🎵 Generating audio...",
            parse_mode="Markdown"
        )

        # Generate audio (existing code)
        chat_id = query.message.chat.id
        success, output_files = await self.generate_audio_f5(script_text, chat_id)

        if not success:
            await context.bot.send_message(chat_id, f"❌ Audio generation failed")
            return

        # POST-PROCESS: Organize audio (NEW!)
        if self.video_organizer and output_files:
            # Get audio GDrive ID from output_files
            audio_gdrive_id = None
            for file_info in output_files:
                if 'gdrive_id' in file_info:
                    audio_gdrive_id = file_info['gdrive_id']
                    break

            if audio_gdrive_id:
                await context.bot.send_message(chat_id, "📦 Organizing files...")

                success = await self.video_organizer.organize_audio(
                    tracking_id,
                    audio_gdrive_id,
                    tomorrow,
                    channel_code,
                    video_num,
                    script_text
                )

                if success:
                    await context.bot.send_message(
                        chat_id,
                        f"✅ Audio organized!\n"
                        f"📁 {tomorrow}/{channel_code}/video_{video_num}/\n\n"
                        f"🎬 Video generation will start automatically."
                    )
                else:
                    await context.bot.send_message(chat_id, "⚠️ Organization failed (non-critical)")

        # Existing delivery code continues...
        await self.send_outputs_by_mode(context, chat_id, output_files, script_text, "Script Audio")

    except Exception as e:
        print(f"❌ Channel selection error: {e}")
        import traceback
        traceback.print_exc()
```

#### F. Register Callback Handler in `main()` (around line 7245)

Add this line:

```python
# After: application.add_handler(CommandHandler(...))
application.add_handler(CallbackQueryHandler(bot_instance.handle_channel_selection, pattern='^channel_'))
```

#### G. Add Thumbnail Handler Method

Add this new method:

```python
async def handle_thumbnail_image(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle thumbnail images with channel/video tagging
    Supports both caption and reply methods
    """
    try:
        if not update.message.photo:
            return

        # Get caption from message or reply
        caption = update.message.caption or ""

        if update.message.reply_to_message:
            reply_text = update.message.reply_to_message.text or ""
            caption = caption or reply_text

        if not caption:
            return  # Not a thumbnail tag

        # Parse pattern: "{CHANNEL} video {NUM}"
        import re
        match = re.match(r'(\w+)\s+video\s+(\d+)', caption, re.IGNORECASE)

        if not match:
            return  # Not a thumbnail tag

        channel_code = match.group(1).upper()
        video_number = int(match.group(2))

        # Validate
        valid_channels = ['BI', 'AFG', 'JIMMY', 'GYH', 'ANU', 'JM']
        if channel_code not in valid_channels:
            await update.message.reply_text(f"❌ Invalid channel: {channel_code}")
            return

        if video_number < 1 or video_number > 4:
            await update.message.reply_text(f"❌ Invalid video number: {video_number} (must be 1-4)")
            return

        # Get largest photo
        photo = update.message.photo[-1]
        file_id = photo.file_id
        file_unique_id = photo.file_unique_id

        # Add to queue
        success = self.supabase.add_thumbnail_to_queue(
            file_id, channel_code, video_number, file_unique_id
        )

        if success:
            await update.message.reply_text(
                f"✅ Thumbnail queued for **{channel_code} video {video_number}**\n\n"
                f"It will be processed automatically when the video is ready.",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text("❌ Failed to queue thumbnail")

    except Exception as e:
        print(f"❌ Thumbnail handler error: {e}")
```

#### H. Register Photo Handler in `main()`

Add this line:

```python
application.add_handler(MessageHandler(filters.PHOTO, bot_instance.handle_thumbnail_image))
```

---

### Step 2: Local Worker Integration (local_video_worker.py)

Find the video upload completion section (search for "upload_video_to_gdrive" or "notify_completion").

After successful video upload, add:

```python
# Existing video upload code...
video_id = self.upload_video_to_gdrive(output_path)

if video_id:
    # Existing notification code...
    await self.notify_completion(...)

    # NEW: Post-process organization
    try:
        from daily_video_organizer import create_organizer
        organizer = create_organizer(self.supabase, self.gdrive)

        # Get job metadata (channel, video_num, date)
        # You'll need to pass these through the job system
        channel = job.get('channel_code')
        video_num = job.get('video_number')
        date = job.get('target_date')

        if channel and video_num and date:
            await organizer.organize_video(
                video_id,
                date,
                channel,
                video_num,
                delete_original=True  # Delete from output folder after copy
            )
            print(f"✅ Video organized and original deleted")
    except Exception as e:
        print(f"⚠️ Video organization failed: {e}")
        # Non-critical - video still uploaded to original folder
```

**Note:** You'll need to enhance the video job system to pass channel/video metadata through the queue.

---

### Step 3: Monitoring Bot (daily_video_monitor.py)

Create new file `daily_video_monitor.py`:

```python
#!/usr/bin/env python3
"""
Daily Video Monitoring Bot
===========================
24/7 service that monitors video completion and sends notifications.

Checks every 30 minutes for:
- Missing scripts
- Pending audio
- Pending video
- Missing thumbnails

Notifies only when items are incomplete.
"""

import os
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from telegram import Bot
from supabase_client import SupabaseClient

load_dotenv()

MONITOR_TOKEN = os.getenv("MONITOR_BOT_TOKEN")
CHAT_ID = os.getenv("MONITOR_CHAT_ID")

class DailyVideoMonitor:
    def __init__(self):
        self.bot = Bot(token=MONITOR_TOKEN)
        self.supabase = SupabaseClient()
        self.chat_id = CHAT_ID

    async def check_videos(self):
        """Main monitoring loop"""
        while True:
            try:
                # Get tomorrow's date (target date)
                tomorrow = (datetime.now() + timedelta(days=1)).date()

                # Get incomplete videos
                incomplete = self.supabase.get_incomplete_videos(tomorrow)

                if not incomplete:
                    # All complete - no notification
                    await asyncio.sleep(30 * 60)  # 30 minutes
                    continue

                # Build notification message
                message = f"⚠️ **{tomorrow} Video Status**\n\n"

                # Group by channel
                by_channel = {}
                for video in incomplete:
                    channel = video['channel_code']
                    if channel not in by_channel:
                        by_channel[channel] = []
                    by_channel[channel].append(video)

                # Format message
                for channel in ['BI', 'AFG', 'JIMMY', 'GYH', 'ANU', 'JM']:
                    if channel in by_channel:
                        message += f"**{channel}:**\n"
                        for v in by_channel[channel]:
                            num = v['video_number']
                            status = self._get_missing_item(v)
                            message += f"  Video {num}: {status}\n"
                        message += "\n"

                # Add completion stats
                stats = self.supabase.get_date_completion_stats(tomorrow)
                message += f"📊 {stats['completed']}/24 complete ({stats['percentage']}%)"

                # Send notification
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode="Markdown"
                )

                # Wait 30 minutes
                await asyncio.sleep(30 * 60)

            except Exception as e:
                print(f"❌ Monitor error: {e}")
                await asyncio.sleep(60)  # Retry in 1 minute

    def _get_missing_item(self, video):
        """Determine what's missing"""
        if not video.get('script_gdrive_id'):
            return "🔴 Script missing"
        elif not video.get('audio_gdrive_id'):
            return "🟡 Audio pending"
        elif not video.get('video_gdrive_id'):
            return "🟡 Video pending"
        elif not video.get('thumbnail_gdrive_id'):
            return "🟠 Thumbnail missing"
        else:
            return "🟢 Complete"

async def main():
    monitor = DailyVideoMonitor()
    print("🔄 Starting daily video monitor...")
    await monitor.check_videos()

if __name__ == "__main__":
    asyncio.run(main())
```

**Deployment:** Deploy to Railway.com or Render.com for 24/7 operation.

---

### Step 4: Thumbnail Background Processor

In your bot's `main()` function, start the thumbnail processor:

```python
# After bot initialization, before polling
if bot_instance.video_organizer:
    # Start thumbnail processor in background
    bot_token = os.getenv("BOT_TOKEN")
    asyncio.create_task(
        bot_instance.video_organizer.process_thumbnail_queue(bot_token)
    )
    print("✅ Thumbnail processor started")
```

---

### Step 5: Cleanup Job

Add daily cleanup job. In monitoring bot or as separate cron:

```python
async def daily_cleanup():
    """Run cleanup at 3 AM daily"""
    from daily_video_organizer import create_organizer

    while True:
        now = datetime.now()
        # Calculate next 3 AM
        next_3am = now.replace(hour=3, minute=0, second=0, microsecond=0)
        if now.hour >= 3:
            next_3am += timedelta(days=1)

        # Sleep until 3 AM
        sleep_seconds = (next_3am - now).total_seconds()
        await asyncio.sleep(sleep_seconds)

        # Run cleanup
        organizer = create_organizer(supabase, gdrive)
        await organizer.cleanup_old_videos(days_old=7)
```

---

## 🧪 Testing Checklist

### Test 1: Script Submission
1. Send long text script to bot
2. Verify inline keyboard appears with 6 channels
3. Select "BI"
4. Verify audio generation starts
5. Check GDrive: `2025-01-23/BI/video_1/` contains `script.txt` and `audio.wav`
6. Check Supabase: `daily_video_tracking` has entry with status='audio_done'

### Test 2: Video Generation
1. Wait for video to be generated by local worker
2. Check GDrive: `2025-01-23/BI/video_1/` now has `video.mp4`
3. Verify original video deleted from output folder
4. Check Supabase: status='video_done'

### Test 3: Thumbnail Tagging (Caption Method)
1. Send image with caption "BI video 1"
2. Verify success message
3. Wait for thumbnail processor (runs every minute)
4. Check GDrive: `thumbnail.jpg` added to folder
5. Check Supabase: status='complete'

### Test 4: Thumbnail Tagging (Reply Method)
1. Send image
2. Reply to image with "AFG video 2"
3. Same verification as Test 3

### Test 5: Monitoring Bot
1. Start monitoring bot
2. Create incomplete video (only script, no audio)
3. Wait 30 minutes
4. Verify notification received in Telegram

### Test 6: Cleanup
1. Create test video with date 8 days ago
2. Run cleanup manually or wait for 3 AM
3. Verify folder deleted from GDrive
4. Verify status='deleted' in database

---

## 📝 Summary

**Completed (Ready to use):**
- ✅ Database schema
- ✅ Supabase client methods
- ✅ GDrive manager methods
- ✅ Organizer module
- ✅ Environment variables

**Remaining Integration Points:**
1. Bot inline keyboard handler (~50 lines)
2. Bot thumbnail handler (~40 lines)
3. Local worker post-process hook (~15 lines)
4. Monitoring bot service (new file, ~100 lines)
5. Thumbnail background processor (1 line to start)
6. Cleanup scheduler (~20 lines)

**Total Additional Code:** ~226 lines across existing and new files

**Estimated Time:** 1-2 hours for integration + testing

---

## 🚀 Next Steps

1. **Run SQL schema** in Supabase dashboard
2. **Integrate bot handlers** (inline keyboard + thumbnail)
3. **Test script submission** → audio → organized folder
4. **Enhance video worker** with post-process hook
5. **Deploy monitoring bot** to Railway
6. **Test complete flow** end-to-end
7. **Set up cleanup schedule**

---

## ⚠️ Important Notes

- **P.py is SAFE**: Already in `.gitignore` (line 67), never committed
- **Backup exists**: `backup-pre-organizer` branch pushed to remote
- **Non-invasive**: Existing audio/video generation unchanged
- **Copy-based**: Audio copied (original kept), video copied then deleted
- **7-day tracking**: Thumbnails can be added anytime within 7 days
- **Dual bots**: Main bot + monitoring bot run in parallel (no conflicts)

Good luck with the integration! 🚀
