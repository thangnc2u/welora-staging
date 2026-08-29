"""P2 — DNA label Hoàn cảnh gia đình."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "dna.html"


class TestP2DnaFamilyVi(unittest.TestCase):
    def test_label(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn(
            "['Hoàn cảnh gia đình', pick(ident,'family_context')??data.family_context]",
            html,
        )
        self.assertIn("\u00e0", html)
        self.assertIn("\u1ea3", html)
        self.assertIn("\u0111", html)
        self.assertIn("\u00ec", html)
        self.assertNotIn("['family_context'", html)
        self.assertIn("pick(ident,'family_context')", html)
        self.assertIn("data.family_context", html)
        self.assertIn("['Giai đoạn sống'", html)
        self.assertIn("['Ổn định thu nhập'", html)
        self.assertIn("['essential_expense_monthly'", html)
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
