-- NEW additive migration: run once before starting code with session attendance.
-- V1/V2/V3 are already installed. Do not rerun them.
-- Select the intended database in your SQL client before executing.
SELECT DATABASE() AS selected_database;

ALTER TABLE match_posts
  ADD COLUMN IF NOT EXISTS attendance_plan JSON NULL
  COMMENT 'Per-post snapshot: {user_ids:[registered IDs],guest_players:count}; NULL=legacy';

SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND table_name = 'match_posts'
  AND column_name = 'attendance_plan';
