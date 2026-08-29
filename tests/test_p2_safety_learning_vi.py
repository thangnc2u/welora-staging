"""P2 Ticket CY — safety option learning → Đang học."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html"

JS = 'textContent="Làm chủ · "+(st==="not_started"?"Chưa bắt đầu":st==="learning"?"Đang học":st==="familiar"?"Quen thuộc":st==="apply"?"Áp dụng":st)'


class TestP2SafetyLearningVi(unittest.TestCase):
    def test_option(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('<option value="learning">Đang học</option>', html)
        self.assertIn(JS, html)
        self.assertIn("\u0110", html)
        self.assertIn("\u1ecd", html)
        self.assertNotIn(">learning</option>", html)
        self.assertIn('value="learning"', html)
        self.assertIn('value="not_started"', html)
        self.assertIn(">Chưa bắt đầu</option>", html)
        self.assertIn(">Quen thuộc</option>", html)
        self.assertIn(">Áp dụng</option>", html)
        self.assertIn(">mastered</option>", html)
        self.assertIn("Làm chủ ·", html)
        self.assertIn("Đạt cổng: chưa", html)
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
