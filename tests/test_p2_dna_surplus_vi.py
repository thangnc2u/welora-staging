"""P2 Ticket CN — DNA label Thói quen thặng dư."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "dna.html"


class TestP2DnaSurplusVi(unittest.TestCase):
    def test_label(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn(
            "['Thói quen thặng dư', pick(psy,'surplus_habit')??data.surplus_habit]",
            html,
        )
        self.assertIn("\u00f3", html)
        self.assertIn("\u1eb7", html)
        self.assertIn("\u01b0", html)
        self.assertNotIn("['surplus_habit'", html)
        self.assertIn("pick(psy,'surplus_habit')", html)
        self.assertIn("data.surplus_habit", html)
        self.assertIn("['Ưu tiên ngắn hạn'", html)
        self.assertIn("['risk_tolerance'", html)
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
