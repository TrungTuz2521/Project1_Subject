-- READ ONLY. Select the intended database (test) in the SQL client first.
-- Review every result before running 003_contract_v3.sql.
SELECT DATABASE() AS selected_database, VERSION() AS server_version;

SELECT table_name, column_name, column_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = DATABASE()
  AND ((table_name = 'match_posts' AND column_name IN
       ('post_type','title','match_time','pitch_id','booking_id','pitch_type','end_time'))
    OR (table_name = 'bookings' AND column_name IN
       ('hold_expires_at','deposit_amount','payment_rule','payer_plan'))
    OR (table_name = 'matches' AND column_name IN ('status','proposal_id','confirmed_at'))
    OR (table_name = 'notifications' AND column_name = 'notification_type'))
ORDER BY table_name, ordinal_position;

SELECT table_name, table_type FROM information_schema.tables
WHERE table_schema = DATABASE()
  AND table_name IN ('match_posts','bookings','matches','notifications',
                    'pitches','match_proposals','proposal_confirmations');

-- Existing linked data that must be reviewed instead of blindly backfilled.
SELECT COUNT(*) AS posts_with_booking_time_mismatch
FROM match_posts p JOIN bookings b ON b.booking_id = p.booking_id
WHERE p.match_time IS NOT NULL AND p.match_time <> b.start_time;

SELECT COUNT(*) AS posts_with_booking_pitch_mismatch
FROM match_posts p JOIN bookings b ON b.booking_id = p.booking_id
WHERE p.pitch_id IS NOT NULL AND p.pitch_id <> b.pitch_id;

SELECT status, COUNT(*) AS total FROM bookings GROUP BY status;
SELECT status, COUNT(*) AS total FROM matches GROUP BY status;
SELECT notification_type, COUNT(*) AS total FROM notifications GROUP BY notification_type;
