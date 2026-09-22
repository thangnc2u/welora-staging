-- WeloraOS P0 · Categories first-class (Fixed/Variable/Goals + tags)
-- gate_months / Hard Deny / CORE / Budget untouched

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS os_categories (
    category_id  TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL,
    tags_json    TEXT NOT NULL DEFAULT '[]',
    note         TEXT,
    status       TEXT NOT NULL DEFAULT 'active',
    disabled_at  TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_os_categories_user ON os_categories(user_id);
CREATE INDEX IF NOT EXISTS idx_os_categories_user_status ON os_categories(user_id, status);
CREATE INDEX IF NOT EXISTS idx_os_categories_user_kind ON os_categories(user_id, kind);
