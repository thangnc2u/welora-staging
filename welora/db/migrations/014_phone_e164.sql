-- P0 follow-up 2 · phone numbers stored in E.164 (+84…). The data step (welora/phone_migration.py,
-- version 014_phone_e164_data) normalises users.phone / otp_challenges.phone; rows whose normalised
-- value would collide with another account are NOT merged — they are left untouched and reported
-- here for manual review. Idempotent.

CREATE TABLE IF NOT EXISTS phone_e164_conflicts (
  id          TEXT PRIMARY KEY,
  table_name  TEXT NOT NULL,
  normalized  TEXT NOT NULL,
  user_ids    TEXT NOT NULL,
  raw_values  TEXT NOT NULL,
  detected_at TEXT NOT NULL
);
