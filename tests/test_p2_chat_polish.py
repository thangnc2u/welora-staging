"""P2 chat polish — no raw user_id, no JSON dump in #log."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

CHAT = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "chat.html"


class TestP2ChatPolish(unittest.TestCase):
    def test_chat_html_no_raw_user_or_json_dump(self):
        html = CHAT.read_text(encoding="utf-8")
        self.assertNotIn("JSON.stringify(d)", html)
        self.assertNotIn("user='+uid", html)
        self.assertNotIn('user="+uid', html)
        self.assertIn('id="gateBadge"', html)
        self.assertIn('id="denyCta"', html)
        self.assertIn('id="navHome"', html)
        self.assertIn("welora_device_id", html)
        self.assertIn("Không có phản hồi", html)
        self.assertIn("safety_gate_status", html)

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
