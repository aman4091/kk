-- ============================================================================
-- DROP EXISTING AUDIO QUEUE TABLES
-- Run this FIRST before running the main schema
-- ============================================================================

-- Drop foreign key constraints first
DO $$
BEGIN
    -- Drop FK from audio_jobs
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_audio_jobs_worker'
    ) THEN
        ALTER TABLE audio_jobs DROP CONSTRAINT fk_audio_jobs_worker;
    END IF;

    -- Drop FK from audio_workers
    IF EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_audio_workers_current_job'
    ) THEN
        ALTER TABLE audio_workers DROP CONSTRAINT fk_audio_workers_current_job;
    END IF;
END $$;

-- Drop tables (in reverse order of dependencies)
DROP TABLE IF EXISTS audio_jobs CASCADE;
DROP TABLE IF EXISTS audio_workers CASCADE;
DROP TABLE IF EXISTS reference_audio_sync CASCADE;

-- Drop functions
DROP FUNCTION IF EXISTS update_reference_audio_current() CASCADE;
DROP FUNCTION IF EXISTS cleanup_old_audio_jobs(INTEGER) CASCADE;
DROP FUNCTION IF EXISTS get_pending_audio_jobs(INTEGER) CASCADE;

-- Success message
DO $$
BEGIN
    RAISE NOTICE '✅ All audio queue tables, constraints, and functions dropped successfully!';
    RAISE NOTICE '📋 Now run supabase_audio_queue_schema.sql to create fresh tables';
END $$;
