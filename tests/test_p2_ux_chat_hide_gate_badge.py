"""P2 UX — hide Cổng badge on /app/chat."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS


class TestP2UxChatHideGateBadge(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_chat_html_has_no_gate_badge(self):
        r = self.client.get("/app/chat")
        self.assertEqual(r.status_code, 200)
        t = r.text
        self.assertNotIn('id="gateBadge"', t)
        self.assertNotIn("Cổng: CHƯA ĐẠT", t)
        self.assertNotIn("Cổng: ĐẠT", t)
        self.assertIn("/agent/chat", t)
        self.assertIn("sendBtn", t)

    def test_home_and_safety_still_show_gate(self):
        home = self.client.get("/app").text
        self.assertIn("Cổng An Toàn", home)
        self.assertIn("gateBadge", home)
        safety = self.client.get("/app/safety").text
        self.assertIn("gateStatus", safety)
        self.assertTrue("CHƯA ĐẠT" in safety or "Cổng" in safety)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        b = self.client.get("/health").json()
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
