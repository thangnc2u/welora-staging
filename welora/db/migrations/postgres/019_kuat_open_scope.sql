-- Ticket "KUAT demo persona" (migration 019) · the open KUAT attempt of a shared demo persona
-- (P1–P6, public password) is kept per login session / client network instead of one per user +
-- node shared by every tester. scope_key = '' for every regular account, so those keep EXACTLY
-- one open attempt per user + node (same guarantee as 018); demo personas get one per scope
-- (welora.academy_store.attempt_scope). The new unique index is created BEFORE 018's index is
-- dropped, so uniqueness is enforced at every moment. Idempotent: safe to run twice (psql -f too).
-- SQLite runs the same change as the Python data step welora.academy_migration.apply_kuat_open_scope
-- (SQLite has no ADD COLUMN IF NOT EXISTS); both are recorded as version 019_kuat_open_scope.

ALTER TABLE academy_kuat_attempts ADD COLUMN IF NOT EXISTS scope_key TEXT NOT NULL DEFAULT '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_academy_kuat_open_scope
  ON academy_kuat_attempts(user_id, node_id, scope_key) WHERE used_at IS NULL;

DROP INDEX IF EXISTS uq_academy_kuat_open;
