#!/usr/bin/env python3
"""
Video Queue Manager - Cloud Side
Creates video jobs and uploads to queue (Supabase + Google Drive)
"""

import os
import json
import tempfile
from datetime import datetime
from typing import Optional, Tuple


class VideoQueueManager:
    """Manages video job queue on cloud side (Vast.ai)"""

    def __init__(self, supabase_client, gdrive_manager):
        """
        Initialize queue manager

        Args:
            supabase_client: SupabaseClient instance
            gdrive_manager: GDriveImageManager instance
        """
        self.supabase = supabase_client
        self.gdrive = gdrive_manager

        # Google Drive folder IDs from environment
        self.queue_folder_id = os.getenv("GDRIVE_VIDEO_QUEUE_FOLDER")

        if not self.queue_folder_id:
            print("⚠️  GDRIVE_VIDEO_QUEUE_FOLDER not set in environment")

        print("✅ VideoQueueManager initialized")

    async def create_video_job(self, audio_path: str, image_path: str,
                               counter: int, chat_id: int,
                               subtitle_style: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Create video job and upload to queue

        Steps:
        1. Upload audio to Google Drive queue folder
        2. Upload image to Google Drive queue folder
        3. Create metadata JSON
        4. Insert job into Supabase video_jobs table

        Args:
            audio_path: Local path to audio file
            image_path: Local path to image file
            counter: Job ID (counter number)
            chat_id: Telegram chat ID
            subtitle_style: ASS subtitle style string

        Returns:
            Tuple[success: bool, job_id: str or None, queue_audio_id: str or None]
        """
        # Generate unique job_id (use counter if available, otherwise timestamp)
        import time
        if counter is not None and counter > 0:
            job_id = str(counter)
        else:
            job_id = str(int(time.time()))

        try:
            print(f"\n{'='*60}")
            print(f"📋 Creating video job: {job_id}")
            print(f"{'='*60}")

            # Check if queue folder is configured
            if not self.queue_folder_id:
                print("❌ Queue folder not configured!")
                print("   Set GDRIVE_VIDEO_QUEUE_FOLDER in environment")
                return False, None

            # 1. Upload audio to Google Drive queue folder
            print(f"📤 Uploading audio to queue folder...")
            audio_filename = f"{job_id}_audio.wav"

            audio_file_id = await self._upload_to_queue(
                audio_path,
                audio_filename
            )

            if not audio_file_id:
                print(f"❌ Failed to upload audio")
                return False, None

            print(f"✅ Audio uploaded: {audio_file_id}")

            # 2. Upload image to Google Drive queue folder
            print(f"📤 Uploading image to queue folder...")
            image_filename = f"{job_id}_image.jpg"

            image_file_id = await self._upload_to_queue(
                image_path,
                image_filename
            )

            if not image_file_id:
                print(f"❌ Failed to upload image")
                # Cleanup: delete audio
                self.gdrive.delete_file(audio_file_id)
                return False, None

            print(f"✅ Image uploaded: {image_file_id}")

            # 3. Insert job into Supabase
            print(f"💾 Creating job record in database...")

            job_data = {
                'job_id': job_id,
                'chat_id': str(chat_id),
                'status': 'pending',
                'audio_gdrive_id': audio_file_id,
                'image_gdrive_id': image_file_id,
                'subtitle_style': subtitle_style or '',
                'priority': 0
            }

            result = self.supabase.client.table('video_jobs').insert(job_data).execute()

            if not result.data:
                print(f"❌ Failed to create job in database")
                # Cleanup
                self.gdrive.delete_file(audio_file_id)
                self.gdrive.delete_file(image_file_id)
                return False, None

            print(f"✅ Job created in database")
            print(f"📊 Job details:")
            print(f"   Job ID: {job_id}")
            print(f"   Chat ID: {chat_id}")
            print(f"   Audio: {audio_file_id}")
            print(f"   Image: {image_file_id}")
            print(f"   Status: pending")
            print(f"{'='*60}\n")

            return True, job_id, audio_file_id

        except Exception as e:
            print(f"❌ Error creating video job: {e}")
            import traceback
            traceback.print_exc()
            return False, None, None

    async def _upload_to_queue(self, file_path: str, filename: str) -> Optional[str]:
        """
        Upload file to Google Drive queue folder

        Args:
            file_path: Local file path
            filename: Filename to use in GDrive

        Returns:
            File ID or None if failed
        """
        try:
            # Use synchronous upload wrapped in asyncio.to_thread
            import asyncio

            file_id = await asyncio.to_thread(
                self._upload_file_sync,
                file_path,
                filename
            )

            return file_id

        except Exception as e:
            print(f"❌ Upload failed: {e}")
            return None

    def _upload_file_sync(self, file_path: str, filename: str) -> Optional[str]:
        """
        Synchronous file upload to Google Drive

        Args:
            file_path: Local file path
            filename: Target filename

        Returns:
            File ID or None
        """
        try:
            from googleapiclient.http import MediaFileUpload

            # Get GDrive service
            service = self.gdrive.service

            file_metadata = {
                'name': filename,
                'parents': [self.queue_folder_id]
            }

            media = MediaFileUpload(file_path, resumable=True)

            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

            return file.get('id')

        except Exception as e:
            print(f"❌ GDrive upload error: {e}")
            return None

    def get_job_status(self, job_id: str) -> Optional[dict]:
        """
        Get job status from database

        Args:
            job_id: Job ID to check

        Returns:
            Job data dict or None
        """
        try:
            result = self.supabase.client.table('video_jobs')\
                .select('*')\
                .eq('job_id', job_id)\
                .execute()

            if result.data:
                return result.data[0]
            return None

        except Exception as e:
            print(f"❌ Error getting job status: {e}")
            return None

    def get_pending_jobs_count(self) -> int:
        """
        Get count of pending jobs in queue

        Returns:
            Number of pending jobs
        """
        try:
            result = self.supabase.client.table('video_jobs')\
                .select('job_id', count='exact')\
                .eq('status', 'pending')\
                .execute()

            return result.count or 0

        except Exception as e:
            print(f"❌ Error counting jobs: {e}")
            return 0
