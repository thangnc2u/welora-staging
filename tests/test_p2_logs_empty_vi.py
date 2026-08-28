"""P2 Ticket BQ — logs empty copy nhật ký."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "logs.html"


class TestP2LogsEmptyVi(unittest.TestCase):
    def test_empty(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Chưa có nhật ký", html)
        self.assertIn("\u01b0", html)
        self.assertIn("\u00f3", html)
        self.assertIn("\u1ead", html)
        self.assertIn("\u00fd", html)
        self.assertNotIn("Chưa có log", html)
        self.assertIn("Không đọc được nhật ký", html)
        self.assertIn("/agent/decision-logs", html)
        self.assertIn("/auth/device", html)
        self.assertIn("<title>Welora · Nhật ký quyết định</title>", html)
        self.assertIn("<h1>Nhật ký quyết định</h1>", html)
        self.assertIn("welora_device_id", html)
        self.assertIn("function redact", html)
        self.assertNotIn("innerHTML", html)
        for nid in ("navHome", "logList", "logErr"):
            self.assertIn(f'id="{nid}"', html)

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
