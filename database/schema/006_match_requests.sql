-- NEW additive migration (006): matchmaking by request instead of public posts.
-- Run ONCE on the intended database BEFORE starting backend code that includes this change.
-- Only ADD COLUMN on match_posts, nothing is dropped or rewritten. Existing ENUMs are reused:
-- status OPEN = searching, MATCHED = paired, EXPIRED = nothing found in time, CANCELLED = withdrawn.
-- post_type FIND_OPPONENT = team looks for a team, RECRUIT_MEMBERS = team needs players for a game,
-- LOOK_FOR_TEAM = a player (with up to 2 friends) wants to join a game.
SELECT DATABASE() AS selected_database;

ALTER TABLE match_posts
  ADD COLUMN IF NOT EXISTS preferred_dates JSON NULL
  COMMENT 'List of YYYY-MM-DD (Vietnam) the requester can play, NULL when tied to a booking';
ALTER TABLE match_posts
  ADD COLUMN IF NOT EXISTS window_start CHAR(5) NULL COMMENT 'HH:MM earliest kick-off (Vietnam time)';
ALTER TABLE match_posts
  ADD COLUMN IF NOT EXISTS window_end CHAR(5) NULL COMMENT 'HH:MM latest finish (Vietnam time)';
ALTER TABLE match_posts
  ADD COLUMN IF NOT EXISTS skill_tolerance TINYINT UNSIGNED NULL
  COMMENT 'Accepted skill gap: 0 same level, 1 one level apart, 4 any level';
ALTER TABLE match_posts
  ADD COLUMN IF NOT EXISTS matched_post_id INT UNSIGNED NULL
  COMMENT 'LOOK_FOR_TEAM: the RECRUIT_MEMBERS request this player joined';

-- Verify: expect 5 rows.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'match_posts'
  AND column_name IN ('preferred_dates', 'window_start', 'window_end', 'skill_tolerance', 'matched_post_id')
ORDER BY column_name;
