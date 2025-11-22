-- Audio Queue System Schema
-- Similar to video_jobs but for audio generation tasks

-- ============================================================================
-- STEP 1: Create tables WITHOUT foreign key constraints (to avoid circular dependency)
-- ============================================================================

-- Audio Workers Table (create first, no dependencies)
CREATE TABLE IF NOT EXISTS audio_workers (
    worker_id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    gpu_model TEXT,
    status TEXT NOT NULL DEFAULT 'online', -- online, offline, busy
    last_heartbeat TIMESTAMPTZ DEFAULT NOW(),

    -- Statistics
    jobs_completed INTEGER DEFAULT 0,
    jobs_failed INTEGER DEFAULT 0,

    -- Worker metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    vastai_instance_id TEXT, -- Vast.ai instance identifier

    -- Performance tracking
    avg_processing_time_seconds REAL,
    current_job_id TEXT  -- Will add FK constraint later
);

-- Audio Jobs Table
CREATE TABLE IF NOT EXISTS audio_jobs (
    job_id TEXT PRIMARY KEY,
    chat_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', -- pending, processing, completed, failed

    -- Script information
    script_text TEXT NOT NULL,
    script_gdrive_id TEXT, -- Optional: if script is stored in GDrive

    -- Channel and video tracking (for daily video system)
    channel_code TEXT, -- BI, AFG, JIMMY, GYH, ANU, JM (nullable for non-daily videos)
    video_number INTEGER, -- 1-4 (nullable for non-daily videos)
    date DATE, -- For daily video tracking

    -- Audio generation metadata
    audio_counter INTEGER, -- Sequential counter for audio naming
    channel_shortform TEXT, -- For batch processing
    reference_audio_gdrive_id TEXT, -- Which reference audio to use

    -- Output
    audio_gdrive_id TEXT, -- Generated audio file in GDrive
    gofile_link TEXT, -- Optional Gofile upload link

    -- Processing metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    processing_started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    worker_id TEXT,  -- Will add FK constraint later

    -- Error handling
    retry_count INTEGER DEFAULT 0,
    error_message TEXT,

    -- Priority (higher number = higher priority)
    priority INTEGER DEFAULT 0
);

-- Reference Audio Sync Table
CREATE TABLE IF NOT EXISTS reference_audio_sync (
    id SERIAL PRIMARY KEY,
    gdrive_id TEXT NOT NULL UNIQUE,
    local_path TEXT,
    last_modified TIMESTAMPTZ NOT NULL,
    file_size_bytes BIGINT,

    -- Metadata
    uploaded_at TIMESTAMPTZ DEFAULT NOW(),
    last_synced_at TIMESTAMPTZ,
    is_current BOOLEAN DEFAULT TRUE, -- Only one reference audio should be current

    -- Tracking
    created_by TEXT, -- Chat ID that uploaded this reference
    checksum TEXT -- MD5 or SHA256 for integrity verification
);

-- ============================================================================
-- STEP 2: Add indexes for efficient querying
-- ============================================================================

-- Audio Jobs Indexes
CREATE INDEX IF NOT EXISTS idx_audio_jobs_status ON audio_jobs(status);
CREATE INDEX IF NOT EXISTS idx_audio_jobs_created_at ON audio_jobs(created_at);
CREATE INDEX IF NOT EXISTS idx_audio_jobs_priority ON audio_jobs(priority DESC, created_at ASC);
CREATE INDEX IF NOT EXISTS idx_audio_jobs_chat_id ON audio_jobs(chat_id);
CREATE INDEX IF NOT EXISTS idx_audio_jobs_date_channel ON audio_jobs(date, channel_code, video_number);
CREATE INDEX IF NOT EXISTS idx_audio_jobs_worker_id ON audio_jobs(worker_id);

-- Audio Workers Indexes
CREATE INDEX IF NOT EXISTS idx_audio_workers_status ON audio_workers(status);
CREATE INDEX IF NOT EXISTS idx_audio_workers_heartbeat ON audio_workers(last_heartbeat);
CREATE INDEX IF NOT EXISTS idx_audio_workers_current_job ON audio_workers(current_job_id);

-- Reference Audio Sync Indexes
CREATE INDEX IF NOT EXISTS idx_reference_audio_current ON reference_audio_sync(is_current) WHERE is_current = TRUE;
CREATE INDEX IF NOT EXISTS idx_reference_audio_modified ON reference_audio_sync(last_modified DESC);

-- ============================================================================
-- STEP 3: Add foreign key constraints (after tables exist)
-- ============================================================================

-- Add FK from audio_jobs to audio_workers
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_audio_jobs_worker'
    ) THEN
        ALTER TABLE audio_jobs
        ADD CONSTRAINT fk_audio_jobs_worker
        FOREIGN KEY (worker_id)
        REFERENCES audio_workers(worker_id)
        ON DELETE SET NULL;
    END IF;
END $$;

-- Add FK from audio_workers to audio_jobs
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'fk_audio_workers_current_job'
    ) THEN
        ALTER TABLE audio_workers
        ADD CONSTRAINT fk_audio_workers_current_job
        FOREIGN KEY (current_job_id)
        REFERENCES audio_jobs(job_id)
        ON DELETE SET NULL;
    END IF;
END $$;

-- ============================================================================
-- STEP 4: Functions and Triggers
-- ============================================================================

-- Function to automatically mark old reference audios as not current
CREATE OR REPLACE FUNCTION update_reference_audio_current()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_current = TRUE THEN
        UPDATE reference_audio_sync
        SET is_current = FALSE
        WHERE id != NEW.id AND is_current = TRUE;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to ensure only one current reference audio
DROP TRIGGER IF EXISTS trigger_update_reference_audio_current ON reference_audio_sync;
CREATE TRIGGER trigger_update_reference_audio_current
    BEFORE INSERT OR UPDATE ON reference_audio_sync
    FOR EACH ROW
    WHEN (NEW.is_current = TRUE)
    EXECUTE FUNCTION update_reference_audio_current();

-- Function to clean up old completed jobs (optional, run periodically)
CREATE OR REPLACE FUNCTION cleanup_old_audio_jobs(days_old INTEGER DEFAULT 30)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM audio_jobs
    WHERE status = 'completed'
    AND completed_at < NOW() - INTERVAL '1 day' * days_old;

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- Function to get pending jobs with priority
CREATE OR REPLACE FUNCTION get_pending_audio_jobs(limit_count INTEGER DEFAULT 10)
RETURNS TABLE (
    job_id TEXT,
    chat_id TEXT,
    script_text TEXT,
    channel_code TEXT,
    video_number INTEGER,
    audio_counter INTEGER,
    reference_audio_gdrive_id TEXT,
    created_at TIMESTAMPTZ,
    priority INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        aj.job_id,
        aj.chat_id,
        aj.script_text,
        aj.channel_code,
        aj.video_number,
        aj.audio_counter,
        aj.reference_audio_gdrive_id,
        aj.created_at,
        aj.priority
    FROM audio_jobs aj
    WHERE aj.status = 'pending'
    ORDER BY aj.priority DESC, aj.created_at ASC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- STEP 5: Comments for documentation
-- ============================================================================

COMMENT ON TABLE audio_jobs IS 'Queue table for audio generation tasks processed by Vast.ai workers';
COMMENT ON TABLE audio_workers IS 'Registry of active audio generation workers';
COMMENT ON TABLE reference_audio_sync IS 'Tracks reference audio files synced between Contabo and Vast.ai';

COMMENT ON COLUMN audio_jobs.job_id IS 'Unique identifier for the audio job (UUID format)';
COMMENT ON COLUMN audio_jobs.status IS 'Current status: pending, processing, completed, failed';
COMMENT ON COLUMN audio_jobs.script_text IS 'Full script text to be converted to audio';
COMMENT ON COLUMN audio_jobs.channel_code IS 'Channel identifier for daily video system (BI, AFG, etc.)';
COMMENT ON COLUMN audio_jobs.audio_counter IS 'Sequential counter for audio file naming';
COMMENT ON COLUMN audio_jobs.priority IS 'Job priority (higher number processed first)';

COMMENT ON COLUMN audio_workers.worker_id IS 'Unique worker identifier (hostname or UUID)';
COMMENT ON COLUMN audio_workers.last_heartbeat IS 'Last time worker reported being alive';
COMMENT ON COLUMN audio_workers.vastai_instance_id IS 'Vast.ai instance ID for tracking';

-- ============================================================================
-- SUCCESS!
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '✅ Audio queue schema created successfully!';
    RAISE NOTICE '📋 Tables created: audio_jobs, audio_workers, reference_audio_sync';
    RAISE NOTICE '🔗 Foreign keys added';
    RAISE NOTICE '📊 Indexes created';
    RAISE NOTICE '⚙️  Functions and triggers installed';
END $$;
