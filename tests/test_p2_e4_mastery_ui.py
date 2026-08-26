"""P2-E4 — Mastery gate + API. Fund đủ + mastery < apply → not_passed."""

from __future__ import annotations

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.fixtures import reset_all_stores
from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.goals_api import use_store
from welora.mastery import reset_mastery_store, set_state
from welora.safety_gate import TARGET_MONTHS


class TestP2E4MasteryGate(unittest.TestCase):
    def setUp(self) -> None:
        use_store(InMemoryEmergencyFundStore())
        reset_all_stores()
        reset_mastery_store()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        use_store(InMemoryEmergencyFundStore())
        reset_all_stores()
        reset_mastery_store()

    def test_health_untouched(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["gate_months"], 3)
        self.assertTrue(body["hard_deny"])
        self.assertEqual(TARGET_MONTHS, 3)

    def test_safety_html_has_mastery_badge(self):
        html = Path("welora/api/static/safety.html").read_text(encoding="utf-8")
        self.assertIn("masteryBadge", html)
        self.assertIn("meets_gate", html)
        self.assertIn("SAFE-02", html)

    def test_fund_enough_familiar_not_passed(self):
        uid = "e4_familiar"
        self.client.post(
            "/goals",
            json={"user_id": uid, "essential_expense_monthly": 10_000_000, "current_amount": 30_000_000},
        )
        r = self.client.patch(f"/users/{uid}/mastery", json={"state": "familiar"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["state"], "familiar")
        self.assertFalse(r.json()["meets_gate"])
        gate = self.client.get(f"/users/{uid}/safety-gate").json()
        self.assertEqual(gate["status"], "not_passed")
        self.assertIn("mastery_missing", gate["reasons"])
        self.assertGreaterEqual(gate["months_covered"], 3)

    def test_fund_enough_apply_passed(self):
        uid = "e4_apply"
        self.client.post(
            "/goals",
            json={"user_id": uid, "essential_expense_monthly": 10_000_000, "current_amount": 30_000_000},
        )
        r = self.client.patch(f"/users/{uid}/mastery", json={"state": "apply"})
        self.assertTrue(r.json()["meets_gate"])
        gate = self.client.get(f"/users/{uid}/safety-gate").json()
        self.assertEqual(gate["status"], "passed")
        self.assertNotIn("mastery_missing", gate.get("reasons") or [])

    def test_score_does_not_pass_gate(self):
        uid = "e4_score"
        self.client.post(
            "/goals",
            json={"user_id": uid, "essential_expense_monthly": 10_000_000, "current_amount": 30_000_000},
        )
        set_state(uid, "learning")
        hs = self.client.get(f"/users/{uid}/health-score").json()
        self.assertIn("score", hs)
        gate = self.client.get(f"/users/{uid}/safety-gate").json()
        self.assertEqual(gate["status"], "not_passed")
        self.assertFalse(bool(hs.get("can_bypass") or hs.get("can_bypass_gate_with_score")))


if __name__ == "__main__":
    unittest.main()
