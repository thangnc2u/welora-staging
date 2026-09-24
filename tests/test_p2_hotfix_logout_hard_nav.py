"""P2 hotfix — early auth-gate.js before paint + full auth storage clear on logout."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
AUTH_GATE = STATIC / "auth-gate.js"
SHELL_JS = STATIC / "shell.js"
GATE_TAG = '<script src="/static/auth-gate.js"></script>'

# Pages that must gate before body paint (shell.js pages + critical UAT surfaces)
APP_HTML_WITH_GATE = (
    "home.html",
    "safety.html",
    "transactions.html",
    "academy.html",
    "dna.html",
    "accounts.html",
    "dual-control.html",
    "budget.html",
    "categories.html",
    "goals.html",
    "onboarding.html",
    "healthscore.html",
    "chat.html",
    "constitution.html",
    "content.html",
)


class TestP2HotfixLogoutHardNav(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())
        cls.gate = AUTH_GATE.read_text(encoding="utf-8")
        cls.shell = SHELL_JS.read_text(encoding="utf-8")

    def test_auth_gate_js_exists_and_sync(self):
        self.assertTrue(AUTH_GATE.is_file())
        g = self.gate
        self.assertIn("welora_token", g)
        self.assertIn('localStorage.getItem("welora_token")', g)
        self.assertIn('location.replace("/app/login")', g)
        self.assertNotIn("?logout=", g)
        self.assertNotIn("/app/login?logout", g)
        for p in (
            "/app/login",
            "/app/register",
            "/app/forgot-password",
            "/app/reset-password",
            "/app/otp",
        ):
            self.assertIn(p, g)
        # sync IIFE — no defer/async/module hints in the gate file itself
        self.assertNotIn("defer", g.lower())
        self.assertNotIn("async", g.lower())

    def test_home_and_safety_gate_in_head_before_body(self):
        for name in ("home.html", "safety.html"):
            with self.subTest(page=name):
                html = (STATIC / name).read_text(encoding="utf-8")
                self.assertIn(GATE_TAG, html)
                gate_i = html.index(GATE_TAG)
                body_i = html.lower().index("<body")
                head_end = html.lower().index("</head>")
                self.assertLess(gate_i, head_end)
                self.assertLess(gate_i, body_i)
                # blocking: tag must not have defer/async
                self.assertNotIn("auth-gate.js\" defer", html)
                self.assertNotIn("auth-gate.js\" async", html)

    def test_all_shell_pages_include_auth_gate_in_head(self):
        for name in APP_HTML_WITH_GATE:
            with self.subTest(page=name):
                html = (STATIC / name).read_text(encoding="utf-8")
                self.assertIn("/static/auth-gate.js", html)
                gate_i = html.index("/static/auth-gate.js")
                body_i = html.lower().index("<body")
                self.assertLess(gate_i, body_i)

    def test_served_app_routes_include_auth_gate(self):
        for path in ("/app", "/app/safety", "/app/accounts"):
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200)
                self.assertIn("/static/auth-gate.js", r.text)
                # gate appears before body open
                gate_i = r.text.index("/static/auth-gate.js")
                body_i = r.text.lower().index("<body")
                self.assertLess(gate_i, body_i)

    def test_shell_js_full_clear_keeps_device_id(self):
        js = self.shell
        self.assertIn("localStorage.clear()", js)
        self.assertIn("sessionStorage.clear()", js)
        self.assertIn('getItem("welora_device_id")', js)
        self.assertIn('setItem("welora_device_id"', js)
        # must NOT wipe device_id via removeItem
        self.assertNotIn('removeItem("welora_device_id")', js)
        self.assertIn('location.replace("/app/login")', js)
        self.assertNotIn("?logout=", js)
        # cookie clear best-effort
        self.assertIn("document.cookie", js)
        self.assertRegex(js, r"welora\|token\|session\|auth")
        # backup gate still present
        self.assertIn('localStorage.getItem("welora_token")', js)
        # POST logout uses token captured BEFORE clear
        self.assertIn("/auth/logout", js)
        self.assertIn("Bearer", js)

    def test_health_gate_hard_deny_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
