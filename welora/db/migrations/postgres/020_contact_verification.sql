-- Ticket "Xác minh OTP sau đăng ký + phone OTP gắn tài khoản có sẵn" (migration 020).
-- users.phone_verified_at  — set when the account proved it owns users.phone (verification OTP
--                            after register, or a phone-OTP login that attached to this account).
-- contact_verifications    — verification OTP challenges bound to ONE existing user_id (never
--                            creates an account): code stored hashed only, TTL, attempt counter,
--                            consumed 0 = open · 1 = used · 2 = superseded by a newer code.
-- Hard Deny / TARGET_MONTHS / gate_months / Pre-Rule / Lifetime / prices untouched.
-- Idempotent: safe to run twice (psql -f too). SQLite runs the same change as the Python data step
-- welora.contact_verify.apply_contact_verification_schema (no ADD COLUMN IF NOT EXISTS there); both
-- are recorded as version 020_contact_verification.

ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_verified_at TEXT;

CREATE TABLE IF NOT EXISTS contact_verifications (
    challenge_id  TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    channel       TEXT NOT NULL CHECK (channel IN ('email', 'phone')),
    target        TEXT NOT NULL,
    code_hash     TEXT NOT NULL,
    attempts      INTEGER NOT NULL DEFAULT 0,
    consumed      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL,
    expires_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contact_verif_user ON contact_verifications(user_id, created_at);
