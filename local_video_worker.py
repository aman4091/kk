#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Video Worker - Runs on PC with RTX 4060
Processes video jobs from queue (Supabase + Google Drive)
"""

import os
import sys
import time
import json
import asyncio
import platform
from datetime import datetime
from pathlib import Path

# Fix Windows console encoding
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
    print(f"⚠️ No .env file found at: {env_path}")

from supabase_client import SupabaseClient
from gdrive_manager import GDriveImageManager
from video_generator import VideoGenerator


class LocalVideoWorker:
    """Local PC video encoding worker"""

    def __init__(self):
        """Initialize worker"""
        # Worker identification (from env or default)
        default_worker_id = f"{platform.node()}_RTX4060"
        self.worker_id = os.getenv("WORKER_ID", default_worker_id)
        self.hostname = platform.node()

        # Detect GPU model (or CPU mode)
        self.gpu_model = os.getenv("GPU_MODEL", "RTX 4060")
        if os.getenv("FORCE_CPU_ENCODER", "").lower() in ("true", "1", "yes"):
            self.gpu_model += " (CPU mode)"

        # Initialize clients
        print("🔄 Initializing worker components...", flush=True)
        self.supabase = SupabaseClient()
        self.gdrive = GDriveImageManager()
        self.video_gen = VideoGenerator()

        # Google Drive folders
        self.queue_folder_id = os.getenv("GDRIVE_VIDEO_QUEUE_FOLDER")
        self.output_folder_id = os.getenv("GDRIVE_VIDEO_OUTPUT_FOLDER")

        # Telegram bot token for notifications
        self.bot_token = os.getenv("BOT_TOKEN")

        # Working directory for temp files (platform-specific)
        if sys.platform == 'win32':
            self.work_dir = "E:/video_worker_temp"
        else:
            self.work_dir = os.path.expanduser("~/video_worker_temp")
        os.makedirs(self.work_dir, exist_ok=True)

        # Configuration
        self.poll_interval = 30  # Check every 30 seconds
        self.max_retries = 3
        self.heartbeat_interval = 5  # Send heartbeat every 5 polls

        print(f"✅ Worker ID: {self.worker_id}", flush=True)
        print(f"✅ Work directory: {self.work_dir}", flush=True)
        print(f"✅ Poll interval: {self.poll_interval}s", flush=True)

    def register_worker(self):
        """Register worker in database"""
        print("📝 Registering worker in database...", flush=True)
        try:
            self.supabase.client.table('video_workers').upsert({
                'worker_id': self.worker_id,
                'hostname': self.hostname,
                'gpu_model': self.gpu_model,
                'status': 'online',
                'last_heartbeat': datetime.now().isoformat()
            }).execute()

            print("✅ Worker registered in database", flush=True)

        except Exception as e:
            print(f"⚠️  Worker registration failed: {e}", flush=True)

    def send_heartbeat(self):
        """Send heartbeat to mark worker as online"""
        try:
            self.supabase.client.table('video_workers').update({
                'status': 'online',
                'last_heartbeat': datetime.now().isoformat()
            }).eq('worker_id', self.worker_id).execute()

        except Exception as e:
            print(f"⚠️  Heartbeat failed: {e}")

    def get_pending_job(self):
        """
        Get next pending job from queue and atomically claim it

        This prevents race conditions when multiple workers are running.
        Uses atomic update to claim job before processing.

        Returns:
            Job dict or None
        """
        print("🔍 Checking for pending jobs...", flush=True)
        try:
            # Get pending jobs
            result = self.supabase.client.table('video_jobs')\
                .select('*')\
                .eq('status', 'pending')\
                .limit(1)\
                .execute()

            if not result.data:
                print(f"⏳ No pending jobs found", flush=True)
                return None

            job = result.data[0]
            job_id = job['job_id']

            print(f"📋 Found pending job: {job_id}, attempting to claim...", flush=True)

            # Atomically claim the job (only succeeds if still pending)
            # This prevents race condition if another worker grabs same job
            claim_result = self.supabase.client.table('video_jobs')\
                .update({
                    'status': 'processing',
                    'processing_started_at': datetime.now().isoformat(),
                    'worker_id': self.worker_id
                })\
                .eq('job_id', job_id)\
                .eq('status', 'pending')\
                .execute()

            if not claim_result.data:
                print(f"⚠️  Failed to claim job {job_id} (another worker grabbed it)", flush=True)
                return None

            print(f"✅ Successfully claimed job: {job_id}", flush=True)
            return job

        except Exception as e:
            print(f"❌ Error fetching job: {e}", flush=True)
            import traceback
            traceback.print_exc()
            return None

    def mark_job_processing(self, job_id: str):
        """Mark job as processing"""
        try:
            self.supabase.client.table('video_jobs').update({
                'status': 'processing',
                'processing_started_at': datetime.now().isoformat(),
                'worker_id': self.worker_id
            }).eq('job_id', job_id).execute()

        except Exception as e:
            print(f"❌ Failed to mark job processing: {e}")

    def mark_job_completed(self, job_id: str, video_gdrive_id: str, video_gofile_link: str):
        """Mark job as completed"""
        try:
            self.supabase.client.table('video_jobs').update({
                'status': 'completed',
                'completed_at': datetime.now().isoformat(),
                'video_gdrive_id': video_gdrive_id,
                'video_gofile_link': video_gofile_link
            }).eq('job_id', job_id).execute()

            # Update worker stats
            worker = self.supabase.client.table('video_workers')\
                .select('jobs_completed')\
                .eq('worker_id', self.worker_id)\
                .execute()

            if worker.data:
                current_count = worker.data[0].get('jobs_completed', 0)
                self.supabase.client.table('video_workers').update({
                    'jobs_completed': current_count + 1
                }).eq('worker_id', self.worker_id).execute()

            print(f"✅ Job {job_id} marked as completed")

        except Exception as e:
            print(f"❌ Failed to mark job completed: {e}")

    def mark_job_failed(self, job_id: str, error_msg: str):
        """Mark job as failed"""
        try:
            # Get current retry count
            job = self.supabase.client.table('video_jobs')\
                .select('retry_count')\
                .eq('job_id', job_id)\
                .execute()

            retry_count = job.data[0].get('retry_count', 0) + 1 if job.data else 1

            # Determine status
            status = 'failed' if retry_count >= self.max_retries else 'pending'

            self.supabase.client.table('video_jobs').update({
                'status': status,
                'error_message': error_msg[:500],  # Limit length
                'retry_count': retry_count
            }).eq('job_id', job_id).execute()

            # Update worker stats if permanently failed
            if status == 'failed':
                worker = self.supabase.client.table('video_workers')\
                    .select('jobs_failed')\
                    .eq('worker_id', self.worker_id)\
                    .execute()

                if worker.data:
                    current_count = worker.data[0].get('jobs_failed', 0)
                    self.supabase.client.table('video_workers').update({
                        'jobs_failed': current_count + 1
                    }).eq('worker_id', self.worker_id).execute()

            print(f"❌ Job {job_id} marked as {status} (retry {retry_count}/{self.max_retries})")

        except Exception as e:
            print(f"❌ Failed to mark job failed: {e}")

    async def send_telegram_notification(self, chat_id: str, message: str):
        """Send Telegram notification"""
        try:
            import telegram
            bot = telegram.Bot(token=self.bot_token)
            # Use plain text (no markdown) to avoid parsing errors
            await bot.send_message(chat_id=chat_id, text=message)

        except Exception as e:
            print(f"⚠️  Telegram notification failed: {e}")
            import traceback
            traceback.print_exc()

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

    async def upload_single_to_gofile(self, file_path: str) -> str:
        """Upload file to Gofile (copied from bot)"""
        try:
            import httpx

            async with httpx.AsyncClient(timeout=600.0) as client:
                # Get server
                server_response = await client.get("https://api.gofile.io/servers")
                if server_response.status_code != 200:
                    return None

                server = server_response.json().get("data", {}).get("servers", [{}])[0].get("name")

                # Upload
                with open(file_path, 'rb') as f:
                    files = {'file': f}
                    upload_response = await client.post(
                        f"https://{server}.gofile.io/contents/uploadfile",
                        files=files
                    )

                if upload_response.status_code == 200:
                    data = upload_response.json().get("data", {})
                    return data.get("downloadPage")

            return None

        except Exception as e:
            print(f"❌ Gofile upload failed: {e}")
            return None

    async def process_job(self, job):
        """
        Process a video job

        Steps:
        1. Download audio + image from Google Drive
        2. Generate video with FFmpeg (h264_nvenc - RTX 4060)
        3. Upload video to Google Drive + Gofile
        4. Update job status in database
        5. Send Telegram notification
        6. Cleanup temp files
        """
        job_id = job['job_id']
        chat_id = job['chat_id']

        audio_path = None
        image_path = None
        video_path = None

        try:
            print(f"\n{'='*60}", flush=True)
            print(f"🎬 Processing Job: {job_id}", flush=True)
            print(f"   Chat ID: {chat_id}", flush=True)
            print(f"   Created: {job['created_at']}", flush=True)
            print(f"{'='*60}\n", flush=True)

            # Job already marked as processing in get_pending_job() atomic claim
            # No need to mark again

            # 1. Download audio from Google Drive
            print(f"📥 Downloading audio from Google Drive...", flush=True)
            audio_path = os.path.join(self.work_dir, f"{job_id}_audio.wav")

            if not self.download_from_gdrive(job['audio_gdrive_id'], audio_path):
                raise Exception("Failed to download audio")

            print(f"✅ Audio downloaded: {audio_path}", flush=True)

            # 2. Download image(s) from Google Drive
            # Check if Jesus folder is active (multi-image support)
            use_multi_images = self.supabase.is_jesus_folder_active()

            if use_multi_images:
                # Jesus folder - download 10 images for transitions
                print(f"📥 Downloading 10 images from Jesus folder for transitions...", flush=True)
                folder_id = job.get('image_folder_id') or self.supabase.get_current_image_folder()

                image_paths, image_ids = self.gdrive.fetch_multiple_images_from_folder(
                    folder_id,
                    count=10,
                    download_dir=self.work_dir
                )

                if not image_paths or len(image_paths) == 0:
                    raise Exception("Failed to download images from Jesus folder")

                print(f"✅ Downloaded {len(image_paths)} images for multi-image video", flush=True)
            else:
                # Nature/Shorts folder - single image (current behaviour)
                print(f"📥 Downloading image from Google Drive...", flush=True)
                image_path = os.path.join(self.work_dir, f"{job_id}_image.jpg")

                if not self.download_from_gdrive(job['image_gdrive_id'], image_path):
                    raise Exception("Failed to download image")

                print(f"✅ Image downloaded: {image_path}", flush=True)
                image_paths = [image_path]  # Convert to list for consistency

            # 3. Generate video with subtitles
            print(f"🎬 Generating video with FFmpeg...", flush=True)
            if use_multi_images:
                print(f"⏰ This will take 50-70 minutes for multi-image video (10 images with transitions)...", flush=True)
            else:
                print(f"⏰ This will take 40-60 minutes for full video...", flush=True)
            print(f"💡 Progress updates will appear every ~30 seconds", flush=True)
            video_path = os.path.join(self.work_dir, f"{job_id}_final_video.mp4")

            subtitle_style = job.get('subtitle_style')

            # Progress callback
            async def video_progress(msg):
                print(f"   {msg}", flush=True)

            # Get event loop
            loop = asyncio.get_event_loop()

            # Create video (runs in thread to not block)
            if use_multi_images and len(image_paths) > 1:
                # Multi-image video with transitions
                final_video = await asyncio.to_thread(
                    self.video_gen.create_video_with_subtitles_multi_image,
                    image_paths,
                    audio_path,
                    video_path,
                    subtitle_style,
                    video_progress,
                    loop
                )
            else:
                # Single image video (original method)
                final_video = await asyncio.to_thread(
                    self.video_gen.create_video_with_subtitles,
                    image_paths[0],  # Use first image if list
                    audio_path,
                    video_path,
                    subtitle_style,
                    video_progress,
                    loop
                )

            if not final_video or not os.path.exists(final_video):
                raise Exception("Video generation failed")

            print(f"✅ Video generated: {final_video}")
            video_size_mb = os.path.getsize(final_video) // (1024 * 1024)
            print(f"   Size: {video_size_mb} MB")

            # 4. Upload to Google Drive (if folder configured)
            gdrive_link = None
            if self.output_folder_id:
                print(f"📤 Uploading to Google Drive...")
                gdrive_file_id = await asyncio.to_thread(
                    self._upload_to_output_folder,
                    final_video,
                    f"{job_id}_video.mp4"
                )

                if gdrive_file_id:
                    # Get shareable link
                    gdrive_link = f"https://drive.google.com/file/d/{gdrive_file_id}/view"
                    print(f"✅ GDrive uploaded: {gdrive_link}")

            # 5. Upload to Gofile
            print(f"📤 Uploading to Gofile...")
            gofile_link = await self.upload_single_to_gofile(final_video)

            if gofile_link:
                print(f"✅ Gofile uploaded: {gofile_link}")

            # 6. Mark job as completed
            self.mark_job_completed(job_id, gdrive_file_id or '', gofile_link or '')

            # 6.5. POST-PROCESS: Organize video to daily folder (if metadata available)
            try:
                # Check if this is a daily video job (has channel/video metadata)
                channel = job.get('channel_code')
                video_num = job.get('video_number')
                target_date = job.get('target_date')

                if channel and video_num and target_date and gdrive_file_id:
                    print(f"📦 Organizing video to daily folder...")
                    from daily_video_organizer import create_organizer

                    organizer = create_organizer(self.supabase, self.gdrive)

                    # Parse date if string
                    if isinstance(target_date, str):
                        from datetime import datetime
                        target_date = datetime.strptime(target_date, '%Y-%m-%d').date()

                    success = await organizer.organize_video(
                        gdrive_file_id,
                        target_date,
                        channel,
                        video_num,
                        delete_original=True  # Delete from output folder
                    )

                    if success:
                        print(f"✅ Video organized to daily folder and original deleted")
                    else:
                        print(f"⚠️ Video organization failed (non-critical)")
                else:
                    print(f"ℹ️ Not a daily video job - skipping organization")
            except Exception as org_error:
                print(f"⚠️ Video organization error (non-critical): {org_error}")
                import traceback
                traceback.print_exc()

            # 7. Send Telegram notification (plain text, no markdown)
            message = f"✅ Video Ready! Job #{job_id}\n\n"
            message += f"📹 Size: {video_size_mb} MB\n\n"

            if gofile_link:
                message += f"📥 Gofile:\n{gofile_link}\n\n"
            if gdrive_link:
                message += f"📁 GDrive:\n{gdrive_link}\n\n"

            message += f"🤖 Worker: {self.worker_id}"

            await self.send_telegram_notification(chat_id, message)

            # 8. Cleanup queue files from Google Drive
            print(f"🧹 Cleaning up queue files...")
            try:
                self.gdrive.delete_image_from_gdrive(job['audio_gdrive_id'])
                self.gdrive.delete_image_from_gdrive(job['image_gdrive_id'])
            except Exception as e:
                print(f"⚠️  Cleanup warning: {e}")

            print(f"\n✅ Job {job_id} completed successfully!")
            print(f"{'='*60}\n")

        except Exception as e:
            error_msg = str(e)
            print(f"\n❌ Job {job_id} failed: {error_msg}")
            import traceback
            traceback.print_exc()

            # Mark job as failed
            self.mark_job_failed(job_id, error_msg)

            # Send failure notification
            await self.send_telegram_notification(
                chat_id,
                f"❌ **Video Processing Failed** (Job #{job_id})\n\n"
                f"Error: {error_msg[:200]}\n\n"
                f"🤖 Worker: {self.worker_id}"
            )

        finally:
            # Cleanup local temp files
            print(f"🧹 Cleaning up local temp files...")
            for path in [audio_path, image_path, video_path]:
                if path and os.path.exists(path):
                    try:
                        os.remove(path)
                        print(f"   Deleted: {os.path.basename(path)}")
                    except:
                        pass

    def _upload_to_output_folder(self, file_path: str, filename: str) -> str:
        """Upload video to Google Drive output folder"""
        try:
            from googleapiclient.http import MediaFileUpload

            file_metadata = {
                'name': filename,
                'parents': [self.output_folder_id]
            }

            media = MediaFileUpload(file_path, resumable=True)

            file = self.gdrive.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()

            return file.get('id')

        except Exception as e:
            print(f"❌ GDrive upload failed: {e}")
            return None

    async def run(self):
        """Main worker loop"""
        print(f"\n{'='*60}", flush=True)
        print(f"🚀 Starting Video Worker", flush=True)
        print(f"   Worker ID: {self.worker_id}", flush=True)
        print(f"   Hostname: {self.hostname}", flush=True)
        print(f"   GPU/CPU: {self.gpu_model}", flush=True)
        print(f"   Poll interval: {self.poll_interval}s", flush=True)
        print(f"   Platform: {sys.platform}", flush=True)
        print(f"{'='*60}\n", flush=True)

        # Register worker
        self.register_worker()

        poll_count = 0

        try:
            while True:
                # Send heartbeat every N polls
                if poll_count % self.heartbeat_interval == 0:
                    self.send_heartbeat()

                poll_count += 1

                # Check for pending jobs
                job = self.get_pending_job()

                if job:
                    print(f"📋 Found pending job: {job['job_id']}", flush=True)
                    print(f"🚀 Starting job processing...", flush=True)
                    await self.process_job(job)
                    print(f"✅ Job processing complete", flush=True)
                else:
                    print(f"⏳ No pending jobs. Waiting {self.poll_interval}s... (poll #{poll_count})")

                # Wait before next poll
                await asyncio.sleep(self.poll_interval)

        except KeyboardInterrupt:
            print(f"\n\n⚠️  Worker stopped by user (Ctrl+C)")

            # Mark worker as offline
            try:
                self.supabase.client.table('video_workers').update({
                    'status': 'offline'
                }).eq('worker_id', self.worker_id).execute()
                print("✅ Worker marked as offline")
            except:
                pass

        except Exception as e:
            print(f"\n❌ Worker error: {e}")
            import traceback
            traceback.print_exc()

            # Wait 1 minute before restart
            print("⏳ Waiting 60 seconds before restart...")
            await asyncio.sleep(60)


if __name__ == "__main__":
    """Entry point"""
    print("🔧 Starting worker initialization...", flush=True)
    try:
        worker = LocalVideoWorker()
        print("✅ Worker object created, starting main loop...", flush=True)
        asyncio.run(worker.run())

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user", flush=True)

    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}", flush=True)
        import traceback
        traceback.print_exc()

    finally:
        print("\n✅ Worker shutdown complete", flush=True)
