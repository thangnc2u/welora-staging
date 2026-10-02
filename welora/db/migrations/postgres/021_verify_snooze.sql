-- Ticket "GP follow-up sau OTP #244 + Academy #245", item 2 (migration 021).
-- users.verify_snooze_until — «Để sau» on the «Xác minh tài khoản» reminder, kept per user on the
--                              server (UTC ISO timestamp; the banner stays hidden until then — 24 h).
--                              NULL = not snoozed. Nothing else changes.
-- Hard Deny / TARGET_MONTHS / gate_months / Pre-Rule / Lifetime / prices untouched.
-- Idempotent: safe to run twice (psql -f too). SQLite runs the same change as the Python data step
-- welora.contact_verify.apply_verify_snooze_schema (no ADD COLUMN IF NOT EXISTS there); both are
-- recorded as version 021_verify_snooze.

ALTER TABLE users ADD COLUMN IF NOT EXISTS verify_snooze_until TEXT;
