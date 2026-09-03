"""P2 UX money copy — VND format, chips, hide debug jargon."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"


class TestP2UxMoneyCopy(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_money_js_vnd_format(self):
        js = (STATIC / "money.js").read_text(encoding="utf-8")
        self.assertIn("formatVnd", js)
        self.assertIn("\u20ab", js)
        self.assertIn("5000000", js)
        # grouping uses dot
        self.assertIn('"."', js)

    def test_onboarding_no_jargon(self):
        r = self.client.get("/app/onboarding")
        self.assertEqual(r.status_code, 200)
        t = r.text
        self.assertNotIn("B0–B5", t)
        self.assertNotIn("B0 ·", t)
        self.assertNotIn("B1 ·", t)
        self.assertNotIn("node_id", t)
        self.assertNotIn("meets_gate", t)
        self.assertNotIn("Welora Academy", t)
        self.assertIn("5tr", t)
        self.assertIn("10tr", t)
        self.assertIn("20tr", t)
        self.assertIn("10.000.000", t)
        self.assertIn("/static/money.js", t)

    def test_fund_inputs_have_quick_chips(self):
        for path in ("/app/onboarding", "/app/safety", "/app/goals"):
            t = self.client.get(path).text
            self.assertIn("5tr", t, path)
            self.assertIn("10tr", t, path)
            self.assertIn("20tr", t, path)
            self.assertIn("data-vnd=\"5000000\"", t, path)

    def test_debug_links_hidden_without_dev(self):
        home = self.client.get("/app").text
        self.assertIn("dev-only", home)
        self.assertIn("navPreRule", home)
        self.assertIn("navLogs", home)
        self.assertIn("?dev=1", home)
        self.assertNotIn("Welora Academy", home)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        b = r.json()
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
