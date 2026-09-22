-- WeloraOS P0 · Budget parity (avg 3–6 months / rollover / goal contrib) — PostgreSQL

CREATE TABLE IF NOT EXISTS os_budgets (
    user_id              TEXT NOT NULL,
    period               TEXT NOT NULL,
    status               TEXT NOT NULL DEFAULT 'applied',
    source               TEXT,
    lines_json           TEXT NOT NULL DEFAULT '[]',
    goal_contrib_json    TEXT NOT NULL DEFAULT '[]',
    total_outflow        DOUBLE PRECISION NOT NULL DEFAULT 0,
    months_used          INTEGER,
    window_months_json   TEXT,
    auto_overwrite       INTEGER NOT NULL DEFAULT 0,
    applied_at           TEXT,
    closed_at            TEXT,
    rolled_from          TEXT,
    created_at           TEXT NOT NULL DEFAULT (now()::text),
    updated_at           TEXT NOT NULL DEFAULT (now()::text),
    PRIMARY KEY (user_id, period),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_os_budgets_user ON os_budgets(user_id);
CREATE INDEX IF NOT EXISTS idx_os_budgets_user_status ON os_budgets(user_id, status);
