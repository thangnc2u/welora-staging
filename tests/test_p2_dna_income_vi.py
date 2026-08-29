"""P2 — DNA label Ổn định thu nhập."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "dna.html"


class TestP2DnaIncomeVi(unittest.TestCase):
    def test_label(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn(
            "['Ổn định thu nhập', pick(ident,'income_stability')??data.income_stability]",
            html,
        )
        self.assertIn("\u1ed4", html)
        self.assertIn("\u0111", html)
        self.assertIn("\u1ead", html)
        self.assertNotIn("['income_stability'", html)
        self.assertIn("pick(ident,'income_stability')", html)
        self.assertIn("data.income_stability", html)
        self.assertIn("['Giai đoạn sống'", html)
        self.assertIn("['family_context'", html)
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
