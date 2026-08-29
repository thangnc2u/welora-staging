"""P2 Ticket CM — DNA label Ưu tiên ngắn hạn."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "dna.html"


class TestP2DnaPriorityVi(unittest.TestCase):
    def test_label(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn(
            "['Ưu tiên ngắn hạn', pick(snap,'near_term_priority')??data.near_term_priority]",
            html,
        )
        self.assertIn("\u01af", html)
        self.assertIn("\u00ea", html)
        self.assertIn("\u1eaf", html)
        self.assertIn("\u1ea1", html)
        self.assertNotIn("['near_term_priority'", html)
        self.assertIn("pick(snap,'near_term_priority')", html)
        self.assertIn("data.near_term_priority", html)
        self.assertIn("['Có nợ nguy hiểm'", html)
        self.assertIn("['surplus_habit'", html)
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
