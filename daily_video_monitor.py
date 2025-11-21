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

Deploy to Railway.com or Render.com for 24/7 operation.
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
        """Initialize monitoring bot"""
        if not MONITOR_TOKEN or not CHAT_ID:
            raise ValueError("MONITOR_BOT_TOKEN and MONITOR_CHAT_ID must be set in .env")

        self.bot = Bot(token=MONITOR_TOKEN)
        self.supabase = SupabaseClient()
        self.chat_id = CHAT_ID

        print("✅ Daily Video Monitor initialized")
        print(f"📱 Monitoring chat: {self.chat_id}")

    async def check_videos(self):
        """Main monitoring loop - runs forever"""
        print("🔄 Starting video monitoring...")

        while True:
            try:
                # Get tomorrow's date (target date)
                tomorrow = (datetime.now() + timedelta(days=1)).date()
                print(f"\n🔍 Checking videos for {tomorrow}...")

                # Get incomplete videos
                incomplete = self.supabase.get_incomplete_videos(tomorrow)

                if not incomplete:
                    # All complete - no notification
                    print(f"✅ All videos complete for {tomorrow}")
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
                print(f"📤 Sending notification: {len(incomplete)} incomplete items")
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=message,
                    parse_mode="Markdown"
                )

                # Wait 30 minutes
                print(f"⏳ Waiting 30 minutes until next check...")
                await asyncio.sleep(30 * 60)

            except Exception as e:
                print(f"❌ Monitor error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(60)  # Retry in 1 minute on error

    def _get_missing_item(self, video):
        """Determine what's missing from a video"""
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

    async def cleanup_old_videos(self):
        """
        Run cleanup daily at 3 AM
        Deletes videos older than 7 days from Google Drive
        """
        print("🗑️ Starting daily cleanup scheduler...")

        while True:
            try:
                now = datetime.now()

                # Calculate next 3 AM
                next_3am = now.replace(hour=3, minute=0, second=0, microsecond=0)
                if now.hour >= 3:
                    next_3am += timedelta(days=1)

                # Sleep until 3 AM
                sleep_seconds = (next_3am - now).total_seconds()
                print(f"⏰ Next cleanup at {next_3am} ({sleep_seconds/3600:.1f} hours)")
                await asyncio.sleep(sleep_seconds)

                # Run cleanup
                print(f"\n🗑️ Running cleanup at {datetime.now()}...")

                from gdrive_manager import GDriveImageManager
                from daily_video_organizer import create_organizer

                gdrive = GDriveImageManager()
                organizer = create_organizer(self.supabase, gdrive)

                await organizer.cleanup_old_videos(days_old=7)

                # Notify completion
                await self.bot.send_message(
                    chat_id=self.chat_id,
                    text=f"✅ Daily cleanup completed at {datetime.now().strftime('%H:%M')}\n"
                         f"🗑️ Deleted videos older than 7 days"
                )

            except Exception as e:
                print(f"❌ Cleanup error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(3600)  # Retry in 1 hour on error

async def main():
    """Main entry point"""
    print("\n" + "="*60)
    print("🤖 Daily Video Monitoring Bot")
    print("="*60 + "\n")

    monitor = DailyVideoMonitor()

    # Start both tasks concurrently
    tasks = [
        asyncio.create_task(monitor.check_videos()),
        asyncio.create_task(monitor.cleanup_old_videos())
    ]

    # Run forever
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Monitor stopped by user (Ctrl+C)")
    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
