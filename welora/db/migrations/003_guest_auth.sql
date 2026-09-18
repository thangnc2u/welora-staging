-- Welora P2 Auth · Guest/demo password auth (staging partner walkthrough)
-- Roles allowed: guest | demo only (fail-closed — never admin)

ALTER TABLE users ADD COLUMN email TEXT;
ALTER TABLE users ADD COLUMN phone TEXT;
ALTER TABLE users ADD COLUMN password_hash TEXT;
ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'guest';

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email
  ON users(email) WHERE email IS NOT NULL AND email != '';

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_phone
  ON users(phone) WHERE phone IS NOT NULL AND phone != '';

CREATE TABLE IF NOT EXISTS password_reset_tokens (
  token TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  consumed INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_pw_reset_user ON password_reset_tokens(user_id);
