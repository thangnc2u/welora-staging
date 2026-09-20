"""P2 UAT — Khóa logic mâu thuẫn form (A–F)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.goals_api import (
    get_debt_flag_audit,
    reset_debt_flag_audit,
    service_create_goal,
    service_safety_gate,
    use_store,
)
from welora.mode_c_act import _PERSONAS, set_persona
from welora.onboarding import (
    complete_session,
    create_session,
    patch_step,
    reset_onboarding_stores,
)
from welora.onboarding_api import service_create_session, service_patch_step
from welora.personas import (
    DEBT_PRIORITY_CONFLICT_VI,
    EMERGENCY_FUND_MONTHS_RANGE_VI,
    OS_PERSONA_DNA_MISMATCH_VI,
    apply_debt_priority_lock,
    debt_cta_allowed,
    normalize_emergency_fund_months_self,
    validate_os_persona_matches_dna,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
ONBOARD = (ROOT / "welora" / "api" / "static" / "onboarding.html").read_text(encoding="utf-8")
DNA = (ROOT / "welora" / "api" / "static" / "dna.html").read_text(encoding="utf-8")
FORM_JS = (ROOT / "welora" / "api" / "static" / "form_locks.js").read_text(encoding="utf-8")
FC_JS = (ROOT / "welora" / "api" / "static" / "family_context.js").read_text(encoding="utf-8")


def _step1(sid: str) -> None:
    patch_step(
        sid,
        1,
        {
            "household": "solo",
            "income_stability": "stable",
            "family_context": "alone",
        },
    )


def _step3_4(sid: str) -> None:
    patch_step(
        sid,
        3,
        {
            "surplus_habit": "hold",
            "risk_tolerance": 3,
            "agent_role_preference": "advisor_only",
        },
    )
    patch_step(sid, 4, {})


class TestP2LockFormLogicConflicts(unittest.TestCase):
    def setUp(self) -> None:
        reset_onboarding_stores()
        reset_debt_flag_audit()
        _PERSONAS.clear()
        use_store(InMemoryEmergencyFundStore())
        self.client = TestClient(create_app())

    # --- A -----------------------------------------------------------------
    def test_a_helpers_matrix(self):
        ok = apply_debt_priority_lock(
            has_dangerous_debt_self=True, near_term_priority="debt"
        )
        self.assertTrue(ok["has_dangerous_debt_self"])
        self.assertEqual(ok["near_term_priority"], "debt")

        ok2 = apply_debt_priority_lock(
            has_dangerous_debt_self=True, near_term_priority=None
        )
        self.assertEqual(ok2["near_term_priority"], "debt")

        ok3 = apply_debt_priority_lock(
            has_dangerous_debt_self=False, near_term_priority="safety"
        )
        self.assertEqual(ok3["near_term_priority"], "safety")

        with self.assertRaises(ValueError) as cm:
            apply_debt_priority_lock(
                has_dangerous_debt_self=False, near_term_priority="debt"
            )
        self.assertEqual(str(cm.exception), DEBT_PRIORITY_CONFLICT_VI)
        self.assertTrue(debt_cta_allowed(True))
        self.assertFalse(debt_cta_allowed(False))

    def test_a_api_400_priority_debt_when_debt_false(self):
        code, sess = service_create_session({"user_id": "u-a-bad"})
        self.assertEqual(code, 201)
        sid = sess["session_id"]
        service_patch_step(
            sid,
            1,
            {
                "household": "solo",
                "income_stability": "stable",
                "family_context": "alone",
            },
        )
        c, body = service_patch_step(
            sid,
            2,
            {
                "essential_expense_monthly": 10_000_000,
                "emergency_fund_months_self": 0,
                "has_dangerous_debt_self": False,
                "near_term_priority": "debt",
            },
        )
        self.assertEqual(c, 400, body)
        err = body.get("error") or body.get("detail") or ""
        self.assertIn("nợ nguy hiểm", str(err))

        r = self.client.post("/onboarding/session", json={"user_id": "u-a-http"})
        sid2 = r.json()["session_id"]
        self.client.patch(
            f"/onboarding/session/{sid2}/step/1",
            json={
                "household": "solo",
                "income_stability": "stable",
                "family_context": "alone",
            },
        )
        r2 = self.client.patch(
            f"/onboarding/session/{sid2}/step/2",
            json={
                "essential_expense_monthly": 10_000_000,
                "emergency_fund_months_self": 1,
                "has_dangerous_debt_self": False,
                "near_term_priority": "debt",
            },
        )
        self.assertEqual(r2.status_code, 400)

    def test_a_debt_true_defaults_priority_and_cta(self):
        s = create_session("u-a-ok")
        _step1(s.session_id)
        patch_step(
            s.session_id,
            2,
            {
                "essential_expense_monthly": 10_000_000,
                "emergency_fund_months_self": 0,
                "has_dangerous_debt_self": True,
            },
        )
        self.assertEqual(s.steps[2]["near_term_priority"], "debt")
        _step3_4(s.session_id)
        out = complete_session(s.session_id)
        self.assertIsNotNone(out["debt_cta"])
        self.assertIn("nợ nguy hiểm", out["debt_cta"]["reason"])

    def test_a_no_cta_when_debt_false(self):
        s = create_session("u-a-safe")
        _step1(s.session_id)
        patch_step(
            s.session_id,
            2,
            {
                "essential_expense_monthly": 10_000_000,
                "emergency_fund_months_self": 0,
                "has_dangerous_debt_self": False,
                "near_term_priority": "safety",
            },
        )
        _step3_4(s.session_id)
        out = complete_session(s.session_id)
        self.assertIsNone(out["debt_cta"])

    def test_a_ui_hides_debt_priority_and_cta_gate(self):
        self.assertIn("form_locks.js", ONBOARD)
        self.assertIn("syncDebtPriorityLock", FORM_JS)
        self.assertIn("debtCtaAllowed", FORM_JS)
        self.assertIn("WeloraFormLocks.syncDebtPriorityLock", ONBOARD)
        self.assertIn("WeloraFormLocks.debtCtaAllowed", ONBOARD)

    # --- B -----------------------------------------------------------------
    def test_b_os_persona_must_match_dna(self):
        s = create_session("u-b")
        _step1(s.session_id)
        patch_step(
            s.session_id,
            2,
            {
                "essential_expense_monthly": 10_000_000,
                "emergency_fund_months_self": 0,
                "has_dangerous_debt_self": False,
                "near_term_priority": "safety",
            },
        )
        _step3_4(s.session_id)
        complete_session(s.session_id)

        code, body = set_persona(user_id="u-b", persona="P1")
        self.assertEqual(code, 200, body)
        code2, body2 = set_persona(user_id="u-b", persona="P4")
        self.assertEqual(code2, 400, body2)
        self.assertIn("khớp", body2["error"])

        with self.assertRaises(ValueError) as cm:
            validate_os_persona_matches_dna("P2", "P1")
        self.assertEqual(str(cm.exception), OS_PERSONA_DNA_MISMATCH_VI)

        r = self.client.post("/os/persona", json={"user_id": "u-b", "persona": "P3"})
        self.assertEqual(r.status_code, 400)

    # --- C -----------------------------------------------------------------
    def test_c_dna_debt_sync_audit_and_gate(self):
        s = create_session("u-c")
        _step1(s.session_id)
        patch_step(
            s.session_id,
            2,
            {
                "essential_expense_monthly": 10_000_000,
                "emergency_fund_months_self": 0,
                "has_dangerous_debt_self": True,
                "near_term_priority": "debt",
            },
        )
        _step3_4(s.session_id)
        complete_session(s.session_id)

        service_create_goal(
            {
                "user_id": "u-c",
                "type": "emergency_fund",
                "essential_expense_monthly": 10_000_000,
                "current_amount": 30_000_000,
            }
        )
        code, gate = service_safety_gate("u-c")
        self.assertEqual(code, 200)
        self.assertTrue(gate.get("has_dangerous_debt"))
        reasons = gate.get("reasons") or []
        self.assertTrue(
            any("dangerous_debt" in str(r) for r in reasons),
            reasons,
        )
        audit = get_debt_flag_audit("u-c")
        self.assertTrue(audit)
        self.assertTrue(audit[-1]["dna_has_dangerous_debt_self"])
        self.assertIn("dna", audit[-1]["source"])

    # --- D -----------------------------------------------------------------
    def test_d_months_range(self):
        for ok_v in (0, 1, 2, 3, 0.5, 1.5, "3"):
            self.assertEqual(
                normalize_emergency_fund_months_self(ok_v),
                float(ok_v),
            )
        for bad in (-1, 4, 99, "abc", None, ""):
            with self.assertRaises(ValueError) as cm:
                normalize_emergency_fund_months_self(bad)
            self.assertEqual(str(cm.exception), EMERGENCY_FUND_MONTHS_RANGE_VI)

        s = create_session("u-d")
        _step1(s.session_id)
        with self.assertRaises(ValueError):
            patch_step(
                s.session_id,
                2,
                {
                    "essential_expense_monthly": 10_000_000,
                    "emergency_fund_months_self": 99,
                    "has_dangerous_debt_self": False,
                    "near_term_priority": "safety",
                },
            )

        r = self.client.post("/onboarding/session", json={"user_id": "u-d-http"})
        sid = r.json()["session_id"]
        self.client.patch(
            f"/onboarding/session/{sid}/step/1",
            json={
                "household": "solo",
                "income_stability": "stable",
                "family_context": "alone",
            },
        )
        r2 = self.client.patch(
            f"/onboarding/session/{sid}/step/2",
            json={
                "essential_expense_monthly": 10_000_000,
                "emergency_fund_months_self": 99,
                "has_dangerous_debt_self": False,
                "near_term_priority": "safety",
            },
        )
        self.assertEqual(r2.status_code, 400)

    # --- E -----------------------------------------------------------------
    def test_e_copy_couple_vs_sandwich(self):
        self.assertNotIn("Nâng đỡ hai đầu", ONBOARD)
        self.assertNotIn("Nâng đỡ hai đầu", DNA)
        self.assertIn("Vợ chồng không con nhỏ", ONBOARD)
        self.assertIn("Vợ chồng không con nhỏ", DNA)
        self.assertIn("Ba đời", ONBOARD)
        self.assertIn("Ba đời", DNA)
        personas = (ROOT / "welora" / "personas.py").read_text(encoding="utf-8")
        self.assertIn(
            'label_vi": "35–59 Nâng đỡ hai đầu (không con nhỏ)"',
            personas,
        )
        self.assertIn(
            'label_vi": "35–59 Ba đời trên một take-home"',
            personas,
        )

    # --- F -----------------------------------------------------------------
    def test_f_regression_family_context_and_health(self):
        self.assertIn("ALLOWED", FC_JS)
        self.assertIn("solo", FC_JS)
        self.assertIn("syncFamilyContextLock", FC_JS)
        self.assertIn("family_context.js", ONBOARD)

        r = self.client.post("/onboarding/session", json={"user_id": "u-f"})
        sid = r.json()["session_id"]
        r2 = self.client.patch(
            f"/onboarding/session/{sid}/step/1",
            json={
                "household": "solo",
                "income_stability": "stable",
                "family_context": "with_family",
            },
        )
        self.assertEqual(r2.status_code, 400)

        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
