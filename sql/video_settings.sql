-- ============================================================================
-- Video Generation Settings Schema
-- ============================================================================

-- Video generation settings per chat
CREATE TABLE IF NOT EXISTS video_settings (
    chat_id TEXT PRIMARY KEY,
    video_enabled BOOLEAN DEFAULT true,
    subtitle_style TEXT DEFAULT 'Style: Banner,Arial,48,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,4,0,0,5,40,40,40,1',
    gdrive_image_folder_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create index on chat_id for faster lookups
CREATE INDEX IF NOT EXISTS idx_video_settings_chat_id ON video_settings(chat_id);

-- Track video outputs (for logging and debugging)
CREATE TABLE IF NOT EXISTS video_outputs (
    id BIGSERIAL PRIMARY KEY,
    counter INTEGER NOT NULL,
    chat_id TEXT,
    audio_path TEXT NOT NULL,
    video_path TEXT NOT NULL,
    gdrive_link TEXT,
    gofile_link TEXT,
    subtitle_style_used TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for video_outputs
CREATE INDEX IF NOT EXISTS idx_video_outputs_counter ON video_outputs(counter);
CREATE INDEX IF NOT EXISTS idx_video_outputs_chat_id ON video_outputs(chat_id);
CREATE INDEX IF NOT EXISTS idx_video_outputs_created_at ON video_outputs(created_at);

-- ============================================================================
-- Default Settings for Active Chats
-- ============================================================================

-- Insert default settings for Aman and Anu chats (if not exists)
INSERT INTO video_settings (chat_id, video_enabled, gdrive_image_folder_id)
VALUES
    ('-1002343932866', true, NULL),  -- IMAGE_SHORTS_CHAT_ID (Aman)
    ('-1002498893774', true, NULL)   -- IMAGE_LONG_CHAT_ID (Anu)
ON CONFLICT (chat_id) DO NOTHING;

-- ============================================================================
-- Helpful Queries
-- ============================================================================

-- Check video settings for all chats
-- SELECT * FROM video_settings ORDER BY created_at DESC;

-- Check recent video outputs
-- SELECT * FROM video_outputs ORDER BY created_at DESC LIMIT 10;

-- Get total videos generated
-- SELECT COUNT(*) as total_videos FROM video_outputs;

-- Get videos by chat
-- SELECT chat_id, COUNT(*) as video_count FROM video_outputs GROUP BY chat_id;

-- Delete old video logs (older than 30 days)
-- DELETE FROM video_outputs WHERE created_at < NOW() - INTERVAL '30 days';
