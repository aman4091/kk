#!/usr/bin/env python3
import os
import json
import asyncio
import logging
import requests
import torch
from pathlib import Path
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import whisper
from datetime import datetime
import time
import glob
import shutil
import subprocess
import re
from dotenv import load_dotenv

# New imports for YouTube Channel Automation
from supabase_client import SupabaseClient
from transcribe_helper import get_youtube_transcript, SupaDataError
from youtube_processor import YouTubeChannelProcessor, YouTubeProcessorError
# Load environment variables from .env file
load_dotenv()

# Auto-set environment variables if not already set
def auto_set_env_vars():
    """
    Automatically set environment variables if missing.

    NOTE: All API keys and confidential data should be set via environment variables.
    Use 'export' command in Vast.ai or add to .env file.

    Required environment variables:
    - BOT_TOKEN: Telegram bot token
    - DEEPSEEK_API_KEY: DeepSeek API key
    - SUPADATA_API_KEY: Supadata API key (or multiple via /add_supadata_key command)
    - SUPABASE_URL: Supabase project URL
    - SUPABASE_ANON_KEY: Supabase anonymous key
    - YOUTUBE_API_KEY: YouTube Data API v3 key
    - IMAGE_SHORTS_CHAT_ID: Telegram chat ID for shorts
    - IMAGE_LONG_CHAT_ID: Telegram chat ID for long content
    - GDRIVE_FOLDER_LONG: Google Drive folder ID for long content
    - GDRIVE_FOLDER_SHORT: Google Drive folder ID for short content
    - CHANNEL_IDS: Comma-separated channel IDs (optional)
    """
    # Only set non-sensitive default configurations
    default_env_vars = {
        "CHANNEL_MODE_ENABLED": "true",
    }

    auto_set_count = 0
    for key, value in default_env_vars.items():
        if not os.getenv(key):
            os.environ[key] = value
            auto_set_count += 1

    if auto_set_count > 0:
        print(f"\n{'='*50}")
        print(f"🔧 AUTO-CONFIGURED ENVIRONMENT")
        print(f"{'='*50}")
        print(f"✅ Set {auto_set_count} default configuration(s)")
        print(f"{'='*50}\n")

# Auto-set environment variables on startup
auto_set_env_vars()

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load bot credentials from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN environment variable is required! Set it via: export BOT_TOKEN='your_token_here'")

CHAT_ID = os.getenv("CHAT_ID")  # Set via: export CHAT_ID='your_chat_id'

# Channel Configuration
CHANNEL_MODE_ENABLED = os.getenv("CHANNEL_MODE_ENABLED", "false").lower() == "true"
CHANNEL_IDS_STR = os.getenv("CHANNEL_IDS", "")
CHANNEL_IDS = [int(ch_id.strip()) for ch_id in CHANNEL_IDS_STR.split(",") if ch_id.strip() and ch_id.strip().lstrip('-').isdigit()]

# Configuration
REFERENCE_DIR = "reference"
OUTPUT_DIR = "output"
SCRIPTS_DIR = "scripts"
MAX_TELEGRAM_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Directories banayiye
os.makedirs(REFERENCE_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(SCRIPTS_DIR, exist_ok=True)

class WorkingF5Bot:
    def __init__(self):
        print("🔄 Working F5-TTS Bot initializing...")
        self.whisper_model = None
        self.f5_model = None
        self.reference_audio = None
        self.reference_text = None
        self.processing_queue = []
        self.completed_files = []  # Track completed files with links
        self.is_processing = False
        self.stop_requested = False  # Add stop flag
        self.gofile_cache = {}
        self.latest_outputs_by_chat = {}

        # Queue batch processing settings
        self.queue_timer = None
        self.queue_wait_time = 120  # 2 minutes wait before processing
        self.queue_start_time = None
        self.batch_mode = False  # True when collecting files for batch
        self.power_policy = "off"    # off | stop | destroy
        self.shutdown_executed = False
        self.delivery_prefs_by_chat = {}

        # Initialize defaults before loading config
        self.deepseek_prompt = "Rewrite this content to be more engaging:"
        self.youtube_transcript_prompt = "Rewrite this YouTube transcript content to be more engaging and natural for text-to-speech:"
        self.ai_mode = "deepseek"  # "deepseek" or "openrouter" - for YouTube transcript processing only
        self.openrouter_model = "deepseek/deepseek-chat"  # Default OpenRouter model
        self.ffmpeg_filter = "afftdn=nr=12:nf=-25,highpass=f=80,lowpass=f=10000,equalizer=f=6000:t=h:width=2000:g=-6"
        self.audio_speed = 0.8
        self.audio_quality = 'high'
        self.chunk_size = 500  # Audio generation chunk size (chars). Higher = faster but lower quality. 4090 can handle 2000+

        # Title generation prompts for DeepSeek
        self.title_prompt_1 = "Based on the following script, generate 1 catchy and engaging title for a video. The title should be attention-grabbing, relevant to the content, and optimized for social media. Keep it concise (under 60 characters). Only return the title, nothing else.\n\nScript:"
        self.title_prompt_2 = "The previous title suggestion was good, but let's refine it further. Make it more engaging, compelling, and click-worthy while maintaining relevance to the script. Keep it under 60 characters. Only return the refined title, nothing else.\n\nPrevious title:"
        self.title_prompt_3 = "This is the final refinement. Polish the title to perfection - make it irresistible while staying true to the content. Ensure it's optimized for maximum engagement. Keep it under 60 characters. Only return the final polished title, nothing else.\n\nPrevious refined title:"
        self.title_prompt_10_more = "Based on the following script, generate 10 different catchy and engaging titles for a video. Each title should be unique, attention-grabbing, and optimized for social media. Keep each title concise (under 60 characters). Number them 1-10, one per line.\n\nScript:"

        # Title generation state tracking
        self.title_generation_state = {}  # {chat_id: {'stage': 'initial'/'refine1'/'refine2', 'title': '...', 'script': '...'}}

        # Configuration file
        self.config_file = "bot_config.json"

        # Load configuration from file (will override defaults if exists)
        self.load_config()

        # Initialize F5-TTS
        self.init_f5_tts()
        
        # Load reference
        self.load_manual_reference()
        self.vast_env_ok = self.check_vast_environment()
        self.api_keys_ok = self.check_api_keys()
        # Initialize YouTube Channel Processor & Supabase
        self.supabase = SupabaseClient()
        self.youtube_processor = YouTubeChannelProcessor()
        self.chunks_dir = "chunks"
        os.makedirs(self.chunks_dir, exist_ok=True)
        print("✅ YouTube channel processor and Supabase client initialized")
        # Multi-chat configuration (Aman & Anu chats)
        self.active_chats = {
            "aman": "-1002343932866",  # Aman chat
            "anu": "-1002498893774"    # Anu chat
        }
        # Store in Supabase if connected
        if self.supabase.is_connected():
            self.supabase.add_chat_config("-1002343932866", "aman")
            self.supabase.add_chat_config("-1002498893774", "anu")
            print("✅ Multi-chat configuration saved to database")
        
    async def _send_chunk_update(self, chat_id, current_chunk, total_chunks):
        """Send chunk progress update to Telegram"""
        try:
            from telegram import Bot
            bot = Bot(token=BOT_TOKEN)
            progress_text = f"🔄 Processing chunk {current_chunk}/{total_chunks}..."
            await bot.send_message(
                chat_id=chat_id,
                text=progress_text
            )
        except Exception as e:
            print(f"Chunk update error: {e}")

    def check_vast_environment(self):
        """Check if Vast.ai environment variables are properly set"""
        issues = []
        
        # Check API key
        if not os.getenv("VAST_API_KEY"):
            issues.append("VAST_API_KEY not set")
        
        # Check instance ID  
        if not (os.getenv("VAST_INSTANCE_ID") or os.getenv("CONTAINER_ID")):
            issues.append("VAST_INSTANCE_ID or CONTAINER_ID not set")
        
        # Check if vastai CLI is available
        try:
            import subprocess
            subprocess.run(["vastai", "--version"], capture_output=True, timeout=10)
        except Exception:
            issues.append("vastai CLI not installed or not in PATH")
        
        if issues:
            print("⚠️ Vast.ai environment issues:")
            for issue in issues:
                print(f"  - {issue}")
            return False
        else:
            print("✅ Vast.ai environment properly configured")
            return True

    def is_channel_message(self, update: Update):
        """Check if message is from a channel"""
        if not update.effective_chat:
            return False
        return update.effective_chat.type == "channel"

    def is_authorized_channel(self, chat_id):
        """Check if channel is authorized to use bot"""
        if not CHANNEL_MODE_ENABLED:
            return False

        # If no channel IDs configured, allow all channels
        if not CHANNEL_IDS:
            return True

        # Check if channel ID is in authorized list
        return chat_id in CHANNEL_IDS

    async def send_message_smart(self, context, chat_id, text, **kwargs):
        """Send message with channel/private chat awareness"""
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                **kwargs
            )
        except Exception as e:
            print(f"❌ Send message error: {e}")
            # Fallback to original CHAT_ID if channel send fails
            try:
                await context.bot.send_message(
                    chat_id=CHAT_ID,
                    text=f"⚠️ Channel message failed. Sending to DM:\n\n{text}",
                    **kwargs
                )
            except Exception as e2:
                print(f"❌ Fallback send also failed: {e2}")

    async def cleanup_old_files(self, max_age_hours=2):
        """Remove files older than specified hours to save storage costs"""
        try:
            current_time = time.time()
            cutoff_time = current_time - (max_age_hours * 3600)
            
            # Clean output directory
            for file_path in glob.glob(os.path.join(OUTPUT_DIR, "*")):
                if os.path.getctime(file_path) < cutoff_time:
                    os.remove(file_path)
                    print(f"Cleaned old file: {os.path.basename(file_path)}")
            
            # Clean scripts directory  
            for file_path in glob.glob(os.path.join(SCRIPTS_DIR, "*.txt")):
                if os.path.getctime(file_path) < cutoff_time:
                    os.remove(file_path)
                    print(f"Cleaned old script: {os.path.basename(file_path)}")
                    
            print("File cleanup completed")
        except Exception as e:
            print(f"Cleanup error: {e}")
        
    async def deep_cleanup_storage(self):
        """Aggressive storage cleanup to reduce costs"""
        try:
            print("🧹 Starting deep storage cleanup...")
            
            # 1. Clean output directory completely
            for file_path in glob.glob(os.path.join(OUTPUT_DIR, "*")):
                try:
                    os.remove(file_path)
                    print(f"Deleted: {os.path.basename(file_path)}")
                except Exception:
                    pass
            
            # 2. Clean scripts directory
            for file_path in glob.glob(os.path.join(SCRIPTS_DIR, "*")):
                try:
                    os.remove(file_path)
                    print(f"Deleted script: {os.path.basename(file_path)}")
                except Exception:
                    pass
            
            # 3. Clean old reference files (keep only current one)
            for file_path in glob.glob(os.path.join(REFERENCE_DIR, "*")):
                if file_path != self.reference_audio:
                    try:
                        os.remove(file_path)
                        print(f"Deleted old ref: {os.path.basename(file_path)}")
                    except Exception:
                        pass
            
            # 4. Clean system temp files
            temp_patterns = [
                "/tmp/*f5*", "/tmp/*audio*", "/tmp/*wav*", "/tmp/*mp3*",
                "*.tmp", "*.temp", "*~"
            ]
            for pattern in temp_patterns:
                for file_path in glob.glob(pattern):
                    try:
                        os.remove(file_path)
                        print(f"Deleted temp: {os.path.basename(file_path)}")
                    except Exception:
                        pass
            
            # 5. Empty trash if it exists
            trash_dirs = ["/root/.local/share/Trash", "/tmp/.trash", "/.trash"]
            for trash_dir in trash_dirs:
                if os.path.exists(trash_dir):
                    import shutil
                    try:
                        shutil.rmtree(trash_dir, ignore_errors=True)
                        os.makedirs(trash_dir, exist_ok=True)
                        print(f"Emptied trash: {trash_dir}")
                    except Exception:
                        pass
            
            # 6. Force disk sync
            try:
                import subprocess
                subprocess.run(["sync"], capture_output=True)
                print("✅ Forced disk sync")
            except Exception:
                pass
            
            print("✅ Deep cleanup completed")
            
        except Exception as e:
            print(f"❌ Deep cleanup error: {e}")

    def load_config(self):
        """Load configuration from file"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.deepseek_prompt = config.get('deepseek_prompt', "Rewrite this content to be more engaging:")
                self.youtube_transcript_prompt = config.get('youtube_transcript_prompt', "Rewrite this YouTube transcript content to be more engaging and natural for text-to-speech:")
                self.ai_mode = config.get('ai_mode', 'deepseek')
                self.openrouter_model = config.get('openrouter_model', 'deepseek/deepseek-chat')
                self.audio_speed = config.get('audio_speed', 0.8)
                self.audio_quality = config.get('audio_quality', 'high')
                self.power_policy = config.get('power_policy', 'off')
                self.chunk_size = config.get('chunk_size', 500)

                # Load FFmpeg filter and clean it if it's a full command
                raw_filter = config.get('ffmpeg_filter', 'afftdn=nr=12:nf=-25,highpass=f=80,lowpass=f=10000,equalizer=f=6000:t=h:width=2000:g=-6')
                self.ffmpeg_filter = self._extract_ffmpeg_filter_static(raw_filter)
                filter_was_cleaned = (raw_filter != self.ffmpeg_filter)
                print(f"✅ FFmpeg filter loaded: {self.ffmpeg_filter[:80]}...")
                if filter_was_cleaned:
                    print(f"🔧 Filter was cleaned from full command")

                # Load title generation prompts
                self.title_prompt_1 = config.get('title_prompt_1', "Based on the following script, generate 1 catchy and engaging title for a video. The title should be attention-grabbing, relevant to the content, and optimized for social media. Keep it concise (under 60 characters). Only return the title, nothing else.\n\nScript:")
                self.title_prompt_2 = config.get('title_prompt_2', "The previous title suggestion was good, but let's refine it further. Make it more engaging, compelling, and click-worthy while maintaining relevance to the script. Keep it under 60 characters. Only return the refined title, nothing else.\n\nPrevious title:")
                self.title_prompt_3 = config.get('title_prompt_3', "This is the final refinement. Polish the title to perfection - make it irresistible while staying true to the content. Ensure it's optimized for maximum engagement. Keep it under 60 characters. Only return the final polished title, nothing else.\n\nPrevious refined title:")
                self.title_prompt_10_more = config.get('title_prompt_10_more', "Based on the following script, generate 10 different catchy and engaging titles for a video. Each title should be unique, attention-grabbing, and optimized for social media. Keep each title concise (under 60 characters). Number them 1-10, one per line.\n\nScript:")

                # Debug logging for title prompts
                print(f"✅ Title Prompt 1 loaded: {self.title_prompt_1[:50]}...")
                print(f"✅ Title Prompt 2 loaded: {self.title_prompt_2[:50]}...")
                print(f"✅ Title Prompt 3 loaded: {self.title_prompt_3[:50]}...")
                print(f"✅ Title Prompt 10 More loaded: {self.title_prompt_10_more[:50]}...")

                # Load delivery preferences if available
                if 'delivery_prefs' in config:
                    self.delivery_prefs_by_chat = config['delivery_prefs']

            print(f"✅ Configuration loaded from {self.config_file}")

            # Save config if filter was cleaned
            if filter_was_cleaned:
                print(f"💾 Saving cleaned filter to config...")
                self.save_config()
        except FileNotFoundError:
            # Config file doesn't exist - defaults already set in __init__
            print(f"ℹ️ Config file not found, using defaults")
            self.save_config()
        except json.JSONDecodeError:
            print(f"⚠️ Invalid JSON in config file, using defaults")
            self.save_config()
        except Exception as e:
            print(f"⚠️ Config load error: {e}, using defaults")
    
    def save_config(self):
        """Save configuration to file"""
        try:
            config = {
                'deepseek_prompt': self.deepseek_prompt,
                'youtube_transcript_prompt': self.youtube_transcript_prompt,
                'ai_mode': self.ai_mode,
                'openrouter_model': self.openrouter_model,
                'audio_speed': self.audio_speed,
                'audio_quality': self.audio_quality,
                'power_policy': self.power_policy,
                'chunk_size': self.chunk_size,
                'ffmpeg_filter': self.ffmpeg_filter,
                'delivery_prefs': self.delivery_prefs_by_chat,
                'title_prompt_1': self.title_prompt_1,
                'title_prompt_2': self.title_prompt_2,
                'title_prompt_3': self.title_prompt_3,
                'title_prompt_10_more': self.title_prompt_10_more
            }
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)
            print(f"✅ Configuration saved to {self.config_file}")
        except Exception as e:
            print(f"❌ Config save error: {e}")
            
    def check_api_keys(self):
        """Check if required API keys are set"""
        missing_keys = []
        
        if not os.getenv("SUPADATA_API_KEY"):
            missing_keys.append("SUPADATA_API_KEY")
        
        if not os.getenv("DEEPSEEK_API_KEY"):
            missing_keys.append("DEEPSEEK_API_KEY")
        
        if missing_keys:
            print(f"⚠️ Missing API keys: {', '.join(missing_keys)}")
            print("Set them with:")
            for key in missing_keys:
                print(f"export {key}='your_key_here'")
            return False
        
        print("✅ All API keys configured")
        return True

    def debug_api_setup(self):
        """Debug API key setup"""
        api_key = os.getenv("SUPADATA_API_KEY")
        
        if not api_key:
            print("❌ SUPADATA_API_KEY environment variable not found")
            return False
        
        print(f"✅ API Key found: {len(api_key)} characters")
        print(f"🔑 Key preview: {api_key[:8]}{'*' * (len(api_key) - 8)}")
        
        # Check for common issues
        if ' ' in api_key:
            print("⚠️ API key contains spaces")
        if '\n' in api_key:
            print("⚠️ API key contains newlines")
        if api_key.startswith('"') or api_key.endswith('"'):
            print("⚠️ API key has quotes")
            
        return True

    async def process_multiple_youtube_links(self, youtube_links, update, context):
        """Process multiple YouTube links sequentially"""
        try:
            total_links = len(youtube_links)
            await update.message.reply_text(
                f"🔗 Found {total_links} YouTube link(s) to process\n"
                f"⏳ Processing them sequentially..."
            )
            
            results = []
            for idx, link in enumerate(youtube_links, 1):
                await update.message.reply_text(
                    f"\n📌 **Processing Link {idx}/{total_links}**\n"
                    f"🔗 {link[:50]}{'...' if len(link) > 50 else ''}",
                    parse_mode="Markdown"
                )
                
                script_path, audio_files = await self.process_youtube_link(link, update, context)
                
                if script_path or audio_files:
                    results.append({
                        'link': link,
                        'script': script_path,
                        'audio': audio_files,
                        'index': idx
                    })
                    
                # Small delay between processing links
                if idx < total_links:
                    await asyncio.sleep(2)
            
            # Summary message
            if results:
                summary = f"\n✅ **Processing Complete!**\n"
                summary += f"📊 Successfully processed {len(results)}/{total_links} link(s)\n\n"
                
                for result in results:
                    summary += f"Link {result['index']}: ✅ Script + Audio generated\n"
                
                await update.message.reply_text(summary, parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ Failed to process any links")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Multiple links processing error: {str(e)}")
    
    async def process_youtube_link(self, youtube_url, update, context):
        """Process YouTube link through SupaData API + DeepSeek API"""
        try:
            # Handle both regular messages and callback queries
            if hasattr(update, 'callback_query') and update.callback_query:
                chat_id = update.callback_query.message.chat.id
                # For callbacks, send new messages instead of replying
                send_message = lambda text: context.bot.send_message(chat_id=chat_id, text=text)
            else:
                chat_id = update.effective_chat.id
                # For regular messages, use reply_text
                send_message = update.message.reply_text
            
            await send_message("🔗 Processing YouTube link...")
            
            # Step 1: Get transcript from SupaData API
            transcript = await self.get_youtube_transcript(youtube_url)
            if not transcript:
                await send_message("❌ Could not get YouTube transcript")
                return None, None
            
            await send_message(f"✅ Transcript retrieved ({len(transcript)} chars)")

            # Step 2: Process through selected AI (DeepSeek or OpenRouter) with YouTube-specific prompt
            if self.ai_mode == "openrouter":
                await send_message(f"🤖 Using OpenRouter AI mode...")
                processed_script = await self.process_with_openrouter(transcript, chat_id, context, self.youtube_transcript_prompt)
            else:
                await send_message(f"🤖 Using DeepSeek AI mode...")
                processed_script = await self.process_with_deepseek(transcript, chat_id, context, self.youtube_transcript_prompt)

            if not processed_script:
                await send_message(f"❌ {self.ai_mode.capitalize()} processing failed")
                return None, None
            
            # Step 3: Save processed script to file
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            script_filename = f"deepseek_script_{timestamp}.txt"
            script_path = os.path.join(SCRIPTS_DIR, script_filename)
            
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(processed_script)
            
            # Step 4: Send script directly through Telegram (no GoFile upload)
            try:
                with open(script_path, 'rb') as f:
                    await context.bot.send_document(
                        chat_id=chat_id,
                        document=f,
                        filename=script_filename,
                        caption=f"📝 **DeepSeek Processed Script**\n"
                               f"📄 File: {script_filename}\n"
                               f"📏 Size: {len(processed_script)} chars\n"
                               f"✅ Ready for F5-TTS processing"
                    )
                print(f"✅ Script sent via Telegram: {script_filename}")
            except Exception as e:
                print(f"❌ Failed to send script via Telegram: {e}")
                try:
                    if len(processed_script) <= 4000:
                        await send_message(f"📝 **DeepSeek Processed Script**\n\n{processed_script[:4000]}")
                    else:
                        await send_message(f"📝 Script too long to send as message. Saved locally as {script_filename}")
                except Exception as e2:
                    print(f"❌ Failed to send script as message: {e2}")
            
            # Step 5: Generate audio with F5-TTS
            await send_message("🎵 Generating audio...")
            success, output_files = await self.generate_audio_f5(processed_script, chat_id)
            
            if success:
                await self.send_outputs_by_mode(context, chat_id, output_files, processed_script, "YouTube Audio")
            else:
                await send_message(f"❌ Audio generation failed: {output_files}")
            
            # Step 6: Cleanup everything except audio and script
            await self.cleanup_processing_files(exclude_scripts=True)
            
            return script_path, output_files if success else None
            
        except Exception as e:
            error_msg = f"❌ YouTube processing error: {str(e)}"
            print(error_msg)
            
            # Handle error messaging for both types
            try:
                if hasattr(update, 'callback_query') and update.callback_query:
                    await context.bot.send_message(
                        chat_id=update.callback_query.message.chat.id,
                        text=error_msg
                    )
                else:
                    await update.message.reply_text(error_msg)
            except:
                print("Could not send error message to user")
            
            return None, None

    async def extract_youtube_audio_as_reference(self, youtube_url, update, context):
        """Extract audio from YouTube video and set it as reference (cropped to ~30 seconds)"""
        try:
            # Handle both regular messages and callback queries
            if hasattr(update, 'callback_query') and update.callback_query:
                chat_id = update.callback_query.message.chat.id
                message = update.callback_query.message
            else:
                chat_id = update.effective_chat.id
                message = update.message
            
            await context.bot.send_message(
                chat_id=chat_id,
                text="🎵 Extracting audio from YouTube video..."
            )
            
            # Download audio using yt-dlp
            try:
                import yt_dlp
            except ImportError:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ yt-dlp not installed!\n\nRun: pip install yt-dlp"
                )
                return False
            
            timestamp = int(time.time())
            temp_output_template = os.path.join(REFERENCE_DIR, f"temp_yt_audio_{timestamp}")
            
            ydl_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'outtmpl': temp_output_template,
                'quiet': False,
                'no_warnings': False,
                'extract_flat': False,
                # Updated headers to bypass YouTube's 403 blocks (Oct 2025)
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36',
                'referer': 'https://www.youtube.com/',
                'http_headers': {
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'DNT': '1',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                    'Sec-Fetch-Dest': 'document',
                    'Sec-Fetch-Mode': 'navigate',
                    'Sec-Fetch-Site': 'none',
                    'Cache-Control': 'max-age=0',
                },
                # Enhanced retry options for 403 errors
                'retries': 10,
                'fragment_retries': 10,
                'skip_unavailable_fragments': True,
                'ignoreerrors': False,
                # Use extractor args for better compatibility
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web'],
                        'player_skip': ['webpage', 'configs'],
                    }
                },
                # Sleep between retries
                'sleep_interval': 1,
                'max_sleep_interval': 5,
            }
            
            print(f"📥 Downloading audio from: {youtube_url}")
            
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # First get info without downloading
                    info = ydl.extract_info(youtube_url, download=False)
                    
                    # Check if it's a live stream
                    if info.get('is_live') or info.get('live_status') in ['is_live', 'is_upcoming', 'live']:
                        await context.bot.send_message(
                            chat_id=chat_id,
                            text=(
                                "❌ Cannot extract audio from LIVE streams!\n\n"
                                "Please wait until the stream ends and becomes a regular video.\n\n"
                                "🔴 This is a live broadcast that's currently streaming."
                            )
                        )
                        return False
                    
                    video_title = info.get('title', 'video')[:50]
                    # Now download
                    ydl.download([youtube_url])
            except Exception as yt_error:
                print(f"❌ yt-dlp error: {yt_error}")
                error_msg = str(yt_error)

                # Provide specific help based on error type
                if "403" in error_msg or "Forbidden" in error_msg:
                    help_text = (
                        "❌ YouTube Download Failed (403 Forbidden)\n\n"
                        "YouTube has blocked this request. Try these fixes:\n\n"
                        "🔧 Solutions:\n"
                        "1️⃣ **Update yt-dlp** (Most Important!):\n"
                        "   Run: `pip install -U yt-dlp`\n"
                        "   Then restart the bot\n\n"
                        "2️⃣ **Wait 2-5 minutes** (YouTube rate limit)\n\n"
                        "3️⃣ **Try a different video**\n\n"
                        "4️⃣ **Check video availability** in your region\n\n"
                        "5️⃣ **Use a different format**: Try short videos (<10 min)\n\n"
                        "📝 Note: YouTube frequently updates their bot protection.\n"
                        "Always keep yt-dlp updated for best results.\n\n"
                        f"Technical Error: {error_msg[:100]}"
                    )
                elif "Private" in error_msg or "unavailable" in error_msg:
                    help_text = (
                        "❌ Video Not Available\n\n"
                        "This video is either:\n"
                        "• Private\n"
                        "• Deleted\n"
                        "• Restricted\n"
                        "• Not available in your region\n\n"
                        "Please try a public video."
                    )
                elif "Sign in" in error_msg:
                    help_text = (
                        "❌ Age Restricted Video\n\n"
                        "This video requires sign-in/age verification.\n"
                        "Bot cannot download age-restricted videos.\n\n"
                        "Try a different video."
                    )
                else:
                    help_text = (
                        f"❌ YouTube download failed!\n\n"
                        f"Error: {error_msg[:200]}\n\n"
                        f"💡 Try:\n"
                        f"• Different video\n"
                        f"• Update yt-dlp: pip install -U yt-dlp\n"
                        f"• Wait a few minutes"
                    )

                await context.bot.send_message(
                    chat_id=chat_id,
                    text=help_text
                )
                return False
            
            # Find the downloaded file (yt-dlp adds .mp3 extension)
            temp_audio_path = f"{temp_output_template}.mp3"
            
            if not os.path.exists(temp_audio_path):
                # Try without extension
                if os.path.exists(temp_output_template):
                    temp_audio_path = temp_output_template
                else:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=f"❌ Downloaded file not found!\n\nExpected: {temp_audio_path}"
                    )
                    return False
            
            print(f"✅ Audio downloaded: {os.path.basename(temp_audio_path)}")
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Audio extracted: {video_title}\n\n🎬 Cropping to ~30 seconds..."
            )
            
            # Crop to 30 seconds using ffmpeg
            cropped_path = os.path.join(REFERENCE_DIR, f"ref_yt_{timestamp}.wav")
            
            try:
                crop_cmd = [
                    'ffmpeg', '-i', temp_audio_path,
                    '-t', '30',
                    '-ar', '24000',
                    '-ac', '1',
                    '-y', cropped_path
                ]
                
                result = subprocess.run(
                    crop_cmd, 
                    capture_output=True, 
                    check=True, 
                    timeout=60,
                    text=True
                )
                print(f"✅ Audio cropped to 30s")
                
            except subprocess.TimeoutExpired:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ FFmpeg timeout! Audio file might be too large."
                )
                return False
            except subprocess.CalledProcessError as e:
                print(f"❌ FFmpeg error: {e.stderr}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Audio cropping failed!\n\nFFmpeg error: {e.stderr[:200]}"
                )
                return False
            except Exception as e:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Cropping error: {str(e)}"
                )
                return False
            
            # Remove temp file
            try:
                if os.path.exists(temp_audio_path):
                    os.remove(temp_audio_path)
                    print(f"🗑️ Cleaned temp file")
            except Exception as e:
                print(f"⚠️ Could not remove temp file: {e}")
            
            await context.bot.send_message(
                chat_id=chat_id,
                text="🎤 Extracting reference text with Whisper..."
            )
            
            # Extract text with Whisper
            try:
                if not self.whisper_model:
                    print("📥 Loading Whisper model...")
                    self.whisper_model = whisper.load_model("base", device="cpu")
                
                result = self.whisper_model.transcribe(cropped_path)
                new_ref_text = result["text"].strip()
                print(f"✅ Whisper transcription: {new_ref_text[:100]}")
                
            except Exception as whisper_error:
                print(f"❌ Whisper error: {whisper_error}")
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Whisper transcription failed!\n\nError: {str(whisper_error)[:200]}"
                )
                return False
            
            # Delete old reference if not default
            if self.reference_audio and os.path.exists(self.reference_audio):
                old_filename = os.path.basename(self.reference_audio)
                if not old_filename.startswith('k.'):
                    try:
                        os.remove(self.reference_audio)
                        print(f"🗑️ Deleted old reference: {old_filename}")
                    except Exception as e:
                        print(f"⚠️ Could not delete old reference: {e}")
            
            # Update reference
            self.reference_audio = cropped_path
            self.reference_text = new_ref_text
            
            # Clear F5-TTS cache
            if hasattr(self.f5_model, '_cached_ref_audio'):
                delattr(self.f5_model, '_cached_ref_audio')
            if hasattr(self.f5_model, '_cached_ref_text'):
                delattr(self.f5_model, '_cached_ref_text')
            
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            import gc
            gc.collect()
            
            print(f"✅ Reference audio updated successfully!")
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"✅ Reference audio updated from YouTube!\n\n"
                     f"🎬 Video: {video_title}\n"
                     f"📄 File: {os.path.basename(cropped_path)}\n"
                     f"⏱️ Duration: ~30 seconds\n\n"
                     f"📝 Extracted text:\n{new_ref_text[:200]}{'...' if len(new_ref_text) > 200 else ''}\n\n"
                     f"✅ Ready to use for voice cloning!"
            )
            
            return True
            
        except Exception as e:
            error_msg = f"❌ YouTube audio extraction error: {str(e)}"
            print(error_msg)
            import traceback
            print(traceback.format_exc())
            
            # Handle both message types for error reporting
            try:
                if hasattr(update, 'callback_query') and update.callback_query:
                    chat_id = update.callback_query.message.chat.id
                else:
                    chat_id = update.effective_chat.id
                    
                await context.bot.send_message(chat_id=chat_id, text=error_msg)
            except:
                print("Could not send error message to user")
            
            return False

    async def get_youtube_transcript(self, url):
        """Get transcript from SupaData API using correct implementation"""
        try:
            api_key = os.getenv("SUPADATA_API_KEY")
            if not api_key:
                print("❌ SUPADATA_API_KEY not set")
                return None

            print(f"🔄 Getting transcript for: {url}")

            # Correct endpoint and headers from your working script
            api_url = "https://api.supadata.ai/v1/transcript"
            headers = {
                "x-api-key": api_key,  # Correct header format
                "Accept": "application/json"
            }

            # Correct parameters from your working script
            params = {
                "url": url,
                "text": True,  # Return plain text instead of timestamped chunks
                "mode": "auto"  # Try native first, fallback to AI generation
            }

            print(f"🔄 Making GET request to SupaData API...")

            # Use GET request with params (not POST with JSON body)
            response = requests.get(
                api_url,
                params=params,
                headers=headers,
                timeout=1000
            )

            print(f"📊 SupaData response: {response.status_code}")

            if response.status_code == 401:
                print("❌ 401 Unauthorized - check API key")
                return None
            elif response.status_code == 202:
                # Async job - need to poll for results
                job_data = response.json()
                job_id = job_data.get("jobId")
                if not job_id:
                    print("❌ Got 202 but no job ID")
                    return None

                print(f"🔄 Large file detected, polling job: {job_id}")
                return await self._poll_supadata_job(job_id, api_key)
            elif response.status_code >= 400:
                error_text = response.text[:200]
                print(f"❌ SupaData error {response.status_code}: {error_text}")
                return None
            elif response.status_code == 200:
                # Direct response - process transcript
                data = response.json()
                print(f"🔍 Response type: {type(data)}")
                if isinstance(data, list):
                    print(f"📊 List with {len(data)} items")
                    if data:
                        print(f"First item type: {type(data[0])}")
                        if isinstance(data[0], dict):
                            print(f"First item keys: {list(data[0].keys())}")
                elif isinstance(data, dict):
                    print(f"📊 Dict with keys: {list(data.keys())}")
                
                transcript = self._extract_transcript_text(data)
                if transcript:
                    print(f"✅ Transcript received: {len(transcript)} characters")
                    return transcript
                else:
                    print("❌ No transcript content found in response")
                    return None
            else:
                print(f"❌ Unexpected status code: {response.status_code}")
                return None

        except Exception as e:
            print(f"❌ SupaData error: {e}")
            return None

    async def get_youtube_transcript_fallback(self, url):
        """Fallback method with different endpoint structure"""
        try:
            api_key = os.getenv("SUPADATA_API_KEY")
            if not api_key:
                return None
            
            # Try alternative endpoint structure
            endpoints_to_try = [
                "https://api.supadata.ai/youtube/transcript",
                "https://api.supadata.ai/v1/youtube/transcript", 
                "https://api.supadata.ai/transcript",
                "https://api.supadata.ai/v1/transcript"
            ]
            
            for endpoint in endpoints_to_try:
                try:
                    print(f"🔄 Trying endpoint: {endpoint}")
                    response = requests.post(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        json={"url": url},
                        timeout=1000
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        transcript = data.get("transcript") or data.get("text") or ""
                        if transcript:
                            print(f"✅ Success with endpoint: {endpoint}")
                            return transcript
                    else:
                        print(f"❌ {endpoint}: {response.status_code}")
                        
                except Exception as e:
                    print(f"❌ {endpoint} error: {e}")
                    continue
            
            return None
            
        except Exception as e:
            print(f"❌ Fallback error: {e}")
            return None

    async def _poll_supadata_job(self, job_id, api_key):
        """Poll for job results when SupaData returns a job ID"""
        poll_url = f"https://api.supadata.ai/v1/transcript/{job_id}"
        headers = {
            "x-api-key": api_key,
            "Accept": "application/json"
        }

        max_attempts = 60  # 5 minutes max
        attempt = 0

        while attempt < max_attempts:
            try:
                response = requests.get(poll_url, headers=headers, timeout=1000)

                if response.status_code == 200:
                    data = response.json()
                    status = data.get("status")

                    if status == "completed":
                        print("✅ Job completed successfully")
                        transcript = self._extract_transcript_text(data)
                        return transcript
                    elif status == "failed":
                        error = data.get("error", "Unknown error")
                        print(f"❌ Job failed: {error}")
                        return None
                    elif status in ["queued", "active"]:
                        print(f"🔄 Job status: {status}, waiting...")
                        await asyncio.sleep(5)  # Wait 5 seconds
                        attempt += 1
                        continue
                    else:
                        print(f"❌ Unknown job status: {status}")
                        return None
                else:
                    print(f"❌ Job status check failed: {response.status_code}")
                    return None

            except Exception as e:
                print(f"⚠️ Poll attempt {attempt + 1} failed: {e}")
                attempt += 1
                await asyncio.sleep(5)

        print("❌ Job polling timeout")
        return None

    def _extract_transcript_text(self, data):
        """Extract transcript text from SupaData response - handle both dict and list"""
        try:
            print(f"🔍 Response data type: {type(data)}")
            
            if isinstance(data, list):
                print(f"📊 List response with {len(data)} items")
                # If it's a list of transcript segments, join them
                if data and isinstance(data[0], dict):
                    # List of objects with text/content fields
                    text_parts = []
                    for item in data:
                        text = item.get("text") or item.get("content") or item.get("transcript") or ""
                        if text:
                            text_parts.append(str(text))
                    
                    if text_parts:
                        full_text = " ".join(text_parts)
                        print(f"✅ Combined {len(text_parts)} segments into {len(full_text)} characters")
                        return full_text
                elif data and isinstance(data[0], str):
                    # List of strings
                    full_text = " ".join(data)
                    print(f"✅ Combined {len(data)} string segments")
                    return full_text
            
            elif isinstance(data, dict):
                # Original dict handling
                # Prefer 'content' key if present
                value = data.get("content")
                if value is not None:
                    if isinstance(value, str):
                        print(f"✅ Extracted from dict 'content' (string): {len(value)} characters")
                        return value.strip()
                    if isinstance(value, list):
                        # Flatten list of strings or dict segments into a single string
                        text_parts = []
                        for item in value:
                            if isinstance(item, str):
                                text_parts.append(item)
                            elif isinstance(item, dict):
                                t = item.get("text") or item.get("content") or item.get("transcript") or ""
                                if isinstance(t, list):
                                    nested = self._extract_transcript_text(t)
                                    if nested:
                                        text_parts.append(nested)
                                elif t:
                                    text_parts.append(str(t))
                        if text_parts:
                            full_text = " ".join(text_parts)
                            print(f"✅ Combined 'content' list into {len(full_text)} characters")
                            return full_text
                
                # Fallback to other common keys
                for key in ("text", "transcript", "data"):
                    if key in data:
                        val = data[key]
                        if isinstance(val, str):
                            print(f"✅ Extracted from dict '{key}' (string): {len(val)} characters")
                            return val.strip()
                        elif isinstance(val, list):
                            # Recursive handling for nested lists
                            return self._extract_transcript_text(val)
                
                print("ℹ️ Dict present but did not contain extractable string content")
                return None
            
            elif isinstance(data, str):
                # Direct string response
                print(f"✅ Direct string response: {len(data)} characters")
                return data.strip()
            
            print("❌ No transcript content found in response")
            print(f"Response preview: {str(data)[:200]}...")
            return None
            
        except Exception as e:
            print(f"❌ Extract transcript error: {e}")
            print(f"Data type: {type(data)}")
            return None


    async def process_with_deepseek(self, transcript, chat_id, context, custom_prompt=None):
        """Process transcript through DeepSeek API in chunks"""
        try:
            api_key = os.getenv("DEEPSEEK_API_KEY")  # Set this environment variable
            prompt = custom_prompt if custom_prompt else self.deepseek_prompt
            
            if not api_key:
                print("❌ DEEPSEEK_API_KEY not set")
                return None
            
            # Split transcript into smaller chunks to reduce API timeouts (configurable)
            try:
                chunk_size = int(os.getenv("DEEPSEEK_CHUNK_SIZE", 7000))
            except Exception:
                chunk_size = 7000
            chunks = self.split_text_into_chunks(transcript, chunk_size)
            processed_chunks = []
            
            await context.bot.send_message(chat_id, f"🤖 Processing {len(chunks)} chunks with DeepSeek...")
            
            for i, chunk in enumerate(chunks):
                await context.bot.send_message(chat_id, f"🔄 DeepSeek chunk {i+1}/{len(chunks)}")

                # Robust DeepSeek API call with retries
                try:
                    max_retries = int(os.getenv("DEEPSEEK_MAX_RETRIES", 3))
                except Exception:
                    max_retries = 3
                try:
                    timeout_seconds = int(os.getenv("DEEPSEEK_TIMEOUT", 1000))
                except Exception:
                    timeout_seconds = 1000
                try:
                    backoff_seconds = int(os.getenv("DEEPSEEK_BACKOFF", 5))
                except Exception:
                    backoff_seconds = 5
                processed_text = None

                for attempt in range(1, max_retries + 1):
                    try:
                        response = requests.post(
                            "https://api.deepseek.com/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json"
                            },
                            json={
                                "model": "deepseek-chat",
                                "messages": [
                                    {"role": "system", "content": prompt},
                                    {"role": "user", "content": chunk}
                                ],
                                "temperature": 0.7
                            },
                            timeout=timeout_seconds
                        )

                        if response.status_code == 200:
                            result = response.json()
                            processed_text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                            break
                        elif response.status_code == 429:
                            # Rate limited - respect Retry-After if present
                            retry_after = response.headers.get("Retry-After")
                            wait_time = int(retry_after) if retry_after and retry_after.isdigit() else backoff_seconds * attempt
                            print(f"⚠️ DeepSeek rate limited (429) on chunk {i+1}, waiting {wait_time}s and retrying ({attempt}/{max_retries})")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            print(f"DeepSeek API error for chunk {i+1}: {response.status_code} - {response.text[:200]}")
                            # Backoff and retry for server errors
                            if 500 <= response.status_code < 600 and attempt < max_retries:
                                await asyncio.sleep(backoff_seconds * attempt)
                                continue
                            break
                    except requests.Timeout:
                        print(f"⏱️ DeepSeek timeout on chunk {i+1}, attempt {attempt}/{max_retries}")
                        if attempt < max_retries:
                            await asyncio.sleep(backoff_seconds * attempt)
                            continue
                    except requests.RequestException as e:
                        print(f"🌐 DeepSeek request error on chunk {i+1}, attempt {attempt}/{max_retries}: {e}")
                        if attempt < max_retries:
                            await asyncio.sleep(backoff_seconds * attempt)
                            continue
                    except Exception as e:
                        print(f"Unexpected DeepSeek error on chunk {i+1}: {e}")
                        break

                if processed_text is None:
                    # Use original if API fails after retries
                    processed_text = chunk
                processed_chunks.append(processed_text)
                # Small delay between chunks to avoid bursts / rate limiting
                await asyncio.sleep(float(os.getenv("DEEPSEEK_INTER_CHUNK_SLEEP", 0.5)))
            
            return " ".join(processed_chunks)
            
        except Exception as e:
            print(f"DeepSeek processing error: {e}")
            return None

    async def process_with_openrouter(self, transcript, chat_id, context, custom_prompt=None):
        """Process transcript through OpenRouter API in chunks"""
        try:
            api_key = os.getenv("OPENROUTER_API_KEY")
            prompt = custom_prompt if custom_prompt else self.youtube_transcript_prompt

            print(f"🔍 [OPENROUTER] Checking API key...")
            print(f"🔍 [OPENROUTER] API key found: {bool(api_key)}")

            if not api_key:
                error_msg = "❌ OPENROUTER_API_KEY not set in .env file"
                print(f"❌ [OPENROUTER] {error_msg}")
                await context.bot.send_message(chat_id, error_msg)
                return None

            # Split transcript into smaller chunks
            try:
                chunk_size = int(os.getenv("OPENROUTER_CHUNK_SIZE", 7000))
            except Exception:
                chunk_size = 7000
            chunks = self.split_text_into_chunks(transcript, chunk_size)
            processed_chunks = []

            await context.bot.send_message(chat_id, f"🤖 Processing {len(chunks)} chunks with OpenRouter...")

            for i, chunk in enumerate(chunks):
                await context.bot.send_message(chat_id, f"🔄 OpenRouter chunk {i+1}/{len(chunks)}")

                # OpenRouter API call with retries
                try:
                    max_retries = 3
                    timeout_seconds = 1000
                    backoff_seconds = 5
                except Exception:
                    max_retries = 3
                    timeout_seconds = 1000
                    backoff_seconds = 5

                processed_text = None

                for attempt in range(1, max_retries + 1):
                    try:
                        print(f"🔄 [OPENROUTER] Making API request for chunk {i+1}...")
                        response = requests.post(
                            "https://openrouter.ai/api/v1/chat/completions",
                            headers={
                                "Authorization": f"Bearer {api_key}",
                                "Content-Type": "application/json",
                                "HTTP-Referer": "https://github.com/anthropics/claude-code",
                                "X-Title": "F5-TTS Bot"
                            },
                            json={
                                "model": self.openrouter_model,
                                "messages": [
                                    {"role": "system", "content": prompt},
                                    {"role": "user", "content": chunk}
                                ],
                                "temperature": 0.7
                            },
                            timeout=timeout_seconds
                        )

                        print(f"📊 [OPENROUTER] Response status: {response.status_code}")

                        if response.status_code == 200:
                            result = response.json()
                            processed_text = result['choices'][0]['message']['content'].strip()
                            print(f"✅ [OPENROUTER] Chunk {i+1} processed successfully")
                            break
                        elif response.status_code == 429:
                            # Rate limited
                            retry_after = response.headers.get("Retry-After")
                            wait_time = int(retry_after) if retry_after and retry_after.isdigit() else backoff_seconds * attempt
                            print(f"⚠️ [OPENROUTER] Rate limited (429) on chunk {i+1}, waiting {wait_time}s")
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            print(f"❌ [OPENROUTER] API error for chunk {i+1}: {response.status_code} - {response.text[:200]}")
                            if 500 <= response.status_code < 600 and attempt < max_retries:
                                await asyncio.sleep(backoff_seconds * attempt)
                                continue
                            break
                    except requests.Timeout:
                        print(f"⏱️ [OPENROUTER] Timeout on chunk {i+1}, attempt {attempt}/{max_retries}")
                        if attempt < max_retries:
                            await asyncio.sleep(backoff_seconds * attempt)
                            continue
                    except requests.RequestException as e:
                        print(f"🌐 [OPENROUTER] Request error on chunk {i+1}, attempt {attempt}/{max_retries}: {e}")
                        if attempt < max_retries:
                            await asyncio.sleep(backoff_seconds * attempt)
                            continue
                    except Exception as e:
                        print(f"❌ [OPENROUTER] Unexpected error on chunk {i+1}: {e}")
                        break

                if processed_text is None:
                    print(f"⚠️ [OPENROUTER] Chunk {i+1} processing failed, using original")
                    processed_text = chunk
                processed_chunks.append(processed_text)
                # Small delay between chunks
                await asyncio.sleep(0.5)

            return " ".join(processed_chunks)

        except Exception as e:
            print(f"❌ [OPENROUTER] Processing error: {e}")
            return None

    async def process_two_sentences_with_prompt(self, two_sentences, prompt_text, chat_id, context):
        """Process exactly 2 sentences with custom prompt via DeepSeek with stop support"""
        try:
            api_key = os.getenv("DEEPSEEK_API_KEY")
            if not api_key:
                print("❌ DEEPSEEK_API_KEY not set")
                return None
            
            full_prompt = f"{prompt_text}\n\nHere is the script:\n{two_sentences}"
            
            # Make request in a thread to allow stop checking
            import concurrent.futures
            
            def make_deepseek_request():
                try:
                    response = requests.post(
                        "https://api.deepseek.com/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "model": "deepseek-chat",
                            "messages": [
                                {"role": "user", "content": full_prompt}
                            ],
                            "temperature": 0.7
                        },
                        timeout=120
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        return result.get("choices", [{}])[0].get("message", {}).get("content", "")
                    else:
                        return None
                except Exception as e:
                    print(f"DeepSeek request error: {e}")
                    return None
            
            # Run in executor with periodic stop checks
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(make_deepseek_request)
                
                # Check every 0.5 seconds if stop was requested
                while not future.done():
                    if self.stop_requested:
                        print("🛑 Stop requested during DeepSeek call")
                        future.cancel()
                        return None
                    await asyncio.sleep(0.5)
                
                return future.result()
            
        except Exception as e:
            print(f"Process two sentences error: {e}")
            return None

    async def generate_title_with_deepseek(self, prompt, content, chat_id, context):
        """Generate title using DeepSeek API with given prompt and content"""
        try:
            api_key = os.getenv("DEEPSEEK_API_KEY")

            # Debug logging
            print(f"🔍 [TITLE GEN] Checking API key...")
            print(f"🔍 [TITLE GEN] API key found: {bool(api_key)}")
            if api_key:
                print(f"🔍 [TITLE GEN] API key length: {len(api_key)}")
                print(f"🔍 [TITLE GEN] API key starts with: {api_key[:10]}...")

            if not api_key:
                error_msg = "❌ DeepSeek API key not configured in .env file"
                print(f"❌ [TITLE GEN] {error_msg}")
                await context.bot.send_message(chat_id, error_msg)
                return None

            # Combine prompt with content
            full_prompt = f"{prompt}\n\n{content}"
            print(f"✅ [TITLE GEN] Full prompt length: {len(full_prompt)} chars")

            # Send processing message
            await context.bot.send_message(chat_id, "🤖 Generating title with DeepSeek AI...")

            # Make API call
            try:
                print(f"🔄 [TITLE GEN] Making API request to DeepSeek...")
                response = requests.post(
                    "https://api.deepseek.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "deepseek-chat",
                        "messages": [
                            {"role": "user", "content": full_prompt}
                        ],
                        "temperature": 0.7
                    },
                    timeout=60
                )

                print(f"📊 [TITLE GEN] Response status: {response.status_code}")

                if response.status_code == 200:
                    result = response.json()
                    title = result['choices'][0]['message']['content'].strip()
                    print(f"✅ [TITLE GEN] Title generated: {title}")
                    return title
                else:
                    error_msg = f"DeepSeek API error: {response.status_code} - {response.text[:200]}"
                    print(f"❌ [TITLE GEN] {error_msg}")
                    await context.bot.send_message(chat_id, f"❌ DeepSeek API error: {response.status_code}\n\nDetails: {response.text[:100]}")
                    return None

            except requests.Timeout:
                error_msg = "DeepSeek request timed out"
                print(f"⏱️ [TITLE GEN] {error_msg}")
                await context.bot.send_message(chat_id, f"❌ {error_msg}")
                return None
            except Exception as e:
                error_msg = f"DeepSeek request error: {str(e)}"
                print(f"❌ [TITLE GEN] {error_msg}")
                await context.bot.send_message(chat_id, f"❌ Error: {str(e)}")
                return None

        except Exception as e:
            error_msg = f"Title generation error: {str(e)}"
            print(f"❌ [TITLE GEN] {error_msg}")
            return None

    def extract_continuation_paragraph(self, deepseek_output):
        """
        Extract only the continuation paragraph (10 sentences) from DeepSeek output.
        """
        try:
            print(f"📝 Raw output length: {len(deepseek_output)} chars")
            
            # Remove any markdown formatting
            text = deepseek_output.replace('**', '').replace('*', '').strip()
            
            # Split into sentences
            sentences = re.split(r'(?<=[.!?])\s+', text)
            
            # Filter out any metadata/labels
            clean_sentences = []
            for sent in sentences:
                sent = sent.strip()
                # Skip sentences that are labels or examples
                if any(skip in sent.lower() for skip in [
                    'original sentence',
                    'rewritten sentences',
                    'continuation sentences',
                    'step 1',
                    'step 2',
                    'example',
                    'here is',
                    'based on'
                ]):
                    continue
                
                # Skip very short sentences (likely labels)
                if len(sent) < 20:
                    continue
                    
                clean_sentences.append(sent)
            
            # The continuation paragraph should be the last 10 sentences
            if len(clean_sentences) >= 10:
                continuation = ' '.join(clean_sentences[-10:])
                print(f"✅ Extracted {len(clean_sentences[-10:])} continuation sentences")
                return continuation
            
            # If we don't have enough, try to get all clean sentences after first 2
            elif len(clean_sentences) > 2:
                continuation = ' '.join(clean_sentences[2:])
                print(f"⚠️ Only found {len(clean_sentences[2:])} sentences, using all after first 2")
                return continuation
            
            # Fallback: return all clean text
            print("⚠️ Could not extract properly, using all clean text")
            return ' '.join(clean_sentences) if clean_sentences else deepseek_output
            
        except Exception as e:
            print(f"❌ Extract error: {e}")
            return deepseek_output.strip()

    async def cleanup_processing_files(self, exclude_scripts=False):
        """Clean up processing files but keep audio"""
        try:
            # Clean scripts directory only if not excluded
            if not exclude_scripts:
                for file_path in glob.glob(os.path.join(SCRIPTS_DIR, "*")):
                    try:
                        os.remove(file_path)
                    except:
                        pass
            
            print("✅ Cleaned processing files")
        except Exception as e:
            print(f"Cleanup error: {e}")

    def init_f5_tts(self):
        """F5-TTS model initialize kariye"""
        try:
            print("🔄 Loading F5-TTS API...")
            from f5_tts.api import F5TTS
            
            self.f5_model = F5TTS()
            print("✅ F5-TTS API loaded successfully!")
            
        except Exception as e:
            print(f"❌ F5-TTS initialization error: {e}")
            self.f5_model = None
    
    def load_manual_reference(self):
        """Manual reference audio load kariye"""
        try:
            # Reference folder mein files check kariye
            audio_files = []
            for ext in ['*.wav', '*.mp3', '*.ogg', '*.m4a']:
                audio_files.extend(glob.glob(os.path.join(REFERENCE_DIR, ext)))
            
            if audio_files:
                # Pehli file use kariye
                new_reference = audio_files[0]
                # If already transcribed for this file, skip
                if getattr(self, 'reference_audio', None) == new_reference and getattr(self, 'reference_text', None):
                    print(f"✅ Reference cached: {new_reference}")
                    return
                self.reference_audio = new_reference
                print(f"✅ Reference audio: {self.reference_audio}")
                
                # Whisper load kariye aur text extract kariye (CPU)
                print("🔄 Loading Whisper for reference text (CPU)...")
                self.whisper_model = whisper.load_model("base", device="cpu")
                
                result = self.whisper_model.transcribe(self.reference_audio)
                self.reference_text = result["text"].strip()
                print(f"✅ Reference text: {self.reference_text[:100]}...")
            else:
                print("⚠️ No reference audio found in reference folder")
                
        except Exception as e:
            print(f"❌ Reference load error: {e}")
    
    async def handle_audio_reference(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle new reference audio uploads"""
        try:
            user_id = update.effective_user.id if update.effective_user else "Channel/Anonymous"
            chat_id = update.effective_chat.id
            is_channel = update.message and update.message.chat.type == "channel"

            print(f"🎵 Audio handler triggered by user: {user_id}, chat: {chat_id}")

            # Helper function to send messages (works for both channels and private chats)
            async def send_message(text):
                if is_channel:
                    await context.bot.send_message(chat_id=chat_id, text=text)
                else:
                    await update.message.reply_text(text)

            if update.message.audio or update.message.voice:
                await send_message("🎵 Processing new reference audio...")

                # Download the audio file
                if update.message.audio:
                    file = await context.bot.get_file(update.message.audio.file_id)
                    filename = f"ref_{int(time.time())}.mp3"
                    print(f"📁 Processing audio file: {filename}")
                else:  # voice message
                    file = await context.bot.get_file(update.message.voice.file_id)
                    filename = f"ref_{int(time.time())}.ogg"
                    print(f"🎤 Processing voice message: {filename}")

                file_path = os.path.join(REFERENCE_DIR, filename)
                await file.download_to_drive(file_path)
                print(f"✅ Downloaded to: {file_path}")

                # Extract text with Whisper
                if not self.whisper_model:
                    print("🔄 Loading Whisper model...")
                    self.whisper_model = whisper.load_model("base", device="cpu")

                print("🔄 Transcribing audio...")
                result = self.whisper_model.transcribe(file_path)
                new_ref_text = result["text"].strip()
                print(f"📝 Extracted: {new_ref_text[:50]}...")

                # Update bot's reference
                old_ref = os.path.basename(self.reference_audio) if self.reference_audio else "None"
                self.reference_audio = file_path
                self.reference_text = new_ref_text

                print(f"✅ Reference updated from {old_ref} to {filename}")

                await send_message(
                    f"✅ Reference audio updated!\n\n"
                    f"🔄 Previous: {old_ref}\n"
                    f"🎵 New: {filename}\n\n"
                    f"📝 Extracted text: {new_ref_text[:150]}{'...' if len(new_ref_text) > 150 else ''}\n\n"
                    f"Use /ref_back to revert to default reference."
                )

            else:
                print("⚠️ No audio or voice in message")

        except Exception as e:
            error_msg = f"❌ Reference update error: {str(e)}"
            print(error_msg)
            # Safe error message sending
            try:
                if is_channel:
                    await context.bot.send_message(chat_id=chat_id, text=error_msg)
                else:
                    await update.message.reply_text(error_msg)
            except:
                print(f"Could not send error message: {error_msg}")

    async def ref_back_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Revert to default reference audio"""
        try:
            # Load original reference
            self.load_manual_reference()
            
            ref_name = os.path.basename(self.reference_audio) if self.reference_audio else "None"
            await update.message.reply_text(
                f"🔄 Reverted to default reference: {ref_name}\n\n"
                f"📝 Text: {self.reference_text[:100]}{'...' if len(self.reference_text) > 100 else ''}"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Revert error: {str(e)}")

    async def set_prompt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Change DeepSeek prompt via Telegram"""
        try:
            if context.args:
                new_prompt = " ".join(context.args)
                self.deepseek_prompt = new_prompt

                # Save configuration to file
                self.save_config()

                # Create a button to return to settings
                keyboard = [[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    f"✅ DeepSeek prompt updated and saved!\n\n"
                    f"📝 New prompt: {new_prompt}",
                    reply_markup=reply_markup
                )
            else:
                # Create a button to return to settings
                keyboard = [[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await update.message.reply_text(
                    f"📝 Current prompt: {self.deepseek_prompt}\n\n"
                    f"💡 Usage: /set_prompt Your new prompt here",
                    reply_markup=reply_markup
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Prompt update error: {str(e)}")

    async def set_youtube_prompt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Change YouTube Transcript Processing prompt via Telegram"""
        try:
            if context.args:
                new_prompt = " ".join(context.args)
                self.youtube_transcript_prompt = new_prompt

                # Save configuration to file
                self.save_config()

                await update.message.reply_text(
                    f"✅ YouTube Transcript prompt updated and saved!\n\n"
                    f"📝 New prompt: {new_prompt}"
                )
            else:
                await update.message.reply_text(
                    f"📝 Current YouTube Transcript prompt:\n{self.youtube_transcript_prompt}\n\n"
                    f"💡 Usage: /set_youtube_prompt Your new prompt here\n\n"
                    f"Example:\n/set_youtube_prompt Rewrite this transcript for engaging TTS audio"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ YouTube prompt update error: {str(e)}")
# New Command Handlers for API Key Management and Supabase Setup
# Add these methods to WorkingF5Bot class

    # =============================================================================
    # SUPABASE & API KEY MANAGEMENT COMMANDS
    # =============================================================================

    async def set_supabase_url_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set Supabase URL via Telegram"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "❌ Missing Supabase URL\n\n"
                    "Usage: /set_supabase_url <your_supabase_url>\n\n"
                    "Example:\n"
                    "/set_supabase_url https://xxxxx.supabase.co"
                )
                return

            url = context.args[0]
            os.environ["SUPABASE_URL"] = url

            # Reinitialize Supabase client
            self.supabase = SupabaseClient(url=url, key=os.getenv("SUPABASE_ANON_KEY"))

            await update.message.reply_text(
                f"✅ Supabase URL set successfully!\n\n"
                f"🔗 URL: {url[:30]}...\n\n"
                f"Next: Set anon key with /set_supabase_key"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Error setting Supabase URL: {str(e)}")

    async def set_supabase_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set Supabase Anon Key via Telegram"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "❌ Missing Supabase Anon Key\n\n"
                    "Usage: /set_supabase_key <your_anon_key>\n\n"
                    "Example:\n"
                    "/set_supabase_key eyJhbGciOiJIUzI1..."
                )
                return

            key = context.args[0]
            os.environ["SUPABASE_ANON_KEY"] = key

            # Reinitialize Supabase client
            self.supabase = SupabaseClient(url=os.getenv("SUPABASE_URL"), key=key)

            if self.supabase.is_connected():
                # Try to initialize tables
                self.supabase.init_tables()

                await update.message.reply_text(
                    f"✅ Supabase connected successfully!\n\n"
                    f"🔑 Key: {key[:20]}...\n\n"
                    f"📊 Database ready for use!\n\n"
                    f"💡 Next steps:\n"
                    f"1. /set_youtube_key <api_key>\n"
                    f"2. /add_supadata_key <api_key>\n"
                    f"3. /set_deepseek_key <api_key>"
                )
            else:
                await update.message.reply_text(
                    "⚠️ Supabase key set but connection failed.\n"
                    "Please check your credentials."
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Error setting Supabase key: {str(e)}")

    async def set_youtube_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set YouTube Data API key via Telegram"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "❌ Missing YouTube API Key\n\n"
                    "Usage: /set_youtube_key <your_api_key>\n\n"
                    "Example:\n"
                    "/set_youtube_key AIzaSyBxxxxxxxxxxxxxx\n\n"
                    "Get API key from:\n"
                    "https://console.cloud.google.com/apis/credentials"
                )
                return

            api_key = context.args[0]

            # Store in Supabase
            if self.supabase.is_connected():
                success = self.supabase.store_api_key('youtube', api_key)
                if success:
                    # Update YouTube processor
                    self.youtube_processor.set_api_key(api_key)

                    await update.message.reply_text(
                        f"✅ YouTube API key saved to database!\n\n"
                        f"🔑 Key: {api_key[:20]}...\n\n"
                        f"You can now process YouTube channels!"
                    )
                else:
                    await update.message.reply_text("❌ Failed to save API key to database")
            else:
                # Fallback: Store in memory only
                self.youtube_processor.set_api_key(api_key)
                await update.message.reply_text(
                    f"⚠️ YouTube API key set (memory only)\n\n"
                    f"🔑 Key: {api_key[:20]}...\n\n"
                    f"⚠️ Supabase not connected. Key won't persist after restart.\n"
                    f"Use /set_supabase_url and /set_supabase_key first."
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Error setting YouTube key: {str(e)}")

    async def add_supadata_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add Supadata API key to pool via Telegram"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "❌ Missing Supadata API Key\n\n"
                    "Usage: /add_supadata_key <your_api_key>\n\n"
                    "Example:\n"
                    "/add_supadata_key sd_xxxxxxxxxx\n\n"
                    "💡 You can add multiple keys for rotation!"
                )
                return

            api_key = context.args[0]

            # Store in Supabase
            if self.supabase.is_connected():
                success = self.supabase.store_api_key('supadata', api_key)
                if success:
                    # Get total active keys
                    all_keys = self.supabase.get_all_api_keys_status()
                    supadata_keys = [k for k in all_keys if k['key_type'] == 'supadata' and k['is_active']]

                    await update.message.reply_text(
                        f"✅ Supadata API key added to pool!\n\n"
                        f"🔑 Key: {api_key[:20]}...\n\n"
                        f"📊 Total active Supadata keys: {len(supadata_keys)}\n\n"
                        f"💡 Keys will auto-rotate on quota exhaustion"
                    )
                else:
                    await update.message.reply_text("❌ Failed to save API key to database")
            else:
                await update.message.reply_text(
                    "⚠️ Supabase not connected!\n\n"
                    "Use /set_supabase_url and /set_supabase_key first."
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Error adding Supadata key: {str(e)}")

    async def set_deepseek_key_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set DeepSeek API key via Telegram"""
        try:
            if not context.args:
                await update.message.reply_text(
                    "❌ Missing DeepSeek API Key\n\n"
                    "Usage: /set_deepseek_key <your_api_key>\n\n"
                    "Example:\n"
                    "/set_deepseek_key sk-xxxxxxxxxx"
                )
                return

            api_key = context.args[0]

            # Store in Supabase
            if self.supabase.is_connected():
                success = self.supabase.store_api_key('deepseek', api_key)
                if success:
                    await update.message.reply_text(
                        f"✅ DeepSeek API key saved to database!\n\n"
                        f"🔑 Key: {api_key[:20]}...\n\n"
                        f"Bot will use this key for text processing."
                    )
                else:
                    await update.message.reply_text("❌ Failed to save API key to database")
            else:
                # Update environment variable as fallback
                os.environ["DEEPSEEK_API_KEY"] = api_key
                await update.message.reply_text(
                    f"⚠️ DeepSeek API key set (memory only)\n\n"
                    f"🔑 Key: {api_key[:20]}...\n\n"
                    f"⚠️ Supabase not connected. Key won't persist.\n"
                    f"Use /set_supabase_url and /set_supabase_key first."
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Error setting DeepSeek key: {str(e)}")

    async def set_channel_prompt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set custom prompt for channel video processing"""
        try:
            if not context.args:
                # Show current prompt
                current_prompt = "Default: Rewrite this content to be more engaging for audio"
                if self.supabase.is_connected():
                    saved_prompt = self.supabase.get_prompt('channel')
                    if saved_prompt:
                        current_prompt = saved_prompt

                await update.message.reply_text(
                    f"📝 Channel Processing Prompt\n\n"
                    f"Current prompt:\n{current_prompt}\n\n"
                    f"Usage: /set_channel_prompt <your_prompt>\n\n"
                    f"Example:\n"
                    f"/set_channel_prompt Rewrite this transcript into engaging storytelling format"
                )
                return

            new_prompt = ' '.join(context.args)

            # Store in Supabase
            if self.supabase.is_connected():
                success = self.supabase.save_prompt('channel', new_prompt)
                if success:
                    await update.message.reply_text(
                        f"✅ Channel prompt saved to database!\n\n"
                        f"📝 New prompt:\n{new_prompt}\n\n"
                        f"This will be used for all channel video processing."
                    )
                else:
                    await update.message.reply_text("❌ Failed to save prompt to database")
            else:
                await update.message.reply_text(
                    "⚠️ Supabase not connected!\n\n"
                    "Prompt not saved. Use /set_supabase_url and /set_supabase_key first."
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Error setting prompt: {str(e)}")

    async def list_keys_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """List all API keys status"""
        try:
            if not self.supabase.is_connected():
                await update.message.reply_text(
                    "⚠️ Supabase not connected!\n\n"
                    "Use /set_supabase_url and /set_supabase_key to connect."
                )
                return

            keys = self.supabase.get_all_api_keys_status()

            if not keys:
                await update.message.reply_text(
                    "📊 No API keys found in database.\n\n"
                    "Add keys using:\n"
                    "• /set_youtube_key\n"
                    "• /add_supadata_key\n"
                    "• /set_deepseek_key"
                )
                return

            # Group by type
            youtube_keys = [k for k in keys if k['key_type'] == 'youtube']
            supadata_keys = [k for k in keys if k['key_type'] == 'supadata']
            deepseek_keys = [k for k in keys if k['key_type'] == 'deepseek']

            message = "📊 **API Keys Status**\n\n"

            # YouTube keys
            message += f"🎥 **YouTube API ({len(youtube_keys)} keys)**\n"
            for k in youtube_keys:
                status = "✅ Active" if k['is_active'] else "❌ Inactive"
                message += f"  • {k['api_key'][:20]}... - {status}\n"
            message += "\n"

            # Supadata keys
            message += f"📜 **Supadata API ({len(supadata_keys)} keys)**\n"
            active_count = sum(1 for k in supadata_keys if k['is_active'])
            message += f"  Active: {active_count}/{len(supadata_keys)}\n"
            for k in supadata_keys:
                status = "✅ Active" if k['is_active'] else "❌ Exhausted"
                message += f"  • {k['api_key'][:20]}... - {status}\n"
            message += "\n"

            # DeepSeek keys
            message += f"🤖 **DeepSeek API ({len(deepseek_keys)} keys)**\n"
            for k in deepseek_keys:
                status = "✅ Active" if k['is_active'] else "❌ Inactive"
                message += f"  • {k['api_key'][:20]}... - {status}\n"

            await update.message.reply_text(message, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"❌ Error listing keys: {str(e)}")
# YouTube Channel Processing Pipeline
# Add this method to WorkingF5Bot class

    async def process_youtube_channel(self, channel_url: str, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Complete pipeline to process a YouTube channel:
        1. Fetch top 1000 videos (>10min, sorted by views)
        2. Select 6 unique videos (15-day cooldown)
        3. For each video:
           - Get transcript
           - Chunk at 7000 chars
           - Process chunks with DeepSeek
           - Generate audio with global counter
           - Upload to Gofile
        4. Send all audio links
        """
        chat_id = update.effective_chat.id

        # Helper function to send messages (handles both direct messages and channels)
        async def send_message(text, parse_mode=None):
            """Send message that works for both channels and direct messages"""
            try:
                if update.message:
                    await update.message.reply_text(text, parse_mode=parse_mode)
                else:
                    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            except Exception as e:
                print(f"Error sending message: {e}")

        try:
            await send_message(
                "🔍 **YouTube Channel Detected!**\n\n"
                "📊 Starting channel processing...",
                parse_mode="Markdown"
            )

            # Step 1: Initialize YouTube processor with API key
            if not self.youtube_processor.youtube:
                # Get API key from database
                if self.supabase.is_connected():
                    yt_key = self.supabase.get_active_api_key('youtube')
                    if yt_key:
                        self.youtube_processor.set_api_key(yt_key)
                    else:
                        await send_message(
                            "❌ No YouTube API key found!\n\n"
                            "Use /set_youtube_key to add one."
                        )
                        return
                else:
                    await send_message(
                        "❌ Supabase not connected!\n\n"
                        "Use /set_supabase_url and /set_supabase_key first."
                    )
                    return

            # Step 2: Fetch channel videos
            await send_message("📺 Fetching channel videos...")

            channel_id, channel_name, all_videos = self.youtube_processor.get_channel_top_videos(
                channel_url, count=1000, min_duration_min=10
            )

            if not channel_id or not all_videos:
                await send_message(
                    "❌ Failed to fetch channel videos.\n"
                    "Please check the channel URL."
                )
                return

            # Show which channel was found (verification for user)
            await send_message(
                f"✅ **Channel Found:**\n"
                f"📺 {channel_name or 'Unknown'}\n"
                f"🆔 `{channel_id}`\n\n"
                f"📊 Found {len(all_videos)} videos (>10 min)\n"
                f"🎯 Selecting top 6 unique videos...",
                parse_mode="Markdown"
            )

            # Step 3: Get unprocessed video IDs (15-day cooldown)
            all_video_ids = [v['video_id'] for v in all_videos]
            unprocessed_ids = all_video_ids  # Default: all

            if self.supabase.is_connected():
                unprocessed_ids = self.supabase.get_unprocessed_videos(all_video_ids, days=15)

            # Step 4: Select top 6
            selected_videos = self.youtube_processor.select_unique_videos(
                all_videos, unprocessed_ids, count=6
            )

            if not selected_videos:
                await send_message(
                    "⚠️ No new videos to process!\n\n"
                    "All videos have been processed in the last 15 days.\n"
                    "Try again later or try a different channel."
                )
                return

            # Show selected video IDs
            video_list = "\n".join([
                f"{i+1}. `{v['video_id']}` - {v['title'][:40]}... ({v['view_count']:,} views)"
                for i, v in enumerate(selected_videos)
            ])

            await send_message(
                f"✅ **Selected {len(selected_videos)} videos:**\n\n"
                f"{video_list}\n\n"
                f"📹 Starting processing...\n"
                f"⏱️ Estimated time: 15-20 minutes",
                parse_mode="Markdown"
            )

            # Step 5: Process each video
            processed_count = 0
            all_audio_links = []

            for idx, video in enumerate(selected_videos, 1):
                video_id = video['video_id']
                video_url = video['url']
                video_title = video['title']

                try:
                    await send_message(
                        f"📹 **Video {idx}/6**\n"
                        f"🎬 {video_title[:60]}...\n"
                        f"🆔 Video ID: `{video_id}`\n"
                        f"👁️ Views: {video['view_count']:,}\n\n"
                        f"🔄 Processing...",
                        parse_mode="Markdown"
                    )

                    # Step 5a: Get transcript
                    transcript, key_exhausted = await self._get_transcript_with_rotation(video_url)

                    if not transcript:
                        await send_message(f"❌ Video {idx}: Transcript fetch failed. Skipping...")
                        continue

                    await send_message(
                        f"✅ Video {idx}: Transcript received ({len(transcript)} chars)"
                    )

                    # Step 5b: Chunk transcript
                    chunks = self.youtube_processor.chunk_text_at_fullstop(transcript, max_chars=7000)
                    await send_message(
                        f"📦 Video {idx}: Split into {len(chunks)} chunks"
                    )

                    # Step 5c: Process chunks with DeepSeek
                    processed_chunks = await self._process_chunks_with_deepseek(
                        chunks, video_id, chat_id, update, context, idx, len(selected_videos)
                    )

                    if not processed_chunks:
                        await send_message(f"❌ Video {idx}: DeepSeek processing failed. Skipping...")
                        continue

                    # Step 5d: Merge chunks
                    merged_script = "\n\n".join(processed_chunks)

                    # Save merged script
                    self.youtube_processor.save_merged_script(merged_script, video_id, self.chunks_dir)

                    await send_message(
                        f"✅ Video {idx}: Script processed ({len(merged_script)} chars)\n"
                        f"🎵 Generating audio..."
                    )

                    # Step 5e: Generate audio with global counter
                    audio_links = await self._generate_audio_with_counter(
                        merged_script, video_id, chat_id, update, context
                    )

                    if audio_links:
                        all_audio_links.extend(audio_links)
                        processed_count += 1

                        # Mark video as processed in database
                        if self.supabase.is_connected():
                            counter = self.supabase.get_counter()
                            self.supabase.mark_video_processed(
                                video_id, video_url, channel_id, str(chat_id), counter
                            )

                        await send_message(
                            f"✅ **Video {idx}/{len(selected_videos)} complete!**\n"
                            f"🆔 Video ID: `{video_id}`\n"
                            f"📊 Progress: {processed_count}/{len(selected_videos)} successful",
                            parse_mode="Markdown"
                        )
                    else:
                        await send_message(f"❌ Video {idx}: Audio generation failed. Skipping...")

                except Exception as e:
                    print(f"Error processing video {idx}: {e}")
                    await send_message(
                        f"❌ Video {idx}: Error - {str(e)[:100]}\n"
                        f"Continuing with next video..."
                    )
                    continue

            # Step 6: Final summary
            if processed_count > 0:
                summary = (
                    f"🎉 **Channel Processing Complete!**\n\n"
                    f"✅ Successfully processed: {processed_count}/{len(selected_videos)} videos\n"
                    f"🔗 Total audio files: {len(all_audio_links)}\n\n"
                    f"📊 All audio links have been sent above.\n"
                    f"💾 Scripts saved in: {self.chunks_dir}/"
                )
                await send_message(summary, parse_mode="Markdown")
            else:
                await send_message(
                    "❌ No videos were successfully processed.\n"
                    "Please check logs for errors."
                )

        except Exception as e:
            error_msg = f"❌ Channel processing error: {str(e)}"
            print(error_msg)
            await send_message(error_msg[:500])

    async def _get_transcript_with_rotation(self, video_url: str) -> tuple:
        """
        Get transcript with automatic Supadata key rotation on exhaustion.
        Returns: (transcript_text, key_exhausted)
        """
        max_attempts = 5  # Try up to 5 different keys

        for attempt in range(max_attempts):
            # Get active Supadata key
            api_key = None
            if self.supabase.is_connected():
                api_key = self.supabase.get_active_api_key('supadata')
            else:
                api_key = os.getenv("SUPADATA_API_KEY")

            if not api_key:
                print("❌ No Supadata API key available")
                return None, False

            # Try to get transcript
            transcript, key_exhausted = await get_youtube_transcript(video_url, api_key)

            if transcript:
                return transcript, False

            if key_exhausted:
                print(f"⚠️ Supadata key exhausted. Rotating... (attempt {attempt + 1}/{max_attempts})")
                # Mark key as exhausted
                if self.supabase.is_connected():
                    self.supabase.mark_key_exhausted(api_key)
                continue
            else:
                # Other error, no point rotating
                return None, False

        print("❌ All Supadata keys exhausted")
        return None, True

    async def _process_chunks_with_deepseek(self, chunks: list, video_id: str, chat_id: int,
                                           update: Update, context: ContextTypes.DEFAULT_TYPE,
                                           video_idx: int, total_videos: int) -> list:
        """
        Process each chunk with DeepSeek API and save to disk.
        Returns list of processed chunks.
        """
        # Helper to send messages (works for both channels and direct messages)
        async def send_msg(text, parse_mode=None):
            try:
                if update.message:
                    await update.message.reply_text(text, parse_mode=parse_mode)
                else:
                    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            except Exception as e:
                print(f"Error sending message: {e}")

        # Get DeepSeek API key
        deepseek_key = None
        if self.supabase.is_connected():
            deepseek_key = self.supabase.get_active_api_key('deepseek')
        if not deepseek_key:
            deepseek_key = os.getenv("DEEPSEEK_API_KEY")

        if not deepseek_key:
            print("❌ No DeepSeek API key available")
            return []

        # Get custom prompt if available
        prompt = None
        if self.supabase.is_connected():
            prompt = self.supabase.get_prompt('channel')
        if not prompt:
            prompt = "Rewrite this content to be more engaging and natural for text-to-speech audio:"

        processed_chunks = []

        # Save original chunks
        self.youtube_processor.save_chunks_to_disk(chunks, video_id, self.chunks_dir)

        for chunk_idx, chunk in enumerate(chunks, 1):
            try:
                await send_msg(
                    f"🤖 Video {video_idx}: Processing chunk {chunk_idx}/{len(chunks)}..."
                )

                # Process with DeepSeek (use existing method from bot)
                processed = await self.process_with_deepseek(
                    chunk, chat_id, context, custom_prompt=prompt
                )

                if processed:
                    processed_chunks.append(processed)
                else:
                    # Fallback to original chunk
                    processed_chunks.append(chunk)

            except Exception as e:
                print(f"Error processing chunk {chunk_idx}: {e}")
                # Fallback to original chunk
                processed_chunks.append(chunk)

        return processed_chunks

    async def _generate_audio_with_counter(self, script: str, video_id: str, chat_id: int,
                                          update: Update, context: ContextTypes.DEFAULT_TYPE) -> list:
        """
        Generate audio using F5-TTS with global counter-based naming.
        Returns list of Gofile links.
        """
        # Helper to send messages (works for both channels and direct messages)
        async def send_msg(text, parse_mode=None):
            try:
                if update.message:
                    await update.message.reply_text(text, parse_mode=parse_mode)
                else:
                    await context.bot.send_message(chat_id=chat_id, text=text, parse_mode=parse_mode)
            except Exception as e:
                print(f"Error sending message: {e}")

        try:
            # Get and increment global counter
            counter = 0
            if self.supabase.is_connected():
                counter = self.supabase.increment_counter()
            else:
                # Fallback: use timestamp
                counter = int(time.time()) % 10000

            # Generate audio (use existing generate_audio method)
            # Modify output path to use counter
            base_output_path = os.path.join(OUTPUT_DIR, f"{counter}")

            # Use existing audio generation logic but with custom filename
            raw_output = f"{base_output_path}_raw.wav"
            enhanced_output = f"{base_output_path}_enhanced.wav"

            # Generate raw audio
            await send_msg(f"🎵 Generating audio {counter}_raw.wav...")
            raw_success = await self._generate_f5_audio(script, raw_output, chat_id, context)

            if not raw_success:
                return []

            # Apply filters for enhanced version
            await send_msg(f"🎛️ Creating enhanced version...")
            self.apply_audio_filters(raw_output, enhanced_output)

            # Upload both files
            links = []

            for file_path in [raw_output, enhanced_output]:
                if os.path.exists(file_path):
                    filename = os.path.basename(file_path)
                    size_mb = os.path.getsize(file_path) // (1024 * 1024)

                    # Upload to Gofile
                    link = await self.upload_single_to_gofile(file_path)

                    if link:
                        await send_msg(
                            f"🔗 **{filename}** ({size_mb} MB)\n{link}",
                            parse_mode="Markdown"
                        )
                        links.append(link)
                    else:
                        await send_msg(f"⚠️ Failed to upload {filename}")

            return links

        except Exception as e:
            print(f"Error generating audio: {e}")
            return []

    async def _generate_f5_audio(self, text: str, output_path: str, chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Generate audio using F5-TTS (wrapper around existing method).
        Returns True if successful.
        """
        try:
            # Use existing generate_audio method from the bot
            # This is a simplified version - you may need to adapt based on your existing implementation

            if not self.f5_model or not self.reference_audio:
                print("❌ F5-TTS model or reference audio not initialized")
                return False

            # Generate audio (use your existing F5-TTS generation code)
            # This is placeholder - adapt to your actual F5-TTS implementation
            from f5_tts.api import F5TTS

            # Generate audio chunks
            wav = self.f5_model.infer(
                ref_audio=self.reference_audio,
                ref_text=self.reference_text,
                gen_text=text[:self.chunk_size],  # Use configured chunk size
                speed=self.audio_speed
            )

            # Save audio
            import soundfile as sf
            sf.write(output_path, wav, 24000)

            return True

        except Exception as e:
            print(f"F5-TTS generation error: {e}")
            return False

    async def start_processing_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Skip batch timer and start processing immediately"""
        try:
            if not self.batch_mode:
                await update.message.reply_text(
                    "ℹ️ No batch collection in progress.\n\n"
                    f"📊 Queue: {len(self.processing_queue)} files\n"
                    f"⏳ Processing status: {'Active' if self.is_processing else 'Idle'}"
                )
                return

            queue_size = len(self.processing_queue)

            if queue_size == 0:
                await update.message.reply_text("❌ Queue is empty!")
                return

            # Cancel timer and start immediately
            await update.message.reply_text(
                f"⚡ **STARTING IMMEDIATELY**\n\n"
                f"📊 Files in queue: {queue_size}\n"
                f"⏱️ Batch timer skipped!\n\n"
                f"Processing will start now..."
            )

            # Stop batch mode
            self.batch_mode = False
            self.queue_start_time = None

            # Start processing
            chat_id = update.effective_chat.id
            asyncio.create_task(self.process_queue(context))

        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def update_ytdlp_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Update yt-dlp to latest version"""
        try:
            await update.message.reply_text("🔄 Updating yt-dlp to latest version...\nThis may take 10-30 seconds.")

            # Run pip update command
            result = subprocess.run(
                ["pip", "install", "-U", "yt-dlp"],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode == 0:
                # Get version
                version_result = subprocess.run(
                    ["yt-dlp", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                version = version_result.stdout.strip() if version_result.returncode == 0 else "unknown"

                await update.message.reply_text(
                    f"✅ yt-dlp updated successfully!\n\n"
                    f"📦 Version: {version}\n\n"
                    f"🎥 You can now try downloading YouTube videos again.\n"
                    f"If still getting 403 errors, wait 2-5 minutes."
                )
            else:
                error_msg = result.stderr[:500] if result.stderr else "Unknown error"
                await update.message.reply_text(
                    f"❌ Update failed!\n\n"
                    f"Error: {error_msg}\n\n"
                    f"💡 Try manually:\n"
                    f"`pip install -U yt-dlp`"
                )
        except subprocess.TimeoutExpired:
            await update.message.reply_text(
                "⏱️ Update timed out!\n\n"
                "💡 Try manually:\n"
                "`pip install -U yt-dlp`"
            )
        except Exception as e:
            await update.message.reply_text(f"❌ Update error: {str(e)}")

    async def set_openrouter_model_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Change OpenRouter model via Telegram"""
        try:
            if context.args:
                new_model = " ".join(context.args)
                self.openrouter_model = new_model

                # Save configuration to file
                self.save_config()

                await update.message.reply_text(
                    f"✅ OpenRouter model updated and saved!\n\n"
                    f"🌐 New model: {new_model}\n\n"
                    f"💡 Popular models:\n"
                    f"• deepseek/deepseek-chat\n"
                    f"• anthropic/claude-3.5-sonnet\n"
                    f"• openai/gpt-4-turbo\n"
                    f"• google/gemini-pro-1.5\n"
                    f"• meta-llama/llama-3.1-70b-instruct"
                )
            else:
                await update.message.reply_text(
                    f"🌐 Current OpenRouter model:\n{self.openrouter_model}\n\n"
                    f"💡 Usage: /set_openrouter_model model_name\n\n"
                    f"Examples:\n"
                    f"/set_openrouter_model deepseek/deepseek-chat\n"
                    f"/set_openrouter_model anthropic/claude-3.5-sonnet\n"
                    f"/set_openrouter_model openai/gpt-4-turbo\n\n"
                    f"Find more models at: https://openrouter.ai/models"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ OpenRouter model update error: {str(e)}")

    async def set_ffmpeg_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Change FFmpeg audio filter via Telegram"""
        try:
            chat_id = update.effective_chat.id

            if context.args:
                raw_input = " ".join(context.args)

                # Smart parsing - extract filter from full ffmpeg command if needed
                new_filter = self._extract_ffmpeg_filter(raw_input)

                if not new_filter:
                    response = (
                        "❌ Could not extract filter!\n\n"
                        "Please provide either:\n"
                        "1. Just the filter: afftdn=nr=12,highpass=f=80\n"
                        "2. Full command: ffmpeg -i input.wav -af \"filter\" output.wav\n\n"
                        "Current filter unchanged."
                    )
                    await context.bot.send_message(chat_id=chat_id, text=response)
                    return

                self.ffmpeg_filter = new_filter

                # Save configuration to file
                self.save_config()

                response = (
                    f"✅ FFmpeg filter updated and saved!\n\n"
                    f"🎚️ New filter: {new_filter}\n\n"
                    f"This will be applied to all enhanced audio from now on."
                )
                await context.bot.send_message(chat_id=chat_id, text=response)
            else:
                response = (
                    f"🎚️ Current FFmpeg filter:\n{self.ffmpeg_filter}\n\n"
                    f"💡 Usage: /set_ffmpeg your_filter_here\n\n"
                    f"Example:\n/set_ffmpeg afftdn=nr=12:nf=-25,highpass=f=80,lowpass=f=10000"
                )
                await context.bot.send_message(chat_id=chat_id, text=response)
        except Exception as e:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"❌ FFmpeg filter update error: {str(e)}")

    async def set_chunk_size_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Change audio generation chunk size via Telegram"""
        try:
            chat_id = update.effective_chat.id

            if context.args:
                try:
                    new_size = int(context.args[0])

                    if new_size < 100 or new_size > 5000:
                        response = (
                            "❌ Invalid chunk size!\n\n"
                            "Must be between 100 and 5000 characters.\n\n"
                            "Recommended values:\n"
                            "• 500 (default) - Best quality, slower\n"
                            "• 1000 - Good quality, faster\n"
                            "• 1500 - Decent quality, fast\n"
                            "• 2000+ - Lower quality, very fast (RTX 4090 recommended)"
                        )
                        await context.bot.send_message(chat_id=chat_id, text=response)
                        return

                    old_size = self.chunk_size
                    self.chunk_size = new_size

                    # Save configuration to file
                    self.save_config()

                    response = (
                        f"✅ Chunk size updated and saved!\n\n"
                        f"📊 Old: {old_size} chars\n"
                        f"📊 New: {new_size} chars\n\n"
                        f"⚠️ Warning:\n"
                        f"Higher chunk size = Faster processing but LOWER audio quality!\n\n"
                        f"Best for:\n"
                        f"• 500-1000: High quality (recommended)\n"
                        f"• 1500-2000: Balanced (RTX 3090/4080)\n"
                        f"• 2000+: Speed priority (RTX 4090)"
                    )
                    await context.bot.send_message(chat_id=chat_id, text=response)
                except ValueError:
                    await context.bot.send_message(chat_id=chat_id, text="❌ Please provide a valid number!\n\nExample: /set_chunk_size 1000")
            else:
                response = (
                    f"📊 Current chunk size: {self.chunk_size} characters\n\n"
                    f"💡 Usage: /set_chunk_size <number>\n\n"
                    f"Examples:\n"
                    f"• /set_chunk_size 500 (best quality)\n"
                    f"• /set_chunk_size 1000 (good quality)\n"
                    f"• /set_chunk_size 2000 (fast, RTX 4090)\n\n"
                    f"⚠️ Higher values = Faster but lower quality!"
                )
                await context.bot.send_message(chat_id=chat_id, text=response)
        except Exception as e:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=f"❌ Chunk size update error: {str(e)}")

    def _extract_ffmpeg_filter(self, raw_input):
        """Extract filter string from FFmpeg command or return as-is if already a filter"""
        try:
            # Remove extra spaces
            raw_input = raw_input.strip()

            # Check if it's a full FFmpeg command (starts with 'ffmpeg')
            if raw_input.lower().startswith('ffmpeg'):
                # Look for -af or -filter:a flag
                import re

                # Pattern 1: -af "filter" or -af 'filter'
                match = re.search(r'-af\s+["\'](.+?)["\']', raw_input)
                if match:
                    return match.group(1)

                # Pattern 2: -af filter (without quotes, until next flag or end)
                # Match filter parts (contains = or , but not .wav/.mp3/.mp4 filenames)
                match = re.search(r'-af\s+([a-zA-Z0-9_=:,\-]+)(?:\s|$)', raw_input)
                if match:
                    return match.group(1).strip()

                # Pattern 3: -filter:a "filter" or -filter:a 'filter'
                match = re.search(r'-filter:a\s+["\'](.+?)["\']', raw_input)
                if match:
                    return match.group(1)

                # Pattern 4: -filter:a filter
                match = re.search(r'-filter:a\s+([a-zA-Z0-9_=:,\-]+)(?:\s|$)', raw_input)
                if match:
                    return match.group(1).strip()

                # Could not extract filter
                return None
            else:
                # Not a full command, assume it's already a filter
                # Remove quotes if present
                if raw_input.startswith('"') and raw_input.endswith('"'):
                    raw_input = raw_input[1:-1]
                elif raw_input.startswith("'") and raw_input.endswith("'"):
                    raw_input = raw_input[1:-1]

                return raw_input

        except Exception as e:
            print(f"❌ Filter extraction error: {e}")
            return None

    @staticmethod
    def _extract_ffmpeg_filter_static(raw_input):
        """Static version of filter extractor for use during config loading"""
        try:
            import re
            raw_input = raw_input.strip()

            # Check if it's a full FFmpeg command (starts with 'ffmpeg')
            if raw_input.lower().startswith('ffmpeg'):
                # Pattern 1: -af "filter" or -af 'filter'
                match = re.search(r'-af\s+["\'](.+?)["\']', raw_input)
                if match:
                    return match.group(1)

                # Pattern 2: -af filter (without quotes)
                match = re.search(r'-af\s+([a-zA-Z0-9_=:,\-]+)(?:\s|$)', raw_input)
                if match:
                    return match.group(1).strip()

                # Pattern 3: -filter:a "filter"
                match = re.search(r'-filter:a\s+["\'](.+?)["\']', raw_input)
                if match:
                    return match.group(1)

                # Pattern 4: -filter:a filter
                match = re.search(r'-filter:a\s+([a-zA-Z0-9_=:,\-]+)(?:\s|$)', raw_input)
                if match:
                    return match.group(1).strip()

                # Could not extract, return default
                print(f"⚠️ Could not extract filter from command, using default")
                return 'afftdn=nr=12:nf=-25,highpass=f=80,lowpass=f=10000,equalizer=f=6000:t=h:width=2000:g=-6'
            else:
                # Not a full command, remove quotes if present
                if raw_input.startswith('"') and raw_input.endswith('"'):
                    raw_input = raw_input[1:-1]
                elif raw_input.startswith("'") and raw_input.endswith("'"):
                    raw_input = raw_input[1:-1]
                return raw_input

        except Exception as e:
            print(f"❌ Static filter extraction error: {e}, using default")
            return 'afftdn=nr=12:nf=-25,highpass=f=80,lowpass=f=10000,equalizer=f=6000:t=h:width=2000:g=-6'

    async def set_jesus_prompt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set Jesus image prompt"""
        try:
            if context.args:
                new_prompt = " ".join(context.args)
                self.jesus_prompt = new_prompt
                self.save_config()

                await update.message.reply_text(
                    f"✅ Jesus prompt updated and saved!\n\n"
                    f"✝️ New prompt: {new_prompt}"
                )
            else:
                await update.message.reply_text(
                    f"✝️ Current Jesus prompt:\n{self.jesus_prompt}\n\n"
                    f"💡 Usage: /set_jesus_prompt your_prompt_here\n\n"
                    f"Example:\n/set_jesus_prompt A serene image of Jesus with divine light"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Jesus prompt update error: {str(e)}")

    async def set_nature_prompt_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set Nature image prompt"""
        try:
            if context.args:
                new_prompt = " ".join(context.args)
                self.nature_prompt = new_prompt
                self.save_config()

                await update.message.reply_text(
                    f"✅ Nature prompt updated and saved!\n\n"
                    f"🌿 New prompt: {new_prompt}"
                )
            else:
                await update.message.reply_text(
                    f"🌿 Current Nature prompt:\n{self.nature_prompt}\n\n"
                    f"💡 Usage: /set_nature_prompt your_prompt_here\n\n"
                    f"Example:\n/set_nature_prompt Beautiful nature landscape with mountains and sunset"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Nature prompt update error: {str(e)}")

    async def set_leonardo_url_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set Leonardo AI URL"""
        try:
            if context.args:
                new_url = " ".join(context.args)
                self.leonardo_url = new_url
                self.save_config()

                await update.message.reply_text(
                    f"✅ Leonardo URL updated and saved!\n\n"
                    f"🎨 New URL: {new_url}"
                )
            else:
                await update.message.reply_text(
                    f"🎨 Current Leonardo URL:\n{self.leonardo_url}\n\n"
                    f"💡 Usage: /set_leonardo_url your_url_here\n\n"
                    f"Example:\n/set_leonardo_url https://leonardo.ai"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Leonardo URL update error: {str(e)}")

    async def set_title_prompt1_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set Title Generation Prompt 1 (Initial)"""
        try:
            if context.args:
                new_prompt = " ".join(context.args)
                self.title_prompt_1 = new_prompt
                self.save_config()

                await update.message.reply_text(
                    f"✅ Title Prompt 1 (Initial) updated and saved!\n\n"
                    f"📝 New prompt: {new_prompt}"
                )
            else:
                await update.message.reply_text(
                    f"📝 Current Title Prompt 1 (Initial):\n{self.title_prompt_1}\n\n"
                    f"💡 Usage: /set_title_prompt1 your_prompt_here\n\n"
                    f"Example:\n/set_title_prompt1 Generate a catchy title for this video script:"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Title Prompt 1 update error: {str(e)}")

    async def set_title_prompt2_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set Title Generation Prompt 2 (Refine)"""
        try:
            if context.args:
                new_prompt = " ".join(context.args)
                self.title_prompt_2 = new_prompt
                self.save_config()

                await update.message.reply_text(
                    f"✅ Title Prompt 2 (Refine) updated and saved!\n\n"
                    f"📝 New prompt: {new_prompt}"
                )
            else:
                await update.message.reply_text(
                    f"📝 Current Title Prompt 2 (Refine):\n{self.title_prompt_2}\n\n"
                    f"💡 Usage: /set_title_prompt2 your_prompt_here\n\n"
                    f"Example:\n/set_title_prompt2 Refine this title to make it more engaging:"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Title Prompt 2 update error: {str(e)}")

    async def set_title_prompt3_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set Title Generation Prompt 3 (Final Polish)"""
        try:
            if context.args:
                new_prompt = " ".join(context.args)
                self.title_prompt_3 = new_prompt
                self.save_config()

                await update.message.reply_text(
                    f"✅ Title Prompt 3 (Final Polish) updated and saved!\n\n"
                    f"📝 New prompt: {new_prompt}"
                )
            else:
                await update.message.reply_text(
                    f"📝 Current Title Prompt 3 (Final Polish):\n{self.title_prompt_3}\n\n"
                    f"💡 Usage: /set_title_prompt3 your_prompt_here\n\n"
                    f"Example:\n/set_title_prompt3 Polish this title to perfection:"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Title Prompt 3 update error: {str(e)}")

    async def set_title_prompt_10more_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set Title Generation Prompt for 10 More Titles"""
        try:
            if context.args:
                new_prompt = " ".join(context.args)
                self.title_prompt_10_more = new_prompt
                self.save_config()

                await update.message.reply_text(
                    f"✅ Title Prompt (10 More) updated and saved!\n\n"
                    f"📝 New prompt: {new_prompt}"
                )
            else:
                await update.message.reply_text(
                    f"📝 Current Title Prompt (10 More):\n{self.title_prompt_10_more}\n\n"
                    f"💡 Usage: /set_title_prompt_10more your_prompt_here\n\n"
                    f"Example:\n/set_title_prompt_10more Generate 10 different catchy titles for this script:"
                )
        except Exception as e:
            await update.message.reply_text(f"❌ Title Prompt (10 More) update error: {str(e)}")

    async def ref_status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show current reference status with buttons"""
        ref_name = os.path.basename(self.reference_audio) if self.reference_audio else "None"
        ref_text = self.reference_text[:200] if self.reference_text else "None"
        
        # Create buttons for reference actions
        keyboard = [
            [InlineKeyboardButton("🔄 Revert to Default", callback_data="ref:back")],
            [InlineKeyboardButton("🎵 Set New Reference", callback_data="settings:ref")],
            [InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🎵 Current Reference Status:\n\n"
            f"📁 File: {ref_name}\n"
            f"📝 Text: {ref_text}{'...' if len(ref_text) > 200 else ''}\n\n"
            f"Choose an action:",
            reply_markup=reply_markup
        )

    async def set_ref_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Command to set new reference - reply to an audio message with /set_ref"""
        try:
            # Check if replying to a message
            if not update.message.reply_to_message:
                await update.message.reply_text(
                    "❌ Usage:\n"
                    "1. Send an audio file to the bot\n"
                    "2. Reply to that audio with /set_ref\n\n"
                    "Or use: /set_ref [then forward an audio]"
                )
                return
            
            replied_msg = update.message.reply_to_message
            print(f"🔍 Checking replied message for audio/voice...")
            print(f"Has audio: {bool(replied_msg.audio)}")
            print(f"Has voice: {bool(replied_msg.voice)}")
            print(f"Has document: {bool(getattr(replied_msg, 'document', None))}")
            
            # Check for audio, voice, or document
            if replied_msg.audio:
                file = await context.bot.get_file(replied_msg.audio.file_id)
                filename = f"ref_{int(time.time())}.mp3"
                print(f"📁 Processing audio file")
            elif replied_msg.voice:
                file = await context.bot.get_file(replied_msg.voice.file_id)
                filename = f"ref_{int(time.time())}.ogg"
                print(f"🎤 Processing voice message")
            elif getattr(replied_msg, 'document', None) and replied_msg.document.mime_type and replied_msg.document.mime_type.startswith('audio'):
                file = await context.bot.get_file(replied_msg.document.file_id)
                filename = f"ref_{int(time.time())}.{replied_msg.document.file_name.split('.')[-1]}"
                print(f"📄 Processing audio document")
            else:
                await update.message.reply_text("❌ The replied message must contain audio, voice, or audio document")
                return
            
            await update.message.reply_text("🎵 Processing new reference audio...")
            
            file_path = os.path.join(REFERENCE_DIR, filename)
            await file.download_to_drive(file_path)
            
            # Extract text with Whisper
            if not self.whisper_model:
                self.whisper_model = whisper.load_model("base", device="cpu")
            
            result = self.whisper_model.transcribe(file_path)
            new_ref_text = result["text"].strip()
            
            # Delete old reference audio to save storage (except default k.wav)
            if self.reference_audio and os.path.exists(self.reference_audio):
                old_filename = os.path.basename(self.reference_audio)
                if not old_filename.startswith('k.') and old_filename != 'k,.wav':  # Keep default
                    try:
                        os.remove(self.reference_audio)
                        print(f"🗑️ Deleted old reference: {old_filename}")
                    except Exception as e:
                        print(f"⚠️ Could not delete old reference: {e}")
            
            # Update bot's reference
            old_ref = os.path.basename(self.reference_audio) if self.reference_audio else "None"
            self.reference_audio = file_path
            self.reference_text = new_ref_text

            # Clear any cached reference data to prevent conflicts
            if hasattr(self.f5_model, '_cached_ref_audio'):
                delattr(self.f5_model, '_cached_ref_audio')
            if hasattr(self.f5_model, '_cached_ref_text'):
                delattr(self.f5_model, '_cached_ref_text')
            
            # Force F5-TTS to reload reference on next generation
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            import gc
            gc.collect()
            
            print(f"✅ Cleared F5-TTS cache for new reference")
            
            await update.message.reply_text(
                f"✅ Reference audio updated!\n\n"
                f"🔄 Previous: {old_ref}\n"
                f"🎵 New: {filename}\n\n"
                f"📝 Extracted text: {new_ref_text[:150]}{'...' if len(new_ref_text) > 150 else ''}\n\n"
                f"Use /ref_back to revert to default."
            )
            
        except Exception as e:
            error_msg = f"❌ Reference update error: {str(e)}"
            print(error_msg)
            await update.message.reply_text(error_msg)


    async def test_audio_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Temporary test handler to debug audio processing"""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id if update.effective_user else "Channel/Anonymous"
        print(f"🔥 TEST: Audio message received from user {user_id}, chat {chat_id}")

        # Send reply only if it's a regular message (not channel post)
        if update.message and update.message.chat.type != "channel":
            await update.message.reply_text("🔥 TEST: Audio handler is working!")

        # Now call the actual reference handler
        await self.handle_audio_reference(update, context)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command - with buttons for settings and processing"""
        try:
            f5_status = "✅ Ready" if self.f5_model else "❌ Failed"
            ref_status = "✅ Ready" if self.reference_audio and self.reference_text else "❌ Missing"
            
            if self.reference_audio and self.reference_text:
                ref_info = f"📁 File: {os.path.basename(self.reference_audio)}\n📝 Text: {self.reference_text[:100]}..."
            else:
                ref_info = "📁 Add audio file to reference/ folder and restart"
            
            welcome_text = (
                f"🎉 F5-TTS Bot Ready!\n\n"
                f"🔧 F5-TTS Status: {f5_status}\n"
                f"🎵 Reference Status: {ref_status}\n\n"
                f"{ref_info}\n\n"
                f"📋 How to use:\n"
                f"📄 Send .txt file with script\n"
                f"📝 Or type text directly\n"
                f"🔗 Send YouTube links for transcript processing\n"
                f"🎵 Send audio to change reference"
            )
            
            # Create main menu buttons
            keyboard = [
                [InlineKeyboardButton("⚙️ Settings", callback_data="main:settings")],
                [InlineKeyboardButton("🔄 Processing", callback_data="main:process")],
                [InlineKeyboardButton("📊 Status", callback_data="main:status")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(welcome_text, reply_markup=reply_markup)
            print(f"✅ Start command sent to user: {update.effective_user.id}")
            # Store the welcome text for reuse in callbacks
            self.welcome_text = welcome_text
            
        except Exception as e:
            print(f"❌ Start command error: {e}")
            await update.message.reply_text("❌ Bot startup error. Please restart.")
        
    async def on_main_menu(self, update, context):
        q = update.callback_query
        try:
            await q.answer()
        except:
            pass

        data = q.data or ""
        chat_id = q.message.chat.id if q and q.message and q.message.chat else None
        
        if data == "main:settings":
            # Settings submenu - ALL COMMANDS ORGANIZED HERE (DeepSeek options removed)
            keyboard = [
                [InlineKeyboardButton("🎵 Reference Audio", callback_data="settings:ref_menu")],
                [InlineKeyboardButton("⚡ Audio Settings", callback_data="settings:audio_menu")],
                [InlineKeyboardButton("📄 Delivery Mode", callback_data="settings:delivery")],
                [InlineKeyboardButton("🔗 Completed Files", callback_data="settings:links")],
                [InlineKeyboardButton("⚡ Power & Control", callback_data="settings:power_menu")],
                [InlineKeyboardButton("🔧 Debug Tools", callback_data="settings:debug")],
                [InlineKeyboardButton("🔄 Pipeline", callback_data="settings:pipeline_menu")],
                [InlineKeyboardButton("🔙 Back to Main", callback_data="main:back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            try:
                await q.edit_message_text(
                    "⚙️ Settings Menu\n\n📋 All commands organized here for easy access:",
                    reply_markup=reply_markup
                )
            except:
                await q.message.reply_text("⚙️ Settings Menu\n\n📋 All commands organized here for easy access:", reply_markup=reply_markup)
        
        elif data == "main:process":
            # Processing options with buttons
            keyboard = [
                [InlineKeyboardButton("📄 Upload Text File", callback_data="process:upload_txt")],
                [InlineKeyboardButton("📝 Type Direct Message", callback_data="process:direct_text")],
                [InlineKeyboardButton("🔗 Process YouTube Link", callback_data="process:youtube")],
                [InlineKeyboardButton("🔙 Back to Main", callback_data="main:back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await q.edit_message_text(
                "🎵 Processing Mode\n\n"
                "Choose how you want to process content:\n"
                "1. Upload a text file (.txt)\n" 
                "2. Type or paste text directly\n"
                "3. Send a YouTube link to transcribe and process\n\n"
                "Or simply send your content directly in chat!",
                reply_markup=reply_markup
            )
        
        elif data == "main:status":
            # Status info
            queue_count = len(self.processing_queue)
            completed_count = len(self.completed_files)
            
            status_text = (
                f"📊 Bot Status\n\n"
                f"📝 Queue: {queue_count} items\n"
                f"✅ Completed: {completed_count} files\n"
                f"🔄 Processing: {'Yes' if self.is_processing else 'No'}\n"
                f"⚡ Speed: {self.audio_speed}x\n"
                f"🔧 Quality: {self.audio_quality}\n"
                f"🎵 Reference: {os.path.basename(self.reference_audio) if self.reference_audio else 'Not set'}\n\n"
            )
            
            keyboard = [
                [InlineKeyboardButton("📃 View Completed Files", callback_data="status:links")],
                [InlineKeyboardButton("🔙 Back to Main", callback_data="main:back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            try:
                await q.edit_message_text(status_text, reply_markup=reply_markup)
            except:
                await q.message.reply_text(status_text, reply_markup=reply_markup)
        
        elif data == "main:back":
            # Back to main menu - create the same content as start_command but for callback
            try:
                f5_status = "✅ Ready" if self.f5_model else "❌ Failed"
                ref_status = "✅ Ready" if self.reference_audio and self.reference_text else "❌ Missing"
                
                if self.reference_audio and self.reference_text:
                    ref_info = f"📁 File: {os.path.basename(self.reference_audio)}\n📝 Text: {self.reference_text[:100]}..."
                else:
                    ref_info = "📁 Add audio file to reference/ folder and restart"
                
                welcome_text = (
                    f"🎉 F5-TTS Bot Ready!\n\n"
                    f"🔧 F5-TTS Status: {f5_status}\n"
                    f"🎵 Reference Status: {ref_status}\n\n"
                    f"{ref_info}\n\n"
                    f"📋 How to use:\n"
                    f"📝 Send .txt file with script\n"
                    f"📝 Or type text directly\n"
                    f"🔗 Send YouTube links for transcript processing\n"
                    f"🎵 Send audio to change reference"
                )
                
                # Create main menu buttons
                keyboard = [
                    [InlineKeyboardButton("⚙️ Settings", callback_data="main:settings")],
                    [InlineKeyboardButton("🔄 Processing", callback_data="main:process")],
                    [InlineKeyboardButton("📊 Status", callback_data="main:status")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                await q.edit_message_text(welcome_text, reply_markup=reply_markup)
            except Exception as e:
                print(f"❌ Back to main error: {e}")
                # If edit fails, try sending a new message
                try:
                    await q.message.reply_text("⚙️ Returning to main menu...")
                    await self.start_command(q.message, context)
                except Exception as e2:
                    print(f"❌ Fallback error: {e2}")
            
        elif data == "status:links":
            # Show completed files
            await self.links_command(q, context)
    
    async def test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Test command - quick generation test"""
        try:
            if not self.f5_model:
                await update.message.reply_text("❌ F5-TTS not initialized!")
                return
                
            if not self.reference_audio or not self.reference_text:
                await update.message.reply_text("❌ Reference audio missing!")
                return
            
            await update.message.reply_text("🧪 Running quick test...")
            
            test_text = "Hello, this is a quick test of the F5-TTS bot."
            success, output_files = await self.generate_audio_f5(test_text)
            if success:
                chat_id = update.effective_chat.id
                self.latest_outputs_by_chat[chat_id] = {"paths": output_files, "links": {}, "filename": "Test", "ts": time.time()}
                await self.send_outputs_by_mode(context, chat_id, output_files, "Test generation", "Test")
            else:
                await update.message.reply_text(f"❌ Test failed: {output_files}")
                
        except Exception as e:
            await update.message.reply_text(f"❌ Test error: {str(e)}")
    
    async def settings_command(self, update, context):
        # Show main settings menu with buttons - ALL COMMANDS ORGANIZED HERE (DeepSeek options removed)
        chat_id = update.effective_chat.id
        keyboard = [
            [InlineKeyboardButton("🎵 Reference Audio", callback_data="settings:ref_menu")],
            [InlineKeyboardButton("⚡ Audio Settings", callback_data="settings:audio_menu")],
            [InlineKeyboardButton("📄 Delivery Mode", callback_data="settings:delivery")],
            [InlineKeyboardButton("🔗 Completed Files", callback_data="settings:links")],
            [InlineKeyboardButton("⚡ Power & Control", callback_data="settings:power_menu")],
            [InlineKeyboardButton("🔧 Debug Tools", callback_data="settings:debug")],
            [InlineKeyboardButton("🔄 Pipeline", callback_data="settings:pipeline_menu")],
            [InlineKeyboardButton("🔙 Back to Main", callback_data="main:back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            "⚙️ Settings Menu\n\n📋 All commands organized here for easy access:",
            reply_markup=reply_markup
        )

    async def on_settings(self, update, context):
        q = update.callback_query
        try:
            await q.answer()
        except Exception:
            pass

        chat_id = None
        try:
            chat_id = q.message.chat.id if q and q.message and q.message.chat else None
        except Exception:
            chat_id = None
        if not chat_id:
            chat_id = q.from_user.id if q and q.from_user else None

        data = q.data or ""
        
        # Handle close button
        if data == "settings:close":
            try:
                await q.edit_message_reply_markup(reply_markup=None)
            except Exception:
                pass
            return

        # ====== NEW ORGANIZED MENU HANDLERS ======

        # 1. REFERENCE AUDIO MENU
        elif data == "settings:ref_menu":
            ref_name = os.path.basename(self.reference_audio) if self.reference_audio else "Not set"
            ref_text = self.reference_text[:50] + "..." if self.reference_text and len(self.reference_text) > 50 else self.reference_text or "Not set"

            keyboard = [
                [InlineKeyboardButton("🎵 Set New Reference", callback_data="settings:ref_set")],
                [InlineKeyboardButton("🔄 Restore Default", callback_data="settings:ref_restore")],
                [InlineKeyboardButton("📊 Check Status", callback_data="settings:ref_status")],
                [InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]
            ]
            await q.edit_message_text(
                f"🎵 Reference Audio Menu\n\n"
                f"Current Reference:\n"
                f"📁 File: {ref_name}\n"
                f"📝 Text: {ref_text}\n\n"
                f"Choose an option:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif data == "settings:ref_set":
            await q.edit_message_text(
                "🎵 Set New Reference Audio\n\n"
                "Send a voice message or audio file to set as your new reference.\n\n"
                "Current reference: " + (os.path.basename(self.reference_audio) if self.reference_audio else "Not set"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:ref_menu")]])
            )

        elif data == "settings:ref_restore":
            try:
                self.load_manual_reference()
                ref_name = os.path.basename(self.reference_audio) if self.reference_audio else "None"
                await q.edit_message_text(
                    f"✅ Restored to default reference!\n\n"
                    f"📁 File: {ref_name}\n"
                    f"📝 Text: {self.reference_text[:100]}{'...' if len(self.reference_text) > 100 else ''}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:ref_menu")]])
                )
            except Exception as e:
                await q.edit_message_text(
                    f"❌ Restore error: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:ref_menu")]])
                )

        elif data == "settings:ref_status":
            ref_status = "✅ Ready" if self.reference_audio and self.reference_text else "❌ Missing"
            ref_name = os.path.basename(self.reference_audio) if self.reference_audio else "Not set"
            ref_text = self.reference_text if self.reference_text else "Not set"

            await q.edit_message_text(
                f"📊 Reference Audio Status\n\n"
                f"Status: {ref_status}\n"
                f"📁 File: {ref_name}\n"
                f"📝 Text: {ref_text}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:ref_menu")]])
            )

        # 2. AUDIO SETTINGS MENU
        elif data == "settings:audio_menu":
            keyboard = [
                [InlineKeyboardButton(f"⚡ Speed: {self.audio_speed}x", callback_data="settings:speed")],
                [InlineKeyboardButton(f"🔧 Quality: {self.audio_quality}", callback_data="settings:quality")],
                [InlineKeyboardButton("🎚️ FFmpeg Filter", callback_data="settings:ffmpeg")],
                [InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]
            ]
            await q.edit_message_text(
                "⚡ Audio Settings Menu\n\n"
                "Configure audio generation settings:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif data == "settings:ffmpeg":
            await q.edit_message_text(
                f"🎚️ FFmpeg Audio Filter\n\n"
                f"Current filter:\n{self.ffmpeg_filter}\n\n"
                f"To change, send:\n/set_ffmpeg your_filter_here\n\n"
                f"Example:\n/set_ffmpeg afftdn=nr=12:nf=-25,highpass=f=80",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:audio_menu")]])
            )

        # 3. DEEPSEEK PROMPT MENU (Disabled - YouTube links now auto-process as Reference Audio)
        elif data == "settings:prompt_menu":
            await q.edit_message_text(
                "ℹ️ DeepSeek Feature Disabled\n\n"
                "YouTube links now automatically process as Reference Audio.\n\n"
                "🎵 Simply send a YouTube link and it will:\n"
                "• Extract audio\n"
                "• Crop to 30 seconds\n"
                "• Set as voice reference",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]])
            )

        elif data == "settings:prompt_view":
            await q.edit_message_text(
                "ℹ️ Feature Not Available\n\n"
                "YouTube links now auto-process as Reference Audio.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main:settings")]])
            )

        elif data == "settings:prompt_help":
            await q.edit_message_text(
                "ℹ️ Feature Not Available\n\n"
                "YouTube links now auto-process as Reference Audio.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main:settings")]])
            )

        # 3B. YOUTUBE TRANSCRIPT PROMPT MENU (Disabled)
        elif data == "settings:youtube_prompt_menu":
            await q.edit_message_text(
                "ℹ️ YouTube Transcript Feature Disabled\n\n"
                "YouTube links now automatically process as Reference Audio only.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]])
            )

        elif data == "settings:youtube_prompt_view":
            await q.edit_message_text(
                "ℹ️ Feature Not Available",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main:settings")]])
            )

        elif data == "settings:youtube_prompt_help":
            await q.edit_message_text(
                "ℹ️ Feature Not Available",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="main:settings")]])
            )

        # 3C. AI MODE TOGGLE (Disabled)
        elif data == "settings:toggle_ai_mode":
            await q.edit_message_text(
                "ℹ️ AI Mode Feature Disabled\n\n"
                "YouTube links now automatically process as Reference Audio only.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]])
            )

        # 3D. OPENROUTER MODEL SETTINGS
        elif data == "settings:openrouter_model":
            await q.edit_message_text(
                f"🤖 OpenRouter Model Settings\n\n"
                f"Current Model:\n{self.openrouter_model}\n\n"
                f"To change model, use:\n"
                f"/set_openrouter_model model_name\n\n"
                f"Popular models:\n"
                f"• deepseek/deepseek-chat\n"
                f"• anthropic/claude-3.5-sonnet\n"
                f"• openai/gpt-4-turbo\n"
                f"• google/gemini-pro-1.5\n"
                f"• meta-llama/llama-3.1-70b-instruct\n\n"
                f"💡 This model is used when AI Mode is set to OpenRouter.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]])
            )

        # 4. TITLE PROMPTS MENU
        elif data == "settings:title_prompts_menu":
            keyboard = [
                [InlineKeyboardButton("📝 Prompt 1 (Initial)", callback_data="settings:title_prompt1")],
                [InlineKeyboardButton("✨ Prompt 2 (Refine)", callback_data="settings:title_prompt2")],
                [InlineKeyboardButton("💎 Prompt 3 (Polish)", callback_data="settings:title_prompt3")],
                [InlineKeyboardButton("🔢 Prompt (10 More)", callback_data="settings:title_prompt_10more")],
                [InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]
            ]
            await q.edit_message_text(
                "🏷️ Title Generation Prompts\n\n"
                "Manage AI prompts for video title generation:\n\n"
                "• Prompt 1: Initial title generation\n"
                "• Prompt 2: First refinement\n"
                "• Prompt 3: Final polish\n"
                "• 10 More: Generate 10 alternatives",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif data == "settings:title_prompt1":
            await q.edit_message_text(
                f"📝 Title Prompt 1 (Initial)\n\n"
                f"Current:\n{self.title_prompt_1}\n\n"
                f"To change:\n/set_title_prompt1 your_prompt_here",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:title_prompts_menu")]])
            )

        elif data == "settings:title_prompt2":
            await q.edit_message_text(
                f"✨ Title Prompt 2 (Refine)\n\n"
                f"Current:\n{self.title_prompt_2}\n\n"
                f"To change:\n/set_title_prompt2 your_prompt_here",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:title_prompts_menu")]])
            )

        elif data == "settings:title_prompt3":
            await q.edit_message_text(
                f"💎 Title Prompt 3 (Polish)\n\n"
                f"Current:\n{self.title_prompt_3}\n\n"
                f"To change:\n/set_title_prompt3 your_prompt_here",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:title_prompts_menu")]])
            )

        elif data == "settings:title_prompt_10more":
            await q.edit_message_text(
                f"🔢 Title Prompt (10 More)\n\n"
                f"Current:\n{self.title_prompt_10_more}\n\n"
                f"To change:\n/set_title_prompt_10more your_prompt_here",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:title_prompts_menu")]])
            )

        # 5. POWER & CONTROL MENU
        elif data == "settings:power_menu":
            processing_status = "🔄 Processing" if self.is_processing else "⏸️ Idle"

            keyboard = [
                [InlineKeyboardButton("⚡ Power Policy", callback_data="settings:power_policy")],
                [InlineKeyboardButton("🛑 Stop Processing", callback_data="settings:stop_processing")],
                [InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]
            ]
            await q.edit_message_text(
                f"⚡ Power & Control Menu\n\n"
                f"Status: {processing_status}\n"
                f"Policy: {self.power_policy}\n\n"
                f"Manage processing and power:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        elif data == "settings:power_policy":
            await q.edit_message_text(
                f"⚡ Power Policy Settings\n\n"
                f"Current: {self.power_policy}\n\n"
                f"Select action after all files finish:",
                parse_mode="Markdown",
                reply_markup=self._power_keyboard(self.power_policy)
            )

        elif data == "settings:stop_processing":
            if not self.is_processing:
                await q.answer("⚠️ No processing currently running", show_alert=True)
                return

            self.stop_requested = True
            await q.edit_message_text(
                "🛑 STOP REQUESTED!\n\n"
                "⏳ Stopping current operation...\n"
                "📊 Queue will be cleared\n"
                "⚠️ Current file may be incomplete",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:power_menu")]])
            )

        # 6. COMPLETED FILES (LINKS)
        elif data == "settings:links":
            if not self.completed_files:
                await q.edit_message_text(
                    "📝 No completed files yet!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]])
                )
                return

            links_text = f"🎉 Completed Files ({len(self.completed_files)}):\n\n"

            for i, file_info in enumerate(self.completed_files, 1):
                filename = file_info.get('filename', f'File {i}')
                link = file_info.get('link', 'No link')
                size = file_info.get('size', 'Unknown')

                links_text += f"{i}. 📄 {filename}\n"
                links_text += f"   📏 Size: {size}\n"
                links_text += f"   🔗 {link}\n\n"

            await q.edit_message_text(
                links_text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]])
            )

        # 7. DEBUG TOOLS
        elif data == "settings:debug":
            keyboard = [
                [InlineKeyboardButton("🧪 Run Test", callback_data="settings:run_test")],
                [InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]
            ]
            await q.edit_message_text(
                "🔧 Debug Tools\n\n"
                "Testing and debugging utilities:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        # 8. PIPELINE MENU
        elif data == "settings:pipeline_menu":
            keyboard = [
                [InlineKeyboardButton("📝 Transcript", callback_data="pipeline:transcript")],
                [InlineKeyboardButton("🎯 Title Creation", callback_data="pipeline:title")],
                [InlineKeyboardButton("🖼️ Image Creation", callback_data="pipeline:image")],
                [InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]
            ]
            await q.edit_message_text(
                "🔄 Pipeline Menu\n\n"
                "Configure your content pipeline:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        # Pipeline sub-menu handlers
        elif data == "pipeline:transcript":
            await q.edit_message_text(
                "📝 Transcript Settings\n\n"
                "Configure transcript generation settings here.\n\n"
                "🚧 Coming soon - More options will be added!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Pipeline", callback_data="settings:pipeline_menu")]])
            )

        elif data == "pipeline:title":
            await q.edit_message_text(
                "🎯 Title Creation Settings\n\n"
                "Configure title generation settings here.\n\n"
                "🚧 Coming soon - More options will be added!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Pipeline", callback_data="settings:pipeline_menu")]])
            )

        elif data == "pipeline:image":
            await q.edit_message_text(
                "🖼️ Image Creation Settings\n\n"
                "Configure image generation settings here.\n\n"
                "🚧 Coming soon - More options will be added!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Pipeline", callback_data="settings:pipeline_menu")]])
            )

        elif data == "settings:run_test":
            try:
                test_text = "This is a test script for F5-TTS."
                await q.edit_message_text("🧪 Running test...", reply_markup=None)

                # Run the test
                chat_id_test = q.message.chat.id if q.message else chat_id
                audio_paths = await self.generate_audio_f5(test_text, chat_id_test)

                if audio_paths:
                    await q.message.reply_text(
                        f"✅ Test successful!\n\n"
                        f"Generated {len(audio_paths)} audio file(s)",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:debug")]])
                    )
                else:
                    await q.message.reply_text(
                        "❌ Test failed - no audio generated",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:debug")]])
                    )
            except Exception as e:
                await q.message.reply_text(
                    f"❌ Test error: {str(e)}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="settings:debug")]])
                )


        # ====== OLD HANDLERS (KEEP FOR COMPATIBILITY) ======

        # Handle settings menu options
        elif data == "settings:ref":
            await q.edit_message_text(
                "🎵 Change Reference Audio\n\n"
                "Send a voice message or audio file to set as your new reference.\n\n"
                "Current reference: " + (os.path.basename(self.reference_audio) if self.reference_audio else "Not set"),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]])
            )
            
        elif data == "settings:prompt":
            await q.edit_message_text(
                "📝 Set DeepSeek Prompt\n\n"
                f"Current prompt: {self.deepseek_prompt}\n\n"
                "To change the prompt, use the command:\n"
                "/set_prompt Your new prompt here",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]])
            )
            
        elif data == "settings:speed":
            # Create speed selection buttons
            keyboard = [
                [
                    InlineKeyboardButton("0.5x", callback_data="speed_0.5"),
                    InlineKeyboardButton("0.8x", callback_data="speed_0.8"),
                    InlineKeyboardButton("1.0x", callback_data="speed_1.0")
                ],
                [
                    InlineKeyboardButton("1.2x", callback_data="speed_1.2"),
                    InlineKeyboardButton("1.5x", callback_data="speed_1.5"),
                    InlineKeyboardButton("2.0x", callback_data="speed_2.0")
                ],
                [InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await q.edit_message_text(
                f"⚡ Audio Speed Settings\n\n"
                f"Current speed: {self.audio_speed}x\n\n"
                f"Select new speed:",
                reply_markup=reply_markup
            )
            
        elif data == "settings:quality":
            # Create quality selection buttons
            keyboard = [
                [InlineKeyboardButton("Low (Faster)", callback_data="quality_low")],
                [InlineKeyboardButton("Medium", callback_data="quality_medium")],
                [InlineKeyboardButton("High (Better)", callback_data="quality_high")],
                [InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await q.edit_message_text(
                f"🔧 Audio Quality Settings\n\n"
                f"Current quality: {self.audio_quality}\n\n"
                f"Select new quality:",
                reply_markup=reply_markup
            )
            
        elif data == "settings:delivery":
            # Show delivery settings
            mode = self.delivery_prefs_by_chat.get(chat_id, "all")
            await q.edit_message_text(
                f"📄 Delivery Settings\n\n"
                f"Current setting: **{mode}**\n\n"
                f"Options:\n"
                f"• All: Both Raw & Enhanced (default)\n"
                f"• Enhanced: Noise reduction + EQ only\n"
                f"• Raw: Unprocessed output only\n\n"
                f"Choose which audio format should be sent automatically.",
                parse_mode="Markdown",
                reply_markup=self._settings_keyboard(mode)
            )
            
        elif data == "settings:power":
            # Show power settings
            await q.edit_message_text(
                f"⚡ Power Settings\n\n"
                f"Current policy: **{self.power_policy}**\n\n"
                f"Select what to do **after all files finish**:",
                parse_mode="Markdown",
                reply_markup=self._power_keyboard(self.power_policy)
            )
        
        # Handle delivery mode settings
        elif data.startswith("settings:set:"):
            new_mode = data.split(":", 2)[2]
            # validate
            allowed = {"enhanced", "raw", "all"}
            if new_mode not in allowed:
                await q.message.reply_text("⚠️ Invalid mode.")
                return

            self.delivery_prefs_by_chat[chat_id] = new_mode
            # Save configuration to file
            self.save_config()
            try:
                await q.edit_message_text(
                    text=f"✅ Saved. Delivery setting: **{new_mode}**\n\nReturn to settings menu?",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]])
                )
            except Exception:
                # if edit fails (e.g., message old), just send a new message
                await q.message.reply_text(f"✅ Saved. Delivery setting: **{new_mode}**", parse_mode="Markdown")
        
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Button callbacks handle kariye"""
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data.startswith("speed_"):
            self.audio_speed = float(data.replace("speed_", ""))
            # Save configuration to file
            self.save_config()
            # Show confirmation with back button
            keyboard = [[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"✅ Speed set to {self.audio_speed}x and saved!\n\nReturn to settings?", 
                reply_markup=reply_markup
            )
            
        elif data.startswith("quality_"):
            self.audio_quality = data.replace("quality_", "")
            # Save configuration to file
            self.save_config()
            # Show confirmation with back button
            keyboard = [[InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"✅ Quality set to {self.audio_quality} and saved!\n\nReturn to settings?", 
                reply_markup=reply_markup
            )
    
    async def links_command(self, update, context: ContextTypes.DEFAULT_TYPE):
        """All completed files links show kariye - works with both direct commands and callbacks"""
        # Handle both direct command and callback query
        is_callback = hasattr(update, 'callback_query')
        
        if is_callback:
            query = update.callback_query
            try:
                await query.answer()
            except:
                pass
        
        if not self.completed_files:
            message = "📝 No completed files yet!"
            if is_callback:
                keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main:status")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.edit_message_text(message, reply_markup=reply_markup)
            else:
                await update.message.reply_text(message)
            return
        
        links_text = f"🎉 Completed Files ({len(self.completed_files)}):\n\n"
        
        for i, file_info in enumerate(self.completed_files, 1):
            filename = file_info.get('filename', f'File {i}')
            link = file_info.get('link', 'No link')
            size = file_info.get('size', 'Unknown')
            
            links_text += f"{i}. 📄 {filename}\n"
            links_text += f"   📏 Size: {size}\n"
            links_text += f"   🔗 {link}\n\n"
        
        # Add back button if it's a callback
        if is_callback:
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="main:status")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(links_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(links_text)
    
    async def on_pick(self, update, context):
        q = update.callback_query
        try:
            await q.answer()
        except Exception:
            pass

        # ✅ robust chat id for callbacks
        chat_id = None
        try:
            chat_id = q.message.chat.id if q and q.message and q.message.chat else None
        except Exception:
            chat_id = None
        if chat_id is None:
            # fallback to user id (last resort)
            chat_id = q.from_user.id if q and q.from_user else None

        if not chat_id:
            print("⚠️ on_pick: could not resolve chat_id")
            return

        data = q.data or ""
        print(f"🛰 on_pick received: {data} from chat {chat_id}")
        if not data.startswith("pick:"):
            return
        choice = data.split(":", 1)[1]

        if choice == "close":
            try:
                await q.edit_message_reply_markup(reply_markup=None)
            except Exception as e:
                print(f"on_pick close edit error: {e}")
            return

        rec = self.latest_outputs_by_chat.get(chat_id)
        if not rec or "paths" not in rec:
            print("on_pick: no recent outputs found for chat")
            await q.message.reply_text("⚠️ No recent output available.")
            return

        paths = rec["paths"]
        wanted = self._pick_paths(paths, choice)
        if not wanted:
            await q.message.reply_text("⚠️ Variant not found for this output.")
            return

        sent = 0
        for p in wanted:
            try:
                # cached link?
                link = rec.get("links", {}).get(p) or self.gofile_cache.get(p)
                if not link:
                    link = await self.upload_single_to_gofile(p)
                    if link:
                        rec.setdefault("links", {})[p] = link
                        self.gofile_cache[p] = link

                base = os.path.basename(p)
                size_mb = os.path.getsize(p) // (1024 * 1024) if os.path.exists(p) else 0

                if link:
                    await q.message.reply_text(f"🔗 {base} ({size_mb}MB)\n{link}")
                    sent += 1
                else:
                    # Telegram fallback for small files
                    if os.path.exists(p) and os.path.getsize(p) < MAX_TELEGRAM_FILE_SIZE:
                        with open(p, "rb") as f:
                            await context.bot.send_audio(
                                chat_id=chat_id, audio=f,
                                caption=f"📄 {base} ({size_mb}MB) — Telegram fallback"
                            )
                        sent += 1
                    else:
                        await q.message.reply_text(f"⚠️ Could not upload {base}; saved locally.")
            except Exception as e:
                print(f"on_pick loop error for {p}: {e}")
                try:
                    await q.message.reply_text(f"⚠️ Error delivering {os.path.basename(p)}: {e}")
                except Exception:
                    pass

        # keep the keyboard visible for more picks
        if sent and choice != "all":
            try:
                await q.edit_message_reply_markup(reply_markup=self._variant_keyboard())
            except Exception as e:
                print(f"on_pick edit_message_reply_markup error: {e}")



    async def handle_document(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Text file documents handle kariye (supports channels and private chat)"""
        try:
            # Determine if this is a channel message
            chat_id = update.effective_chat.id
            is_channel = self.is_channel_message(update)

            # Channel authorization check
            if is_channel:
                if not self.is_authorized_channel(chat_id):
                    print(f"⚠️ Unauthorized channel attempted document upload: {chat_id}")
                    return
                print(f"📢 Channel document detected from: {chat_id}")

            # Get document from message or channel_post
            message_obj = update.message if update.message else update.channel_post
            document = message_obj.document

            # Check ki text file hai ya nahi
            if not document.file_name.endswith('.txt'):
                error_msg = "❌ Only .txt files supported!\n📄 Send text file with your script."
                if is_channel:
                    await context.bot.send_message(chat_id=chat_id, text=error_msg)
                else:
                    await update.message.reply_text(error_msg)
                return

            print(f"📄 Text file received: {document.file_name} ({'Channel' if is_channel else 'Private'})")

            # Send downloading message
            download_msg = "📄 Downloading text file..."
            if is_channel:
                await context.bot.send_message(chat_id=chat_id, text=download_msg)
            else:
                await update.message.reply_text(download_msg)

            # File download kariye
            file = await context.bot.get_file(document.file_id)
            file_path = os.path.join(SCRIPTS_DIR, document.file_name)

            # Download with longer timeout and better error handling
            try:
                # Send a progress message for large files
                file_size_mb = document.file_size / (1024 * 1024) if hasattr(document, 'file_size') else 0
                if file_size_mb > 5:  # For files larger than 5MB
                    progress_msg = (
                        f"💾 Downloading large file ({file_size_mb:.1f}MB)...\n"
                        f"This might take some time. Please be patient."
                    )
                    if is_channel:
                        await context.bot.send_message(chat_id=chat_id, text=progress_msg)
                    else:
                        await update.message.reply_text(progress_msg)

                await asyncio.wait_for(
                    file.download_to_drive(file_path),
                    timeout=1000  # Increased to 120 seconds timeout
                )
            except asyncio.TimeoutError:
                timeout_msg = (
                    "⚠️ Download timed out! The file might be too large or network is slow.\n"
                    "Please try a smaller file or try again later."
                )
                if is_channel:
                    await context.bot.send_message(chat_id=chat_id, text=timeout_msg)
                else:
                    await update.message.reply_text(timeout_msg)
                return
            except Exception as download_error:
                error_msg = f"❌ Download error: {str(download_error)}"
                if is_channel:
                    await context.bot.send_message(chat_id=chat_id, text=error_msg)
                else:
                    await update.message.reply_text(error_msg)
                return

            # File content read kariye
            with open(file_path, 'r', encoding='utf-8') as f:
                script_content = f.read().strip()

            # ZERO Telegram messages - pure silent operation
            if not script_content:
                print(f"⚠️ Empty file skipped: {document.file_name}")
                return

            print(f"✅ Text file loaded: {len(script_content)} characters from {document.file_name}")

            # COMPLETELY SILENT queuing - NO messages at all
            # Directly add to queue without calling process_text messaging
            timestamp = int(time.time() * 1000)
            filename = f"{document.file_name.replace('.txt', '')}_{timestamp}.txt"

            queue_item = {
                'script': script_content,
                'filename': filename,
                'timestamp': time.time(),
                'chat_id': chat_id,
                'is_channel': is_channel
            }
            self.processing_queue.append(queue_item)
            queue_size = len(self.processing_queue)

            print(f"📥 Queued silently: {document.file_name} (Queue: {queue_size})")

            # Start batch timer ONLY for first file, NO messages
            if not self.batch_mode and not self.is_processing and queue_size == 1:
                self.batch_mode = True
                self.queue_start_time = time.time()

                # Store context for channel processing
                if is_channel:
                    context._chat_id = chat_id

                # Start batch timer silently
                print(f"⏳ Batch timer started silently - {self.queue_wait_time}s")
                asyncio.create_task(self.start_batch_timer(context, chat_id))

        except Exception as e:
            # CRITICAL: NO Telegram messages in exception handler!
            # Only console logs to avoid flood control
            print(f"❌ Document processing error: {str(e)}")
            print(f"⚠️ File skipped due to error: {document.file_name}")

            # Don't try to send ANY Telegram messages - this causes flood control!
            # Just log the error and continue processing next files
    
    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages and YouTube links (supports both private chat and channels)"""
        try:
            chat_id = update.effective_chat.id
            is_channel = self.is_channel_message(update)

            # Channel authorization check
            if is_channel:
                if not self.is_authorized_channel(chat_id):
                    print(f"⚠️ Unauthorized channel attempted access: {chat_id}")
                    return
                print(f"📢 Channel message detected from: {chat_id}")

            script_text = update.message.text if update.message else update.channel_post.text
            print(f"📝 Text received ({('Channel' if is_channel else 'Private')}): {len(script_text)} characters")

            # Skip commands
            if script_text.startswith('/'):
                return

            # Check for YouTube links (both videos AND channels)
            youtube_patterns = [
                # Video patterns
                r'(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)',
                r'(?:www\.)?youtube\.com/watch\?v=',
                r'youtu\.be/',
                # Channel patterns
                r'(?:www\.)?youtube\.com/@[\w-]+',
                r'(?:www\.)?youtube\.com/c/[\w-]+',
                r'(?:www\.)?youtube\.com/channel/UC[\w-]+',
                r'(?:www\.)?youtube\.com/user/[\w-]+'
            ]

            # Extract all YouTube links from the message
            youtube_links = []
            for line in script_text.split():
                if any(re.search(pattern, line, re.IGNORECASE) for pattern in youtube_patterns):
                    youtube_links.append(line.strip())
            

            if youtube_links:
                # Check if it's a channel or video
                for youtube_url in youtube_links:
                    # Detect channel vs video
                    if self.youtube_processor.is_youtube_channel_url(youtube_url):
                        # Channel URL detected - process as channel
                        msg_text = (
                            f"📺 **YouTube Channel Detected!**\n\n"
                            f"🔗 URL: {youtube_url[:50]}{'...' if len(youtube_url) > 50 else ''}\n\n"
                            f"🎯 Will process top 6 videos (>10 min, not processed in last 15 days)\n"
                            f"⏱️ Estimated time: 15-20 minutes"
                        )

                        try:
                            if is_channel:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=msg_text,
                                    parse_mode="Markdown"
                                )
                            else:
                                await update.message.reply_text(msg_text, parse_mode="Markdown")

                            # Process channel
                            print(f"📺 Processing YouTube channel: {youtube_url}")
                            await self.process_youtube_channel(youtube_url, update, context)

                        except Exception as e:
                            print(f"Error processing YouTube channel: {e}")
                            error_msg = f"❌ Failed to process YouTube channel: {str(e)[:100]}"
                            if is_channel:
                                await context.bot.send_message(chat_id=chat_id, text=error_msg)
                            else:
                                await update.message.reply_text(error_msg)

                    elif self.youtube_processor.is_youtube_video_url(youtube_url):
                        # Video URL detected - process as reference audio
                        msg_text = (
                            f"🔗 YouTube video detected!\n\n"
                            f"📺 URL: {youtube_url[:50]}{'...' if len(youtube_url) > 50 else ''}\n\n"
                            f"🎵 Automatically processing as Reference Audio...\n"
                            f"📥 Extracting audio → Cropping to 30s → Setting as voice reference"
                        )

                        try:
                            if is_channel:
                                await context.bot.send_message(
                                    chat_id=chat_id,
                                    text=msg_text
                                )
                            else:
                                await update.message.reply_text(msg_text)

                            # Automatically extract audio as reference
                            print(f"🎵 Auto-processing YouTube video as Reference Audio: {youtube_url}")
                            await self.extract_youtube_audio_as_reference(youtube_url, update, context)

                        except Exception as e:
                            print(f"Error processing YouTube video: {e}")
                            error_msg = f"❌ Failed to process YouTube video: {str(e)[:100]}"
                            if is_channel:
                                await context.bot.send_message(chat_id=chat_id, text=error_msg)
                            else:
                                await update.message.reply_text(error_msg)
                    else:
                        # Unknown YouTube URL format
                        error_msg = "⚠️ Could not determine if this is a channel or video URL"
                        if is_channel:
                            await context.bot.send_message(chat_id=chat_id, text=error_msg)
                        else:
                            await update.message.reply_text(error_msg)

            else:
                await self.process_text(script_text, update, context)
            
        except Exception as e:
            error_msg = f"❌ Text handling error: {str(e)}"
            print(error_msg)
            # Handle reply for both channel and private chat
            try:
                if is_channel:
                    await context.bot.send_message(chat_id=chat_id, text=error_msg)
                else:
                    await update.message.reply_text(error_msg)
            except:
                print("Failed to send error message")
    
    async def process_text(self, script_text, update, context, silent=False, skip_errors=False):
        """Text process kariye with filename tracking (supports channel & private)

        Args:
            silent: If True, don't send intermediate messages (for batch uploads)
            skip_errors: If True, suppress error messages
        """
        try:
            # Get chat ID and determine if it's a channel
            chat_id = update.effective_chat.id
            is_channel = self.is_channel_message(update)

            # Prerequisites check
            if not self.f5_model:
                error_msg = "❌ F5-TTS not ready! Check installation."
                if is_channel:
                    await context.bot.send_message(chat_id=chat_id, text=error_msg)
                else:
                    await update.message.reply_text(error_msg)
                return

            if not self.reference_audio or not self.reference_text:
                error_msg = "❌ Reference audio missing! Add to reference/ folder and restart."
                if is_channel:
                    await context.bot.send_message(chat_id=chat_id, text=error_msg)
                else:
                    await update.message.reply_text(error_msg)
                return

            # Get filename if document was sent
            filename = "Direct Text"
            message_obj = update.message if update.message else update.channel_post
            if hasattr(message_obj, 'document') and message_obj.document:
                filename = message_obj.document.file_name
            elif is_channel:
                filename = "Channel Post"

            # Queue mein add kariye with filename and chat_id
            queue_item = {
                'script': script_text,
                'filename': filename,
                'timestamp': time.time(),
                'chat_id': chat_id,  # Store chat ID for response
                'is_channel': is_channel
            }
            self.processing_queue.append(queue_item)
            queue_size = len(self.processing_queue)

            # Batch mode logic - agar pehli file hai toh timer start karo
            if not self.batch_mode and not self.is_processing:
                self.batch_mode = True
                self.queue_start_time = time.time()

                # Only send message if not silent mode
                if not silent:
                    queue_msg = (
                        f"📝 File added to queue!\n"
                        f"📄 File: {filename}\n"
                        f"📊 Queue position: {queue_size}\n\n"
                        f"⏳ **BATCH MODE ACTIVATED**\n"
                        f"⏱️ Waiting 2 minutes to collect all files...\n"
                        f"📥 Send more files now - they'll be queued!\n\n"
                        f"Processing will start automatically after 2 minutes."
                    )

                    try:
                        if is_channel:
                            await context.bot.send_message(chat_id=chat_id, text=queue_msg)
                        else:
                            await update.message.reply_text(queue_msg)
                    except Exception as msg_err:
                        if "Flood control" in str(msg_err):
                            print(f"⚠️ Flood control - skipping message for {filename}")
                        else:
                            print(f"Error sending queue message: {msg_err}")

                # Store context for channel processing
                if is_channel:
                    context._chat_id = chat_id

                # Start batch timer (2 minutes wait, then process)
                asyncio.create_task(self.start_batch_timer(context, chat_id))

            else:
                # Already in batch mode - silent mode or just log
                if not silent:
                    elapsed = int(time.time() - self.queue_start_time) if self.queue_start_time else 0
                    remaining = max(0, self.queue_wait_time - elapsed)

                    if self.batch_mode:
                        queue_msg = (
                            f"✅ Added to batch queue!\n"
                            f"📄 File: {filename}\n"
                            f"📊 Total in queue: {queue_size}\n"
                            f"⏱️ Time remaining: {remaining}s"
                        )
                    else:
                        # Processing already started
                        queue_msg = (
                            f"📝 Added to queue!\n"
                            f"📄 File: {filename}\n"
                            f"📊 Queue position: {queue_size}\n"
                            f"⏳ Currently processing..."
                        )

                    try:
                        if is_channel:
                            await context.bot.send_message(chat_id=chat_id, text=queue_msg)
                        else:
                            await update.message.reply_text(queue_msg)
                    except Exception as msg_err:
                        if "Flood control" in str(msg_err):
                            print(f"⚠️ Flood control - file {filename} queued silently (#{queue_size})")
                        else:
                            print(f"Error sending queue message: {msg_err}")
                
        except Exception as e:
            error_msg = f"❌ Process text error: {str(e)}"
            print(error_msg)

            # Only send error message if not in skip_errors mode
            if not skip_errors:
                try:
                    await update.message.reply_text(error_msg)
                except:
                    print("Could not send error message (likely flood control)")

    async def start_batch_timer(self, context, chat_id):
        """2 minutes wait karke batch processing start karo"""
        try:
            print(f"⏳ Batch timer started - waiting {self.queue_wait_time} seconds...")

            # Wait intervals with progress updates
            intervals = [30, 60, 90, 120]  # Progress at 30s, 1m, 1.5m, 2m
            last_time = 0

            for interval in intervals:
                wait_time = interval - last_time
                await asyncio.sleep(wait_time)
                last_time = interval

                remaining = self.queue_wait_time - interval
                queue_size = len(self.processing_queue)

                if remaining > 0:
                    # Progress update
                    progress_msg = (
                        f"⏱️ Batch Timer Update\n"
                        f"📊 Files in queue: {queue_size}\n"
                        f"⏳ Time remaining: {remaining}s\n\n"
                        f"💡 Keep sending files - they'll be added to queue!"
                    )
                    try:
                        await context.bot.send_message(chat_id=chat_id, text=progress_msg)
                    except:
                        pass  # Ignore if send fails

            # Timer completed - start processing
            queue_count = len(self.processing_queue)
            print(f"✅ Batch timer completed! Starting processing of {queue_count} files...")

            # Create detailed queue summary
            file_list = "\n".join([f"  {i+1}. {item['filename']}" for i, item in enumerate(self.processing_queue[:10])])
            if queue_count > 10:
                file_list += f"\n  ... and {queue_count - 10} more files"

            start_msg = (
                f"🚀 **BATCH PROCESSING STARTING**\n\n"
                f"📊 Total files collected: {queue_count}\n"
                f"⚡ Processing speed: {self.audio_speed}x\n"
                f"🔧 Audio quality: {self.audio_quality}\n\n"
                f"📝 Files in queue:\n{file_list}\n\n"
                f"Processing files one by one...\n"
                f"You'll get updates for each completed file!"
            )

            try:
                await context.bot.send_message(chat_id=chat_id, text=start_msg)
            except:
                pass

            # Disable batch mode and start processing
            self.batch_mode = False

            # Start queue processing
            await self.process_queue(context)

        except Exception as e:
            print(f"❌ Batch timer error: {e}")
            self.batch_mode = False
            # Try to process anyway
            await self.process_queue(context)

    async def process_queue(self, context):
        """Queue process kariye - one by one files with individual completion"""
        if self.is_processing:
            print("⚠️ Already processing...")
            return

        # CRITICAL: Check if reference audio is set before processing
        if not self.reference_audio or not os.path.exists(self.reference_audio):
            error_msg = (
                "❌ **REFERENCE AUDIO NOT SET!**\n\n"
                "⚠️ Cannot process queue without reference audio.\n\n"
                "📝 **How to set reference audio:**\n"
                "1️⃣ Send a YouTube link (audio will auto-extract)\n"
                "2️⃣ Or send an MP3/audio file\n\n"
                f"📊 Files in queue: {len(self.processing_queue)}\n"
                "💡 Queue will be preserved - set reference audio and processing will start automatically!"
            )
            print(error_msg)

            # Send error to channel/chat
            try:
                actual_chat_id = context._chat_id if hasattr(context, '_chat_id') else CHAT_ID
                await context.bot.send_message(chat_id=actual_chat_id, text=error_msg)
            except:
                print("Failed to send reference audio error message")

            self.is_processing = False
            return

        self.is_processing = True
        self.stop_requested = False  # Reset stop flag
        print("📄 Queue processing started...")

        try:
            while self.processing_queue:
                # Check for stop request
                if self.stop_requested:
                    actual_chat_id = context._chat_id if hasattr(context, '_chat_id') else CHAT_ID
                    await context.bot.send_message(
                        chat_id=actual_chat_id,
                        text=f"🛑 Processing stopped by user!\n\n"
                             f"📊 Remaining in queue: {len(self.processing_queue)}\n"
                             f"✅ Completed before stop: {len(self.completed_files)}"
                    )
                    # Clear queue
                    self.processing_queue.clear()
                    self.stop_requested = False
                    break
                
                queue_item = self.processing_queue.pop(0)
                script_text = queue_item['script']
                filename = queue_item['filename']
                item_chat_id = queue_item.get('chat_id', CHAT_ID)  # Get chat ID from queue item
                is_channel_item = queue_item.get('is_channel', False)

                print(f"📄 Processing: {filename} ({len(script_text)} characters) for {'Channel' if is_channel_item else 'Private'} {item_chat_id}")

                # Use the chat ID from queue item (channel or private chat)
                actual_chat_id = item_chat_id

                # User ko notify kariye
                # Safe reference audio display (handle None case)
                ref_display = os.path.basename(self.reference_audio) if self.reference_audio else "⚠️ Not Set (using default)"

                await context.bot.send_message(
                    chat_id=actual_chat_id,
                    text=f"📄 Processing: {filename}\n\n"
                         f"📝 Script: {len(script_text)} characters\n"
                         f"📌 Preview: {script_text[:200]}{'...' if len(script_text) > 200 else ''}\n"
                         f"🎵 Reference: {ref_display}\n"
                         f"⚡ Speed: {self.audio_speed}x\n"
                         f"🔧 Quality: {self.audio_quality}\n\n"
                         f"⏳ Please wait, generation in progress...\n"
                         f"🛑 Use /stop to cancel"
                )
                
                # Check stop before audio generation
                if self.stop_requested:
                    await context.bot.send_message(
                        chat_id=actual_chat_id,
                        text=f"🛑 Stopped before generating: {filename}"
                    )
                    self.processing_queue.clear()
                    self.stop_requested = False
                    break
                
                # Store chat ID for chunk updates
                self._current_chat_id = actual_chat_id
                # Audio generate kariye (pass chat id)
                success, output_files = await self.generate_audio_f5(script_text, actual_chat_id)
                # Cleanup chunk progress context
                self._current_chat_id = None
                
                # Check if stopped during audio generation
                if self.stop_requested:
                    await context.bot.send_message(
                        chat_id=actual_chat_id,
                        text=(
                            f"🛑 Processing stopped!\n\n"
                            f"📄 Last file: {filename}\n"
                            f"⚠️ Audio generation interrupted\n"
                            f"📊 Remaining: {len(self.processing_queue)} files"
                        )
                    )
                    self.processing_queue.clear()
                    self.stop_requested = False
                    break
                
                if success:
                    self.latest_outputs_by_chat[actual_chat_id] = {
                        "paths": output_files, "links": {}, "filename": filename, "ts": time.time()
                    }
                    link_or_status = await self.send_outputs_by_mode(context, actual_chat_id, output_files, script_text, filename)

                    # Track completed file(s)
                    total_bytes = sum(os.path.getsize(p) for p in output_files if os.path.exists(p))
                    self.completed_files.append({
                        'filename': filename,
                        'link': link_or_status,
                        'size': f"{total_bytes // (1024*1024)}MB",
                        'timestamp': time.time()
                    })
                    
                    # Individual completion message
                    remaining = len(self.processing_queue)
                    await context.bot.send_message(
                        chat_id=actual_chat_id,
                        text=f"✅ {filename} completed!\n\n"
                             f"📊 Remaining in queue: {remaining}\n"
                             f"✅ Total completed: {len(self.completed_files)}"
                    )
                    
                else:
                    await context.bot.send_message(
                        chat_id=actual_chat_id,
                        text=f"❌ {filename} failed!\n\n"
                             f"Error: {output_files}\n\n"
                             f"🔧 Continuing with next file..."
                    )
                
                # Memory cleanup
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                
                await asyncio.sleep(2)  # Small delay between files
            
            # All files completed - Final summary (only for multiple files)
            if self.completed_files and len(self.completed_files) > 1:
                summary_text = f"🎉 ALL {len(self.completed_files)} FILES COMPLETED!\n\n"
                summary_text += f"📊 Total processed: {len(self.completed_files)} files\n"
                summary_text += f"⚡ Speed used: {self.audio_speed}x\n"
                summary_text += f"🔧 Quality: {self.audio_quality} ({64 if self.audio_quality == 'high' else 32} steps)\n\n"
                summary_text += f"📋 ALL DOWNLOAD LINKS:\n\n"
                
                for i, file_info in enumerate(self.completed_files, 1):
                    summary_text += f"{i}. 📄 {file_info['filename']}\n"
                    summary_text += f"   📏 {file_info['size']}\n"
                    summary_text += f"   🔗 {file_info['link']}\n\n"

                # Completion message removed - will show after video if created
                await context.bot.send_message(
                    chat_id=actual_chat_id,
                    text=summary_text
                )
            # No completion message here - let user decide about video first
            
        except Exception as e:
            error_msg = f"❌ Queue processing error: {str(e)}"
            print(error_msg)
            try:
                await context.bot.send_message(chat_id=actual_chat_id, text=error_msg)
            except:
                print("Could not send error message to user")
        finally:
            self.is_processing = False
            self.batch_mode = False  # Reset batch mode
            self.queue_start_time = None  # Reset timer
            print("✅ Queue processing finished")
            try:
                await self.maybe_shutdown_after_queue(context, actual_chat_id)
            except Exception as _e:
                pass
    
    async def generate_audio_f5(self, script_text, chat_id=None):
        """F5-TTS API with PC-like parameters and processing"""
        try:
            # Optional chat context for progress updates
            if chat_id:
                self._current_chat_id = chat_id
            print(f"🔄 F5-TTS generation starting...")
            print(f"📝 Script length: {len(script_text)} characters")
            print(f"🎵 Reference: {self.reference_audio}")
            
            # Create output filename
            timestamp = int(time.time())
            base_output_path = os.path.join(OUTPUT_DIR, f"generated_{timestamp}")
            raw_output = f"{base_output_path}_raw.wav"
            
            # Split text into chunks (configurable size)
            chunks = self.split_text_into_chunks(script_text, self.chunk_size)
            print(f"📊 Split into {len(chunks)} chunks ({self.chunk_size} chars each)")
            
            # Generate audio for each chunk
            audio_segments = []
            
            for i, chunk in enumerate(chunks):
                # Check for stop request BEFORE processing
                if self.stop_requested:
                    print(f"🛑 Stop requested during chunk {i+1}/{len(chunks)}")
                    # Clean up and return immediately
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    return False, "Stopped by user"
                
                print(f"📄 Processing chunk {i+1}/{len(chunks)}")
                
                # Send chunk progress to Telegram (skip first chunk as it's already notified)
                if i > 0:  # Don't send for chunk 1 as it's already in the main processing message
                    try:
                        # Get chat ID from context (you'll need to pass it to this method)
                        if hasattr(self, '_current_chat_id') and self._current_chat_id:
                            await self._send_chunk_update(self._current_chat_id, i+1, len(chunks))
                            # Check again after sending update (user might have sent /stop)
                            if self.stop_requested:
                                print(f"🛑 Stop requested after chunk update")
                                if torch.cuda.is_available():
                                    torch.cuda.empty_cache()
                                return False, "Stopped by user"
                    except Exception as e:
                        print(f"Failed to send chunk update: {e}")
                
                # Clear CUDA memory before each chunk
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                
                # Check one more time before heavy processing
                if self.stop_requested:
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    return False, "Stopped by user"
                
                # F5-TTS API call with cached reference text and inference mode
                with torch.inference_mode():
                    result = self.f5_model.infer(
                        ref_file=self.reference_audio,
                        ref_text="",  # Let F5-TTS auto-extract to avoid cache conflicts
                        gen_text=chunk,
                        remove_silence=True,
                        cross_fade_duration=0.15,
                        speed=self.audio_speed,
                        nfe_step=32,
                        cfg_strength=1.5,
                        target_rms=0.1
                    )
                
                # Check after inference completes
                if self.stop_requested:
                    print(f"🛑 Stop requested after inference chunk {i+1}")
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    return False, "Stopped by user"
                
                # Extract audio data
                if isinstance(result, tuple):
                    audio_data = result[0]
                else:
                    audio_data = result
                
                # Move to CPU to save VRAM
                if torch.is_tensor(audio_data):
                    audio_data = audio_data.cpu()
                
                audio_segments.append(audio_data)
                
                # Cleanup after each chunk
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
            
            # Save raw audio first
            print(f"💾 Saving raw audio...")
            if torch.is_tensor(final_audio):
                if final_audio.dim() == 1:
                    final_audio = final_audio.unsqueeze(0)
                import torchaudio
                torchaudio.save(raw_output, final_audio, 24000)
                audio_array = final_audio.squeeze().numpy()
            else:
                import soundfile as sf
                sf.write(raw_output, final_audio, 24000)
                audio_array = final_audio
            
            # Now create 4 versions like PC file
            output_files = await self.create_audio_variants(base_output_path, audio_array)
            
            print(f"✅ Generated {len(output_files)} audio variants")
            return True, output_files
                
        except Exception as e:
            error_msg = f"F5-TTS generation error: {str(e)}"
            print(f"❌ {error_msg}")
            return False, error_msg
    
    def split_text_into_chunks(self, text, max_length):
        """Split text into chunks like PC version"""
        import re
        
        # Split by sentences first
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        
        chunks = []
        current_chunk = ""
        
        for sentence in sentences:
            if len(current_chunk) + len(sentence) > max_length:
                if current_chunk:
                    chunks.append(current_chunk.strip())
                    current_chunk = sentence
                else:
                    # Single sentence too long, force split
                    words = sentence.split()
                    temp_chunk = ""
                    for word in words:
                        if len(temp_chunk) + len(word) > max_length:
                            if temp_chunk:
                                chunks.append(temp_chunk.strip())
                                temp_chunk = word
                            else:
                                chunks.append(word)
                        else:
                            temp_chunk += " " + word if temp_chunk else word
                    current_chunk = temp_chunk
            else:
                current_chunk += " " + sentence if current_chunk else sentence
        
        if current_chunk:
            chunks.append(current_chunk.strip())
        
        return chunks
    
    async def create_audio_variants(self, base_path, audio_array):
        """Create 2 audio variants: Raw and Enhanced (using ffmpeg filter)"""
        import numpy as np
        import subprocess
        import soundfile as sf
        
        output_files = []
        
        try:
            # 1. Raw audio (already saved)
            raw_file = f"{base_path}_raw.wav"
            output_files.append(raw_file)
            
            # 2. Enhanced audio with ffmpeg filter
            enhanced_file = f"{base_path}_enhanced.wav"
            ffmpeg_enhance_cmd = [
                'ffmpeg', '-i', raw_file,
                '-af', self.ffmpeg_filter,
                '-y', enhanced_file
            ]
            
            try:
                subprocess.run(ffmpeg_enhance_cmd, capture_output=True, check=True, timeout=60)
                output_files.append(enhanced_file)
                print("Enhanced audio created")
            except Exception as e:
                print(f"Enhanced audio creation failed: {e}")
                # Use raw as fallback
                import shutil
                shutil.copy(raw_file, enhanced_file)
                output_files.append(enhanced_file)
            
            return output_files
            
        except Exception as e:
            print(f"Audio variants creation error: {e}")
            return [raw_file] if os.path.exists(raw_file) else []

    async def send_audio_variants(self, context, file_paths, script_text, chat_id=None, filename="Generated Audio"):
        """
        Upload EACH variant individually to GoFile and send its link.
        No folder, no zip. Per-file retry+fallback. If a file fails to upload and is < 50MB, send via Telegram.
        """
        try:
            if chat_id is None:
                chat_id = CHAT_ID

            # Normalize
            if isinstance(file_paths, str):
                file_paths = [file_paths]
            file_paths = [p for p in file_paths if p and os.path.exists(p)]
            if not file_paths:
                await context.bot.send_message(chat_id=chat_id, text="❌ No output files found.")
                return "No files"

            results = []
            for p in file_paths:
                size_mb = os.path.getsize(p) // (1024 * 1024)
                base = os.path.basename(p)

                link = await self.upload_single_to_gofile(p)
                if link:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"✅ Uploaded: {base}\n"
                            f"📏 Size: {size_mb}MB\n"
                            f"🔗 Link: {link}"
                        ),
                    )
                    results.append(link)
                    continue

                # Fallback: small files go via Telegram
                if os.path.getsize(p) < MAX_TELEGRAM_FILE_SIZE:
                    try:
                        with open(p, "rb") as f:
                            await context.bot.send_audio(
                                chat_id=chat_id,
                                audio=f,
                                caption=(
                                    f"✅ {filename}\n"
                                    f"📄 Variant: {base}\n"
                                    f"📏 Size: {size_mb}MB\n"
                                    f"🎵 Ref: {os.path.basename(self.reference_audio)}\n"
                                    f"⚡ Speed: {self.audio_speed}x"
                                )
                            )
                        results.append("Sent via Telegram")
                        continue
                    except Exception as e:
                        print(f"⚠️ Telegram fallback failed for {base}: {e}")

                # If we reach here, upload+fallback failed
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ Could not deliver: {base}. File saved locally on server."
                )
                results.append("Local only")

            return ", ".join(results) if results else "Done"
        except Exception as e:
            err = f"Send audio variants error: {e}"
            print(f"❌ {err}")
            try:
                await context.bot.send_message(chat_id=chat_id or CHAT_ID, text=f"❌ {err}")
            except:
                pass
            return "Error"
    
    async def send_audio(self, context, audio_paths, script_text, chat_id=None, filename="Generated Audio"):
        """Send 4 variants if small; else upload all 4 to GoFile (one link). Returns 'Sent via Telegram' or URL."""
        try:
            if chat_id is None:
                chat_id = CHAT_ID

            # Normalize to list
            if not isinstance(audio_paths, list):
                audio_paths = [audio_paths]
            audio_paths = [p for p in audio_paths if p and os.path.exists(p)]
            if not audio_paths:
                raise RuntimeError("No audio files found to send.")

            sizes = [(p, os.path.getsize(p)) for p in audio_paths]
            total_mb = sum(sz for _, sz in sizes) // (1024 * 1024)
            any_too_big = any(sz >= MAX_TELEGRAM_FILE_SIZE for _, sz in sizes)

            if not any_too_big:
                # Send all variants to Telegram
                for p, sz in sizes:
                    caption = (
                        f"✅ {filename}\n"
                        f"📄 Variant: {os.path.basename(p)}\n"
                        f"📏 Size: {sz // (1024*1024)}MB\n"
                        f"📏 Script: {len(script_text)} chars\n"
                        f"🎵 Ref: {os.path.basename(self.reference_audio)}\n"
                        f"⚡ Speed: {self.audio_speed}x"
                    )
                    try:
                        if p.lower().endswith(".mp3"):
                            with open(p, "rb") as f:
                                await context.bot.send_audio(chat_id=chat_id, audio=f, caption=caption)
                        else:
                            with open(p, "rb") as f:
                                await context.bot.send_document(chat_id=chat_id, document=f, caption=caption)
                    except Exception as e:
                        print(f"⚠️ Failed to send {p}: {e}")
                print("✅ All variants sent via Telegram")
                return "Sent via Telegram"

            # Too big: upload all 4 to one GoFile folder
            print("🔄 One or more variants too large; uploading all 4 to a single GoFile link...")
            link = await self.upload_multiple_to_gofile(audio_paths)
            if link:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ {filename} (4 variants) uploaded to GoFile.\n\n"
                        f"📊 Total size: {total_mb}MB\n"
                        f"🔗 Link: {link}\n\n"
                        f"📏 Script: {len(script_text)} chars\n"
                        f"🎵 Ref: {os.path.basename(self.reference_audio)}\n"
                        f"⚡ Speed: {self.audio_speed}x"
                    ),
                )
                print("✅ GoFile link sent")
                return link

            # If upload failed, still tell user where files are
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"✅ {filename} Generated & Saved locally.\n"
                    f"📁 Files: {', '.join([os.path.basename(p) for p in audio_paths])}\n"
                    f"⚠️ Upload failed."
                ),
            )
            return "Saved locally"
        except Exception as e:
            err = f"Send audio error: {str(e)}"
            print(f"❌ {err}")
            try:
                await context.bot.send_message(chat_id=chat_id or CHAT_ID, text=f"❌ {err}")
            except:
                pass
            return None
    
    async def upload_multiple_to_gofile(self, file_paths):
        """
        Upload multiple files to a SINGLE GoFile folder and return that folder's download page URL.
        If GOFILE_TOKEN is set, we include it for better control/quota.
        """
        try:
            token = os.getenv("GOFILE_TOKEN")  # optional
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            folder_id = None
            download_page = None

            for path in file_paths:
                if not os.path.exists(path):
                    continue
                with open(path, "rb") as f:
                    data = {"folderId": folder_id} if folder_id else {}
                    files = {"file": f}
                    resp = requests.post(
                        "https://upload.gofile.io/uploadfile",
                        headers=headers,
                        data=data,
                        files=files,
                        timeout=1000
                    )
                resp.raise_for_status()
                j = resp.json()
                # GoFile returns info in "data"
                d = j.get("data", {}) if isinstance(j, dict) else {}
                # First upload creates a folder; subsequent uploads reuse it
                folder_id = d.get("folderId") or d.get("parentFolderId") or folder_id
                # Keep the folder's download page (user-facing page listing all files)
                download_page = download_page or d.get("downloadPage")

            return download_page
        except Exception as e:
            print(f"❌ GoFile multi-upload error: {e}")
            return None

    async def upload_single_to_gofile(self, file_path):
        """
        Upload exactly one file to GoFile and return its download page URL.
        Strategy:
          1) Try new API:   https://upload.gofile.io/uploadfile
          2) On 5xx/fail → fallback to legacy server flow:
             - GET https://api.gofile.io/getServer
             - POST https://{server}.gofile.io/uploadFile
        Retries with exponential backoff.
        """
        token = os.getenv("GOFILE_TOKEN")  # optional
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        def _try_new_api():
            with open(file_path, "rb") as f:
                resp = requests.post(
                    "https://upload.gofile.io/uploadfile",
                    headers=headers,
                    files={"file": f},
                    timeout=1000,
                )
            return resp

        def _try_legacy_api():
            # Get server
            srv = requests.get("https://api.gofile.io/getServer", timeout=15)
            srv.raise_for_status()
            server = srv.json().get("data", {}).get("server")
            if not server:
                raise RuntimeError("GoFile getServer returned no server.")
            # Upload to that server
            with open(file_path, "rb") as f:
                resp = requests.post(
                    f"https://{server}.gofile.io/uploadFile",
                    headers=headers,
                    files={"file": f},
                    timeout=1000,
                )
            return resp

        last_err = None
        for attempt in range(3):
            try:
                # 1) New API
                r = _try_new_api()
                if r.status_code == 200 and r.headers.get("content-type",""").startswith("application/json"):
                    j = r.json()
                    d = j.get("data", {}) if isinstance(j, dict) else {}
                    link = d.get("downloadPage")
                    if link:
                        return link
                # Fall back if 5xx or missing link
                # 2) Legacy server API
                r = _try_legacy_api()
                if r.status_code == 200 and r.headers.get("content-type",""").startswith("application/json"):
                    j = r.json()
                    # legacy returns {"status":"ok","data":{"downloadPage": "..."}}
                    if j.get("status") == "ok":
                        d = j.get("data", {})
                        link = d.get("downloadPage")
                        if link:
                            return link
                last_err = f"GoFile upload failed (attempt {attempt+1}): {r.status_code} {r.text[:200]}"
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
            # backoff
            time.sleep(1.5 * (2 ** attempt))

        print(f"❌ GoFile single-upload error: {last_err}")
        return None

    def _classify_variant(self, path: str) -> str:
        p = path.lower()
        if p.endswith(".mp3"):
            return "mp3"
        if p.endswith("_loudness.wav"):
            return "loud"
        if p.endswith("_normalized.wav"):
            return "norm"
        if p.endswith(".wav"):
            return "raw"
        return "other"

    def _pick_paths(self, paths, which: str):
        if which == "all":
            return list(paths)
        if which == "enhanced":
            return [p for p in paths if p.endswith("_enhanced.wav")]
        if which == "raw":
            return [p for p in paths if p.endswith("_raw.wav")]
        # Default to all (both raw and enhanced)
        return list(paths)

    def _settings_keyboard(self, current: str):
        def label(mode, text):
            return f"✓ {text}" if mode == current else text

        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton(label("all", "All (default)"), callback_data="settings:set:all"),
            ],
            [
                InlineKeyboardButton(label("enhanced", "Enhanced"), callback_data="settings:set:enhanced"),
                InlineKeyboardButton(label("raw", "Raw"), callback_data="settings:set:raw"),
            ],
            [InlineKeyboardButton("Close", callback_data="settings:close")],
        ])

    def _variant_keyboard(self):
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🧺 Both (default)", callback_data="pick:all"),
            ],
            [
                InlineKeyboardButton("🎧 Enhanced", callback_data="pick:enhanced"),
                InlineKeyboardButton("📼 Raw", callback_data="pick:raw"),
            ],
            [
                InlineKeyboardButton("✕ Close", callback_data="pick:close"),
            ],
        ])

    def _power_keyboard(self, current: str):
        def mark(opt, label):
            return f"✓ {label}" if current == opt else label
        return InlineKeyboardMarkup([
            [InlineKeyboardButton(mark("off","Do nothing"),  callback_data="power:set:off")],
            [InlineKeyboardButton(mark("stop","Stop instance (safe)"), callback_data="power:set:stop")],
            [InlineKeyboardButton(mark("destroy","Destroy instance (danger)"), callback_data="power:set:destroy")],
            [InlineKeyboardButton("🔙 Back", callback_data="settings:power_menu")]
        ])

    async def send_outputs_by_mode(self, context, chat_id, file_paths, script_text, filename):
        """
        Look up the saved mode for this chat and deliver exactly those variant links (no picker).
        """
        mode = self.delivery_prefs_by_chat.get(chat_id, "all")  # Default to all (both raw & enhanced)
        wanted = self._pick_paths(file_paths, mode)
        if not wanted:
            # fallback to 'raw' if the expected variant isn't present
            wanted = self._pick_paths(file_paths, "raw")

        results = []
        for p in wanted:
            # cached?
            link = self.gofile_cache.get(p)
            if not link:
                link = await self.upload_single_to_gofile(p)
                if link:
                    self.gofile_cache[p] = link

            base = os.path.basename(p)
            size_mb = os.path.getsize(p)//(1024*1024) if os.path.exists(p) else 0

            if link:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🔗 {base} ({size_mb}MB)\n{link}"
                )
                results.append(link)
            else:
                # small file Telegram fallback
                if os.path.exists(p) and os.path.getsize(p) < MAX_TELEGRAM_FILE_SIZE:
                    try:
                        with open(p, "rb") as f:
                            await context.bot.send_audio(
                                chat_id=chat_id, audio=f,
                                caption=f"📄 {base} ({size_mb}MB) — Telegram fallback"
                            )
                        results.append("Sent via Telegram")
                    except Exception as e:
                        await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Could not deliver {base}: {e}")
                else:
                    await context.bot.send_message(chat_id=chat_id, text=f"⚠️ Could not upload {base}; saved locally.")
                    results.append("Local only")

        return ", ".join(results) if results else "Done"

    async def power_command(self, update, context):
        chat_id = update.effective_chat.id
        await update.message.reply_text(
            f"⚡ Power Settings\n\n"
            f"Current policy: **{self.power_policy}**\n\n"
            f"Select what to do **after all files finish**:",
            parse_mode="Markdown",
            reply_markup=self._power_keyboard(self.power_policy)
        )

    async def stop_processing_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Stop all ongoing processing immediately"""
        try:
            if not self.is_processing:
                await update.message.reply_text(
                    "⚠️ No processing currently running.\n\n"
                    "Use this command when audio/video generation is in progress."
                )
                return

            self.stop_requested = True

            await update.message.reply_text(
                "🛑 STOP REQUESTED!\n\n"
                "⏳ Stopping current operation...\n"
                "📊 Current queue will be cleared\n"
                "⚠️ Current file may be incomplete\n\n"
                "Please wait a moment..."
            )

        except Exception as e:
            await update.message.reply_text(f"❌ Stop command error: {str(e)}")


    async def on_power(self, update, context):
        q = update.callback_query
        try: await q.answer()
        except: pass

        data = q.data or ""
        if data == "power:close":
            try: await q.edit_message_reply_markup(reply_markup=None)
            except: pass
            return

        if data.startswith("power:set:"):
            choice = data.split(":", 2)[2]
            if choice not in {"off","stop","destroy"}:
                await q.message.reply_text("⚠️ Invalid option.")
                return
            self.power_policy = choice
            # Save configuration to file
            self.save_config()
            warn = "\n\n⚠️ *Destroy deletes all data. Irreversible.*" if choice == "destroy" else ""
            try:
                await q.edit_message_text(
                    text=f"✅ Saved. Power policy: **{choice}**{warn}",
                    parse_mode="Markdown",
                    reply_markup=self._power_keyboard(self.power_policy)
                )
            except:
                await q.message.reply_text(f"✅ Saved. Power policy: **{choice}**{warn}", parse_mode="Markdown")

    async def on_process(self, update, context):
        """Handle process menu callbacks"""
        q = update.callback_query
        try:
            await q.answer()
        except:
            pass

        data = q.data or ""
        chat_id = q.message.chat.id if q and q.message and q.message.chat else None
        
        if data == "process:upload_txt":
            await q.edit_message_text(
                "📄 Please upload a text file (.txt) with your script content.\n\n"
                "The file will be processed automatically once uploaded."
            )
        
        elif data == "process:direct_text":
            await q.edit_message_text(
                "📝 Please type or paste your text directly in the chat.\n\n"
                "Your message will be processed automatically once sent."
            )
        
        elif data == "process:youtube":
            await q.edit_message_text(
                "🔗 Please paste a YouTube link in the chat.\n\n"
                "The video transcript will be extracted, processed, and converted to audio.\n"
                "You can also send multiple YouTube links in one message."
            )
            
    async def on_status(self, update, context):
        """Handle status menu callbacks"""
        q = update.callback_query
        try:
            await q.answer()
        except:
            pass

        data = q.data or ""
        
        if data == "status:links":
            await self.links_command(update, context)
            
    async def on_ref(self, update, context):
        """Handle reference audio callbacks"""
        q = update.callback_query
        try:
            await q.answer()
        except:
            pass

        data = q.data or ""
        
        if data == "ref:back":
            # Load original reference
            self.load_manual_reference()
            
            ref_name = os.path.basename(self.reference_audio) if self.reference_audio else "None"
            
            # Create buttons for reference actions
            keyboard = [
                [InlineKeyboardButton("🎵 Set New Reference", callback_data="settings:ref")],
                [InlineKeyboardButton("🔙 Back to Settings", callback_data="main:settings")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await q.edit_message_text(
                f"🔄 Reverted to default reference!\n\n"
                f"📁 File: {ref_name}\n"
                f"📝 Text: {self.reference_text[:100]}{'...' if len(self.reference_text) > 100 else ''}\n\n"
                f"Choose an action:",
                reply_markup=reply_markup
            )

    async def on_youtube_mode(self, update, context):
        """Handle YouTube mode selection callbacks"""
        q = update.callback_query
        try:
            await q.answer()
        except:
            pass

        data = q.data or ""

        # Extract URL from callback data
        if not data.startswith("yt_mode:"):
            return

        parts = data.split(":", 2)
        if len(parts) < 3:
            await q.message.reply_text("❌ Invalid callback data")
            return

        mode = parts[1]  # 'ai' or 'ref'
        youtube_url = parts[2]

        if mode == "ai":
            # Process with AI (current flow)
            await q.edit_message_text("🤖 Processing with AI Mode (DeepSeek + F5-TTS)...")
            # Pass the update object directly, not q
            await self.process_youtube_link(youtube_url, update, context)

        elif mode == "ref":
            # Extract and set as reference
            await q.edit_message_text("🎵 Extracting audio as Reference...")
            # Pass the update object directly, not q
            await self.extract_youtube_audio_as_reference(youtube_url, update, context)


    # === Vast.ai helpers ===
    def _vast_headers(self):
        token = os.getenv("VAST_API_KEY")
        if not token:
            raise RuntimeError("VAST_API_KEY not set")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _vast_instance_id(self):
        iid = os.getenv("VAST_INSTANCE_ID") or os.getenv("CONTAINER_ID")
        if not iid:
            raise RuntimeError("VAST_INSTANCE_ID or CONTAINER_ID not set")
        return str(iid)

    def vast_stop_instance(self):
        """Stop Vast.ai instance using CLI (now that it's installed)"""
        try:
            # Method 1: Try to stop all instances
            try:
                result = subprocess.run(
                    ["vastai", "stop", "instance", "--all"],
                    capture_output=True,
                    text=True,
                    timeout=1000
                )
                print(f"CLI stop all result: {result.returncode}")
                print(f"Stdout: {result.stdout}")
                print(f"Stderr: {result.stderr}")
                
                if result.returncode == 0:
                    print("✅ Vast.ai CLI stop --all successful")
                    return True
                else:
                    print(f"⚠️ Stop --all failed: {result.stderr}")
            except Exception as e:
                print(f"CLI --all method failed: {e}")
            
            # Method 2: Get instance list and stop individually
            try:
                list_result = subprocess.run(
                    ["vastai", "show", "instances"],
                    capture_output=True,
                    text=True,
                    timeout=1000
                )
                
                if list_result.returncode == 0 and list_result.stdout:
                    # Parse instance IDs from output
                    lines = list_result.stdout.strip().split('\n')
                    for line in lines[1:]:  # Skip header
                        parts = line.split()
                        if parts and parts[0].isdigit():
                            instance_id = parts[0]
                            # Try to stop this specific instance
                            stop_result = subprocess.run(
                                ["vastai", "stop", "instance", instance_id],
                                capture_output=True,
                                text=True,
                                timeout=1000
                            )
                            if stop_result.returncode == 0:
                                print(f"✅ Stopped instance {instance_id}")
                                return True
                            else:
                                print(f"⚠️ Failed to stop {instance_id}: {stop_result.stderr}")
            except Exception as e:
                print(f"Individual stop method failed: {e}")
            
            # Method 3: API fallback (your previous working method)
            try:
                api_key = os.getenv("VAST_API_KEY")
                instance_id = os.getenv("VAST_INSTANCE_ID") or os.getenv("CONTAINER_ID")
                
                if api_key and instance_id:
                    headers = {
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json"
                    }
                    url = f"https://console.vast.ai/api/v0/instances/{instance_id}/"
                    
                    response = requests.put(
                        url, 
                        headers=headers, 
                        json={"state": "stopped"}, 
                        timeout=1000
                    )
                    
                    if response.status_code == 200:
                        print(f"✅ API method stopped instance {instance_id}")
                        return True
                    else:
                        print(f"⚠️ API method failed: {response.status_code}")
                else:
                    print("⚠️ API credentials missing")
                    
            except Exception as e:
                print(f"API fallback failed: {e}")
            
            print("❌ All stop methods failed")
            return False
            
        except Exception as e:
            print(f"❌ Vast.ai stop error: {e}")
            return False

    def vast_destroy_instance(self):
        iid = self._vast_instance_id()
        url = f"https://console.vast.ai/api/v0/instances/{iid}/"
        for attempt in range(2):
            try:
                r = requests.delete(url, headers=self._vast_headers(), timeout=20)
                if r.status_code == 200:
                    return True
                time.sleep(1.5 * (2**attempt))
            except Exception:
                time.sleep(1.5 * (2**attempt))
        return False

    async def maybe_shutdown_after_queue(self, context, chat_id=None):
        if self.shutdown_executed:
            return

        policy = self.power_policy
        if policy == "off":
            return

        msg_chat = chat_id or (getattr(context, "chat_id", None) or None)
        
        try:
            # Clean all folders before shutdown
            await self.deep_cleanup_storage()
            
            if not self.vast_env_ok:
                if msg_chat:
                    await context.bot.send_message(
                        chat_id=msg_chat,
                        text="⚠️ Vast.ai environment not configured. Cleaned files but cannot auto-stop."
                    )
                return
            
            if policy == "stop":
                ok = self.vast_stop_instance()
                if msg_chat:
                    await context.bot.send_message(
                        chat_id=msg_chat,
                        text="🧹 Cleaned all files & folders.\n🛑 " + 
                             ("✅ Instance stopped successfully." if ok else "⚠️ Stop failed - check manually.")
                    )
            elif policy == "destroy":
                ok = self.vast_destroy_instance()
                if msg_chat:
                    await context.bot.send_message(
                        chat_id=msg_chat,
                        text="🧹 Cleaned all files & folders.\n🗑️ " + 
                             ("✅ Instance destroyed." if ok else "⚠️ Destroy failed - check manually.")
                    )
            self.shutdown_executed = True
        except Exception as e:
            if msg_chat:
                await context.bot.send_message(chat_id=msg_chat, text=f"⚠️ Cleanup/shutdown error: {e}")

# Main function
async def async_main():
    """Async main bot function with proper initialization."""
    print("🚀 Starting Final Working F5-TTS Bot...")

    # Bot instance
    bot_instance = WorkingF5Bot()

    if not bot_instance.f5_model:
        print("❌ F5-TTS initialization failed! Check installation.")
        return

    print("✅ Bot fully initialized and ready!")

    # Display channel configuration
    print("\n" + "="*50)
    print("📢 CHANNEL CONFIGURATION")
    print("="*50)
    if CHANNEL_MODE_ENABLED:
        print("✅ Channel Mode: ENABLED")
        if CHANNEL_IDS:
            print(f"📋 Authorized Channels: {len(CHANNEL_IDS)}")
            for ch_id in CHANNEL_IDS:
                print(f"   • Channel ID: {ch_id}")
        else:
            print("⚠️ No specific channels configured (accepting all)")
    else:
        print("❌ Channel Mode: DISABLED")
    print("="*50 + "\n")

    # Application with longer timeout for Vast.ai network
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(60.0)
        .read_timeout(60.0)
        .write_timeout(60.0)
        .pool_timeout(60.0)
        .build()
    )

    # IMPORTANT: Initialize the application first
    await application.initialize()
    
    # Register handlers - START COMMAND FIRST
    # NOTE: Most commands now accessible via Settings menu for better organization
    application.add_handler(CommandHandler("start", bot_instance.start_command))
    application.add_handler(CommandHandler("settings", bot_instance.settings_command))

    # Keep these commands for text input convenience
    application.add_handler(CommandHandler("set_prompt", bot_instance.set_prompt_command))
    application.add_handler(CommandHandler("set_youtube_prompt", bot_instance.set_youtube_prompt_command))
    application.add_handler(CommandHandler("set_openrouter_model", bot_instance.set_openrouter_model_command))
    application.add_handler(CommandHandler("set_ffmpeg", bot_instance.set_ffmpeg_command))
    application.add_handler(CommandHandler("set_chunk_size", bot_instance.set_chunk_size_command))
    application.add_handler(CommandHandler("update_ytdlp", bot_instance.update_ytdlp_command))
    application.add_handler(CommandHandler("start_processing", bot_instance.start_processing_command))
    # YouTube Channel Automation Commands
    application.add_handler(CommandHandler("set_supabase_url", bot_instance.set_supabase_url_command))
    application.add_handler(CommandHandler("set_supabase_key", bot_instance.set_supabase_key_command))
    application.add_handler(CommandHandler("set_youtube_key", bot_instance.set_youtube_key_command))
    application.add_handler(CommandHandler("add_supadata_key", bot_instance.add_supadata_key_command))
    application.add_handler(CommandHandler("set_deepseek_key", bot_instance.set_deepseek_key_command))
    application.add_handler(CommandHandler("set_channel_prompt", bot_instance.set_channel_prompt_command))
    application.add_handler(CommandHandler("list_keys", bot_instance.list_keys_command))

    # All other commands accessible via Settings menu:
    # - Test: Settings > Debug Tools > Run Test
    # - Links: Settings > Completed Files
    # - Power: Settings > Power & Control
    # - Reference: Settings > Reference Audio
    # - Bulk: Settings > Bulk Shorts
    # - Stop: Settings > Power & Control > Stop Processing
    
    # Callback handlers
    application.add_handler(CallbackQueryHandler(bot_instance.on_main_menu, pattern=r"^main:"))
    application.add_handler(CallbackQueryHandler(bot_instance.on_pick, pattern=r"^pick:"))
    application.add_handler(CallbackQueryHandler(bot_instance.on_settings, pattern=r"^settings:"))
    application.add_handler(CallbackQueryHandler(bot_instance.on_settings, pattern=r"^pipeline:"))
    application.add_handler(CallbackQueryHandler(bot_instance.on_power, pattern=r"^power:"))
    application.add_handler(CallbackQueryHandler(bot_instance.on_process, pattern=r"^process:"))
    application.add_handler(CallbackQueryHandler(bot_instance.on_status, pattern=r"^status:"))
    application.add_handler(CallbackQueryHandler(bot_instance.on_ref, pattern=r"^ref:"))
    application.add_handler(CallbackQueryHandler(bot_instance.on_youtube_mode, pattern=r"^yt_mode:"))

    # Message handlers (order matters!)
    application.add_handler(MessageHandler(filters.AUDIO | filters.VOICE | filters.Document.AUDIO, bot_instance.test_audio_handler))
    application.add_handler(MessageHandler(filters.Document.TXT, bot_instance.handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot_instance.handle_text))

    # Channel post handlers (for channel messages)
    if CHANNEL_MODE_ENABLED:
        print("📢 Channel mode enabled - adding channel post handlers...")

        # Channel commands support
        application.add_handler(CommandHandler("set_ffmpeg", bot_instance.set_ffmpeg_command, filters=filters.ChatType.CHANNEL))

        # Channel text and file handlers
        application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.Document.TXT, bot_instance.handle_document))
        application.add_handler(MessageHandler(filters.ChatType.CHANNEL & filters.TEXT & ~filters.COMMAND, bot_instance.handle_text))
        print(f"✅ Channel handlers registered for {len(CHANNEL_IDS) if CHANNEL_IDS else 'all'} channel(s)")
        print(f"✅ Channel commands enabled: /set_ffmpeg")

    print("✅ All handlers registered")

    # Start the bot with proper async context
    print("🔄 Starting bot polling...")
    await application.start()
    await application.updater.start_polling()

    print("✅ Bot is now running! Press Ctrl+C to stop.")

    # Keep the bot running
    try:
        import signal
        stop_event = asyncio.Event()

        def signal_handler(sig, frame):
            stop_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        await stop_event.wait()
    except KeyboardInterrupt:
        pass
    finally:
        print("\n🛑 Stopping bot...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

def main():
    """Synchronous main entry point."""
    asyncio.run(async_main())

if __name__ == "__main__":
    main()