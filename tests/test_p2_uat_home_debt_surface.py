"""P2 UAT — Home surface nợ / debt_payoff (Safety #debtCard parity)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
HOME = (STATIC / "home.html").read_text(encoding="utf-8")
SAFETY = (STATIC / "safety.html").read_text(encoding="utf-8")


class TestP2UatHomeDebtSurface(unittest.TestCase):
    def test_home_has_compact_debt_card_parity_copy(self):
        self.assertIn('id="debtCard"', HOME)
        self.assertIn('id="debtTitle"', HOME)
        self.assertIn('id="debtMeta"', HOME)
        self.assertIn('id="ctaGoalsDebt"', HOME)
        self.assertIn('id="debtBar"', HOME)
        # hidden by default — no false alarm for EF-only
        self.assertIn('id="debtCard" hidden', HOME)
        # Safety parity CTA / DNA copy
        self.assertIn("Bạn đã khai nợ nguy hiểm — tạo mục tiêu trả nợ", HOME)
        self.assertIn("Mở Mục tiêu · Trả nợ", HOME)
        self.assertIn('href="/app/goals?focus=debt"', HOME)
        self.assertIn("Chưa có mục tiêu trả nợ", HOME)
        # same strings live on Safety
        self.assertIn("Bạn đã khai nợ nguy hiểm — tạo mục tiêu trả nợ", SAFETY)
        self.assertIn("Mở Mục tiêu · Trả nợ", SAFETY)
        self.assertIn('id="debtCard"', SAFETY)

    def test_show_when_gate_debt_or_goal(self):
        # visibility: has_dangerous_debt OR dangerous_debt_unhandled OR debt goal
        self.assertIn("has_dangerous_debt", HOME)
        self.assertIn("dangerous_debt_unhandled", HOME)
        self.assertIn("type=debt_payoff", HOME)
        self.assertIn("showDebt", HOME)
        self.assertIn("debtCard.hidden=!showDebt", HOME)
        # fetch goals debt_payoff (GET only)
        self.assertIn("/goals?user_id=", HOME)
        self.assertIn("&type=debt_payoff", HOME)
        # never auto-create debt from Home
        self.assertNotIn('type:"debt_payoff"', HOME)
        self.assertNotIn("POST /goals", HOME)

    def test_dna_no_goal_vs_active_goal_branches(self):
        # DNA / no goal → create CTA
        self.assertIn("link.textContent='Bạn đã khai nợ nguy hiểm — tạo mục tiêu trả nợ'", HOME)
        # Active goal → paid/target · % + open CTA
        self.assertIn("link.textContent='Mở Mục tiêu · Trả nợ'", HOME)
        self.assertIn("debt.current", HOME)
        self.assertIn("debt.target", HOME)
        # branch on debt presence
        self.assertIn("if(debt){", HOME)
        self.assertIn("}else{", HOME[HOME.index("if(debt){") :])

    def test_ef_empty_and_hien_phap_preserved_174(self):
        # #174: EF empty + Hiến pháp CTA must survive
        self.assertIn("Chưa có quỹ", HOME)
        self.assertIn("!det.goal_id", HOME)
        self.assertIn("Number(tgt)===0", HOME)
        self.assertIn("efLabel').textContent='Chưa có quỹ'", HOME)
        self.assertIn("Bắt đầu · Hiến pháp", HOME)
        self.assertIn("gateCta.textContent='Bắt đầu · Hiến pháp'", HOME)
        self.assertIn("gateCta.href='/app/onboarding'", HOME)

    def test_app_home_200_spotcheck(self):
        r = TestClient(create_app()).get("/app")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('id="debtCard"', body)
        self.assertIn("type=debt_payoff", body)
        self.assertIn("Bạn đã khai nợ nguy hiểm — tạo mục tiêu trả nợ", body)
        self.assertIn("Chưa có quỹ", body)
        self.assertIn("Bắt đầu · Hiến pháp", body)

    def test_hard_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        self.assertIn("no_efund_invest", SAFETY)
        # Home must not reopen GATE mastery / GATE_NODE
        self.assertNotIn("no_efund_invest", HOME)
        self.assertNotIn("masteryState", HOME)


if __name__ == "__main__":
    unittest.main()
