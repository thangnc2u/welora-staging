"""P2 Ticket AR — demo 8-step headings Vietnamese."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "demo.html"


class TestP2DemoVi(unittest.TestCase):
    def test_headings(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("<title>Welora · Demo 8 bước</title>", html)
        self.assertIn("<h1>Welora · Demo 8 bước</h1>", html)
        self.assertIn("Đăng nhập → Bắt đầu → Goal quỹ → Deny → Nạp quỹ 3 tháng → Cổng → R01 vẫn deny", html)
        self.assertIn("<h2>1 · Đăng nhập</h2>", html)
        self.assertIn("<h2>2 · Phiên Bắt đầu</h2>", html)
        self.assertIn("<h2>3 · Hoàn tất DNA</h2>", html)
        self.assertIn("<h2>4 · Goal quỹ</h2>", html)
        self.assertIn("<h2>5 · Deny (tất tay ETF)</h2>", html)
        self.assertIn("<h2>6 · Nạp quỹ 3 tháng</h2>", html)
        self.assertIn("<h2>7 · Cổng</h2>", html)
        self.assertIn("<h2>8 · R01 vẫn deny</h2>", html)
        self.assertIn("Chạy demo 8 bước", html)
        self.assertIn("\u1edb", html)
        self.assertIn("\u0103", html)
        self.assertIn("\u1ead", html)
        self.assertIn("\u00e0", html)
        self.assertIn("\u1ea1", html)
        self.assertIn("\u1ed5", html)
        self.assertIn("\u1eab", html)
        self.assertNotIn("<h1>Welora · Demo E2E</h1>", html)
        self.assertNotIn("Complete DNA", html)
        self.assertNotIn("Onboard session", html)
        self.assertNotIn("R01 still denies", html)
        self.assertIn("function setStep", html)
        self.assertIn("textContent", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn("welora_device_id", html)
        self.assertIn("young_single", html)
        self.assertIn("stable", html)
        self.assertIn("/agent/chat", html)
        self.assertIn("set_amount", html)
        self.assertIn("guardrail_result", html)
        self.assertIn("rule_hit", html)
        for nid in ("navHome", "run", "step1", "step2", "step3", "step4", "step5", "step6", "step7", "step8"):
            self.assertIn(f'id="{nid}"', html)
        self.assertIn("7 · C\u1ed5ng", html)
        self.assertNotIn("7 · C\u1ed1ng", html)

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
