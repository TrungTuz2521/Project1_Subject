-- NEW additive migration (007): where a bank refund is sent.
-- A SePay webhook never says who sent a transfer, so customers fill in their own refund account.
-- Only ADD COLUMN on users, nothing is dropped or rewritten. Run ONCE before starting code with this change.
SELECT DATABASE() AS selected_database;

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS refund_bank_name VARCHAR(100) NULL COMMENT 'Bank of the refund account';
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS refund_account_no VARCHAR(30) NULL COMMENT 'Refund account number, digits only';
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS refund_account_name VARCHAR(100) NULL COMMENT 'Refund account holder name';

-- Verify: expect 3 rows.
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = DATABASE() AND table_name = 'users'
  AND column_name IN ('refund_bank_name', 'refund_account_no', 'refund_account_name')
ORDER BY column_name;
