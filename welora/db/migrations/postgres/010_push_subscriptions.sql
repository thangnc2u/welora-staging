-- Checkout P1 follow-ups · PAY-05 renewal push (Web Push / VAPID subscriptions)
-- gate_months / Hard Deny / Pre-Rule / TARGET_MONTHS untouched. No secrets stored
-- (p256dh/auth are the browser's public subscription keys, not server secrets).

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id               TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    endpoint         TEXT NOT NULL UNIQUE,
    p256dh           TEXT NOT NULL,
    auth             TEXT NOT NULL,
    user_agent       TEXT,
    created_at       TEXT NOT NULL,
    last_success_at  TEXT,
    failures         INTEGER NOT NULL DEFAULT 0,
    disabled_at      TEXT
);

CREATE INDEX IF NOT EXISTS idx_push_subscriptions_user ON push_subscriptions(user_id);
