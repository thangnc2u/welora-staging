"""P2-OS-16 Demo ẩn HTTP + rule_hit kỹ thuật."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "demo.html"


class TestP2OsDemoHttpRulehitVi(unittest.TestCase):
    def test_no_http_or_rule_hit_chrome(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertNotIn("'HTTP '+r.status", html)
        self.assertNotIn("rule_hit", html)
        self.assertIn("setStep(1,'tài khoản sẵn sàng','ok');", html)
        self.assertIn("setStep(2,'phiên tạo xong','ok');", html)
        self.assertIn("setStep(3,'DNA + Hiến pháp xong','ok');", html)
        self.assertIn("setStep(4,'Quỹ khẩn cấp 3 tháng đã tạo','ok');", html)
        self.assertIn("setStep(5,resultLabel(r.d.guardrail_result),", html)
        self.assertIn("setStep(6,'Nạp quỹ = 3 × 10.000.000 = 30.000.000','ok');", html)
        self.assertIn("setStep(8,resultLabel(r.d.guardrail_result),", html)
        self.assertIn("==='deny'", html)
        self.assertIn("'deny':'ok'", html)
        self.assertIn(".deny{", html)
        self.assertIn("function resultLabel", html)
        self.assertIn("/auth/device", html)
        self.assertIn("/onboarding/session", html)
        self.assertIn("/goals", html)
        self.assertIn("/agent/chat", html)
        self.assertIn("/users/", html)
        self.assertIn("safety-gate", html)
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
