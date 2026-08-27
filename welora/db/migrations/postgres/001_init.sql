-- Welora P2-E1 · 001_init.sql (PostgreSQL)
-- Target months emergency fund = 3 (LOCKED)

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (now()::text)
);

CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    display_name  TEXT,
    device_id     TEXT,
    created_at    TEXT NOT NULL DEFAULT (now()::text),
    updated_at    TEXT NOT NULL DEFAULT (now()::text)
);

CREATE TABLE IF NOT EXISTS user_flags (
    user_id                   TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    has_dangerous_debt        INTEGER NOT NULL DEFAULT 0,
    debt_on_track             INTEGER NOT NULL DEFAULT 1,
    mastery_no_efund_invest   TEXT NOT NULL DEFAULT 'not_started',
    recent_violations         INTEGER NOT NULL DEFAULT 0,
    updated_at                TEXT NOT NULL DEFAULT (now()::text)
);

CREATE TABLE IF NOT EXISTS onboarding_sessions (
    session_id    TEXT PRIMARY KEY,
    user_id       TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    step          INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'in_progress',
    payload_json  TEXT NOT NULL DEFAULT '{}',
    created_at    TEXT NOT NULL DEFAULT (now()::text),
    updated_at    TEXT NOT NULL DEFAULT (now()::text),
    completed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_onboarding_user ON onboarding_sessions(user_id);

CREATE TABLE IF NOT EXISTS dna_profiles (
    user_id              TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    life_stage           TEXT,
    income_stability     TEXT,
    family_context       TEXT,
    essential_expense_monthly DOUBLE PRECISION,
    emergency_fund_months_self TEXT,
    has_dangerous_debt_self INTEGER DEFAULT 0,
    near_term_priority   TEXT,
    surplus_habit        TEXT,
    risk_tolerance       INTEGER,
    agent_role_preference TEXT,
    raw_json             TEXT NOT NULL DEFAULT '{}',
    created_at           TEXT NOT NULL DEFAULT (now()::text),
    updated_at           TEXT NOT NULL DEFAULT (now()::text)
);

CREATE TABLE IF NOT EXISTS constitutions (
    user_id          TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    version          TEXT NOT NULL DEFAULT '1.0',
    articles_json    TEXT NOT NULL DEFAULT '[]',
    custom_json      TEXT NOT NULL DEFAULT '[]',
    confirmed_at     TEXT,
    created_at       TEXT NOT NULL DEFAULT (now()::text),
    updated_at       TEXT NOT NULL DEFAULT (now()::text)
);

CREATE TABLE IF NOT EXISTS goals (
    goal_id              TEXT PRIMARY KEY,
    user_id              TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    type                 TEXT NOT NULL,
    subtype              TEXT,
    title                TEXT NOT NULL DEFAULT 'Quỹ khẩn cấp',
    status               TEXT NOT NULL DEFAULT 'active',
    priority             INTEGER NOT NULL DEFAULT 1,
    principle_keys_json  TEXT NOT NULL DEFAULT '[]',
    target_amount        DOUBLE PRECISION NOT NULL DEFAULT 0,
    target_unit          TEXT NOT NULL DEFAULT 'VND',
    months_of_expense    INTEGER NOT NULL DEFAULT 3,
    target_date          TEXT,
    current_amount       DOUBLE PRECISION NOT NULL DEFAULT 0,
    essential_expense_monthly DOUBLE PRECISION,
    safety_gate_relevant INTEGER NOT NULL DEFAULT 0,
    linked_from_onboarding INTEGER NOT NULL DEFAULT 0,
    plan_json            TEXT NOT NULL DEFAULT '{}',
    created_at           TEXT NOT NULL DEFAULT (now()::text),
    updated_at           TEXT NOT NULL DEFAULT (now()::text),
    completed_at         TEXT
);

CREATE INDEX IF NOT EXISTS idx_goals_user ON goals(user_id);
CREATE INDEX IF NOT EXISTS idx_goals_user_type_status ON goals(user_id, type, status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_emergency_fund
    ON goals(user_id) WHERE type = 'emergency_fund' AND status = 'active';

CREATE TABLE IF NOT EXISTS goal_history (
    id          SERIAL PRIMARY KEY,
    goal_id     TEXT NOT NULL REFERENCES goals(goal_id) ON DELETE CASCADE,
    at          TEXT NOT NULL DEFAULT (now()::text),
    amount      DOUBLE PRECISION NOT NULL,
    source      TEXT NOT NULL DEFAULT 'manual',
    note        TEXT
);

CREATE INDEX IF NOT EXISTS idx_goal_history_goal ON goal_history(goal_id);

CREATE TABLE IF NOT EXISTS mastery_nodes (
    user_id          TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    node_id          TEXT NOT NULL,
    state            TEXT NOT NULL DEFAULT 'not_started',
    principle_keys_json TEXT NOT NULL DEFAULT '[]',
    updated_at       TEXT NOT NULL DEFAULT (now()::text),
    PRIMARY KEY (user_id, node_id)
);

CREATE TABLE IF NOT EXISTS decision_logs (
    id                    TEXT PRIMARY KEY,
    user_id               TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    timestamp             TEXT NOT NULL DEFAULT (now()::text),
    user_query_summary    TEXT,
    context_snapshot_json TEXT NOT NULL DEFAULT '{}',
    rule_hit              TEXT,
    principle_keys_json   TEXT NOT NULL DEFAULT '[]',
    guardrail_result      TEXT NOT NULL,
    reason                TEXT,
    cta_offered_json      TEXT NOT NULL DEFAULT '[]',
    model_used            TEXT,
    raw_response_preview  TEXT
);

CREATE INDEX IF NOT EXISTS idx_decision_logs_user ON decision_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_decision_logs_ts ON decision_logs(timestamp);
