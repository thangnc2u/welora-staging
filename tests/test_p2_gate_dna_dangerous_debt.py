"""P2 — Safety gate honors DNA has_dangerous_debt_self (not only debt_payoff goals)."""

from __future__ import annotations

import os
import unittest

os.environ.setdefault("WELORA_STORE", "memory")

import welora.onboarding as ob
from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.safety_gate import TARGET_MONTHS, REASON_DEBT
from welora.goals_api import (
    USER_FLAGS,
    service_create_goal,
    service_progress,
    service_safety_gate,
    set_user_flags,
    use_store,
)


def reset() -> None:
    use_store(InMemoryEmergencyFundStore())
    USER_FLAGS.clear()
    ob.reset_onboarding_stores()


def _complete_onboarding(user_id: str, *, has_dangerous_debt_self: bool, essential: float = 10_000_000) -> dict:
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
            "emergency_fund_months_self": "0.5",
            "has_dangerous_debt_self": has_dangerous_debt_self,
            "near_term_priority": "safety",
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


def _efund_ready(user_id: str, *, essential: float = 10_000_000) -> None:
    service_create_goal(
        {
            "user_id": user_id,
            "essential_expense_monthly": essential,
            "current_amount": essential * TARGET_MONTHS,
        }
    )
    set_user_flags(user_id, mastery_no_efund_invest="apply")


class TestGateDnaDangerousDebt(unittest.TestCase):
    def setUp(self) -> None:
        reset()

    def test_1_dna_true_no_debt_goal_blocks_gate(self):
        """DNA true + no completed/on-track debt_payoff → not_passed + dangerous_debt_unhandled."""
        completed = _complete_onboarding("dna1", has_dangerous_debt_self=True)
        snap = completed["dna"]["financial_snapshot_self"]
        self.assertTrue(snap["has_dangerous_debt_self"])
        _efund_ready("dna1")

        code, gate = service_safety_gate("dna1")
        self.assertEqual(code, 200)
        self.assertEqual(gate["status"], "not_passed")
        self.assertIn(REASON_DEBT, gate["reasons"])
        self.assertIn("dangerous_debt_unhandled", gate["reasons"])
        self.assertTrue(gate["has_dangerous_debt"])
        self.assertFalse(gate["debt_on_track"])
        self.assertGreaterEqual(gate["months_covered"], TARGET_MONTHS)

    def test_2_dna_true_debt_active_insufficient_progress(self):
        """DNA true + debt_payoff active without progress → keep unhandled / debt_on_track=false."""
        _complete_onboarding("dna2", has_dangerous_debt_self=True)
        _efund_ready("dna2")
        service_create_goal(
            {"user_id": "dna2", "type": "debt_payoff", "target_amount": 8_000_000}
        )

        code, gate = service_safety_gate("dna2")
        self.assertEqual(code, 200)
        self.assertEqual(gate["status"], "not_passed")
        self.assertIn("dangerous_debt_unhandled", gate["reasons"])
        self.assertTrue(gate["has_dangerous_debt"])
        self.assertFalse(gate["debt_on_track"])

    def test_2b_dna_true_partial_progress_set_amount_1_not_passed(self):
        """DNA true + debt progress set_amount=1 (~0%) must NOT pass / clear unhandled."""
        _complete_onboarding("dna2b", has_dangerous_debt_self=True)
        _efund_ready("dna2b")
        _, debt = service_create_goal(
            {
                "user_id": "dna2b",
                "type": "debt_payoff",
                "target_amount": 8_000_000,
                "current_amount": 0,
            }
        )
        service_progress(debt["goal_id"], {"set_amount": 1})
        code, gate = service_safety_gate("dna2b")
        self.assertEqual(code, 200)
        self.assertEqual(gate["status"], "not_passed")
        self.assertIn("dangerous_debt_unhandled", gate["reasons"])
        self.assertTrue(gate["has_dangerous_debt"])
        self.assertFalse(gate["debt_on_track"])

    def test_3_dna_true_debt_completed_may_pass(self):
        """DNA true + debt_payoff completed + efund≥TARGET_MONTHS + mastery apply → may passed."""
        _complete_onboarding("dna3", has_dangerous_debt_self=True)
        _efund_ready("dna3")
        _, debt = service_create_goal(
            {
                "user_id": "dna3",
                "type": "debt_payoff",
                "target_amount": 8_000_000,
                "current_amount": 0,
            }
        )
        _, blocked = service_safety_gate("dna3")
        self.assertEqual(blocked["status"], "not_passed")
        self.assertIn("dangerous_debt_unhandled", blocked["reasons"])

        service_progress(debt["goal_id"], {"set_amount": 8_000_000})
        code, gate = service_safety_gate("dna3")
        self.assertEqual(code, 200)
        self.assertNotIn("dangerous_debt_unhandled", gate["reasons"])
        self.assertTrue(gate["debt_on_track"])
        self.assertEqual(gate["status"], "passed")
        self.assertGreaterEqual(gate["months_covered"], TARGET_MONTHS)

    def test_4_dna_false_unchanged_existing_behavior(self):
        """DNA false / no debt → gate can pass with efund + mastery alone (unchanged)."""
        completed = _complete_onboarding("dna4", has_dangerous_debt_self=False)
        self.assertFalse(completed["dna"]["financial_snapshot_self"]["has_dangerous_debt_self"])
        _efund_ready("dna4")

        code, gate = service_safety_gate("dna4")
        self.assertEqual(code, 200)
        self.assertEqual(gate["status"], "passed")
        self.assertNotIn("dangerous_debt_unhandled", gate["reasons"])
        self.assertFalse(gate["has_dangerous_debt"])
        self.assertTrue(gate["debt_on_track"])

    def test_no_auto_create_debt_from_near_term_priority(self):
        """Out of scope: DNA debt must not invent a debt_payoff goal."""
        _complete_onboarding("dna5", has_dangerous_debt_self=True)
        _efund_ready("dna5")
        from welora.goals_api import service_list_goals

        _, listed = service_list_goals("dna5", type="debt_payoff")
        self.assertEqual(listed["items"], [])
        _, gate = service_safety_gate("dna5")
        self.assertIn("dangerous_debt_unhandled", gate["reasons"])

    def test_target_months_and_reason_stable(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(REASON_DEBT, "dangerous_debt_unhandled")


if __name__ == "__main__":
    unittest.main()
