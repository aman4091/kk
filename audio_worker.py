#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Audio Worker - Runs on Vast.ai with GPU
Processes audio generation jobs from queue (Supabase + Google Drive)
"""

import os
import sys
import time
import asyncio
import platform
import torch
import hashlib
from datetime import datetime
from pathlib import Path

# Fix console encoding if needed
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file if exists
from dotenv import load_dotenv
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
    print(f"✅ Loaded environment from: {env_path}")
else:
    print(f"⚠️  No .env file found at: {env_path}")

from supabase_client import SupabaseClient
from gdrive_manager import GDriveImageManager
from f5_tts.api import F5TTS


class AudioWorker:
    """Vast.ai audio generation worker"""

    def __init__(self):
        """Initialize worker"""
        # Worker identification
        vastai_instance = os.getenv("VAST_CONTAINERLABEL", "local")
        default_worker_id = f"vastai_{vastai_instance}_{platform.node()}"
        self.worker_id = os.getenv("WORKER_ID", default_worker_id)
        self.hostname = platform.node()
        self.vastai_instance_id = vastai_instance

        # Detect GPU
        if torch.cuda.is_available():
            self.gpu_model = torch.cuda.get_device_name(0)
        else:
            self.gpu_model = "CPU (No CUDA)"
            print("⚠️  WARNING: Running without GPU! Audio generation will be SLOW.")

        # Initialize clients
        print("🔄 Initializing worker components...", flush=True)
        self.supabase = SupabaseClient()
        self.gdrive = GDriveImageManager()

        # Initialize F5-TTS model
        print("🔄 Loading F5-TTS model...", flush=True)
        self.f5_model = F5TTS()
        print("✅ F5-TTS model loaded", flush=True)

        # Reference audio settings
        self.reference_audio_folder_id = os.getenv("GDRIVE_REFERENCE_AUDIO_FOLDER")
        self.reference_audio_path = None
        self.reference_audio_checksum = None
        self.last_reference_check = None

        # Audio generation settings
        self.chunk_size = int(os.getenv("CHUNK_SIZE", "500"))
        self.audio_speed = float(os.getenv("AUDIO_SPEED", "1.0"))

        # Google Drive folders
        self.output_folder_id = os.getenv("GDRIVE_VIDEO_OUTPUT_FOLDER")
        self.parent_organized_folder_id = os.getenv("GDRIVE_ORGANIZED_PARENT_FOLDER")

        # Telegram bot token for notifications
        self.bot_token = os.getenv("BOT_TOKEN")

        # Working directory for temp files
        self.work_dir = os.path.expanduser("~/audio_worker_temp")
        os.makedirs(self.work_dir, exist_ok=True)

        # Output directory for generated audio
        self.output_dir = os.path.join(self.work_dir, "output")
        os.makedirs(self.output_dir, exist_ok=True)

        # Configuration
        self.poll_interval = 30  # Check every 30 seconds
        self.max_retries = 3
        self.heartbeat_interval = 5  # Send heartbeat every 5 polls
        self.reference_sync_interval = 300  # Check reference audio every 5 minutes

        print(f"✅ Worker ID: {self.worker_id}", flush=True)
        print(f"✅ GPU: {self.gpu_model}", flush=True)
        print(f"✅ Work directory: {self.work_dir}", flush=True)
        print(f"✅ Poll interval: {self.poll_interval}s", flush=True)

    def register_worker(self):
        """Register worker in database"""
        print("📝 Registering worker in database...", flush=True)
        try:
            self.supabase.client.table('audio_workers').upsert({
                'worker_id': self.worker_id,
                'hostname': self.hostname,
                'gpu_model': self.gpu_model,
                'status': 'online',
                'vastai_instance_id': self.vastai_instance_id,
                'last_heartbeat': datetime.utcnow().isoformat()
            }).execute()

            print("✅ Worker registered in database", flush=True)

        except Exception as e:
            print(f"⚠️  Worker registration failed: {e}", flush=True)

    def send_heartbeat(self):
        """Send heartbeat to mark worker as online"""
        try:
            self.supabase.client.table('audio_workers').update({
                'status': 'online',
                'last_heartbeat': datetime.utcnow().isoformat()
            }).eq('worker_id', self.worker_id).execute()

        except Exception as e:
            print(f"⚠️  Heartbeat failed: {e}")

    def get_pending_job(self):
        """
        Get next pending job from queue and atomically claim it

        Returns:
            Job dict or None
        """
        print("🔍 Checking for pending jobs...", flush=True)
        try:
            # Get pending jobs ordered by priority
            result = self.supabase.client.table('audio_jobs')\
                .select('*')\
                .eq('status', 'pending')\
                .order('priority', desc=True)\
                .order('created_at', desc=False)\
                .limit(1)\
                .execute()

            if not result.data:
                print(f"⏳ No pending jobs found", flush=True)
                return None

            job = result.data[0]
            job_id = job['job_id']

            print(f"📋 Found pending job: {job_id[:12]}..., attempting to claim...", flush=True)

            # Atomically claim the job
            claim_result = self.supabase.client.table('audio_jobs')\
                .update({
                    'status': 'processing',
                    'processing_started_at': datetime.utcnow().isoformat(),
                    'worker_id': self.worker_id
                })\
                .eq('job_id', job_id)\
                .eq('status', 'pending')\
                .execute()

            if not claim_result.data:
                print(f"⚠️  Failed to claim job {job_id[:12]}... (another worker grabbed it)", flush=True)
                return None

            print(f"✅ Successfully claimed job: {job_id[:12]}...", flush=True)
            return job

        except Exception as e:
            print(f"❌ Error fetching job: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return None

    def mark_job_completed(self, job_id: str, audio_gdrive_id: str, gofile_link: str = None):
        """Mark job as completed"""
        try:
            self.supabase.client.table('audio_jobs').update({
                'status': 'completed',
                'completed_at': datetime.utcnow().isoformat(),
                'audio_gdrive_id': audio_gdrive_id,
                'gofile_link': gofile_link
            }).eq('job_id', job_id).execute()

            # Update worker stats
            worker = self.supabase.client.table('audio_workers')\
                .select('jobs_completed')\
                .eq('worker_id', self.worker_id)\
                .execute()

            if worker.data:
                current_count = worker.data[0].get('jobs_completed', 0)
                self.supabase.client.table('audio_workers').update({
                    'jobs_completed': current_count + 1
                }).eq('worker_id', self.worker_id).execute()

            print(f"✅ Job {job_id[:12]}... marked as completed")

        except Exception as e:
            print(f"❌ Failed to mark job completed: {e}")

    def mark_job_failed(self, job_id: str, error_msg: str):
        """Mark job as failed"""
        try:
            # Get current retry count
            job = self.supabase.client.table('audio_jobs')\
                .select('retry_count')\
                .eq('job_id', job_id)\
                .execute()

            retry_count = job.data[0].get('retry_count', 0) + 1 if job.data else 1

            # Determine status
            status = 'failed' if retry_count >= self.max_retries else 'pending'

            self.supabase.client.table('audio_jobs').update({
                'status': status,
                'error_message': error_msg[:500],
                'retry_count': retry_count
            }).eq('job_id', job_id).execute()

            # Update worker stats if permanently failed
            if status == 'failed':
                worker = self.supabase.client.table('audio_workers')\
                    .select('jobs_failed')\
                    .eq('worker_id', self.worker_id)\
                    .execute()

                if worker.data:
                    current_count = worker.data[0].get('jobs_failed', 0)
                    self.supabase.client.table('audio_workers').update({
                        'jobs_failed': current_count + 1
                    }).eq('worker_id', self.worker_id).execute()

            print(f"❌ Job {job_id[:12]}... marked as {status} (retry {retry_count}/{self.max_retries})")

        except Exception as e:
            print(f"❌ Failed to mark job failed: {e}")

    async def sync_reference_audio(self, gdrive_id: str) -> bool:
        """
        Download or update reference audio from Google Drive

        Args:
            gdrive_id: Google Drive file ID

        Returns:
            True if successfully synced
        """
        try:
            # Define local path
            ref_audio_path = os.path.join(self.work_dir, "reference_audio.wav")

            # Check if we already have this version (using checksum)
            needs_download = True

            if os.path.exists(ref_audio_path) and self.reference_audio_checksum:
                # Get current file checksum
                current_checksum = self._calculate_file_checksum(ref_audio_path)

                # Check database for the checksum of this gdrive_id
                result = self.supabase.client.table('reference_audio_sync')\
                    .select('checksum')\
                    .eq('gdrive_id', gdrive_id)\
                    .execute()

                if result.data and result.data[0].get('checksum') == current_checksum:
                    print(f"✅ Reference audio already up to date")
                    needs_download = False

            if needs_download:
                print(f"📥 Downloading reference audio from GDrive: {gdrive_id}")

                if not self.download_from_gdrive(gdrive_id, ref_audio_path):
                    print(f"❌ Failed to download reference audio")
                    return False

                # Calculate new checksum
                self.reference_audio_checksum = self._calculate_file_checksum(ref_audio_path)
                print(f"✅ Reference audio downloaded: {ref_audio_path}")

            # Update reference audio path
            self.reference_audio_path = ref_audio_path
            self.last_reference_check = time.time()

            return True

        except Exception as e:
            print(f"❌ Error syncing reference audio: {e}")
            return False

    def download_from_gdrive(self, file_id: str, output_path: str) -> bool:
        """Download file from Google Drive"""
        try:
            request = self.gdrive.service.files().get_media(fileId=file_id)

            with open(output_path, 'wb') as f:
                from googleapiclient.http import MediaIoBaseDownload
                downloader = MediaIoBaseDownload(f, request)

                done = False
                while not done:
                    status, done = downloader.next_chunk()
                    if status:
                        print(f"   Download progress: {int(status.progress() * 100)}%")

            return True

        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False

    def _calculate_file_checksum(self, file_path: str) -> str:
        """Calculate SHA256 checksum of file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    async def generate_audio_f5(self, script_text: str, job_id: str):
        """
        Generate audio using F5-TTS

        Args:
            script_text: Text to convert to audio
            job_id: Job ID for file naming

        Returns:
            Tuple[success: bool, output_path: str or error_msg: str]
        """
        try:
            print(f"🔄 F5-TTS generation starting for job {job_id[:12]}...")
            print(f"📝 Script length: {len(script_text)} characters")
            print(f"🎵 Reference: {self.reference_audio_path}")

            # Output path
            base_output_path = os.path.join(self.output_dir, f"{job_id}_raw")
            raw_output = f"{base_output_path}.wav"

            # Split text into chunks
            chunks = self.split_text_into_chunks(script_text, self.chunk_size)
            print(f"📊 Split into {len(chunks)} chunks ({self.chunk_size} chars each)")

            # Generate audio for each chunk
            audio_segments = []

            for i, chunk in enumerate(chunks):
                print(f"📄 Processing chunk {i+1}/{len(chunks)}")

                # Clear CUDA memory before each chunk
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

                # F5-TTS API call
                with torch.inference_mode():
                    result = self.f5_model.infer(
                        ref_file=self.reference_audio_path,
                        ref_text="",  # Auto-extract
                        gen_text=chunk,
                        remove_silence=True,
                        cross_fade_duration=0.15,
                        speed=self.audio_speed,
                        nfe_step=32,
                        cfg_strength=1.5,
                        target_rms=0.1
                    )

                # Extract audio data
                if isinstance(result, tuple):
                    audio_data = result[0]
                else:
                    audio_data = result

                # Move to CPU to save VRAM
                if torch.is_tensor(audio_data):
                    audio_data = audio_data.cpu()

                audio_segments.append(audio_data)

                # Cleanup
                del result
                import gc
                gc.collect()
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

            print("🔗 Combining audio segments...")

            # Concatenate all segments
            if torch.is_tensor(audio_segments[0]):
                final_audio = torch.cat(audio_segments, dim=-1).cpu()
            else:
                import numpy as np
                final_audio = np.concatenate(audio_segments)

            # Save raw audio
            print(f"💾 Saving raw audio to {raw_output}...")
            if torch.is_tensor(final_audio):
                if final_audio.dim() == 1:
                    final_audio = final_audio.unsqueeze(0)
                import torchaudio
                torchaudio.save(raw_output, final_audio, 24000)
            else:
                import soundfile as sf
                sf.write(raw_output, final_audio, 24000)

            print(f"✅ Audio generation complete: {raw_output}")
            return True, raw_output

        except Exception as e:
            error_msg = f"F5-TTS generation error: {str(e)}"
            print(f"❌ {error_msg}")
            import traceback
            traceback.print_exc()
            return False, error_msg

    def split_text_into_chunks(self, text, max_length):
        """Split text into chunks"""
        import re

        # Split by sentences first
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())

        chunks = []
        current_chunk = ""

        for sentence in sentences:
            if len(current_chunk) + len(sentence) + 1 <= max_length:
                current_chunk += sentence + " "
            else:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                current_chunk = sentence + " "

        if current_chunk:
            chunks.append(current_chunk.strip())

        # If no chunks created (single long sentence), force split
        if not chunks:
            chunks = [text[i:i + max_length] for i in range(0, len(text), max_length)]

        return chunks

    def upload_audio_to_gdrive(self, file_path: str, target_folder_id: str, filename: str) -> str:
        """
        Upload audio file to Google Drive

        Args:
            file_path: Local file path
            target_folder_id: Target folder ID in GDrive
            filename: Target filename

        Returns:
            File ID or None
        """
        try:
            from googleapiclient.http import MediaFileUpload

            service = self.gdrive.service

            file_metadata = {
                'name': filename,
                'parents': [target_folder_id]
            }

            media = MediaFileUpload(file_path, resumable=True)

            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

            file_id = file.get('id')
            print(f"✅ Uploaded to GDrive: {file_id}")
            return file_id

        except Exception as e:
            print(f"❌ GDrive upload error: {e}")
            return None

    async def send_telegram_notification(self, chat_id: str, message: str):
        """Send Telegram notification"""
        try:
            import telegram
            bot = telegram.Bot(token=self.bot_token)
            await bot.send_message(chat_id=chat_id, text=message)
            print(f"✅ Telegram notification sent to {chat_id}")

        except Exception as e:
            print(f"⚠️  Telegram notification failed: {e}")

    async def update_daily_video_tracking(self, job):
        """
        Update daily_video_tracking table with audio GDrive ID

        Args:
            job: Job dictionary with channel_code, video_number, date, audio_gdrive_id
        """
        try:
            if not all([job.get('channel_code'), job.get('video_number'), job.get('date')]):
                print("⏭️  Skipping daily_video_tracking update (not a daily video)")
                return

            # Update the tracking record
            result = self.supabase.client.table('daily_video_tracking')\
                .update({
                    'audio_gdrive_id': job['audio_gdrive_id'],
                    'status': 'audio_done'
                })\
                .eq('date', job['date'])\
                .eq('channel_code', job['channel_code'])\
                .eq('video_number', job['video_number'])\
                .execute()

            if result.data:
                print(f"✅ Updated daily_video_tracking for {job['channel_code']} video {job['video_number']}")
            else:
                print(f"⚠️  No matching daily_video_tracking record found")

        except Exception as e:
            print(f"❌ Error updating daily_video_tracking: {e}")

    def get_organized_folder_path(self, date: str, channel_code: str, video_number: int) -> str:
        """
        Get the organized folder ID for daily video

        Returns:
            Folder ID where audio should be uploaded
        """
        try:
            # Format: Parent/YYYY-MM-DD/CHANNEL_CODE/video_X/
            # We need to find or create this structure

            # For simplicity, let's just return the parent folder for now
            # The full folder structure creation can be added later if needed
            return self.parent_organized_folder_id or self.output_folder_id

        except Exception as e:
            print(f"❌ Error getting organized folder: {e}")
            return self.output_folder_id

    async def process_job(self, job):
        """
        Process an audio generation job

        Steps:
        1. Sync reference audio if needed
        2. Generate audio with F5-TTS
        3. Upload audio to Google Drive
        4. Update daily_video_tracking (if applicable)
        5. Send Telegram notification
        6. Mark job completed
        7. Cleanup temp files
        """
        job_id = job['job_id']
        chat_id = job['chat_id']
        script_text = job['script_text']

        try:
            print(f"\n{'='*60}", flush=True)
            print(f"🎙️  Processing Audio Job: {job_id[:12]}...", flush=True)
            print(f"   Chat ID: {chat_id}", flush=True)
            print(f"   Channel: {job.get('channel_code', 'N/A')}", flush=True)
            print(f"   Script: {len(script_text)} chars", flush=True)
            print(f"{'='*60}\n", flush=True)

            # 1. Sync reference audio
            reference_gdrive_id = job.get('reference_audio_gdrive_id')
            if reference_gdrive_id:
                print(f"📥 Syncing reference audio...")
                if not await self.sync_reference_audio(reference_gdrive_id):
                    raise Exception("Failed to sync reference audio")
            else:
                print(f"⚠️  No reference audio specified, using default")

            # 2. Generate audio
            print(f"🎵 Generating audio...")
            success, result = await self.generate_audio_f5(script_text, job_id)

            if not success:
                raise Exception(result)  # result contains error message

            audio_path = result  # result contains output path

            # 3. Upload to Google Drive
            print(f"📤 Uploading audio to Google Drive...")

            # Determine target folder and filename
            if job.get('channel_code') and job.get('video_number'):
                # Daily video - upload to organized folder
                target_folder_id = self.get_organized_folder_path(
                    job.get('date'),
                    job.get('channel_code'),
                    job.get('video_number')
                )
                filename = "audio.wav"
            else:
                # Other audio - upload to output folder
                target_folder_id = self.output_folder_id
                audio_counter = job.get('audio_counter', job_id[:8])
                filename = f"{audio_counter}_raw.wav"

            audio_gdrive_id = self.upload_audio_to_gdrive(
                audio_path,
                target_folder_id,
                filename
            )

            if not audio_gdrive_id:
                raise Exception("Failed to upload audio to GDrive")

            # Store gdrive_id in job for later use
            job['audio_gdrive_id'] = audio_gdrive_id

            # 4. Update daily_video_tracking (if applicable)
            await self.update_daily_video_tracking(job)

            # 5. Send Telegram notification
            print(f"📱 Sending notification to user...")
            notification_msg = f"✅ Audio generation complete!\n\n"
            if job.get('channel_code'):
                notification_msg += f"Channel: {job['channel_code']}\n"
            if job.get('video_number'):
                notification_msg += f"Video: #{job['video_number']}\n"
            notification_msg += f"Job ID: {job_id[:12]}...\n"
            notification_msg += f"\nAudio uploaded to Google Drive.\n"
            notification_msg += f"Video will be generated automatically."

            await self.send_telegram_notification(chat_id, notification_msg)

            # 6. Mark job completed
            self.mark_job_completed(job_id, audio_gdrive_id)

            # 7. Cleanup temp files
            try:
                os.remove(audio_path)
                print(f"🗑️  Cleaned up temp file: {audio_path}")
            except:
                pass

            print(f"\n{'='*60}", flush=True)
            print(f"✅ Job {job_id[:12]}... completed successfully!", flush=True)
            print(f"{'='*60}\n", flush=True)

        except Exception as e:
            error_msg = f"Job processing error: {str(e)}"
            print(f"❌ {error_msg}", flush=True)
            import traceback
            traceback.print_exc()

            # Mark job as failed
            self.mark_job_failed(job_id, error_msg)

            # Send error notification
            try:
                error_notification = f"❌ Audio generation failed\n\nJob ID: {job_id[:12]}...\nError: {str(e)[:200]}"
                await self.send_telegram_notification(chat_id, error_notification)
            except:
                pass

    async def run(self):
        """Main worker loop"""
        print(f"\n{'='*60}", flush=True)
        print(f"🚀 Audio Worker Starting", flush=True)
        print(f"{'='*60}\n", flush=True)

        # Register worker
        self.register_worker()

        poll_count = 0

        try:
            while True:
                # Send heartbeat every N polls
                if poll_count % self.heartbeat_interval == 0:
                    self.send_heartbeat()

                # Get and process job
                job = self.get_pending_job()

                if job:
                    await self.process_job(job)
                else:
                    # No jobs, wait before next poll
                    print(f"💤 Waiting {self.poll_interval}s before next poll...")
                    await asyncio.sleep(self.poll_interval)

                poll_count += 1

        except KeyboardInterrupt:
            print(f"\n🛑 Worker stopped by user", flush=True)

        except Exception as e:
            print(f"\n❌ Worker crashed: {e}", flush=True)
            import traceback
            traceback.print_exc()

        finally:
            # Mark worker as offline
            try:
                self.supabase.client.table('audio_workers').update({
                    'status': 'offline'
                }).eq('worker_id', self.worker_id).execute()
                print(f"✅ Worker marked as offline", flush=True)
            except:
                pass


if __name__ == "__main__":
    worker = AudioWorker()
    asyncio.run(worker.run())
