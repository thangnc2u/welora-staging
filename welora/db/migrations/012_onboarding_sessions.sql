-- P0 authz · onboarding sessions persisted on the shared DB (were in-process memory →
-- 201-then-404 when two instances overlap during a deploy; lost on restart).
-- Reuses onboarding_sessions from 001_init (step, status, payload_json = steps) and adds
-- the completed DNA / Personal Constitution JSON for durable reads.
-- gate_months / Hard Deny / Pre-Rule / TARGET_MONTHS untouched.

ALTER TABLE onboarding_sessions ADD COLUMN dna_id TEXT;
ALTER TABLE onboarding_sessions ADD COLUMN constitution_id TEXT;
ALTER TABLE onboarding_sessions ADD COLUMN dna_json TEXT;
ALTER TABLE onboarding_sessions ADD COLUMN constitution_json TEXT;

CREATE INDEX IF NOT EXISTS idx_onboarding_user_status ON onboarding_sessions(user_id, status, completed_at);
