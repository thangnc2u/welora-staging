"""P2 UX — onboarding debt priority → Goals focus=debt CTA (no auto debt_payoff)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

import welora.onboarding as ob
from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
ONBOARD = (ROOT / "welora" / "api" / "static" / "onboarding.html").read_text(encoding="utf-8")
GOALS = (ROOT / "welora" / "api" / "static" / "goals.html").read_text(encoding="utf-8")
SAFETY = (ROOT / "welora" / "api" / "static" / "safety.html").read_text(encoding="utf-8")


def _complete(
    user_id: str,
    *,
    near_term_priority: str,
    has_dangerous_debt_self: bool = False,
    essential: float = 10_000_000,
) -> dict:
    s = ob.create_session(user_id)
    ob.patch_step(
        s.session_id,
        1,
        {
            "life_stage": "young_single",
            "income_stability": "stable",
            "family_context": "alone",
        },
    )
    ob.patch_step(
        s.session_id,
        2,
        {
            "essential_expense_monthly": essential,
            "emergency_fund_months_self": "0",
            "has_dangerous_debt_self": has_dangerous_debt_self,
            "near_term_priority": near_term_priority,
        },
    )
    ob.patch_step(
        s.session_id,
        3,
        {
            "surplus_habit": "hold",
            "risk_tolerance": 3,
            "agent_role_preference": "advisor_only",
        },
    )
    ob.patch_step(s.session_id, 4, {})
    return ob.complete_session(s.session_id)


class TestP2UxOnboardingDebtCta(unittest.TestCase):
    def setUp(self) -> None:
        ob.reset_onboarding_stores()
        self.client = TestClient(create_app())

    def test_debt_priority_complete_has_debt_cta(self):
        out = _complete("u-debt", near_term_priority="debt", has_dangerous_debt_self=True)
        self.assertEqual(out["cta"]["code"], "create_emergency_fund_goal")
        self.assertEqual(out["cta_goal"]["type"], "emergency_fund")
        self.assertIsNotNone(out["debt_cta"])
        self.assertEqual(out["debt_cta"]["href"], "/app/goals?focus=debt")
        self.assertIn("nợ nguy hiểm", out["debt_cta"]["reason"])
        self.assertIn("trả nợ", out["debt_cta"]["reason"].lower())
        # Never auto-create: no target_amount / prefill for debt_payoff
        self.assertNotIn("prefill_body", out["debt_cta"])
        self.assertNotIn("target_amount", out["debt_cta"])

    def test_dangerous_debt_self_even_if_priority_safety(self):
        out = _complete(
            "u-dna-debt",
            near_term_priority="safety",
            has_dangerous_debt_self=True,
        )
        self.assertIsNotNone(out["debt_cta"])
        self.assertIn("focus=debt", out["debt_cta"]["href"])

    def test_safety_priority_no_debt_cta(self):
        out = _complete(
            "u-safety",
            near_term_priority="safety",
            has_dangerous_debt_self=False,
        )
        self.assertIsNone(out["debt_cta"])
        self.assertEqual(out["os_nudge"]["goal_type"], "emergency_fund")
        self.assertEqual(out["os_nudge"]["href"], "/app/goals")
        self.assertNotIn("focus=debt", out["os_nudge"]["href"])

    def test_onboarding_html_debt_redirect_path(self):
        self.assertIn("/app/goals?focus=debt", ONBOARD)
        self.assertIn("debt_cta", ONBOARD)
        self.assertIn("needsDebt", ONBOARD)
        self.assertIn("/app/safety?user_id=", ONBOARD)
        # Still creates efund; never POSTs debt_payoff from onboarding
        self.assertIn("type:'emergency_fund'", ONBOARD)
        self.assertNotIn("type:'debt_payoff'", ONBOARD)
        self.assertNotIn('type:"debt_payoff"', ONBOARD)
        self.assertIn("Bạn đã khai nợ nguy hiểm — tạo mục tiêu trả nợ", ONBOARD)

    def test_goals_html_focus_debt(self):
        self.assertIn('id="debtForm"', GOALS)
        self.assertIn('id="debtFocusBanner"', GOALS)
        self.assertIn("applyDebtFocus", GOALS)
        self.assertIn("focus", GOALS)
        self.assertIn("Bạn đã khai nợ nguy hiểm — tạo mục tiêu trả nợ", GOALS)

    def test_safety_debt_cta_synced(self):
        self.assertIn("/app/goals?focus=debt", SAFETY)
        self.assertIn("dangerous_debt_unhandled", SAFETY)
        self.assertNotIn('type:"debt_payoff"', SAFETY)

    def test_http_complete_debt_vs_safety(self):
        # debt priority
        r = self.client.post("/onboarding/session", json={"user_id": "http-debt"})
        sid = r.json()["session_id"]
        self.client.patch(
            f"/onboarding/session/{sid}/step/1",
            json={
                "life_stage": "young_single",
                "income_stability": "stable",
                "family_context": "alone",
            },
        )
        self.client.patch(
            f"/onboarding/session/{sid}/step/2",
            json={
                "essential_expense_monthly": 8_000_000,
                "has_dangerous_debt_self": True,
                "near_term_priority": "debt",
            },
        )
        done = self.client.post(f"/onboarding/session/{sid}/complete")
        self.assertEqual(done.status_code, 200)
        body = done.json()
        self.assertIn("focus=debt", body["debt_cta"]["href"])

        # safety priority
        r2 = self.client.post("/onboarding/session", json={"user_id": "http-safe"})
        sid2 = r2.json()["session_id"]
        self.client.patch(
            f"/onboarding/session/{sid2}/step/1",
            json={
                "life_stage": "young_single",
                "income_stability": "stable",
                "family_context": "alone",
            },
        )
        self.client.patch(
            f"/onboarding/session/{sid2}/step/2",
            json={
                "essential_expense_monthly": 8_000_000,
                "has_dangerous_debt_self": False,
                "near_term_priority": "safety",
            },
        )
        done2 = self.client.post(f"/onboarding/session/{sid2}/complete")
        self.assertEqual(done2.status_code, 200)
        body2 = done2.json()
        self.assertIsNone(body2["debt_cta"])

    def test_hard_constraints(self):
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        self.assertEqual(self.client.get("/app/onboarding").status_code, 200)
        self.assertEqual(self.client.get("/app/goals").status_code, 200)
        self.assertEqual(self.client.get("/app/safety").status_code, 200)


if __name__ == "__main__":
    unittest.main()
