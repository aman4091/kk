# 🚨 URGENT: Run This SQL in Supabase NOW

## Problem
Bot is failing with error:
```
Could not find the 'channel_code' column of 'video_jobs' in the schema cache
```

## Solution
Add 3 columns to `video_jobs` table

## Steps (2 minutes)

1. **Open Supabase Dashboard**
   - Go to: https://supabase.com/dashboard
   - Select your project: `zrczbdkighpnzenjdsbi`

2. **Open SQL Editor**
   - Click "SQL Editor" in left sidebar
   - Click "New Query"

3. **Copy-Paste This SQL**
```sql
ALTER TABLE video_jobs
    ADD COLUMN IF NOT EXISTS channel_code TEXT,
    ADD COLUMN IF NOT EXISTS video_number INTEGER,
    ADD COLUMN IF NOT EXISTS target_date DATE;

CREATE INDEX IF NOT EXISTS idx_video_jobs_daily_video
    ON video_jobs (target_date, channel_code, video_number);
```

4. **Click "Run" button**

5. **Verify**
   - Should see: "Success. No rows returned"
   - Go to "Table Editor" → "video_jobs"
   - Check that columns exist: `channel_code`, `video_number`, `target_date`

## Done!
Bot will work now. Video queue will accept metadata and local worker will organize videos.

---

**Full SQL with comments available at:** `sql/add_daily_video_columns.sql`
