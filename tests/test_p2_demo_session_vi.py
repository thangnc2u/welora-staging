"""P2 Ticket BY — demo step2 phiên tạo xong."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "demo.html"


class TestP2DemoSessionVi(unittest.TestCase):
    def test_step2(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("phiên tạo xong", html)
        self.assertIn("\u00ea", html)
        self.assertIn("\u1ea1", html)
        self.assertNotIn("session tạo xong", html)
        self.assertIn("setStep(2,'HTTP '+r.status+' · phiên tạo xong','ok');", html)
        self.assertIn("/onboarding/session", html)
        self.assertIn("session_id", html)
        self.assertIn("tài khoản sẵn sàng", html)
        self.assertIn("<h2>2 · Phiên Bắt đầu</h2>", html)
        self.assertIn("Nạp quỹ = 3 × 10.000.000 = 30.000.000 · HTTP ", html)
        self.assertIn("set_amount:30000000", html)
        self.assertIn("Tôi muốn all-in ETF ngay", html)
        self.assertNotIn("innerHTML", html)
        for nid in ("navHome", "run", "step1", "step2", "step3", "step4", "step5", "step6", "step7", "step8"):
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
