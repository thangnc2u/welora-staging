"""P2 Ticket AL — home nav Vietnamese labels, ids/hrefs unchanged."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "home.html"

NAVS = (
    ("navOnboarding", "/app/onboarding", "Bắt đầu · Hiến pháp"),
    ("navSafety", "/app/safety", "Cổng An Toàn"),
    ("navChat", "/app/chat", "Chat với Agent"),
    ("navContent", "/app/content", "Welorapedia"),
    ("navDemo", "/app/demo", "Demo 8 bước"),
    ("navParser", "/app/parser", "Sao kê CSV"),
    ("navMetrics", "/app/metrics", "Chỉ số"),
    ("navLogs", "/app/logs", "Nhật ký quyết định"),
    ("navConstitution", "/app/constitution", "Hiến pháp cá nhân"),
    ("navDna", "/app/dna", "DNA tài chính"),
    ("navGoals", "/app/goals", "Quỹ khẩn cấp"),
    ("navOtp", "/app/otp", "OTP điện thoại"),
    ("navPreRule", "/app/pre-rule", "Pre-Rule debug"),
    ("navHealth", "/app/health-score", "Điểm sức khỏe"),
)


class TestP2HomeNavVi(unittest.TestCase):
    def test_nav_ids_hrefs_labels(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", html)
        self.assertNotIn(">Metrics<", html)
        self.assertNotIn(">Decision logs<", html)
        self.assertNotIn(">Health Score<", html)
        for nid, href, label in NAVS:
            self.assertIn(f'id="{nid}"', html)
            self.assertIn(f'href="{href}"', html)
            self.assertIn(label, html)

    def test_app_home_200(self):
        r = TestClient(create_app()).get("/app")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Bắt đầu · Hiến pháp", r.text)
        self.assertIn("Điểm sức khỏe", r.text)

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
