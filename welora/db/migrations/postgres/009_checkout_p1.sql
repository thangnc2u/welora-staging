-- Checkout VietQR P1 (PostgreSQL) · CK-11…CK-14 · mục 7 renewal · mục 8 refund · mục 9 admin 2FA
-- gate_months / Hard Deny / Pre-Rule / TARGET_MONTHS untouched. No secrets stored.

-- CK-14 upgrade credit + mục 8 refund bookkeeping on orders
ALTER TABLE orders ADD COLUMN upgrade_from_plan TEXT;
ALTER TABLE orders ADD COLUMN upgrade_credit BIGINT NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN refund_amount BIGINT NOT NULL DEFAULT 0;
ALTER TABLE orders ADD COLUMN refunded_at TEXT;

-- CK-11 coupons (validity, redemption count, applicable plans — server only)
CREATE TABLE IF NOT EXISTS coupons (
    code             TEXT PRIMARY KEY,
    kind             TEXT NOT NULL CHECK (kind IN ('percent','fixed')),
    value            BIGINT NOT NULL CHECK (value > 0),
    plans            TEXT NOT NULL DEFAULT '[]',
    cycles           TEXT NOT NULL DEFAULT '[]',
    starts_at        TEXT,
    ends_at          TEXT,
    max_redemptions  INTEGER,
    per_user_limit   INTEGER NOT NULL DEFAULT 1,
    active           INTEGER NOT NULL DEFAULT 1,
    created_by       TEXT,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coupon_redemptions (
    id               TEXT PRIMARY KEY,
    coupon_code      TEXT NOT NULL,
    order_id         TEXT NOT NULL UNIQUE,
    user_id          TEXT NOT NULL,
    discount         BIGINT NOT NULL DEFAULT 0,
    redeemed_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_coupon_redemptions_code ON coupon_redemptions(coupon_code);

-- CK-12 fixed A/B group per user
CREATE TABLE IF NOT EXISTS experiment_assignments (
    user_id          TEXT NOT NULL,
    experiment_key   TEXT NOT NULL,
    variant          TEXT NOT NULL,
    assigned_at      TEXT NOT NULL,
    PRIMARY KEY (user_id, experiment_key)
);

-- mục 7 renewal reminders (idempotent per subscription period + step)
CREATE TABLE IF NOT EXISTS renewal_reminders (
    id               TEXT PRIMARY KEY,
    subscription_id  TEXT NOT NULL,
    period_end       TEXT NOT NULL,
    step             TEXT NOT NULL,
    channels         TEXT NOT NULL DEFAULT '[]',
    status           TEXT NOT NULL DEFAULT 'sent',
    sent_at          TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_renewal_reminders_step
    ON renewal_reminders(subscription_id, period_end, step);

-- mục 7 one-tap renewal magic link (token stored hashed, 24h)
CREATE TABLE IF NOT EXISTS renewal_links (
    token_hash       TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    plan_id          TEXT NOT NULL,
    billing_cycle    TEXT NOT NULL,
    expires_at       TEXT NOT NULL,
    used_at          TEXT,
    created_at       TEXT NOT NULL
);

-- mục 9 admin 2FA (TOTP secrets live in env only; DB holds sessions + replay state)
CREATE TABLE IF NOT EXISTS admin_2fa_sessions (
    token_hash       TEXT PRIMARY KEY,
    user_id          TEXT NOT NULL,
    expires_at       TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS admin_totp_state (
    user_id          TEXT PRIMARY KEY,
    last_step        BIGINT NOT NULL DEFAULT 0,
    failed           INTEGER NOT NULL DEFAULT 0,
    locked_until     TEXT
);
