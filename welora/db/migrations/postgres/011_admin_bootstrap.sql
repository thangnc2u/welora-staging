-- Checkout admin bootstrap (PostgreSQL) · WELORA_ADMIN_EMAILS (email OTP only) + auth audit
-- gate_months / Hard Deny / Pre-Rule / TARGET_MONTHS untouched. OTP codes stored hashed only.

ALTER TABLE users ADD COLUMN IF NOT EXISTS email_verified_at TEXT;

CREATE TABLE IF NOT EXISTS email_otp_challenges (
    challenge_id     TEXT PRIMARY KEY,
    email            TEXT NOT NULL,
    code_hash        TEXT NOT NULL,
    expires_at       TEXT NOT NULL,
    attempts         INTEGER NOT NULL DEFAULT 0,
    consumed         INTEGER NOT NULL DEFAULT 0,
    user_id          TEXT,
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_email_otp_email ON email_otp_challenges(email);

CREATE TABLE IF NOT EXISTS auth_audit (
    id               TEXT PRIMARY KEY,
    user_id          TEXT,
    action           TEXT NOT NULL,
    actor            TEXT NOT NULL,
    detail           TEXT NOT NULL DEFAULT '{}',
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_audit_user ON auth_audit(user_id);
