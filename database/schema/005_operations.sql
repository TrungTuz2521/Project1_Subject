-- NEW additive migration (005): counter operations.
-- Run ONCE on the intended database BEFORE starting backend code that includes this change.
-- V1-V4 are already installed. Only ADD COLUMN, nothing is dropped or rewritten.
-- Select the intended database in your SQL client before executing.
SELECT DATABASE() AS selected_database;

-- Peak pricing: one peak price per pitch, the complex decides which hours are peak.
ALTER TABLE pitches
  ADD COLUMN IF NOT EXISTS peak_price_per_slot DECIMAL(12,2) NULL
  COMMENT 'Price of a slot inside peak hours, NULL = same as price_per_slot';

ALTER TABLE field_complexes
  ADD COLUMN IF NOT EXISTS peak_start_time CHAR(5) NULL COMMENT 'HH:MM local time, inclusive, NULL = no daily peak';
ALTER TABLE field_complexes
  ADD COLUMN IF NOT EXISTS peak_end_time CHAR(5) NULL COMMENT 'HH:MM local time, exclusive';
ALTER TABLE field_complexes
  ADD COLUMN IF NOT EXISTS weekend_is_peak TINYINT(1) NOT NULL DEFAULT 0 COMMENT '1 = Saturday and Sunday are peak all day';

-- Regular customers (same slot every week) and counter check-in.
ALTER TABLE bookings
  ADD COLUMN IF NOT EXISTS series_id VARCHAR(36) NULL COMMENT 'Shared by the weekly bookings created together';
ALTER TABLE bookings
  ADD COLUMN IF NOT EXISTS arrival_status VARCHAR(16) NULL COMMENT 'NULL | ARRIVED | NO_SHOW, set at the counter';
ALTER TABLE bookings
  ADD COLUMN IF NOT EXISTS arrived_at DATETIME NULL COMMENT 'UTC time the customer was checked in';
CREATE INDEX IF NOT EXISTS idx_bookings_series ON bookings (series_id);

-- Verify: expect 7 rows.
SELECT table_name, column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND ((table_name = 'pitches' AND column_name = 'peak_price_per_slot')
    OR (table_name = 'field_complexes' AND column_name IN ('peak_start_time', 'peak_end_time', 'weekend_is_peak'))
    OR (table_name = 'bookings' AND column_name IN ('series_id', 'arrival_status', 'arrived_at')))
ORDER BY table_name, column_name;
