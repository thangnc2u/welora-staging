"""P2 Ticket CL — DNA label Có nợ nguy hiểm."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "dna.html"


class TestP2DnaDebtVi(unittest.TestCase):
    def test_label(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn(
            "['Có nợ nguy hiểm', pick(snap,'has_dangerous_debt_self')??data.has_dangerous_debt_self]",
            html,
        )
        self.assertIn("\u00f3", html)
        self.assertIn("\u1ee3", html)
        self.assertIn("\u1ec3", html)
        self.assertNotIn("['has_dangerous_debt_self'", html)
        self.assertIn("pick(snap,'has_dangerous_debt_self')", html)
        self.assertIn("data.has_dangerous_debt_self", html)
        self.assertIn("['Tháng quỹ khẩn cấp'", html)
        self.assertIn("['near_term_priority'", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn('id="navHome"', html)
        self.assertIn('id="dna"', html)
        self.assertIn("emptyState", html)

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
