"""P2 hotfix — early auth-gate.js before paint + full auth storage clear on logout."""

from __future__ import annotations

from pathlib import Path
import os
import re
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

    def test_shell_js_sync_token_remove_before_redirect(self):
        """Hotfix #3: removeItem(welora_token) must run sync on click before replace."""
        js = self.shell
        # Explicit removeItem must appear in source before location.replace("/app/login")
        # Use the logout-path replace (last occurrence — gate + logout both have replace)
        rm = 'removeItem("welora_token")'
        self.assertIn(rm, js)
        self.assertGreaterEqual(js.count(rm), 2)  # sync clear + belt before redirect
        replace = 'location.replace("/app/login")'
        # First removeItem (sync clear) must precede the logout redirect replace.
        # Find logout click region via clearAuthStorage / keepalive fire-and-forget.
        self.assertIn("clearAuthStorage", js)
        self.assertIn("keepalive: true", js)
        # Sync removeItem on click path — not solely gated behind fetch.then
        click_i = js.index('btn.addEventListener("click"')
        logout_region = js[click_i:]
        self.assertIn(rm, logout_region)
        first_rm = logout_region.index(rm)
        replace_i = logout_region.index(replace)
        self.assertLess(first_rm, replace_i)
        # Must NOT solely gate clear behind fetch.then(once)
        self.assertNotIn("function once()", logout_region)
        self.assertNotIn(".then(once, once)", logout_region)
        # Fire-and-forget: clearAuthStorage called before fetch
        clear_i = logout_region.index("clearAuthStorage()")
        fetch_i = logout_region.index('fetch("/auth/logout"')
        self.assertLess(clear_i, fetch_i)
        self.assertLess(fetch_i, replace_i)
        # belt removeItem again before replace
        belt_after_fetch = logout_region[fetch_i:].index(rm)
        self.assertLess(belt_after_fetch, logout_region[fetch_i:].index(replace))
        # keep device_id; no ?logout=
        self.assertNotIn('removeItem("welora_device_id")', logout_region)
        self.assertNotIn("?logout=", logout_region)


    def test_served_shell_js_cache_bust_query(self):
        """Hotfix #4: every /app* HTML that loads shell uses ?v=<git_sha>."""
        prev = os.environ.get("WELORA_GIT_SHA")
        os.environ["WELORA_GIT_SHA"] = "cafebabe999"
        try:
            from welora.api.app import create_app as _ca
            client = TestClient(_ca())
            for path in ("/app", "/app/safety", "/app/accounts", "/app/goals", "/app/chat"):
                with self.subTest(path=path):
                    r = client.get(path)
                    self.assertEqual(r.status_code, 200)
                    self.assertIn("/static/shell.js?v=cafebab", r.text)
                    # no bare unversioned shell.js src
                    self.assertNotRegex(
                        r.text,
                        r'src=["\']/static/shell\.js["\']',
                    )
                    refs = re.findall(r'/static/shell\.js\?v=[^\s"\']+', r.text)
                    self.assertTrue(refs, path)
                    self.assertTrue(all(x.startswith("/static/shell.js?v=") for x in refs))
        finally:
            if prev is None:
                os.environ.pop("WELORA_GIT_SHA", None)
            else:
                os.environ["WELORA_GIT_SHA"] = prev

    def test_login_belt_wipes_token_keeps_device_id(self):
        """Hotfix #4: /app/login entry belt-removes welora_token; never device_id."""
        login_html = (STATIC / "login.html").read_text(encoding="utf-8")
        self.assertIn('removeItem("welora_token")', login_html)
        self.assertNotIn('removeItem("welora_device_id")', login_html)
        g = self.gate
        self.assertIn('path === "/app/login"', g)
        # belt remove inside allowlist branch
        allow_i = g.index("allow[path]")
        belt_region = g[allow_i : allow_i + 400]
        self.assertIn('removeItem("welora_token")', belt_region)
        self.assertNotIn('removeItem("welora_device_id")', g)
        # served login also includes belt
        r = self.client.get("/app/login")
        self.assertEqual(r.status_code, 200)
        self.assertIn('removeItem("welora_token")', r.text)
        self.assertNotIn("?logout=", r.text)

    def test_shell_js_assert_token_gone_before_replace(self):
        """Hotfix #4: before location.replace, assert !token then belt remove."""
        js = self.shell
        click_i = js.index('btn.addEventListener("click"')
        region = js[click_i:]
        replace = 'location.replace("/app/login")'
        replace_i = region.index(replace)
        before = region[:replace_i]
        # getItem check + removeItem must appear before replace (assert belt)
        self.assertIn('getItem("welora_token")', before)
        self.assertGreaterEqual(before.count('removeItem("welora_token")'), 2)
        # last assert pattern: if getItem then removeItem
        self.assertRegex(
            before,
            r'if\s*\(\s*localStorage\.getItem\("welora_token"\)\s*\)\s*\{\s*localStorage\.removeItem\("welora_token"\)',
        )
        self.assertNotIn("?logout=", region)
        self.assertNotIn('removeItem("welora_device_id")', region)


    def test_health_gate_hard_deny_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
