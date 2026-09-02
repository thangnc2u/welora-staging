"""P2-OS-04 Safety Mục tiêu + debt card."""

from __future__ import annotations

from pathlib import Path
import unittest

from welora.safety_gate import TARGET_MONTHS

HTML = (Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html").read_text(encoding="utf-8")


class TestP2OsSafetyGoalsDebt(unittest.TestCase):
    def test_section_muc_tieu(self):
        self.assertIn('class="section-title">Mục tiêu<', HTML)
        self.assertNotIn('class="section-title">Goal quỹ<', HTML)
        self.assertIn("Tạo Goal quỹ 3 tháng", HTML)
        self.assertIn('id="essential"', HTML)
        self.assertIn('id="btnCreate"', HTML)
        self.assertIn('id="btnSave"', HTML)

    def test_debt_card(self):
        self.assertIn('id="debtCard"', HTML)
        self.assertIn('id="debtMeta"', HTML)
        self.assertIn('id="ctaGoalsDebt"', HTML)
        self.assertIn('href="/app/goals"', HTML)
        self.assertIn("Chưa có mục tiêu trả nợ", HTML)
        self.assertIn("type=debt_payoff", HTML)
        self.assertNotIn("essential_expense_monthly:ess,type:\"debt_payoff\"", HTML)

    def test_no_create_debt_on_safety(self):
        self.assertNotIn("type:\"debt_payoff\"", HTML)
        self.assertIn("type:\"emergency_fund\"", HTML)

    def test_keep_chrome(self):
        self.assertIn('id="navHome"', HTML)
        self.assertIn('id="masteryState"', HTML)
        self.assertIn("welora_device_id", HTML)
        self.assertNotIn("innerHTML", HTML)
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
