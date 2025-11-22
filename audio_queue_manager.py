#!/usr/bin/env python3
"""
Audio Queue Manager - Bot Side (Contabo)
Creates audio jobs and manages queue (Supabase + Google Drive)
"""

import os
import uuid
import hashlib
from datetime import datetime
from typing import Optional, Tuple, Dict
from pathlib import Path


class AudioQueueManager:
    """Manages audio job queue on bot side (Contabo)"""

    def __init__(self, supabase_client, gdrive_manager):
        """
        Initialize audio queue manager

        Args:
            supabase_client: SupabaseClient instance
            gdrive_manager: GDriveImageManager instance
        """
        self.supabase = supabase_client
        self.gdrive = gdrive_manager

        # Google Drive folder ID for reference audio sync
        self.reference_audio_folder_id = os.getenv("GDRIVE_REFERENCE_AUDIO_FOLDER")

        if not self.reference_audio_folder_id:
            print("⚠️  GDRIVE_REFERENCE_AUDIO_FOLDER not set in environment")

        print("✅ AudioQueueManager initialized")

    async def create_audio_job(
        self,
        script_text: str,
        chat_id: int,
        channel_code: Optional[str] = None,
        video_number: Optional[int] = None,
        date: Optional[str] = None,
        audio_counter: Optional[int] = None,
        channel_shortform: Optional[str] = None,
        script_gdrive_id: Optional[str] = None,
        priority: int = 0
    ) -> Tuple[bool, Optional[str]]:
        """
        Create audio generation job in queue

        Args:
            script_text: The script text to convert to audio
            chat_id: Telegram chat ID for notification
            channel_code: Channel identifier (BI, AFG, etc.) for daily videos
            video_number: Video number (1-4) for daily videos
            date: Date for daily video tracking (YYYY-MM-DD format)
            audio_counter: Sequential counter for audio file naming
            channel_shortform: Short channel name for batch processing
            script_gdrive_id: GDrive ID if script is stored in GDrive
            priority: Job priority (higher = processed first)

        Returns:
            Tuple[success: bool, job_id: str or None]
        """
        # Generate unique job_id
        job_id = str(uuid.uuid4())

        try:
            print(f"\n{'='*60}")
            print(f"🎙️  Creating audio job: {job_id[:8]}...")
            print(f"{'='*60}")

            # Get current reference audio GDrive ID
            reference_audio_gdrive_id = await self._get_current_reference_audio_id()

            # Prepare job data
            job_data = {
                'job_id': job_id,
                'chat_id': str(chat_id),
                'status': 'pending',
                'script_text': script_text,
                'script_gdrive_id': script_gdrive_id,
                'channel_code': channel_code,
                'video_number': video_number,
                'date': date,
                'audio_counter': audio_counter,
                'channel_shortform': channel_shortform,
                'reference_audio_gdrive_id': reference_audio_gdrive_id,
                'priority': priority,
                'retry_count': 0
            }

            # Insert into Supabase
            print(f"💾 Inserting job into audio_jobs table...")
            result = self.supabase.client.table('audio_jobs').insert(job_data).execute()

            if not result.data:
                print(f"❌ Failed to create audio job in database")
                return False, None

            print(f"✅ Audio job created successfully")
            print(f"📊 Job details:")
            print(f"   Job ID: {job_id[:12]}...")
            print(f"   Chat ID: {chat_id}")
            print(f"   Channel: {channel_code or 'N/A'}")
            print(f"   Video #: {video_number or 'N/A'}")
            print(f"   Counter: {audio_counter or 'N/A'}")
            print(f"   Script length: {len(script_text)} chars")
            print(f"   Priority: {priority}")
            print(f"{'='*60}\n")

            return True, job_id

        except Exception as e:
            print(f"❌ Error creating audio job: {e}")
            import traceback
            traceback.print_exc()
            return False, None

    async def _get_current_reference_audio_id(self) -> Optional[str]:
        """
        Get the current reference audio GDrive ID from database

        Returns:
            GDrive ID of current reference audio or None
        """
        try:
            result = self.supabase.client.table('reference_audio_sync')\
                .select('gdrive_id')\
                .eq('is_current', True)\
                .order('last_modified', desc=True)\
                .limit(1)\
                .execute()

            if result.data and len(result.data) > 0:
                gdrive_id = result.data[0].get('gdrive_id')
                print(f"📎 Using reference audio: {gdrive_id}")
                return gdrive_id
            else:
                print(f"⚠️  No current reference audio found in database")
                return None

        except Exception as e:
            print(f"❌ Error getting reference audio: {e}")
            return None

    async def sync_reference_audio_to_gdrive(
        self,
        local_path: str,
        chat_id: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Upload reference audio to Google Drive and register in database

        Args:
            local_path: Path to local reference audio file
            chat_id: Chat ID that uploaded this reference (for tracking)

        Returns:
            Tuple[success: bool, gdrive_id: str or None]
        """
        try:
            print(f"\n{'='*60}")
            print(f"📤 Syncing reference audio to GDrive...")
            print(f"{'='*60}")

            if not self.reference_audio_folder_id:
                print("❌ Reference audio folder not configured!")
                print("   Set GDRIVE_REFERENCE_AUDIO_FOLDER in environment")
                return False, None

            # Check if file exists
            if not os.path.exists(local_path):
                print(f"❌ File not found: {local_path}")
                return False, None

            # Calculate file checksum
            checksum = self._calculate_file_checksum(local_path)
            file_size = os.path.getsize(local_path)

            # Upload to GDrive
            print(f"📤 Uploading to GDrive reference audio folder...")
            filename = f"reference_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"

            gdrive_id = await self._upload_reference_audio_sync(local_path, filename)

            if not gdrive_id:
                print(f"❌ Failed to upload reference audio to GDrive")
                return False, None

            print(f"✅ Uploaded to GDrive: {gdrive_id}")

            # Get file modified time from GDrive
            last_modified = datetime.utcnow()

            # Insert into reference_audio_sync table
            print(f"💾 Registering in database...")

            sync_data = {
                'gdrive_id': gdrive_id,
                'local_path': local_path,
                'last_modified': last_modified.isoformat(),
                'file_size_bytes': file_size,
                'is_current': True,  # This will trigger the function to mark others as False
                'created_by': str(chat_id) if chat_id else None,
                'checksum': checksum,
                'last_synced_at': datetime.utcnow().isoformat()
            }

            result = self.supabase.client.table('reference_audio_sync')\
                .insert(sync_data)\
                .execute()

            if not result.data:
                print(f"❌ Failed to register reference audio in database")
                # Note: File is uploaded to GDrive but not tracked. Manual cleanup may be needed.
                return False, None

            print(f"✅ Reference audio synced successfully")
            print(f"📊 Sync details:")
            print(f"   GDrive ID: {gdrive_id}")
            print(f"   Checksum: {checksum[:16]}...")
            print(f"   Size: {file_size} bytes")
            print(f"{'='*60}\n")

            return True, gdrive_id

        except Exception as e:
            print(f"❌ Error syncing reference audio: {e}")
            import traceback
            traceback.print_exc()
            return False, None

    async def _upload_reference_audio_sync(self, file_path: str, filename: str) -> Optional[str]:
        """
        Upload reference audio to Google Drive synchronously

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
                'parents': [self.reference_audio_folder_id]
            }

            media = MediaFileUpload(file_path, resumable=True)

            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,modifiedTime'
            ).execute()

            return file.get('id')

        except Exception as e:
            print(f"❌ GDrive upload error: {e}")
            return None

    def _calculate_file_checksum(self, file_path: str) -> str:
        """
        Calculate SHA256 checksum of file

        Args:
            file_path: Path to file

        Returns:
            Hex digest of SHA256 hash
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def get_job_status(self, job_id: str) -> Optional[Dict]:
        """
        Get audio job status from database

        Args:
            job_id: Job ID to check

        Returns:
            Job data dict or None
        """
        try:
            result = self.supabase.client.table('audio_jobs')\
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
        Get count of pending audio jobs in queue

        Returns:
            Number of pending jobs
        """
        try:
            result = self.supabase.client.table('audio_jobs')\
                .select('job_id', count='exact')\
                .eq('status', 'pending')\
                .execute()

            return result.count or 0

        except Exception as e:
            print(f"❌ Error counting jobs: {e}")
            return 0

    def get_processing_jobs_count(self) -> int:
        """
        Get count of currently processing audio jobs

        Returns:
            Number of processing jobs
        """
        try:
            result = self.supabase.client.table('audio_jobs')\
                .select('job_id', count='exact')\
                .eq('status', 'processing')\
                .execute()

            return result.count or 0

        except Exception as e:
            print(f"❌ Error counting processing jobs: {e}")
            return 0

    async def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a pending audio job

        Args:
            job_id: Job ID to cancel

        Returns:
            True if successfully cancelled
        """
        try:
            # Can only cancel pending jobs
            result = self.supabase.client.table('audio_jobs')\
                .update({'status': 'failed', 'error_message': 'Cancelled by user'})\
                .eq('job_id', job_id)\
                .eq('status', 'pending')\
                .execute()

            if result.data:
                print(f"✅ Job {job_id[:8]}... cancelled")
                return True
            else:
                print(f"⚠️  Job {job_id[:8]}... not found or already processing")
                return False

        except Exception as e:
            print(f"❌ Error cancelling job: {e}")
            return False
