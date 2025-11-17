#!/usr/bin/env python3
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

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from supabase_client import SupabaseClient
from gdrive_manager import GDriveImageManager
from video_generator import VideoGenerator


class LocalVideoWorker:
    """Local PC video encoding worker"""

    def __init__(self):
        """Initialize worker"""
        # Worker identification
        self.worker_id = f"{platform.node()}_RTX4060"
        self.hostname = platform.node()

        # Initialize clients
        print("🔄 Initializing worker components...")
        self.supabase = SupabaseClient()
        self.gdrive = GDriveImageManager()
        self.video_gen = VideoGenerator()

        # Google Drive folders
        self.queue_folder_id = os.getenv("GDRIVE_VIDEO_QUEUE_FOLDER")
        self.output_folder_id = os.getenv("GDRIVE_VIDEO_OUTPUT_FOLDER")

        # Telegram bot token for notifications
        self.bot_token = os.getenv("BOT_TOKEN")

        # Working directory for temp files
        self.work_dir = "E:/video_worker_temp"
        os.makedirs(self.work_dir, exist_ok=True)

        # Configuration
        self.poll_interval = 30  # Check every 30 seconds
        self.max_retries = 3
        self.heartbeat_interval = 5  # Send heartbeat every 5 polls

        print(f"✅ Worker ID: {self.worker_id}")
        print(f"✅ Work directory: {self.work_dir}")
        print(f"✅ Poll interval: {self.poll_interval}s")

    def register_worker(self):
        """Register worker in database"""
        try:
            self.supabase.client.table('video_workers').upsert({
                'worker_id': self.worker_id,
                'hostname': self.hostname,
                'gpu_model': 'RTX 4060',
                'status': 'online',
                'last_heartbeat': datetime.now().isoformat()
            }).execute()

            print("✅ Worker registered in database")

        except Exception as e:
            print(f"⚠️  Worker registration failed: {e}")

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
        Get next pending job from queue (highest priority first)

        Returns:
            Job dict or None
        """
        try:
            result = self.supabase.client.table('video_jobs')\
                .select('*')\
                .eq('status', 'pending')\
                .order('priority', desc=True)\
                .order('created_at', desc=False)\
                .limit(1)\
                .execute()

            if result.data:
                return result.data[0]
            return None

        except Exception as e:
            print(f"❌ Error fetching job: {e}")
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
            await bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")

        except Exception as e:
            print(f"⚠️  Telegram notification failed: {e}")

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
            print(f"\n{'='*60}")
            print(f"🎬 Processing Job: {job_id}")
            print(f"   Chat ID: {chat_id}")
            print(f"   Created: {job['created_at']}")
            print(f"{'='*60}\n")

            # Mark as processing
            self.mark_job_processing(job_id)

            # 1. Download audio from Google Drive
            print(f"📥 Downloading audio from Google Drive...")
            audio_path = os.path.join(self.work_dir, f"{job_id}_audio.wav")

            if not self.download_from_gdrive(job['audio_gdrive_id'], audio_path):
                raise Exception("Failed to download audio")

            print(f"✅ Audio downloaded: {audio_path}")

            # 2. Download image from Google Drive
            print(f"📥 Downloading image from Google Drive...")
            image_path = os.path.join(self.work_dir, f"{job_id}_image.jpg")

            if not self.download_from_gdrive(job['image_gdrive_id'], image_path):
                raise Exception("Failed to download image")

            print(f"✅ Image downloaded: {image_path}")

            # 3. Generate video with subtitles
            print(f"🎬 Generating video with FFmpeg...")
            video_path = os.path.join(self.work_dir, f"{job_id}_final_video.mp4")

            subtitle_style = job.get('subtitle_style')

            # Progress callback
            async def video_progress(msg):
                print(f"   {msg}")

            # Get event loop
            loop = asyncio.get_event_loop()

            # Create video (runs in thread to not block)
            final_video = await asyncio.to_thread(
                self.video_gen.create_video_with_subtitles,
                image_path,
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

            # 7. Send Telegram notification
            message = (
                f"✅ **Video Ready!** (Job #{job_id})\n\n"
                f"📹 Size: {video_size_mb} MB\n"
            )
            if gofile_link:
                message += f"📥 [Download from Gofile]({gofile_link})\n"
            if gdrive_link:
                message += f"📁 [View on Google Drive]({gdrive_link})\n"

            message += f"\n🤖 Processed by: {self.worker_id}"

            await self.send_telegram_notification(chat_id, message)

            # 8. Cleanup queue files from Google Drive
            print(f"🧹 Cleaning up queue files...")
            self.gdrive.delete_file(job['audio_gdrive_id'])
            self.gdrive.delete_file(job['image_gdrive_id'])

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
        print(f"\n{'='*60}")
        print(f"🚀 Starting Local Video Worker")
        print(f"   Worker ID: {self.worker_id}")
        print(f"   Hostname: {self.hostname}")
        print(f"   GPU: RTX 4060")
        print(f"   Poll interval: {self.poll_interval}s")
        print(f"{'='*60}\n")

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
                    print(f"📋 Found pending job: {job['job_id']}")
                    await self.process_job(job)
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
    try:
        worker = LocalVideoWorker()
        asyncio.run(worker.run())

    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")

    except Exception as e:
        print(f"\n\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        print("\n✅ Worker shutdown complete")
