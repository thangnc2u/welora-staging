-- GP P0b round 2 · at most ONE open (unused) KUAT attempt per user + node, enforced by the database:
-- a concurrent start gets the existing open attempt instead of a second one. Attempts left open by
-- the round-1 code are closed first (the learner simply gets a fresh attempt), and stored scores are
-- dropped (KUAT records keep pass / fail only). Idempotent.

UPDATE academy_kuat_attempts SET used_at = created_at, outcome = 'superseded' WHERE used_at IS NULL;

UPDATE academy_kuat_attempts SET score = NULL WHERE score IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_academy_kuat_open ON academy_kuat_attempts(user_id, node_id) WHERE used_at IS NULL;
