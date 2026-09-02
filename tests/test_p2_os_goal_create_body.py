"""P2-OS-01b — GoalCreateBody HTTP debt_payoff vs emergency_fund."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("WELORA_STORE", "memory")

from fastapi.testclient import TestClient

from welora.api.app import GoalCreateBody, app
from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.goals_api import USER_FLAGS, use_store
from welora.safety_gate import TARGET_MONTHS


class TestGoalCreateBodyHttp(unittest.TestCase):
    def setUp(self) -> None:
        use_store(InMemoryEmergencyFundStore())
        USER_FLAGS.clear()
        self.client = TestClient(app)

    def test_model_has_optional_target_and_essential(self):
        fields = GoalCreateBody.model_fields
        self.assertIn("target_amount", fields)
        self.assertIn("essential_expense_monthly", fields)
        self.assertFalse(fields["target_amount"].is_required())
        self.assertFalse(fields["essential_expense_monthly"].is_required())

    def test_post_debt_payoff_without_essential_201(self):
        r = self.client.post(
            "/goals",
            json={
                "user_id": "os01b-debt",
                "type": "debt_payoff",
                "target_amount": 8_000_000,
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertEqual(body["type"], "debt_payoff")
        self.assertEqual(body["principle_keys"], ["DEBT-01", "DEBT-03", "CORE-07"])
        self.assertEqual(body["target"]["amount"], 8_000_000)
        self.assertTrue(body["safety_gate_relevant"])

    def test_post_emergency_fund_missing_essential_400(self):
        r = self.client.post(
            "/goals",
            json={"user_id": "os01b-ef", "type": "emergency_fund"},
        )
        self.assertEqual(r.status_code, 400, r.text)
        detail = r.json().get("detail") or ""
        self.assertIn("essential_expense_monthly", str(detail))

    def test_target_months_unchanged(self):
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
