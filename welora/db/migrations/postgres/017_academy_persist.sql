-- GP P0b · Academy progress persisted (survives restart / deploy / other instances) + server-held
-- KUAT attempts (the server knows exactly which questions / option order it served; an attempt is
-- single-use and expires). Per-question correctness is never stored. Idempotent.

CREATE TABLE IF NOT EXISTS academy_profiles (
  user_id      TEXT PRIMARY KEY,
  profile_json TEXT NOT NULL,
  rev          INTEGER NOT NULL DEFAULT 1,
  updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS academy_kuat_attempts (
  attempt_id  TEXT PRIMARY KEY,
  user_id     TEXT NOT NULL,
  node_id     TEXT NOT NULL,
  served_json TEXT NOT NULL,
  created_at  TEXT NOT NULL,
  expires_at  TEXT NOT NULL,
  used_at     TEXT,
  outcome     TEXT,
  score       REAL
);

CREATE INDEX IF NOT EXISTS idx_academy_kuat_user_node ON academy_kuat_attempts(user_id, node_id, created_at);
