#!/usr/bin/env python3
"""
Supabase Database Client for F5-TTS Bot
========================================
Handles all database operations including:
- API key management with rotation
- YouTube channel & video tracking
- 15-day processed video cooldown
- Global counter for audio file naming
- Custom prompts storage
- Multi-chat configuration
"""

import os
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from supabase import create_client, Client

class SupabaseClient:
    def __init__(self, url: Optional[str] = None, key: Optional[str] = None):
        """Initialize Supabase client with URL and anon key"""
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_ANON_KEY")

        if not self.url or not self.key:
            print("⚠️ Supabase credentials not set. Use /set_supabase_url and /set_supabase_key commands.")
            self.client = None
        else:
            try:
                self.client: Client = create_client(self.url, self.key)
                print("✅ Supabase client initialized")
            except Exception as e:
                print(f"❌ Supabase connection error: {e}")
                self.client = None

    def is_connected(self) -> bool:
        """Check if Supabase client is connected"""
        return self.client is not None

    # =============================================================================
    # TABLE INITIALIZATION
    # =============================================================================

    def init_tables(self) -> bool:
        """
        Initialize all required tables.
        NOTE: This assumes tables are already created in Supabase dashboard.
        Returns True if tables exist, False otherwise.
        """
        if not self.is_connected():
            return False

        try:
            # Check if tables exist by querying them
            tables_to_check = [
                'api_keys', 'youtube_channels', 'processed_videos',
                'prompts', 'chat_configs', 'global_counter', 'audio_links',
                'direct_script_audio'
            ]

            for table in tables_to_check:
                self.client.table(table).select("*").limit(1).execute()

            print("✅ All Supabase tables verified")
            return True
        except Exception as e:
            print(f"⚠️ Table check failed: {e}")
            print("📝 Please create tables using SQL schema in Supabase dashboard")
            return False

    def get_table_creation_sql(self) -> str:
        """Return SQL for creating all required tables"""
        return """
-- API Keys Table
CREATE TABLE IF NOT EXISTS api_keys (
    id BIGSERIAL PRIMARY KEY,
    key_type TEXT NOT NULL CHECK (key_type IN ('youtube', 'supadata', 'deepseek')),
    api_key TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_used TIMESTAMPTZ DEFAULT NOW(),
    usage_count INTEGER DEFAULT 0
);

-- YouTube Channels Table
CREATE TABLE IF NOT EXISTS youtube_channels (
    id BIGSERIAL PRIMARY KEY,
    channel_url TEXT NOT NULL UNIQUE,
    channel_id TEXT NOT NULL,
    channel_name TEXT,
    videos_json JSONB,  -- Top 1000 videos cache
    last_updated TIMESTAMPTZ DEFAULT NOW()
);

-- Processed Videos Table
CREATE TABLE IF NOT EXISTS processed_videos (
    id BIGSERIAL PRIMARY KEY,
    video_id TEXT NOT NULL,
    video_url TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    processed_date TIMESTAMPTZ DEFAULT NOW(),
    chat_id TEXT NOT NULL,
    audio_counter INTEGER
);

-- Create index for 15-day lookup
CREATE INDEX IF NOT EXISTS idx_processed_videos_date ON processed_videos (video_id, processed_date DESC);

-- Prompts Table
CREATE TABLE IF NOT EXISTS prompts (
    id BIGSERIAL PRIMARY KEY,
    prompt_type TEXT NOT NULL CHECK (prompt_type IN ('deepseek', 'youtube', 'channel')),
    prompt_text TEXT NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Chat Configs Table
CREATE TABLE IF NOT EXISTS chat_configs (
    id BIGSERIAL PRIMARY KEY,
    chat_id TEXT NOT NULL UNIQUE,
    chat_name TEXT NOT NULL,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Global Counter Table
CREATE TABLE IF NOT EXISTS global_counter (
    id INTEGER PRIMARY KEY DEFAULT 1,
    counter INTEGER DEFAULT 0,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CHECK (id = 1)  -- Ensure only one row
);

-- Initialize counter if not exists
INSERT INTO global_counter (id, counter) VALUES (1, 0) ON CONFLICT (id) DO NOTHING;

-- Audio Links Table (for download queue)
CREATE TABLE IF NOT EXISTS audio_links (
    id BIGSERIAL PRIMARY KEY,
    enhanced_link TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for faster lookups
CREATE INDEX IF NOT EXISTS idx_audio_links_created ON audio_links (created_at DESC);

-- Direct Script Audio Table (for raw audio storage)
CREATE TABLE IF NOT EXISTS direct_script_audio (
    id BIGSERIAL PRIMARY KEY,
    filename TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    gofile_link TEXT,
    file_size_mb REAL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index for faster downloads
CREATE INDEX IF NOT EXISTS idx_direct_script_audio_created ON direct_script_audio (created_at DESC);
"""

    # =============================================================================
    # API KEY MANAGEMENT
    # =============================================================================

    def store_api_key(self, key_type: str, api_key: str) -> bool:
        """Store or update an API key"""
        if not self.is_connected():
            return False

        try:
            # Check if key already exists
            result = self.client.table('api_keys').select('*').eq('api_key', api_key).execute()

            if result.data:
                # Update existing key
                self.client.table('api_keys').update({
                    'is_active': True,
                    'last_used': datetime.now().isoformat()
                }).eq('api_key', api_key).execute()
            else:
                # Insert new key
                self.client.table('api_keys').insert({
                    'key_type': key_type,
                    'api_key': api_key,
                    'is_active': True
                }).execute()

            print(f"✅ {key_type} API key stored")
            return True
        except Exception as e:
            print(f"❌ Error storing API key: {e}")
            return False

    def get_active_api_key(self, key_type: str) -> Optional[str]:
        """Get an active API key of specified type"""
        if not self.is_connected():
            return None

        try:
            result = self.client.table('api_keys')\
                .select('api_key')\
                .eq('key_type', key_type)\
                .eq('is_active', True)\
                .order('last_used', desc=False)\
                .limit(1)\
                .execute()

            if result.data:
                key = result.data[0]['api_key']
                # Update last_used
                self.client.table('api_keys')\
                    .update({'last_used': datetime.now().isoformat()})\
                    .eq('api_key', key)\
                    .execute()
                return key
            return None
        except Exception as e:
            print(f"❌ Error getting API key: {e}")
            return None

    def mark_key_exhausted(self, api_key: str) -> bool:
        """Mark an API key as exhausted (inactive)"""
        if not self.is_connected():
            return False

        try:
            self.client.table('api_keys')\
                .update({'is_active': False})\
                .eq('api_key', api_key)\
                .execute()
            print(f"⚠️ API key marked as exhausted")
            return True
        except Exception as e:
            print(f"❌ Error marking key exhausted: {e}")
            return False

    def rotate_supadata_key(self) -> Optional[str]:
        """
        Rotate to next available Supadata API key.
        Returns next active key or None if all exhausted.
        """
        return self.get_active_api_key('supadata')

    def get_all_api_keys_status(self) -> List[Dict[str, Any]]:
        """Get status of all API keys"""
        if not self.is_connected():
            return []

        try:
            result = self.client.table('api_keys')\
                .select('key_type, api_key, is_active, last_used, usage_count')\
                .execute()

            return result.data if result.data else []
        except Exception as e:
            print(f"❌ Error getting API keys status: {e}")
            return []

    # =============================================================================
    # YOUTUBE CHANNEL & VIDEO MANAGEMENT
    # =============================================================================

    def store_youtube_channel(self, channel_url: str, channel_id: str,
                              channel_name: str, videos: List[Dict]) -> bool:
        """Store or update YouTube channel with top 1000 videos"""
        if not self.is_connected():
            return False

        try:
            data = {
                'channel_url': channel_url,
                'channel_id': channel_id,
                'channel_name': channel_name,
                'videos_json': json.dumps(videos),
                'last_updated': datetime.now().isoformat()
            }

            # Upsert (insert or update)
            self.client.table('youtube_channels').upsert(data).execute()
            print(f"✅ Channel cached: {channel_name} ({len(videos)} videos)")
            return True
        except Exception as e:
            print(f"❌ Error storing channel: {e}")
            return False

    def get_youtube_channel(self, channel_url: str) -> Optional[Dict]:
        """Get cached YouTube channel data"""
        if not self.is_connected():
            return None

        try:
            result = self.client.table('youtube_channels')\
                .select('*')\
                .eq('channel_url', channel_url)\
                .execute()

            if result.data:
                channel = result.data[0]
                # Parse videos JSON
                if channel.get('videos_json'):
                    channel['videos'] = json.loads(channel['videos_json'])
                return channel
            return None
        except Exception as e:
            print(f"❌ Error getting channel: {e}")
            return None

    def mark_video_processed(self, video_id: str, video_url: str, channel_id: str,
                            chat_id: str, audio_counter: int) -> bool:
        """Mark a video as processed"""
        if not self.is_connected():
            return False

        try:
            self.client.table('processed_videos').insert({
                'video_id': video_id,
                'video_url': video_url,
                'channel_id': channel_id,
                'processed_date': datetime.now().isoformat(),
                'chat_id': chat_id,
                'audio_counter': audio_counter
            }).execute()
            print(f"✅ Video marked as processed: {video_id}")
            return True
        except Exception as e:
            print(f"❌ Error marking video processed: {e}")
            return False

    def get_unprocessed_videos(self, video_ids: List[str], days: int = 15) -> List[str]:
        """
        Get list of video IDs that haven't been processed in the last N days.
        Returns IDs that are NOT in processed_videos within the time window.
        """
        if not self.is_connected():
            return video_ids  # Return all if DB not connected

        try:
            cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()

            # Get recently processed video IDs
            result = self.client.table('processed_videos')\
                .select('video_id')\
                .in_('video_id', video_ids)\
                .gte('processed_date', cutoff_date)\
                .execute()

            recent_ids = {row['video_id'] for row in result.data} if result.data else set()

            # Return videos NOT in recent list
            unprocessed = [vid for vid in video_ids if vid not in recent_ids]
            print(f"📊 Unprocessed videos: {len(unprocessed)}/{len(video_ids)} (last {days} days)")
            return unprocessed
        except Exception as e:
            print(f"❌ Error checking processed videos: {e}")
            return video_ids  # Return all on error

    # =============================================================================
    # GLOBAL COUNTER MANAGEMENT
    # =============================================================================

    def get_counter(self) -> int:
        """Get current global counter value"""
        if not self.is_connected():
            return 0

        try:
            result = self.client.table('global_counter')\
                .select('counter')\
                .eq('id', 1)\
                .execute()

            if result.data:
                return result.data[0]['counter']
            return 0
        except Exception as e:
            print(f"❌ Error getting counter: {e}")
            return 0

    def increment_counter(self) -> int:
        """Increment global counter and return new value"""
        if not self.is_connected():
            return 0

        try:
            # Get current value
            current = self.get_counter()
            new_value = current + 1

            # Update
            self.client.table('global_counter')\
                .update({'counter': new_value, 'updated_at': datetime.now().isoformat()})\
                .eq('id', 1)\
                .execute()

            return new_value
        except Exception as e:
            print(f"❌ Error incrementing counter: {e}")
            return 0

    # =============================================================================
    # PROMPT MANAGEMENT
    # =============================================================================

    def save_prompt(self, prompt_type: str, prompt_text: str) -> bool:
        """Save or update a prompt"""
        if not self.is_connected():
            return False

        try:
            # Upsert based on prompt_type
            data = {
                'prompt_type': prompt_type,
                'prompt_text': prompt_text,
                'updated_at': datetime.now().isoformat()
            }

            # Check if exists
            result = self.client.table('prompts')\
                .select('id')\
                .eq('prompt_type', prompt_type)\
                .execute()

            if result.data:
                # Update existing
                self.client.table('prompts')\
                    .update(data)\
                    .eq('prompt_type', prompt_type)\
                    .execute()
            else:
                # Insert new
                self.client.table('prompts').insert(data).execute()

            print(f"✅ {prompt_type} prompt saved")
            return True
        except Exception as e:
            print(f"❌ Error saving prompt: {e}")
            return False

    def get_prompt(self, prompt_type: str) -> Optional[str]:
        """Get a prompt by type"""
        if not self.is_connected():
            return None

        try:
            result = self.client.table('prompts')\
                .select('prompt_text')\
                .eq('prompt_type', prompt_type)\
                .execute()

            if result.data:
                return result.data[0]['prompt_text']
            return None
        except Exception as e:
            print(f"❌ Error getting prompt: {e}")
            return None

    # =============================================================================
    # CHAT CONFIGURATION
    # =============================================================================

    def add_chat_config(self, chat_id: str, chat_name: str) -> bool:
        """Add or update chat configuration"""
        if not self.is_connected():
            return False

        try:
            data = {
                'chat_id': chat_id,
                'chat_name': chat_name,
                'is_active': True
            }

            self.client.table('chat_configs').upsert(data).execute()
            print(f"✅ Chat config saved: {chat_name} ({chat_id})")
            return True
        except Exception as e:
            print(f"❌ Error saving chat config: {e}")
            return False

    def get_active_chats(self) -> List[Dict]:
        """Get all active chat configurations"""
        if not self.is_connected():
            return []

        try:
            result = self.client.table('chat_configs')\
                .select('*')\
                .eq('is_active', True)\
                .execute()

            return result.data if result.data else []
        except Exception as e:
            print(f"❌ Error getting active chats: {e}")
            return []

    # =============================================================================
    # AUDIO LINKS MANAGEMENT (for download queue)
    # =============================================================================

    def save_audio_link(self, enhanced_link: str) -> bool:
        """Save enhanced audio link to database for later processing"""
        if not self.is_connected():
            return False

        try:
            self.client.table('audio_links').insert({
                'enhanced_link': enhanced_link,
                'created_at': datetime.now().isoformat()
            }).execute()
            print(f"✅ Audio link saved to database")
            return True
        except Exception as e:
            print(f"❌ Error saving audio link: {e}")
            return False

    def get_pending_audio_links(self) -> List[Dict]:
        """Fetch all pending audio links from database"""
        if not self.is_connected():
            return []

        try:
            result = self.client.table('audio_links')\
                .select('id, enhanced_link')\
                .order('created_at', desc=False)\
                .execute()

            return result.data if result.data else []
        except Exception as e:
            print(f"❌ Error fetching audio links: {e}")
            return []

    def delete_audio_link(self, link_id: int) -> bool:
        """Delete processed audio link from database"""
        if not self.is_connected():
            return False

        try:
            self.client.table('audio_links')\
                .delete()\
                .eq('id', link_id)\
                .execute()
            print(f"✅ Audio link deleted from database (ID: {link_id})")
            return True
        except Exception as e:
            print(f"❌ Error deleting audio link: {e}")
            return False

    # =============================================================================
    # DIRECT SCRIPT RAW AUDIO STORAGE (Supabase Storage Integration)
    # =============================================================================

    def upload_raw_audio(self, file_path: str, bucket_name: str = "raw_audio_files") -> Optional[str]:
        """
        Upload raw audio file to Supabase Storage.
        Returns storage path on success, None on failure.
        """
        if not self.is_connected():
            return None

        try:
            import os
            filename = os.path.basename(file_path)

            # Read file
            with open(file_path, 'rb') as f:
                file_data = f.read()

            # Upload to storage
            storage_path = f"audio/{filename}"
            result = self.client.storage.from_(bucket_name).upload(
                path=storage_path,
                file=file_data,
                file_options={"content-type": "audio/wav"}
            )

            print(f"✅ Raw audio uploaded to Supabase Storage: {storage_path}")
            return storage_path
        except Exception as e:
            print(f"❌ Error uploading raw audio to Supabase: {e}")
            return None

    def save_direct_script_audio(self, filename: str, storage_path: str,
                                 gofile_link: Optional[str] = None,
                                 file_size_mb: Optional[float] = None) -> bool:
        """Save direct script audio metadata to database"""
        if not self.is_connected():
            return False

        try:
            self.client.table('direct_script_audio').insert({
                'filename': filename,
                'storage_path': storage_path,
                'gofile_link': gofile_link,
                'file_size_mb': file_size_mb,
                'created_at': datetime.now().isoformat()
            }).execute()
            print(f"✅ Direct script audio metadata saved")
            return True
        except Exception as e:
            print(f"❌ Error saving direct script audio: {e}")
            return False

    def get_pending_downloads(self) -> List[Dict]:
        """Fetch all pending audio files to download from Supabase"""
        if not self.is_connected():
            return []

        try:
            result = self.client.table('direct_script_audio')\
                .select('id, filename, storage_path, gofile_link, file_size_mb, created_at')\
                .order('created_at', desc=False)\
                .execute()

            return result.data if result.data else []
        except Exception as e:
            print(f"❌ Error fetching pending downloads: {e}")
            return []

    def download_audio_file(self, storage_path: str, local_path: str,
                           bucket_name: str = "raw_audio_files") -> bool:
        """
        Download audio file from Supabase Storage to local path.
        Returns True on success, False on failure.
        """
        if not self.is_connected():
            return False

        try:
            # Download from storage
            result = self.client.storage.from_(bucket_name).download(storage_path)

            # Save to local file
            import os
            os.makedirs(os.path.dirname(local_path), exist_ok=True)

            with open(local_path, 'wb') as f:
                f.write(result)

            print(f"✅ Audio downloaded: {os.path.basename(local_path)}")
            return True
        except Exception as e:
            print(f"❌ Error downloading audio: {e}")
            return False

    def delete_direct_script_audio(self, audio_id: int, storage_path: str,
                                   bucket_name: str = "raw_audio_files") -> bool:
        """
        Delete audio file from both Supabase Storage and database.
        Returns True if successful, False otherwise.
        """
        if not self.is_connected():
            return False

        try:
            # Delete from storage
            try:
                self.client.storage.from_(bucket_name).remove([storage_path])
                print(f"✅ Audio deleted from Supabase Storage: {storage_path}")
            except Exception as e:
                print(f"⚠️ Storage deletion warning: {e}")

            # Delete from database
            self.client.table('direct_script_audio')\
                .delete()\
                .eq('id', audio_id)\
                .execute()
            print(f"✅ Audio metadata deleted from database (ID: {audio_id})")
            return True
        except Exception as e:
            print(f"❌ Error deleting direct script audio: {e}")
            return False
