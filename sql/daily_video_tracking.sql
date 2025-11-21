-- Daily Video Tracking System
-- Tracks videos being produced for each channel (BI, AFG, JIMMY, GYH, ANU, JM)
-- Each channel can have up to 4 videos per day

-- Main tracking table
CREATE TABLE IF NOT EXISTS daily_video_tracking (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  date DATE NOT NULL,
  channel_code TEXT NOT NULL,  -- BI, AFG, JIMMY, GYH, ANU, JM
  video_number INT NOT NULL CHECK (video_number BETWEEN 1 AND 4),
  script_text TEXT,
  script_gdrive_id TEXT,
  audio_gdrive_id TEXT,
  video_gdrive_id TEXT,
  thumbnail_gdrive_id TEXT,
  organized_folder_id TEXT,    -- GDrive folder ID for date/channel/video_X structure
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'audio_done', 'video_done', 'complete', 'deleted')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  UNIQUE(date, channel_code, video_number)
);

-- Thumbnail queue table
CREATE TABLE IF NOT EXISTS thumbnail_queue (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  telegram_file_id TEXT NOT NULL,
  telegram_file_unique_id TEXT,
  channel_code TEXT NOT NULL,
  video_number INT NOT NULL CHECK (video_number BETWEEN 1 AND 4),
  target_date DATE,  -- NULL initially, assigned when matched with video
  processed BOOLEAN DEFAULT FALSE,
  gdrive_file_id TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  processed_at TIMESTAMPTZ
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_tracking_date_channel ON daily_video_tracking(date, channel_code);
CREATE INDEX IF NOT EXISTS idx_tracking_status ON daily_video_tracking(status);
CREATE INDEX IF NOT EXISTS idx_tracking_date_status ON daily_video_tracking(date, status);
CREATE INDEX IF NOT EXISTS idx_thumbnail_processed ON thumbnail_queue(processed);
CREATE INDEX IF NOT EXISTS idx_thumbnail_channel_video ON thumbnail_queue(channel_code, video_number);

-- Function to get next available video number for a channel on a date
CREATE OR REPLACE FUNCTION get_next_video_number(p_date DATE, p_channel TEXT)
RETURNS INT AS $$
DECLARE
  next_num INT;
BEGIN
  SELECT COALESCE(MAX(video_number), 0) + 1 INTO next_num
  FROM daily_video_tracking
  WHERE date = p_date AND channel_code = p_channel;

  RETURN next_num;
END;
$$ LANGUAGE plpgsql;

-- Function to check if all videos complete for a date
CREATE OR REPLACE FUNCTION get_date_completion_status(p_date DATE)
RETURNS TABLE(
  total_videos INT,
  completed_videos INT,
  pending_videos INT,
  completion_percentage NUMERIC
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    COUNT(*)::INT as total_videos,
    COUNT(*) FILTER (WHERE status = 'complete')::INT as completed_videos,
    COUNT(*) FILTER (WHERE status != 'complete')::INT as pending_videos,
    ROUND((COUNT(*) FILTER (WHERE status = 'complete')::NUMERIC / NULLIF(COUNT(*), 0)) * 100, 2) as completion_percentage
  FROM daily_video_tracking
  WHERE date = p_date;
END;
$$ LANGUAGE plpgsql;

-- View for monitoring incomplete videos
CREATE OR REPLACE VIEW incomplete_videos AS
SELECT
  date,
  channel_code,
  video_number,
  status,
  CASE
    WHEN script_gdrive_id IS NULL THEN 'Script missing'
    WHEN audio_gdrive_id IS NULL THEN 'Audio pending'
    WHEN video_gdrive_id IS NULL THEN 'Video pending'
    WHEN thumbnail_gdrive_id IS NULL THEN 'Thumbnail missing'
    ELSE 'Unknown'
  END as missing_item,
  created_at,
  NOW() - created_at as age
FROM daily_video_tracking
WHERE status != 'complete' AND status != 'deleted'
ORDER BY date DESC, channel_code, video_number;

-- Comments
COMMENT ON TABLE daily_video_tracking IS 'Tracks daily video production for 6 channels (BI, AFG, JIMMY, GYH, ANU, JM), 4 videos per channel';
COMMENT ON TABLE thumbnail_queue IS 'Queue for thumbnail images sent via Telegram before/after video creation';
COMMENT ON COLUMN daily_video_tracking.organized_folder_id IS 'Google Drive folder ID following structure: date/channel/video_X/';
COMMENT ON COLUMN daily_video_tracking.status IS 'pending → audio_done → video_done → complete (when thumbnail added)';
