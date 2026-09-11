"""P2 UAT — health-score DNA dangerous-debt flags parity with safety-gate."""

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
from welora.health_score import health_score_for_user


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


def _assert_gate_parity(test: unittest.TestCase, user_id: str) -> tuple[dict, dict]:
    """Embedded health-score.safety_gate must match dedicated /safety-gate debt fields."""
    _, gate = service_safety_gate(user_id)
    hs = health_score_for_user(user_id)
    emb = hs["safety_gate"]
    for key in ("status", "reasons", "has_dangerous_debt", "debt_on_track"):
        test.assertEqual(emb[key], gate[key], f"mismatch on {key}")
    return hs, gate


class TestHealthScoreDnaDebtParity(unittest.TestCase):
    def setUp(self) -> None:
        reset()

    def test_dna_only_no_debt_goal_debt_component_not_full(self):
        """DNA has_dangerous_debt_self + no on_track debt_payoff → debt flags + score < 250."""
        _complete_onboarding("hs-dna1", has_dangerous_debt_self=True)
        _efund_ready("hs-dna1")

        hs, gate = _assert_gate_parity(self, "hs-dna1")
        self.assertEqual(gate["status"], "not_passed")
        self.assertIn(REASON_DEBT, gate["reasons"])
        self.assertIn("dangerous_debt_unhandled", gate["reasons"])
        self.assertTrue(gate["has_dangerous_debt"])
        self.assertFalse(gate["debt_on_track"])

        debt = hs["components"]["debt"]
        self.assertTrue(debt["details"]["has_dangerous_debt"])
        self.assertFalse(debt["details"]["on_track"])
        self.assertLess(debt["score"], 250)

    def test_ef_only_no_dna_debt_parity_passed(self):
        """EF-only (DNA false, no debt goal) → gate may pass; debt component full 250."""
        _complete_onboarding("hs-ef1", has_dangerous_debt_self=False)
        _efund_ready("hs-ef1")

        hs, gate = _assert_gate_parity(self, "hs-ef1")
        self.assertEqual(gate["status"], "passed")
        self.assertNotIn("dangerous_debt_unhandled", gate["reasons"])
        self.assertFalse(gate["has_dangerous_debt"])
        self.assertTrue(gate["debt_on_track"])

        debt = hs["components"]["debt"]
        self.assertFalse(debt["details"]["has_dangerous_debt"])
        self.assertTrue(debt["details"]["on_track"])
        self.assertEqual(debt["score"], 250)

    def test_dna_plus_active_debt_payoff_unhandled_parity(self):
        """DNA true + active debt_payoff without completion → unhandled on both paths."""
        _complete_onboarding("hs-debt1", has_dangerous_debt_self=True)
        _efund_ready("hs-debt1")
        service_create_goal(
            {"user_id": "hs-debt1", "type": "debt_payoff", "target_amount": 8_000_000}
        )

        hs, gate = _assert_gate_parity(self, "hs-debt1")
        self.assertEqual(gate["status"], "not_passed")
        self.assertIn("dangerous_debt_unhandled", gate["reasons"])
        self.assertTrue(gate["has_dangerous_debt"])
        self.assertFalse(gate["debt_on_track"])

        debt = hs["components"]["debt"]
        self.assertTrue(debt["details"]["has_dangerous_debt"])
        self.assertFalse(debt["details"]["on_track"])
        self.assertLess(debt["score"], 250)

    def test_dna_debt_completed_clears_unhandled_parity(self):
        """DNA true + debt_payoff completed → debt_on_track; no dangerous_debt_unhandled."""
        _complete_onboarding("hs-debt2", has_dangerous_debt_self=True)
        _efund_ready("hs-debt2")
        _, debt_goal = service_create_goal(
            {
                "user_id": "hs-debt2",
                "type": "debt_payoff",
                "target_amount": 8_000_000,
                "current_amount": 0,
            }
        )
        service_progress(debt_goal["goal_id"], {"set_amount": 8_000_000})

        hs, gate = _assert_gate_parity(self, "hs-debt2")
        self.assertEqual(gate["status"], "passed")
        self.assertNotIn("dangerous_debt_unhandled", gate["reasons"])
        self.assertTrue(gate["debt_on_track"])

        debt = hs["components"]["debt"]
        self.assertTrue(debt["details"]["on_track"])

    def test_no_auto_create_debt_and_constraints(self):
        _complete_onboarding("hs-dna5", has_dangerous_debt_self=True)
        _efund_ready("hs-dna5")
        from welora.goals_api import service_list_goals

        _, listed = service_list_goals("hs-dna5", type="debt_payoff")
        self.assertEqual(listed["items"], [])
        hs, gate = _assert_gate_parity(self, "hs-dna5")
        self.assertIn("dangerous_debt_unhandled", gate["reasons"])
        self.assertFalse(hs.get("can_bypass_gate_with_score", True))
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(REASON_DEBT, "dangerous_debt_unhandled")


if __name__ == "__main__":
    unittest.main()
