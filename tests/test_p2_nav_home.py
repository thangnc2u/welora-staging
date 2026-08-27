"""P2 #navHome on every screen → /app."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"


class TestP2NavHome(unittest.TestCase):
    def test_six_screens_have_nav_home(self):
        names = (
            "onboarding.html",
            "safety.html",
            "chat.html",
            "content.html",
            "demo.html",
            "parser.html",
        )
        for name in names:
            html = (STATIC / name).read_text(encoding="utf-8")
            self.assertIn('id="navHome"', html, name)
            self.assertIn('href="/app"', html, name)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
