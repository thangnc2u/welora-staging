"""P2 hotfix — Đăng xuất clears session + auth gate on /app/* (post-#217, no ?logout=1)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
SHELL_JS = STATIC / "shell.js"
SHELL_CSS = STATIC / "shell.css"


class TestP2HotfixAppLogoutBtn(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())
        cls.js = SHELL_JS.read_text(encoding="utf-8")
        cls.css = SHELL_CSS.read_text(encoding="utf-8")

    def test_app_pages_load_shell(self):
        for path in ("/app", "/app/safety", "/app/accounts"):
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200)
                self.assertIn("/static/shell.js", r.text)
                self.assertIn("/static/shell.css", r.text)

    def test_shell_js_logout_control(self):
        self.assertTrue(SHELL_JS.is_file())
        js = self.js
        self.assertIn("Đăng xuất", js)
        self.assertIn("weloraLogout", js)
        self.assertIn("welora-logout-btn", js)
        self.assertIn("localStorage.clear()", js)
        self.assertIn("sessionStorage.clear()", js)
        self.assertIn('localStorage.setItem("welora_device_id"', js)
        self.assertIn('getItem("welora_device_id")', js)
        self.assertIn("clearAuthStorage", js)
        self.assertIn('removeItem("welora_token")', js)
        self.assertIn("keepalive: true", js)
        self.assertIn('location.replace("/app/login")', js)
        self.assertIn("/auth/logout", js)
        self.assertIn("Authorization", js)
        self.assertIn("Bearer", js)
        # Scope B — never rely on logout query deeplink
        self.assertNotIn("/app/login?logout", js)
        self.assertNotIn("?logout=", js)
        self.assertNotRegex(js, r"location\.href\s*=\s*['\"][^'\"]*logout=" )
        # keep device identity
        self.assertNotIn('removeItem("welora_device_id")', js)
        # sync clear — not solely behind fetch.then
        self.assertNotIn("function once()", js)
        self.assertNotIn(".then(once, once)", js)
        click_i = js.index('btn.addEventListener("click"')
        region = js[click_i:]
        self.assertLess(region.index('removeItem("welora_token")'), region.index('location.replace("/app/login")'))
        self.assertLess(region.index("clearAuthStorage()"), region.index('fetch("/auth/logout"'))
        # skip auth pages (logout chrome + gate allowlist)
        for p in ("/app/login", "/app/register", "/app/forgot-password", "/app/reset-password", "/app/otp"):
            self.assertIn(p, js)

    def test_shell_js_auth_gate_requires_token(self):
        """After logout clear, /app shell must redirect to login when no welora_token."""
        js = self.js
        self.assertIn("welora_token", js)
        self.assertIn('localStorage.getItem("welora_token")', js)
        self.assertIn('location.replace("/app/login")', js)
        # gate allowlist includes auth pages; no ?logout=
        self.assertIn("/app/otp", js)
        self.assertNotIn("?logout=", js)
        # gate runs before chrome inject (replace present; early return on missing token)
        gate_idx = js.index('location.replace("/app/login")')
        logout_idx = js.index("weloraLogout")
        self.assertLess(gate_idx, logout_idx)

    def test_shell_css_logout_styles(self):
        self.assertTrue(SHELL_CSS.is_file())
        css = self.css
        self.assertIn("#weloraLogout", css)
        self.assertIn(".welora-logout-btn", css)
        self.assertIn("#weloraTopChrome", css)
        self.assertIn("--border-focus", css)
        # navy/dark friendly — not black text rule for logout btn
        self.assertIn("--text-primary", css)

    def test_health_gate_hard_deny_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])

    def test_auth_logout_endpoint_still_reachable(self):
        r = self.client.post("/auth/logout")
        # no token → still handled (not 404/405)
        self.assertNotIn(r.status_code, (404, 405))
        self.assertIn(r.status_code, (200, 400, 401, 403, 422))


if __name__ == "__main__":
    unittest.main()
