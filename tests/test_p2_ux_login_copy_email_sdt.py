"""P2 UX — /app/login copy: Email + SĐT, no «tuỳ chọn…», hint one-of-two."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
LOGIN_HTML = (STATIC / "login.html").read_text(encoding="utf-8")
FRIENDLY = (STATIC / "friendly_labels.js").read_text(encoding="utf-8")


class TestP2UxLoginCopyEmailSdt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def test_login_route_serves_new_copy(self):
        r = self.client.get("/app/login")
        self.assertEqual(r.status_code, 200)
        t = r.text
        self.assertIn("Khách / demo · chỉ cần email hoặc SĐT + mật khẩu", t)
        self.assertIn(">Email<", t)
        self.assertIn(">Số điện thoại<", t)
        self.assertIn('placeholder="ban@email.com"', t)
        self.assertIn('placeholder="+84…"', t)
        self.assertIn("Chỉ cần điền một trong hai", t)
        self.assertNotIn("tuỳ chọn", t)
        self.assertNotIn("tuỳ chọn nếu có", t)

    def test_login_html_static_file(self):
        t = LOGIN_HTML
        self.assertIn("Khách / demo · chỉ cần email hoặc SĐT + mật khẩu", t)
        self.assertIn('<label for="email">Email</label>', t)
        self.assertIn('<label for="phone">Số điện thoại</label>', t)
        self.assertIn('placeholder="ban@email.com"', t)
        self.assertIn('placeholder="+84…"', t)
        self.assertIn("Chỉ cần điền một trong hai", t)
        self.assertNotIn("tuỳ chọn", t)
        # Hotfix #4 belt untouched
        self.assertIn('localStorage.removeItem("welora_token")', t)
        self.assertIn("/static/auth-gate.js", t)

    def test_friendly_labels_guest_demo_synced(self):
        self.assertIn(
            'guest_demo: "Khách / demo · chỉ cần email hoặc SĐT + mật khẩu"',
            FRIENDLY,
        )

    def test_hard_deny_and_gate_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        sg = (ROOT / "welora" / "safety_gate.py").read_text(encoding="utf-8")
        self.assertIn("TARGET_MONTHS = 3", sg)
        self.assertIn("months: int = TARGET_MONTHS", sg)
        # login copy change must not touch / introduce Hard Deny adjacent surface
        for banned in ("Open Banking", "Investments", "Pre-Rule", "gate_months", "TARGET_MONTHS"):
            self.assertNotIn(banned, LOGIN_HTML)


if __name__ == "__main__":
    unittest.main()
