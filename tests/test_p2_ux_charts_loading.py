"""P2 UX charts + AI loading."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS


class TestP2UxChartsLoading(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_home_donut_and_ef_pct(self):
        r = self.client.get("/app")
        self.assertEqual(r.status_code, 200)
        t = r.text
        self.assertIn("hsDonut", t)
        self.assertIn("hsArc", t)
        self.assertIn("/ 1000", t)
        self.assertIn("efPct", t)
        self.assertIn("efBar", t)
        self.assertNotIn("Welora Academy", t)
        self.assertIn("Welorademy", t)

    def test_chat_typing(self):
        r = self.client.get("/app/chat")
        self.assertEqual(r.status_code, 200)
        t = r.text
        self.assertIn('id="typing"', t)
        self.assertIn("Đang soạn", t)
        self.assertIn("setLoading", t)
        self.assertIn("sendBtn", t)
        self.assertNotIn("Welora Academy", t)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        b = self.client.get("/health").json()
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
