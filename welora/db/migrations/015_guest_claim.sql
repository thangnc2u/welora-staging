-- P0 follow-up 2 · guest → account claim (POST /auth/guest/claim). A claimed device-guest row keeps
-- its user_id (history / audit) but records which account took its data; the conditional
-- "WHERE claimed_by_user_id IS NULL" update makes the claim single-winner and idempotent.

ALTER TABLE users ADD COLUMN claimed_by_user_id TEXT;
ALTER TABLE users ADD COLUMN claimed_at TEXT;

CREATE INDEX IF NOT EXISTS idx_users_claimed_by ON users(claimed_by_user_id);
