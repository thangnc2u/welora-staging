-- Checkout VietQR P0 · Phụ lục mục 6 — orders / payment_events / subscriptions
-- + checkout_admin_audit (CK-10 manual actions log)
-- gate_months / Hard Deny / Pre-Rule untouched

CREATE TABLE IF NOT EXISTS orders (
    id               TEXT PRIMARY KEY,
    order_code       INTEGER NOT NULL UNIQUE,
    user_id          TEXT NOT NULL,
    plan_id          TEXT NOT NULL,
    billing_cycle    TEXT NOT NULL CHECK (billing_cycle IN ('month','year')),
    list_price       INTEGER NOT NULL,
    discount         INTEGER NOT NULL DEFAULT 0,
    amount           INTEGER NOT NULL,
    coupon_code      TEXT,
    price_variant    TEXT,
    provider         TEXT NOT NULL DEFAULT 'payos',
    provider_link_id TEXT,
    checkout_url     TEXT,
    qr_code          TEXT,
    status           TEXT NOT NULL DEFAULT 'PENDING' CHECK (status IN
                       ('PENDING','PAID','UNDERPAID','CANCELLED','EXPIRED','REFUND_PENDING','REFUNDED')),
    expires_at       TEXT NOT NULL,
    paid_at          TEXT,
    amount_paid      INTEGER NOT NULL DEFAULT 0,
    is_preorder      INTEGER NOT NULL DEFAULT 0,
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
-- 1 PENDING per user per plan (mục 8)
CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_one_pending
    ON orders(user_id, plan_id) WHERE status = 'PENDING';

CREATE TABLE IF NOT EXISTS payment_events (
    id               TEXT PRIMARY KEY,
    order_id         TEXT,
    provider         TEXT NOT NULL,
    event_type       TEXT NOT NULL,
    provider_txn_ref TEXT NOT NULL UNIQUE,
    amount           INTEGER NOT NULL DEFAULT 0,
    raw_payload      TEXT NOT NULL,
    signature_valid  INTEGER NOT NULL DEFAULT 0,
    received_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_payment_events_order ON payment_events(order_id);

CREATE TABLE IF NOT EXISTS subscriptions (
    id                   TEXT PRIMARY KEY,
    user_id              TEXT NOT NULL,
    plan_id              TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','grace','expired')),
    current_period_start TEXT NOT NULL,
    current_period_end   TEXT NOT NULL,
    last_order_id        TEXT,
    members              TEXT NOT NULL DEFAULT '[]'
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_subscriptions_user_plan ON subscriptions(user_id, plan_id);

CREATE TABLE IF NOT EXISTS checkout_admin_audit (
    id            TEXT PRIMARY KEY,
    admin_user_id TEXT NOT NULL,
    action        TEXT NOT NULL,
    order_id      TEXT,
    order_code    INTEGER,
    reason        TEXT NOT NULL,
    detail        TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_checkout_admin_audit_order ON checkout_admin_audit(order_id);
