#!/usr/bin/env python3
"""
Automatic Audio Downloader from Supabase
=========================================
Downloads raw audio files from Supabase Storage to local PC.
Only downloads direct script audio (not channel automation).
Deletes from Supabase immediately after successful download.

Usage:
    python download_audio.py

Or use the batch file:
    start_audio_downloader.bat
"""

import os
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict
from dotenv import load_dotenv
from supabase_client import SupabaseClient

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
DOWNLOAD_FOLDER = os.getenv("DOWNLOAD_FOLDER", r"F:\audiio")
CHECK_INTERVAL = 30  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


class AudioDownloader:
    def __init__(self):
        """Initialize audio downloader with Supabase connection"""
        self.download_folder = Path(DOWNLOAD_FOLDER)
        self.download_folder.mkdir(parents=True, exist_ok=True)

        # Initialize Supabase client
        self.supabase = SupabaseClient()

        if not self.supabase.is_connected():
            logger.error("❌ Supabase not connected! Check SUPABASE_URL and SUPABASE_ANON_KEY in .env")
            raise ConnectionError("Supabase connection failed")

        logger.info(f"✅ Audio downloader initialized")
        logger.info(f"📁 Download folder: {self.download_folder}")

    def download_audio_with_retry(self, audio_item: Dict) -> bool:
        """
        Download a single audio file with retry logic.
        Returns True if successful, False otherwise.
        """
        audio_id = audio_item['id']
        filename = audio_item['filename']
        storage_path = audio_item['storage_path']
        file_size = audio_item.get('file_size_mb', 0)

        local_path = self.download_folder / filename

        logger.info(f"📥 Downloading: {filename} ({file_size}MB)")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # Download from Supabase Storage
                success = self.supabase.download_audio_file(storage_path, str(local_path))

                if success:
                    # Verify file exists and has content
                    if local_path.exists() and local_path.stat().st_size > 0:
                        logger.info(f"✅ Downloaded: {filename}")

                        # Delete from Supabase immediately
                        if self.supabase.delete_direct_script_audio(audio_id, storage_path):
                            logger.info(f"🗑️  Deleted from Supabase: {filename}")
                        else:
                            logger.warning(f"⚠️  Failed to delete from Supabase: {filename}")

                        return True
                    else:
                        logger.error(f"❌ Downloaded file is empty or doesn't exist: {filename}")
                        if local_path.exists():
                            local_path.unlink()  # Delete empty file
                        raise Exception("Downloaded file is invalid")

                else:
                    raise Exception("Download returned False")

            except Exception as e:
                if attempt < MAX_RETRIES:
                    logger.warning(f"⚠️  Attempt {attempt}/{MAX_RETRIES} failed: {e}")
                    logger.info(f"⏳ Retrying in {RETRY_DELAY} seconds...")
                    time.sleep(RETRY_DELAY)
                else:
                    logger.error(f"❌ Failed after {MAX_RETRIES} attempts: {filename}")
                    logger.error(f"   Error: {e}")
                    return False

        return False

    def process_downloads(self) -> int:
        """
        Process all pending downloads.
        Returns number of successful downloads.
        """
        try:
            # Fetch pending downloads
            pending = self.supabase.get_pending_downloads()

            if not pending:
                return 0

            logger.info(f"📦 Found {len(pending)} pending audio file(s)")

            success_count = 0
            for audio_item in pending:
                if self.download_audio_with_retry(audio_item):
                    success_count += 1
                    logger.info(f"Progress: {success_count}/{len(pending)} completed")

            if success_count > 0:
                logger.info(f"🎉 Successfully downloaded {success_count} file(s)")

            return success_count

        except Exception as e:
            logger.error(f"❌ Error processing downloads: {e}")
            return 0

    def run_continuous(self):
        """Run downloader in continuous mode (checks every 30 seconds)"""
        logger.info("=" * 70)
        logger.info("🚀 AUDIO DOWNLOADER STARTED")
        logger.info("=" * 70)
        logger.info(f"📁 Download folder: {self.download_folder}")
        logger.info(f"⏱️  Check interval: {CHECK_INTERVAL} seconds")
        logger.info(f"🔄 Max retries: {MAX_RETRIES}")
        logger.info("=" * 70)
        logger.info("Press Ctrl+C to stop")
        logger.info("")

        check_count = 0
        total_downloaded = 0

        try:
            while True:
                check_count += 1
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                logger.info(f"[Check #{check_count}] {timestamp} - Checking for new audio...")

                downloaded = self.process_downloads()
                total_downloaded += downloaded

                if downloaded == 0:
                    logger.info("💤 No new audio files. Waiting...")

                logger.info(f"📊 Total downloaded this session: {total_downloaded}")
                logger.info(f"⏳ Next check in {CHECK_INTERVAL} seconds...")
                logger.info("-" * 70)

                time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            logger.info("")
            logger.info("=" * 70)
            logger.info("🛑 DOWNLOADER STOPPED BY USER")
            logger.info(f"📊 Total files downloaded: {total_downloaded}")
            logger.info("=" * 70)
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}")
            raise


def main():
    """Main entry point"""
    try:
        downloader = AudioDownloader()
        downloader.run_continuous()
    except ConnectionError:
        logger.error("")
        logger.error("=" * 70)
        logger.error("SETUP REQUIRED:")
        logger.error("1. Check .env file has SUPABASE_URL and SUPABASE_ANON_KEY")
        logger.error("2. Create 'raw_audio_files' bucket in Supabase Storage")
        logger.error("3. Make bucket public or add proper policies")
        logger.error("=" * 70)
        input("\nPress Enter to exit...")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        input("\nPress Enter to exit...")


if __name__ == "__main__":
    main()
