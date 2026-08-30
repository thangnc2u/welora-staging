"""P2-OS-01 — Goal debt_payoff + Cổng dangerous_debt_unhandled."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("WELORA_STORE", "memory")

from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.safety_gate import TARGET_MONTHS
from welora import goals_api
from welora.goals_api import (
    USER_FLAGS,
    service_create_goal,
    service_list_goals,
    service_progress,
    service_safety_gate,
    set_user_flags,
    use_store,
)
from welora.health_score import health_score_for_user


def reset() -> None:
    use_store(InMemoryEmergencyFundStore())
    USER_FLAGS.clear()


class TestDebtPayoffGoal(unittest.TestCase):
    def setUp(self) -> None:
        reset()

    def test_create_debt_goal_keys(self):
        code, body = service_create_goal(
            {
                "user_id": "d1",
                "type": "debt_payoff",
                "target_amount": 20_000_000,
                "subtype": "credit_card",
            }
        )
        self.assertEqual(code, 201)
        self.assertEqual(body["type"], "debt_payoff")
        self.assertTrue(body["safety_gate_relevant"])
        self.assertEqual(body["principle_keys"], ["DEBT-01", "DEBT-03", "CORE-07"])
        self.assertEqual(body["target"]["amount"], 20_000_000)

    def test_list_keeps_emergency_and_debt(self):
        service_create_goal({"user_id": "d2", "essential_expense_monthly": 10_000_000})
        service_create_goal(
            {"user_id": "d2", "type": "debt_payoff", "target_amount": 5_000_000}
        )
        code, listed = service_list_goals("d2")
        self.assertEqual(code, 200)
        types = {i["type"] for i in listed["items"]}
        self.assertEqual(types, {"emergency_fund", "debt_payoff"})

    def test_gate_debt_unhandled_not_passed(self):
        service_create_goal(
            {
                "user_id": "d3",
                "essential_expense_monthly": 10_000_000,
                "current_amount": 30_000_000,
            }
        )
        set_user_flags("d3", mastery_no_efund_invest="apply")
        service_create_goal(
            {"user_id": "d3", "type": "debt_payoff", "target_amount": 8_000_000}
        )
        code, gate = service_safety_gate("d3")
        self.assertEqual(code, 200)
        self.assertEqual(gate["status"], "not_passed")
        self.assertIn("dangerous_debt_unhandled", gate["reasons"])
        self.assertTrue(gate["has_dangerous_debt"])
        self.assertFalse(gate["debt_on_track"])
        self.assertGreaterEqual(gate["months_covered"], TARGET_MONTHS)

    def test_gate_on_track_can_pass(self):
        service_create_goal(
            {
                "user_id": "d4",
                "essential_expense_monthly": 10_000_000,
                "current_amount": 30_000_000,
            }
        )
        set_user_flags("d4", mastery_no_efund_invest="apply")
        _, debt = service_create_goal(
            {
                "user_id": "d4",
                "type": "debt_payoff",
                "target_amount": 8_000_000,
                "monthly_contribution": 1_000_000,
                "plan_method": "avalanche",
            }
        )
        code, gate = service_safety_gate("d4")
        self.assertEqual(code, 200)
        self.assertNotIn("dangerous_debt_unhandled", gate["reasons"])
        self.assertTrue(gate["debt_on_track"])
        self.assertEqual(gate["status"], "passed")
        self.assertEqual(debt["principle_keys"], ["DEBT-01", "DEBT-03", "CORE-07"])

    def test_progress_then_on_track(self):
        service_create_goal(
            {
                "user_id": "d5",
                "essential_expense_monthly": 10_000_000,
                "current_amount": 30_000_000,
            }
        )
        set_user_flags("d5", mastery_no_efund_invest="apply")
        _, debt = service_create_goal(
            {"user_id": "d5", "type": "debt_payoff", "target_amount": 8_000_000}
        )
        _, unpaid = service_safety_gate("d5")
        self.assertEqual(unpaid["status"], "not_passed")
        service_progress(debt["goal_id"], {"add_amount": 500_000})
        _, paid = service_safety_gate("d5")
        self.assertTrue(paid["debt_on_track"])
        self.assertEqual(paid["status"], "passed")

    def test_health_score_does_not_bypass(self):
        service_create_goal(
            {
                "user_id": "d6",
                "essential_expense_monthly": 10_000_000,
                "current_amount": 30_000_000,
            }
        )
        set_user_flags("d6", mastery_no_efund_invest="apply")
        service_create_goal(
            {"user_id": "d6", "type": "debt_payoff", "target_amount": 8_000_000}
        )
        hs = health_score_for_user("d6")
        self.assertFalse(hs.get("can_bypass_gate_with_score", True))
        self.assertEqual(hs["safety_gate"]["status"], "not_passed")

    def test_target_months_unchanged(self):
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
