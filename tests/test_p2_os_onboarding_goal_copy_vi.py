"""P2-OS-07 Onboarding Goal copy → quỹ khẩn cấp VI."""

from __future__ import annotations

from pathlib import Path
import unittest

from welora.safety_gate import TARGET_MONTHS

HTML = (Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "onboarding.html").read_text(
    encoding="utf-8"
)


class TestP2OsOnboardingGoalCopyVi(unittest.TestCase):
    def test_copy(self):
        self.assertIn("B0–B5 · DNA · Quỹ khẩn cấp 3 tháng", HTML)
        self.assertIn("<h2>B5 · Tóm tắt + Quỹ khẩn cấp 3 tháng</h2>", HTML)
        self.assertIn(">Tạo quỹ khẩn cấp 3 tháng<", HTML)
        self.assertIn("Không tạo được quỹ khẩn cấp", HTML)
        self.assertNotIn("Goal quỹ", HTML)
        self.assertNotIn("Tạo Goal quỹ khẩn cấp", HTML)
        self.assertNotIn("Không tạo được Goal", HTML)

    def test_api_unchanged(self):
        self.assertIn('id="ctaGoal"', HTML)
        self.assertIn("type:'emergency_fund'", HTML)
        self.assertIn("essential_expense_monthly:essential", HTML)
        self.assertIn("linked_from_onboarding:true", HTML)
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertNotIn("innerHTML", HTML)


if __name__ == "__main__":
    unittest.main()
