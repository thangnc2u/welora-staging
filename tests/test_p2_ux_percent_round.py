"""P2 UX — percent helper, Vietnamese comma."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.pct_format import format_pct
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]


class TestP2UxPercentRound(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_format_pct_cases(self):
        self.assertEqual(format_pct(16.666666666666664), "16,7%")
        self.assertIn("16,7%", format_pct(16.666666666666664))
        self.assertEqual(format_pct(100), "100%")
        self.assertEqual(format_pct(0), "0%")
        self.assertEqual(format_pct(33.33), "33,3%")

    def test_money_js_has_helper(self):
        js = (ROOT / "welora" / "api" / "static" / "money.js").read_text(encoding="utf-8")
        self.assertIn("formatPct", js)
        self.assertIn('replace(".", ",")', js)

    def test_goals_html_uses_helper_not_long_float(self):
        html = (ROOT / "welora" / "api" / "static" / "goals.html").read_text(encoding="utf-8")
        self.assertIn("formatPct", html)
        self.assertIn("pct(cur.percent)", html)
        self.assertNotIn("666666", html)
        self.assertNotIn("Welora Academy", html)
        self.assertIn("Welorademy", html)

    def test_dashboard_and_gate_use_helper(self):
        home = self.client.get("/app").text
        self.assertIn("formatPct", home)
        self.assertNotIn("Welora Academy", home)
        safety = self.client.get("/app/safety").text
        self.assertIn("formatPct", safety)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        b = self.client.get("/health").json()
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
