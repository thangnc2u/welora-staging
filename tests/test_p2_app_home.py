"""P2 Native UI /app home — 6 nav links, no JSON dump."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HOME_HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "home.html"


class TestP2AppHome(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_get_app_200_has_six_nav(self):
        r = self.client.get("/app")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('id="navOnboarding"', body)
        self.assertIn('href="/app/onboarding"', body)
        self.assertIn('id="navSafety"', body)
        self.assertIn('href="/app/safety"', body)
        self.assertIn('id="navChat"', body)
        self.assertIn('href="/app/chat"', body)
        self.assertIn('id="navContent"', body)
        self.assertIn('href="/app/content"', body)
        self.assertIn('id="navDemo"', body)
        self.assertIn('href="/app/demo"', body)
        self.assertIn('id="navParser"', body)
        self.assertIn('href="/app/parser"', body)
        self.assertNotIn("JSON.stringify", body)
        self.assertNotIn("/goals", body)
        self.assertNotIn("/agent/chat", body)
        self.assertNotIn("/auth", body)

    def test_home_html_file_has_nav_ids(self):
        html = HOME_HTML.read_text(encoding="utf-8")
        for i in ("navOnboarding", "navSafety", "navChat", "navContent", "navDemo", "navParser"):
            self.assertIn(f'id="{i}"', html)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
