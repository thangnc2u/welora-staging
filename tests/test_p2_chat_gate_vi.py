"""P2 Ticket AK — chat gate badge Vietnamese."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "chat.html"


class TestP2ChatGateVi(unittest.TestCase):
    def test_gate_badge_vietnamese(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Cổng: ĐẠT", html)
        self.assertIn("Cổng: CHƯA ĐẠT", html)
        self.assertIn("function setGate", html)
        self.assertIn("className=s", html)
        self.assertIn("'passed'", html)
        self.assertIn("'not_passed'", html)
        self.assertNotIn("'Cổng: '+s", html)
        self.assertNotIn('"Cổng: "+s', html)
        self.assertNotIn("innerHTML", html)
        self.assertIn('id="navHome"', html)
        self.assertIn('id="denyCta"', html)
        self.assertIn("/app/content?key=SAFE-02", html)
        self.assertIn("/agent/chat", html)
        self.assertIn("user_id:uid", html)
        self.assertIn("message:q", html)
        self.assertIn("welora_device_id", html)

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
