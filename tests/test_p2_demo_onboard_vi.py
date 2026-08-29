"""P2 Ticket AV — demo Onboard/Founders labels Vietnamese."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "demo.html"


class TestP2DemoOnboardVi(unittest.TestCase):
    def test_copy(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Đăng nhập → Bắt đầu → Goal quỹ → Deny → Nạp quỹ 3 tháng → Cổng → R01 vẫn deny", html)
        self.assertIn("<h2>2 · Phiên Bắt đầu</h2>", html)
        self.assertIn("Chạy đủ demo 8 bước", html)
        self.assertIn("<h1>Welora · Demo 8 bước</h1>", html)
        self.assertIn("Chạy demo 8 bước", html)
        self.assertIn("<h2>4 · Goal quỹ</h2>", html)
        self.assertIn("<h2>5 · Deny (tất tay ETF)</h2>", html)
        self.assertIn("<h2>8 · R01 vẫn deny</h2>", html)
        self.assertIn("\u1eaf", html)
        self.assertIn("\u1ea7", html)
        self.assertIn("\u1ee7", html)
        self.assertIn("\u00ea", html)
        self.assertNotIn("Phiên onboard", html)
        self.assertNotIn("→ Onboard →", html)
        self.assertNotIn("Founders E2E", html)
        self.assertIn("/onboarding/session", html)
        self.assertIn("function setStep", html)
        self.assertIn("textContent", html)
        self.assertNotIn("innerHTML", html)
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
