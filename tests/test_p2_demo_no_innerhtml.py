"""P2 Ticket AH — demo setStep without innerHTML."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "demo.html"


class TestP2DemoNoInnerHtml(unittest.TestCase):
    def test_demo_html_no_innerhtml(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('id="run"', html)
        self.assertIn('id="navHome"', html)
        self.assertIn("welora_device_id", html)
        for i in range(1, 9):
            self.assertIn(f'id="step{i}"', html)
        self.assertIn("function setStep", html)
        self.assertIn("textContent", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn("/auth/device", html)
        self.assertIn("/onboarding/session", html)
        self.assertIn("/goals", html)
        self.assertIn("/agent/chat", html)
        self.assertIn("all-in ETF", html)
        self.assertNotIn("user='+", html)

    def test_app_demo_200(self):
        r = TestClient(create_app()).get("/app/demo")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("innerHTML", r.text)

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
