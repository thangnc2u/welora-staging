"""P2 Native UI /app/logs — readable decision logs, no raw user id dump."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"


class TestP2LogsUi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_get_app_logs_200(self):
        r = self.client.get("/app/logs")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('id="logList"', body)
        self.assertIn('id="navHome"', body)
        self.assertIn("welora_device_id", body)
        self.assertNotIn("JSON.stringify(d)", body)
        self.assertNotIn("'user='+", body)
        self.assertNotIn('user="+', body)

    def test_logs_html_no_display_user_id(self):
        html = (STATIC / "logs.html").read_text(encoding="utf-8")
        self.assertNotIn("textContent=uid", html)
        self.assertNotIn("textContent=user_id", html)
        self.assertNotIn("textContent = user_id", html)
        self.assertNotIn("'user='+", html)
        self.assertNotIn('"user="+', html)

    def test_home_has_nav_logs(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        self.assertIn('id="navLogs"', html)
        self.assertIn('href="/app/logs"', html)

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
