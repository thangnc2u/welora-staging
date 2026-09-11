"""P2 UAT — Cổng Safety #debtCard hide (Home #177 showDebt parity)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
SAFETY = (STATIC / "safety.html").read_text(encoding="utf-8")
HOME = (STATIC / "home.html").read_text(encoding="utf-8")


class TestP2UatCongSafetyDebtCard(unittest.TestCase):
    def test_debt_card_hidden_by_default_ef_only(self):
        self.assertIn('id="debtCard" hidden', SAFETY)
        self.assertIn("showDebt", SAFETY)
        self.assertIn("debtCard.hidden=!showDebt", SAFETY)
        # EF-only / no debt signal → stays hidden
        self.assertIn("has_dangerous_debt", SAFETY)
        self.assertIn("dangerous_debt_unhandled", SAFETY)
        self.assertIn("type=debt_payoff", SAFETY)

    def test_show_debt_parity_with_home_177(self):
        # same showDebt predicate shape as Home #177
        self.assertIn(
            "showDebt=!!(gate.has_dangerous_debt || gateReasons.indexOf('dangerous_debt_unhandled')>=0 || state.debt)",
            SAFETY,
        )
        self.assertIn(
            "showDebt=!!(gate.has_dangerous_debt || reasons.indexOf('dangerous_debt_unhandled')>=0 || debt)",
            HOME,
        )
        # never auto-create debt from Safety
        self.assertNotIn('type:"debt_payoff"', SAFETY)
        self.assertIn('type:"emergency_fund"', SAFETY)

    def test_dna_no_goal_vs_active_goal_branches(self):
        # DNA / no debt goal → create CTA
        self.assertIn(
            'link.textContent="Bạn đã khai nợ nguy hiểm — tạo mục tiêu trả nợ"',
            SAFETY,
        )
        self.assertIn("/app/goals?focus=debt", SAFETY)
        # Active goal → paid/target · % + open CTA
        self.assertIn('link.textContent="Mở Mục tiêu · Trả nợ"', SAFETY)
        self.assertIn("state.debt.current", SAFETY)
        self.assertIn("state.debt.target", SAFETY)
        self.assertIn("if(state.debt){", SAFETY)

    def test_checklist_debt_cta_by_goal(self):
        # Checklist row CTA mirrors card: create only when no goal
        self.assertIn(
            "ctaText: state.debt ? 'Mở Mục tiêu · Trả nợ' : 'Tạo mục tiêu trả nợ'",
            SAFETY,
        )
        self.assertIn("Tạo mục tiêu trả nợ", SAFETY)
        self.assertIn("Mở Mục tiêu · Trả nợ", SAFETY)
        # row still gated on debt signal
        self.assertIn("dangerous_debt_unhandled", SAFETY)
        self.assertIn("has_dangerous_debt", SAFETY)

    def test_app_safety_200_spotcheck(self):
        r = TestClient(create_app()).get("/app/safety")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('id="debtCard" hidden', body)
        self.assertIn("showDebt", body)
        self.assertIn("Bạn đã khai nợ nguy hiểm — tạo mục tiêu trả nợ", body)
        self.assertIn("Mở Mục tiêu · Trả nợ", body)
        self.assertIn("type=debt_payoff", body)

    def test_hard_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        # mastery GATE_NODE still on Safety (not reopened/regressed)
        self.assertIn("no_efund_invest", SAFETY)
        self.assertIn("masteryState", SAFETY)


if __name__ == "__main__":
    unittest.main()
