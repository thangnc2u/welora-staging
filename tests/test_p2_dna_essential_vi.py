"""P2 — DNA label Chi tiêu thiết yếu / tháng."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "dna.html"


class TestP2DnaEssentialVi(unittest.TestCase):
    def test_label(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn(
            "['Chi tiêu thiết yếu / tháng', pick(snap,'essential_expense_monthly')??data.essential_expense_monthly]",
            html,
        )
        self.assertIn("\u00ea", html)
        self.assertIn("\u1ebf", html)
        self.assertIn("\u00e1", html)
        self.assertNotIn("['essential_expense_monthly'", html)
        self.assertIn("pick(snap,'essential_expense_monthly')", html)
        self.assertIn("data.essential_expense_monthly", html)
        self.assertIn("['Giai đoạn sống'", html)
        self.assertIn("['Ổn định thu nhập'", html)
        self.assertIn("['Hoàn cảnh gia đình'", html)
        self.assertIn("['emergency_fund_months_self'", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn('id="navHome"', html)
        self.assertIn('id="dna"', html)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
