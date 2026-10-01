-- P0 · rate limits for unauthenticated auth endpoints (/auth/otp/request, /auth/otp/verify,
-- /auth/forgot-password) counted in the shared DB so they hold across instances/restarts.
-- key_hash = sha256 of the normalised IP / phone / email (no raw PII stored). Idempotent.

CREATE TABLE IF NOT EXISTS auth_rate_events (
  event_id   TEXT PRIMARY KEY,
  action     TEXT NOT NULL,
  scope      TEXT NOT NULL,
  key_hash   TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_auth_rate_lookup ON auth_rate_events(action, scope, key_hash, created_at);
