-- Project1 contract V3. Target: existing TiDB v8.5.3 database test AFTER V2.
-- AUTHORING ONLY: this file has NOT been executed or integration-tested on TiDB.
-- Run the separate preflight file and review a backup before applying this file.
-- Use a client that STOPS ON FIRST ERROR; execute numbered steps individually.
-- TiDB DDL is not one atomic transaction. ROLLBACK cannot undo these ALTERs.
-- Do not rerun V1/V2. Do not execute this file automatically at app startup.
-- IF NOT EXISTS avoids duplicate columns; it does NOT verify existing definitions.
-- Stop if preflight finds an existing V3 column with a conflicting definition.
-- Pause application/worker writes during application and validation.

USE `test`;
SET NAMES utf8mb4;
SET SESSION time_zone = '+00:00';

-- 1. Preserve historical rows: nullable additions, no fabricated defaults.
ALTER TABLE match_posts
  ADD COLUMN IF NOT EXISTS pitch_type VARCHAR(16) NULL DEFAULT NULL
  COMMENT 'Requested pitch type; new MVP posts accept PITCH_5 or PITCH_7';

ALTER TABLE match_posts
  ADD COLUMN IF NOT EXISTS end_time DATETIME NULL DEFAULT NULL
  COMMENT 'Requested end in UTC; new 90-minute posts calculated by backend';

ALTER TABLE bookings
  ADD COLUMN IF NOT EXISTS payment_rule VARCHAR(32) NULL DEFAULT NULL
  COMMENT 'New records: SPLIT_EQUAL for two teams, DIRECT_BOOKING for direct booking';

ALTER TABLE bookings
  ADD COLUMN IF NOT EXISTS payer_plan JSON NULL
  COMMENT 'Immutable deposit allocation [{user_id,amount}]; amounts are decimal strings';

-- 2. Default for FUTURE matches only. No UPDATE of existing match statuses.
-- New backend still sets SUGGESTED explicitly before collecting deposits.
ALTER TABLE matches ALTER COLUMN status SET DEFAULT 'SUGGESTED';

-- 3. Keep all seven existing ENUM members in their original order; APPEND only.
-- Avoid ENUM -> VARCHAR conversion. Validate this ALTER on a staging TiDB first.
-- If the existing ENUM is different from V2, STOP and reconcile; do not shrink it.
ALTER TABLE notifications MODIFY COLUMN notification_type
  ENUM('MATCH_PROPOSAL','PROPOSAL_ACCEPTED','PROPOSAL_REJECTED',
       'BOOKING_HOLD','BOOKING_CONFIRMED','PAYMENT_SUCCESS','TEAM_JOINED',
       'POST_EXPIRED','PROPOSAL_EXPIRED','MATCH_CONFIRMED','MATCH_CANCELLED',
       'BOOKING_EXPIRED','REFUND_PROCESSING','REFUND_SUCCESS','REFUND_FAILED')
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL;

-- 4. Backfill ONLY facts available from existing linked rows.
-- These two UPDATE statements are atomic together; DDL above remains separate.
-- Existing non-NULL values are never overwritten.
START TRANSACTION;

UPDATE match_posts AS p
JOIN pitches AS pitch ON pitch.pitch_id = p.pitch_id
SET p.pitch_type = pitch.pitch_type
WHERE p.pitch_type IS NULL;

UPDATE match_posts AS p
JOIN bookings AS b ON b.booking_id = p.booking_id
SET p.end_time = b.end_time
WHERE p.end_time IS NULL
  AND p.match_time = b.start_time
  AND b.end_time > b.start_time
  AND p.pitch_id = b.pitch_id;

COMMIT;

-- Do not guess missing historical times/types or payer allocations.
-- No changes to deposit_amount, total_amount, payment status, or user roles.
-- No DROP TABLE / DROP VIEW. The unused revenue-by-pitch view stays untouched.
-- No new refresh-token tables. No match-result/loser-pays schema.
-- Run 003_contract_v3_verify.sql next and review all reported anomalies.
