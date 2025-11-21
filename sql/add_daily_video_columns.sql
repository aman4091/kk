-- ============================================================================
-- ADD DAILY VIDEO METADATA COLUMNS TO video_jobs TABLE
-- ============================================================================
-- Purpose: Support daily video organization system
-- Date: 2025-11-21
-- ============================================================================

-- Add optional columns for daily video tracking
-- These are used by local worker to organize videos after generation

ALTER TABLE video_jobs
    ADD COLUMN IF NOT EXISTS channel_code TEXT,
    ADD COLUMN IF NOT EXISTS video_number INTEGER,
    ADD COLUMN IF NOT EXISTS target_date DATE;

-- Add index for daily video queries
CREATE INDEX IF NOT EXISTS idx_video_jobs_daily_video
    ON video_jobs (target_date, channel_code, video_number);

-- Add comment for documentation
COMMENT ON COLUMN video_jobs.channel_code IS 'Channel identifier (BI, AFG, JIMMY, GYH, ANU, JM) - optional for daily videos';
COMMENT ON COLUMN video_jobs.video_number IS 'Video number within channel (1-4) - optional for daily videos';
COMMENT ON COLUMN video_jobs.target_date IS 'Target date for daily folder organization - optional for daily videos';

-- ============================================================================
-- VERIFICATION QUERY
-- ============================================================================
-- Run this to verify columns were added:
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'video_jobs'
-- AND column_name IN ('channel_code', 'video_number', 'target_date');

-- ============================================================================
-- DONE!
-- ============================================================================
