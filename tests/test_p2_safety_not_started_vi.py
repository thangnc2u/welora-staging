"""P2 Ticket CX — safety option not_started → Chưa bắt đầu."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html"


class TestP2SafetyNotStartedVi(unittest.TestCase):
    def test_option(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('<option value="not_started">Chưa bắt đầu</option>', html)
        self.assertIn(
            'textContent="Làm chủ · "+(st==="not_started"?"Chưa bắt đầu":st)',
            html,
        )
        self.assertIn("\u01b0", html)
        self.assertIn("\u1eaf", html)
        self.assertIn("\u0111", html)
        self.assertIn("\u1ea7", html)
        self.assertNotIn(">not_started</option>", html)
        self.assertIn('value="not_started"', html)
        self.assertIn('||"not_started"', html)
        self.assertIn('state:"not_started"', html)
        self.assertIn(">learning</option>", html)
        self.assertIn(">familiar</option>", html)
        self.assertIn(">apply</option>", html)
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
