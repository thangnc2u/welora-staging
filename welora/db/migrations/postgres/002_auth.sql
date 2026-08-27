-- Welora P2-E1 · 002_auth.sql (PostgreSQL)

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_device_id
    ON users(device_id) WHERE device_id IS NOT NULL AND device_id != '';

CREATE TABLE IF NOT EXISTS auth_tokens (
    token         TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    device_id     TEXT,
    kind          TEXT NOT NULL DEFAULT 'device',
    created_at    TEXT NOT NULL DEFAULT (now()::text),
    expires_at    TEXT,
    revoked       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_auth_tokens_user ON auth_tokens(user_id);

CREATE TABLE IF NOT EXISTS otp_challenges (
    challenge_id  TEXT PRIMARY KEY,
    phone         TEXT NOT NULL,
    code          TEXT NOT NULL,
    user_id       TEXT REFERENCES users(user_id),
    attempts      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (now()::text),
    expires_at    TEXT NOT NULL,
    consumed      INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_otp_phone ON otp_challenges(phone);
