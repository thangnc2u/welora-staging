-- WeloraOS P0 · Accounts CRUD (manual + soft-hide + consent)
-- gate_months / Hard Deny / CORE untouched

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS os_accounts (
    account_id   TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    type         TEXT NOT NULL,
    balance      REAL NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'manual',
    consent_ack  INTEGER NOT NULL DEFAULT 0,
    consent_at   TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    hidden_at    TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_os_accounts_user ON os_accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_os_accounts_user_status ON os_accounts(user_id, status);
