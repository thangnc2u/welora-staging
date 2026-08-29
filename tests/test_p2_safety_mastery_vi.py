"""P2 Ticket CW — safety chrome Làm chủ ·."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html"


class TestP2SafetyMasteryVi(unittest.TestCase):
    def test_chrome(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('id="masteryStatus">Làm chủ · —</div>', html)
        self.assertIn('textContent="Làm chủ · "+(st==="not_started"?"Chưa bắt đầu":st==="learning"?"Đang học":st==="familiar"?"Quen thuộc":st==="apply"?"Áp dụng":st)', html)
        self.assertIn("\u00e0", html)
        self.assertIn("\u1ee7", html)
        self.assertIn("\u00b7", html)
        self.assertIn("\u2014", html)
        self.assertNotIn("Mastery ·", html)
        self.assertIn("/mastery", html)
        self.assertIn('id="masteryStatus"', html)
        self.assertIn("Đạt cổng: chưa", html)
        self.assertIn('value="not_started"', html)
        self.assertIn('value="apply"', html)
        self.assertNotIn("innerHTML", html)

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
