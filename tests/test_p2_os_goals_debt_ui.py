"""P2-OS-02 Native UI /app/goals — debt_payoff + Mục tiêu."""

from __future__ import annotations

from pathlib import Path
import unittest

from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"
HTML = (STATIC / "goals.html").read_text(encoding="utf-8")


class TestP2OsGoalsDebtUi(unittest.TestCase):
    def test_title_muc_tieu(self):
        self.assertIn("<h1>Mục tiêu</h1>", HTML)
        self.assertIn("Trả nợ", HTML)
        self.assertIn("debt_payoff", HTML)
        self.assertIn("emergency_fund", HTML)

    def test_debt_create_form(self):
        self.assertIn('id="debtCreateBtn"', HTML)
        self.assertIn('id="debtTarget"', HTML)
        self.assertIn('id="debtTitle"', HTML)
        self.assertIn('id="debtSubtype"', HTML)
        self.assertIn("type:'debt_payoff'", HTML)
        self.assertIn("target_amount", HTML)
        self.assertNotIn("essential_expense_monthly", HTML)

    def test_progress_select_not_only_first(self):
        self.assertIn('id="goalPick"', HTML)
        self.assertIn("add_amount", HTML)
        self.assertIn("/progress", HTML)

    def test_keep_chrome(self):
        self.assertIn('id="goalList"', HTML)
        self.assertIn('id="navHome"', HTML)
        self.assertIn("welora_device_id", HTML)
        self.assertIn("ctaOnboarding", HTML)
        self.assertIn("Chưa có quỹ khẩn cấp", HTML)
        self.assertNotIn("JSON.stringify", HTML)
        self.assertNotIn("innerHTML", HTML)

    def test_target_months_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
