#!/usr/bin/env python3
"""
Daily Video Organizer
=====================
Post-processing module for organizing audio/video files into structured folders.

Folder Structure:
    Parent Folder (1ZKnCa-7ieNt3bLhI6f6mCZBmyAP0-dnF)/
        └── 2025-01-22/          # Date folder
            └── BI/               # Channel folder
                └── video_1/      # Video folder
                    ├── script.txt
                    ├── audio.wav
                    ├── video.mp4
                    └── thumbnail.jpg

Key Features:
- Non-invasive: Works after existing audio/video generation
- Copy-based: Original files remain untouched (audio), or deleted after copy (video)
- Database-tracked: All operations logged in Supabase
- Thumbnail queue: Processes thumbnails sent before/after video creation
"""

import os
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Tuple
from pathlib import Path

class DailyVideoOrganizer:
    def __init__(self, supabase_client, gdrive_manager, parent_folder_id: str):
        """
        Initialize organizer

        Args:
            supabase_client: SupabaseClient instance
            gdrive_manager: GDriveImageManager instance
            parent_folder_id: Google Drive parent folder ID (1ZKnCa-7ieNt3bLhI6f6mCZBmyAP0-dnF)
        """
        self.supabase = supabase_client
        self.gdrive = gdrive_manager
        self.parent_folder = parent_folder_id

        print("✅ DailyVideoOrganizer initialized")

    def create_folder_structure(self, date, channel_code: str, video_number: int) -> Optional[str]:
        """
        Create organized folder structure: date/channel/video_X/

        Args:
            date: Target date
            channel_code: Channel code (BI, AFG, etc)
            video_number: Video number (1-4)

        Returns:
            video_folder_id: GDrive folder ID for video_X/ or None
        """
        try:
            # Convert date to string
            if hasattr(date, 'strftime'):
                date_str = date.strftime('%Y-%m-%d')
            else:
                date_str = str(date)

            print(f"\n📁 Creating folder structure: {date_str}/{channel_code}/video_{video_number}/")

            # Create/get date folder
            date_folder_id = self.gdrive.get_or_create_folder(date_str, self.parent_folder)
            if not date_folder_id:
                print(f"❌ Failed to create date folder: {date_str}")
                return None
            print(f"✅ Date folder: {date_str} (ID: {date_folder_id})")

            # Create/get channel folder
            channel_folder_id = self.gdrive.get_or_create_folder(channel_code.upper(), date_folder_id)
            if not channel_folder_id:
                print(f"❌ Failed to create channel folder: {channel_code}")
                return None
            print(f"✅ Channel folder: {channel_code} (ID: {channel_folder_id})")

            # Create/get video folder
            video_folder_name = f"video_{video_number}"
            video_folder_id = self.gdrive.get_or_create_folder(video_folder_name, channel_folder_id)
            if not video_folder_id:
                print(f"❌ Failed to create video folder: {video_folder_name}")
                return None
            print(f"✅ Video folder: {video_folder_name} (ID: {video_folder_id})")

            return video_folder_id

        except Exception as e:
            print(f"❌ Error creating folder structure: {e}")
            return None

    async def organize_audio(self, tracking_id: str, audio_gdrive_id: str,
                            date, channel_code: str, video_number: int,
                            script_text: str = None) -> bool:
        """
        Organize audio + script into structured folder

        Steps:
        1. Create folder structure (date/channel/video_X/)
        2. Copy audio from original folder
        3. Upload script as text file
        4. Update database tracking

        Args:
            tracking_id: Database tracking UUID
            audio_gdrive_id: GDrive file ID of audio
            date: Target date
            channel_code: Channel code
            video_number: Video number
            script_text: Optional script content

        Returns:
            success: bool
        """
        try:
            print(f"\n{'='*60}")
            print(f"📦 Organizing Audio: {channel_code} video {video_number}")
            print(f"{'='*60}")

            # Create folder structure
            video_folder_id = self.create_folder_structure(date, channel_code, video_number)
            if not video_folder_id:
                return False

            # Copy audio file
            print(f"\n📤 Copying audio file...")
            new_audio_id = self.gdrive.copy_file(
                audio_gdrive_id,
                video_folder_id,
                new_name="audio.wav"
            )

            if not new_audio_id:
                print(f"❌ Failed to copy audio")
                return False

            # Upload script if provided
            script_id = None
            if script_text:
                print(f"📤 Uploading script...")
                script_id = self.gdrive.upload_text_file(
                    script_text,
                    video_folder_id,
                    filename="script.txt"
                )

                if not script_id:
                    print(f"⚠️ Script upload failed (non-critical)")

            # Update database
            print(f"💾 Updating database...")
            print(f"   Tracking ID: {tracking_id}")
            print(f"   ORIGINAL Audio GDrive ID (will be stored): {audio_gdrive_id}")
            print(f"   NEW Copied Audio ID (not stored): {new_audio_id}")

            updates = {
                'audio_gdrive_id': audio_gdrive_id,  # Keep ORIGINAL audio ID for worker query
                'script_gdrive_id': script_id,
                'organized_folder_id': video_folder_id,
                'status': 'audio_done'
            }

            success = self.supabase.update_video_tracking(tracking_id, updates)

            if success:
                print(f"✅ Audio organized successfully!")
                print(f"📁 Folder ID: {video_folder_id}")
                print(f"🎵 Audio ID (stored in tracking): {audio_gdrive_id}")
                if script_id:
                    print(f"📝 Script ID: {script_id}")
            else:
                print(f"⚠️ Database update failed")

            return success

        except Exception as e:
            print(f"❌ Error organizing audio: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def organize_video(self, video_gdrive_id: str, date,
                            channel_code: str, video_number: int,
                            delete_original: bool = True) -> bool:
        """
        Organize video into structured folder + optionally delete original

        Steps:
        1. Get tracking entry (has organized_folder_id)
        2. Copy video to organized folder
        3. Delete original from output folder (if delete_original=True)
        4. Update database

        Args:
            video_gdrive_id: GDrive file ID of video
            date: Target date
            channel_code: Channel code
            video_number: Video number
            delete_original: Delete original after copy (default True)

        Returns:
            success: bool
        """
        try:
            print(f"\n{'='*60}")
            print(f"📦 Organizing Video: {channel_code} video {video_number}")
            print(f"{'='*60}")

            # Get tracking entry
            tracking = self.supabase.get_video_tracking(date, channel_code, video_number)
            if not tracking:
                print(f"❌ No tracking entry found for {channel_code} video {video_number}")
                return False

            video_folder_id = tracking.get('organized_folder_id')
            if not video_folder_id:
                print(f"❌ No organized folder found - audio may not have been processed yet")
                return False

            # Copy video
            print(f"\n📤 Copying video file...")
            new_video_id = self.gdrive.copy_file(
                video_gdrive_id,
                video_folder_id,
                new_name="video.mp4"
            )

            if not new_video_id:
                print(f"❌ Failed to copy video")
                return False

            # Delete original (cleanup)
            if delete_original:
                print(f"🗑️ Deleting original video from output folder...")
                delete_success = self.gdrive.delete_image_from_gdrive(video_gdrive_id)
                if delete_success:
                    print(f"✅ Original deleted")
                else:
                    print(f"⚠️ Original deletion failed (non-critical)")

            # Update database
            print(f"💾 Updating database...")
            updates = {
                'video_gdrive_id': new_video_id,
                'status': 'video_done'  # Will become 'complete' when thumbnail added
            }

            success = self.supabase.update_video_tracking(tracking['id'], updates)

            if success:
                print(f"✅ Video organized successfully!")
                print(f"📁 Folder ID: {video_folder_id}")
                print(f"🎬 Video ID: {new_video_id}")
            else:
                print(f"⚠️ Database update failed")

            return success

        except Exception as e:
            print(f"❌ Error organizing video: {e}")
            import traceback
            traceback.print_exc()
            return False

    async def process_thumbnail_queue(self, bot_token: str):
        """
        Background job: Process pending thumbnails from queue

        This runs continuously and:
        1. Checks for unprocessed thumbnails
        2. Finds matching video entries (within 7 days)
        3. Downloads thumbnail from Telegram
        4. Uploads to organized folder
        5. Updates database

        Args:
            bot_token: Telegram bot token for downloading files
        """
        print(f"\n🔄 Starting thumbnail queue processor...")

        while True:
            try:
                # Get pending thumbnails
                thumbnails = self.supabase.get_pending_thumbnails()

                if not thumbnails:
                    # No thumbnails to process
                    await asyncio.sleep(60)  # Check every minute
                    continue

                print(f"\n📋 Processing {len(thumbnails)} pending thumbnail(s)...")

                for thumb in thumbnails:
                    await self._process_single_thumbnail(thumb, bot_token)

                # Small delay before next check
                await asyncio.sleep(60)

            except Exception as e:
                print(f"❌ Thumbnail queue processor error: {e}")
                await asyncio.sleep(60)

    async def _process_single_thumbnail(self, thumb: dict, bot_token: str) -> bool:
        """
        Process a single thumbnail from queue

        Args:
            thumb: Thumbnail dict from database
            bot_token: Telegram bot token

        Returns:
            success: bool
        """
        try:
            channel = thumb['channel_code']
            video_num = thumb['video_number']

            print(f"\n🖼️ Processing thumbnail: {channel} video {video_num}")

            # Find matching video entry (within 7 days)
            video = self.supabase.find_video_for_thumbnail(channel, video_num, days_back=7)

            if not video:
                print(f"⚠️ No video found for {channel} video {video_num} (within 7 days)")
                return False

            video_folder_id = video.get('organized_folder_id')
            if not video_folder_id:
                print(f"⚠️ Video not yet organized (no folder ID)")
                return False

            # Download thumbnail from Telegram
            print(f"📥 Downloading from Telegram...")
            local_path = await self._download_telegram_file(
                thumb['telegram_file_id'],
                bot_token
            )

            if not local_path:
                print(f"❌ Failed to download thumbnail")
                return False

            # Upload to organized folder
            print(f"📤 Uploading to organized folder...")
            thumb_id = self.gdrive.upload_file(
                local_path,
                video_folder_id,
                filename="thumbnail.jpg"
            )

            if not thumb_id:
                print(f"❌ Failed to upload thumbnail")
                # Cleanup temp file
                try:
                    os.remove(local_path)
                except:
                    pass
                return False

            # Update video tracking (mark as complete!)
            print(f"💾 Marking video as complete...")
            self.supabase.update_video_tracking(video['id'], {
                'thumbnail_gdrive_id': thumb_id,
                'status': 'complete',
                'completed_at': datetime.now().isoformat()
            })

            # Mark thumbnail as processed
            self.supabase.mark_thumbnail_processed(thumb['id'], thumb_id)

            # Cleanup temp file
            try:
                os.remove(local_path)
            except:
                pass

            print(f"✅ Thumbnail processed successfully!")
            print(f"🖼️ Thumbnail ID: {thumb_id}")
            print(f"✅ Video marked as COMPLETE!")

            return True

        except Exception as e:
            print(f"❌ Error processing thumbnail: {e}")
            return False

    async def _download_telegram_file(self, file_id: str, bot_token: str) -> Optional[str]:
        """
        Download file from Telegram

        Args:
            file_id: Telegram file ID
            bot_token: Bot token

        Returns:
            local_path: Path to downloaded file or None
        """
        try:
            from telegram import Bot

            bot = Bot(token=bot_token)

            # Get file
            file = await bot.get_file(file_id)

            # Download to temp directory
            import tempfile
            temp_dir = tempfile.gettempdir()
            local_path = os.path.join(temp_dir, f"thumb_{file_id}.jpg")

            await file.download_to_drive(local_path)

            print(f"✅ Downloaded to: {local_path}")
            return local_path

        except Exception as e:
            print(f"❌ Telegram download error: {e}")
            return None

    async def cleanup_old_videos(self, days_old: int = 7):
        """
        Delete videos older than N days

        This should run daily (e.g., at 3 AM) to cleanup old videos.

        Args:
            days_old: Age threshold in days (default 7)
        """
        try:
            print(f"\n🗑️ Cleaning up videos older than {days_old} days...")

            # Get old videos
            old_videos = self.supabase.get_old_videos(days_old)

            if not old_videos:
                print(f"✅ No old videos to cleanup")
                return

            print(f"📋 Found {len(old_videos)} old video(s) to delete")

            for video in old_videos:
                try:
                    date_str = video['date']
                    channel = video['channel_code']
                    video_num = video['video_number']

                    print(f"\n🗑️ Deleting: {date_str}/{channel}/video_{video_num}")

                    # Delete organized folder (contains all files)
                    if video.get('organized_folder_id'):
                        self.gdrive.delete_folder(video['organized_folder_id'])
                        print(f"✅ Folder deleted")

                    # Mark as deleted in database
                    self.supabase.update_video_tracking(video['id'], {
                        'status': 'deleted'
                    })

                except Exception as e:
                    print(f"⚠️ Error deleting {video['id']}: {e}")

            print(f"\n✅ Cleanup complete!")

        except Exception as e:
            print(f"❌ Cleanup error: {e}")


# Helper function for easy import
def create_organizer(supabase_client, gdrive_manager, parent_folder_id: str = None):
    """
    Factory function to create organizer instance

    Args:
        supabase_client: SupabaseClient instance
        gdrive_manager: GDriveImageManager instance
        parent_folder_id: Optional parent folder ID (default from env)

    Returns:
        DailyVideoOrganizer instance
    """
    if not parent_folder_id:
        parent_folder_id = os.getenv("DAILY_VIDEO_PARENT_FOLDER", "1ZKnCa-7ieNt3bLhI6f6mCZBmyAP0-dnF")

    return DailyVideoOrganizer(supabase_client, gdrive_manager, parent_folder_id)
