-- WeloraOS P0 · Manual transactions + split — PostgreSQL

CREATE TABLE IF NOT EXISTS os_transactions (
    transaction_id TEXT PRIMARY KEY,
    user_id        TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    account_id     TEXT NOT NULL REFERENCES os_accounts(account_id) ON DELETE CASCADE,
    amount         DOUBLE PRECISION NOT NULL,
    category       TEXT NOT NULL,
    date           TEXT NOT NULL,
    note           TEXT,
    merchant       TEXT,
    source         TEXT NOT NULL DEFAULT 'manual',
    consent_ack    INTEGER NOT NULL DEFAULT 0,
    consent_at     TEXT,
    is_split       INTEGER NOT NULL DEFAULT 0,
    splits_json    TEXT NOT NULL DEFAULT '[]',
    status         TEXT NOT NULL DEFAULT 'active',
    hidden_at      TEXT,
    created_at     TEXT NOT NULL DEFAULT (now()::text),
    updated_at     TEXT NOT NULL DEFAULT (now()::text)
);

CREATE INDEX IF NOT EXISTS idx_os_tx_user ON os_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_os_tx_user_account ON os_transactions(user_id, account_id);
CREATE INDEX IF NOT EXISTS idx_os_tx_user_status ON os_transactions(user_id, status);
CREATE INDEX IF NOT EXISTS idx_os_tx_date ON os_transactions(date);
