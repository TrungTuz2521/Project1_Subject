-- READ ONLY. Run AFTER the V3 migration, on the same selected database.
SELECT DATABASE() AS selected_database, VERSION() AS server_version;

SELECT expected.table_name, expected.column_name,
       CASE WHEN actual.column_name IS NULL THEN 'MISSING' ELSE 'PRESENT' END AS result,
       actual.column_type, actual.is_nullable, actual.column_default
FROM (
    SELECT 'match_posts' AS table_name, 'pitch_type' AS column_name
    UNION ALL SELECT 'match_posts', 'end_time'
    UNION ALL SELECT 'bookings', 'payment_rule'
    UNION ALL SELECT 'bookings', 'payer_plan'
    UNION ALL SELECT 'matches', 'status'
    UNION ALL SELECT 'notifications', 'notification_type'
) AS expected
LEFT JOIN information_schema.columns AS actual
  ON actual.table_schema = DATABASE()
 AND actual.table_name = expected.table_name
 AND actual.column_name = expected.column_name
ORDER BY expected.table_name, expected.column_name;

-- PASS: matches.status default SUGGESTED; all 15 notification ENUM members.
-- NULL historical values below are review items, not permission to invent data.
SELECT COUNT(*) AS posts_missing_matching_fields
FROM match_posts
WHERE pitch_type IS NULL OR match_time IS NULL OR end_time IS NULL;

SELECT COUNT(*) AS posts_with_invalid_interval
FROM match_posts WHERE end_time <= match_time;

SELECT pitch_type, COUNT(*) AS total FROM match_posts GROUP BY pitch_type;
SELECT COUNT(*) AS legacy_bookings_without_payer_plan
FROM bookings WHERE payment_rule IS NULL OR payer_plan IS NULL;

SELECT COUNT(*) AS v3_bookings_with_invalid_payer_plan
FROM bookings
WHERE payer_plan IS NOT NULL
  AND (JSON_TYPE(payer_plan) <> 'ARRAY' OR JSON_LENGTH(payer_plan) = 0);

SELECT payment_rule, COUNT(*) AS total FROM bookings GROUP BY payment_rule;
SELECT status, COUNT(*) AS total FROM matches GROUP BY status;
SELECT notification_type, COUNT(*) AS total FROM notifications GROUP BY notification_type;

SELECT table_name, table_type FROM information_schema.tables
WHERE table_schema = DATABASE() ORDER BY table_type, table_name;
