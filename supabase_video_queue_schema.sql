-- ============================================================================
-- VIDEO JOB QUEUE SYSTEM - Supabase Schema
-- ============================================================================
-- Purpose: Distributed video encoding between Cloud (Vast.ai) and Local PC
-- Author: Claude Code
-- Date: 2025-11-17
-- ============================================================================

-- ============================================================================
-- TABLE 1: video_jobs (Job Queue)
-- ============================================================================

CREATE TABLE IF NOT EXISTS video_jobs (
    -- Primary identification
    job_id TEXT PRIMARY KEY,  -- Counter number (e.g., "12345")
    chat_id TEXT NOT NULL,    -- Telegram chat ID

    -- Job status
    status TEXT NOT NULL CHECK (status IN ('pending', 'processing', 'completed', 'failed')) DEFAULT 'pending',

    -- Google Drive file IDs
    audio_gdrive_id TEXT NOT NULL,     -- Audio file in GDrive queue folder
    image_gdrive_id TEXT NOT NULL,     -- Image file in GDrive queue folder
    subtitle_style TEXT NOT NULL,      -- ASS subtitle style string
    video_gdrive_id TEXT,               -- Video file (filled after completion)
    video_gofile_link TEXT,             -- Gofile upload link

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processing_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,

    -- Worker tracking
    worker_id TEXT,                     -- Which PC processed this job
    retry_count INTEGER DEFAULT 0,      -- Number of retry attempts
    error_message TEXT,                 -- Error details if failed

    -- Priority (higher = process first)
    priority INTEGER DEFAULT 0
);

-- Index for fast queue lookups (pending jobs sorted by priority)
CREATE INDEX IF NOT EXISTS idx_video_jobs_status_priority
    ON video_jobs (status, priority DESC, created_at ASC);

-- Index for chat_id lookups
CREATE INDEX IF NOT EXISTS idx_video_jobs_chat_id
    ON video_jobs (chat_id);

-- ============================================================================
-- TABLE 2: video_workers (Worker Status Tracking)
-- ============================================================================

CREATE TABLE IF NOT EXISTS video_workers (
    -- Worker identification
    worker_id TEXT PRIMARY KEY,         -- e.g., "DESKTOP-ABC123_RTX4060"
    hostname TEXT,                      -- Computer name
    gpu_model TEXT,                     -- e.g., "RTX 4060"

    -- Status
    status TEXT CHECK (status IN ('online', 'offline', 'busy')) DEFAULT 'offline',
    last_heartbeat TIMESTAMPTZ DEFAULT NOW(),

    -- Statistics
    jobs_completed INTEGER DEFAULT 0,
    jobs_failed INTEGER DEFAULT 0,
    total_encoding_time_minutes INTEGER DEFAULT 0,

    -- System info
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================================
-- HELPER FUNCTIONS (Optional but useful)
-- ============================================================================

-- Function to get next pending job (ordered by priority)
CREATE OR REPLACE FUNCTION get_next_pending_job()
RETURNS SETOF video_jobs
LANGUAGE sql
AS $$
    SELECT * FROM video_jobs
    WHERE status = 'pending'
    ORDER BY priority DESC, created_at ASC
    LIMIT 1;
$$;

-- Function to mark worker as online
CREATE OR REPLACE FUNCTION worker_heartbeat(p_worker_id TEXT)
RETURNS VOID
LANGUAGE sql
AS $$
    INSERT INTO video_workers (worker_id, status, last_heartbeat)
    VALUES (p_worker_id, 'online', NOW())
    ON CONFLICT (worker_id)
    DO UPDATE SET
        status = 'online',
        last_heartbeat = NOW();
$$;

-- ============================================================================
-- ROW LEVEL SECURITY (Optional - enable if needed)
-- ============================================================================

-- Disable RLS for now (since bot uses service role key)
ALTER TABLE video_jobs DISABLE ROW LEVEL SECURITY;
ALTER TABLE video_workers DISABLE ROW LEVEL SECURITY;

-- If you want to enable RLS later:
-- ALTER TABLE video_jobs ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY "Allow all operations" ON video_jobs FOR ALL USING (true);

-- ============================================================================
-- SAMPLE DATA (For testing)
-- ============================================================================

-- Insert test job (uncomment to test)
-- INSERT INTO video_jobs (
--     job_id, chat_id, status,
--     audio_gdrive_id, image_gdrive_id, subtitle_style
-- ) VALUES (
--     'test_001',
--     '447705580',
--     'pending',
--     '1abc123_test_audio',
--     '1def456_test_image',
--     'Fontname=Arial,Fontsize=48,PrimaryColour=&H00FFFFFF'
-- );

-- ============================================================================
-- USEFUL QUERIES
-- ============================================================================

-- Get queue summary
-- SELECT status, COUNT(*) as count, AVG(retry_count) as avg_retries
-- FROM video_jobs
-- GROUP BY status;

-- Get pending jobs count
-- SELECT COUNT(*) FROM video_jobs WHERE status = 'pending';

-- Get worker status
-- SELECT worker_id, status, last_heartbeat, jobs_completed, jobs_failed
-- FROM video_workers
-- ORDER BY last_heartbeat DESC;

-- Get failed jobs
-- SELECT job_id, error_message, retry_count, created_at
-- FROM video_jobs
-- WHERE status = 'failed'
-- ORDER BY created_at DESC;

-- Get processing time stats (completed jobs)
-- SELECT
--     job_id,
--     EXTRACT(EPOCH FROM (completed_at - processing_started_at)) / 60 as duration_minutes
-- FROM video_jobs
-- WHERE status = 'completed'
-- ORDER BY duration_minutes DESC
-- LIMIT 10;

-- ============================================================================
-- DONE!
-- ============================================================================
-- Next steps:
-- 1. Run this SQL in Supabase SQL Editor
-- 2. Verify tables created: Check "Table Editor" tab
-- 3. Test with sample insert (uncomment SAMPLE DATA section)
-- ============================================================================
