"""P2 UX — /app/login + /app/register: single identifier field (email OR phone)."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
LOGIN_HTML = (STATIC / "login.html").read_text(encoding="utf-8")
REGISTER_HTML = (STATIC / "register.html").read_text(encoding="utf-8")
FRIENDLY = (STATIC / "friendly_labels.js").read_text(encoding="utf-8")


def _split_identifier_js_logic(raw: str) -> dict:
    """Mirror login/register splitIdentifier: @ → email, else phone."""
    v = (raw or "").strip()
    if not v:
        return {}
    if "@" in v:
        return {"email": v}
    return {"phone": v}


class TestP2UxLoginSingleIdentifier(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def test_login_route_single_identifier_copy(self):
        r = self.client.get("/app/login")
        self.assertEqual(r.status_code, 200)
        t = r.text
        self.assertIn("Khách / demo · chỉ cần email hoặc SĐT + mật khẩu", t)
        self.assertIn(">Email hoặc Số điện thoại<", t)
        self.assertIn('id="identifier"', t)
        self.assertIn('placeholder="ban@email.com hoặc +84…"', t)
        self.assertIn('id="password"', t)
        # old dual labels / hint gone
        self.assertNotIn(">Email<", t)
        self.assertNotIn(">Số điện thoại<", t)
        self.assertNotIn('id="phone"', t)
        self.assertNotIn("Chỉ cần điền một trong hai", t)
        self.assertNotIn("emailPhoneHint", t)
        self.assertNotIn("tuỳ chọn", t)

    def test_login_html_static_file(self):
        t = LOGIN_HTML
        self.assertIn('<label for="identifier">Email hoặc Số điện thoại</label>', t)
        self.assertIn('id="identifier"', t)
        self.assertIn('placeholder="ban@email.com hoặc +84…"', t)
        self.assertIn("function splitIdentifier", t)
        self.assertIn("v.includes('@')", t)
        self.assertNotIn('<label for="email">Email</label>', t)
        self.assertNotIn('<label for="phone">Số điện thoại</label>', t)
        self.assertNotIn("Chỉ cần điền một trong hai", t)
        # Hotfix #4 belt untouched
        self.assertIn('localStorage.removeItem("welora_token")', t)
        self.assertIn("/static/auth-gate.js", t)

    def test_register_single_identifier_parity(self):
        r = self.client.get("/app/register")
        self.assertEqual(r.status_code, 200)
        t = r.text
        self.assertIn(">Email hoặc Số điện thoại<", t)
        self.assertIn('id="identifier"', t)
        self.assertIn('placeholder="ban@email.com hoặc +84…"', t)
        self.assertNotIn('id="phone"', t)
        self.assertNotIn("tuỳ chọn nếu có", t)
        self.assertIn("function splitIdentifier", REGISTER_HTML)
        self.assertIn("v.includes('@')", REGISTER_HTML)

    def test_split_identifier_maps_email_or_phone(self):
        self.assertEqual(
            _split_identifier_js_logic("partner@welora.demo"),
            {"email": "partner@welora.demo"},
        )
        self.assertEqual(
            _split_identifier_js_logic("ban@email.com"),
            {"email": "ban@email.com"},
        )
        self.assertEqual(
            _split_identifier_js_logic("+84911222333"),
            {"phone": "+84911222333"},
        )
        self.assertEqual(_split_identifier_js_logic("  "), {})

    def test_submit_payload_still_sends_email_or_phone(self):
        """Static handlers must build {email|phone, password} for existing API."""
        for html in (LOGIN_HTML, REGISTER_HTML):
            self.assertIn("splitIdentifier", html)
            self.assertRegex(html, r"body\s*=\s*\{password,\s*\.\.\.parts\}")
            # must not invent new API field names
            self.assertNotIn("body.identifier", html)
            self.assertNotIn('"identifier":', html)

    def test_demo_partner_login_still_works_via_email_payload(self):
        """Identifier path for demo still hits /auth/login with email field."""
        seed = self.client.post("/auth/demo/seed")
        self.assertEqual(seed.status_code, 200, seed.text)
        email = seed.json().get("email") or "partner@welora.demo"
        parts = _split_identifier_js_logic(email)
        self.assertEqual(parts, {"email": email})
        login = self.client.post(
            "/auth/login",
            json={**parts, "password": "WeloraDemo1!"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertIn("token", login.json())

    def test_phone_identifier_login_payload(self):
        phone = "+84999888777"
        password = "PhoneIdPath1!"
        reg = self.client.post(
            "/auth/register", json={"phone": phone, "password": password}
        )
        self.assertEqual(reg.status_code, 201, reg.text)
        parts = _split_identifier_js_logic(phone)
        self.assertEqual(parts, {"phone": phone})
        login = self.client.post(
            "/auth/login", json={**parts, "password": password}
        )
        self.assertEqual(login.status_code, 200, login.text)

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
        for banned in ("Open Banking", "Investments", "Pre-Rule", "gate_months", "TARGET_MONTHS"):
            self.assertNotIn(banned, LOGIN_HTML)
            self.assertNotIn(banned, REGISTER_HTML)


if __name__ == "__main__":
    unittest.main()
