"""Ticket «GP · Cutover Production app4.welora.vn» (LỆNH Forge 04/10): URLs / CORS / host from env,
no server cookies, client IP behind the Render proxy, and the production boot guard.

Production (WELORA_ENV=production) must refuse to START when: WELORA_OTP_ECHO is set; WELORA_GUEST_DEMO
is not 0; WELORA_OTP_HMAC_KEY is missing; WELORA_ADMIN_TOTP_SECRETS is missing; a test-only flag is on
(WELORA_OTP_FIXED / WELORA_RESET_ECHO / WELORA_CHECKOUT_TEST_HOOKS, any WELORA_RL_* ≤ 0). It also needs
an https WELORA_PUBLIC_BASE_URL (6th guard) and refuses WELORA_CHECKOUT_ENABLED on (7th guard, PR #250 r2)."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests._db_target import db_env
from welora import auth_ratelimit, checkout, prod_config
from welora.api.app import create_app

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://app4.welora.vn"
GOOD_PROD = {
    "WELORA_ENV": "production",
    "WELORA_GUEST_DEMO": "0",
    "WELORA_OTP_HMAC_KEY": "k" * 48,  # test value only
    "WELORA_ADMIN_TOTP_SECRETS": "admin@example.test:JBSWY3DPEHPK3PXP",  # RFC test secret, not a real one
    "WELORA_PUBLIC_BASE_URL": BASE,
}
TOUCHED = tuple(GOOD_PROD) + (
    "WELORA_OTP_ECHO", "WELORA_OTP_FIXED", "WELORA_RESET_ECHO", "WELORA_CHECKOUT_TEST_HOOKS", "WELORA_CORS_ORIGINS",
    "WELORA_ALLOWED_HOSTS", "WELORA_STORE", "WELORA_DB_URL", "WELORA_DEMO_AUTOSEED", "WELORA_RL_IP_MAX",
    "WELORA_RL_LOGIN_IP_MAX", "WELORA_RL_WINDOW_S", "WELORA_CHECKOUT_ENABLED",
)


class _Env(unittest.TestCase):
    def setUp(self) -> None:
        self._prev = {k: os.environ.get(k) for k in TOUCHED}
        for k in TOUCHED:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="welora-cutover-")
        os.environ.update({"WELORA_DEMO_AUTOSEED": "0", **db_env(self.tmp)})

    def tearDown(self) -> None:
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def prod(self, **extra: str) -> None:
        os.environ.update(GOOD_PROD)
        os.environ.update(extra)


# ----------------------------------------------------------------------------- URLs from env
class TestUrlsFromEnv(_Env):
    def test_absolute_links_use_the_base_url(self):
        self.prod()
        self.assertEqual(prod_config.public_base_url(), BASE)
        self.assertEqual(prod_config.absolute_url("/app/academy"), BASE + "/app/academy")
        self.assertEqual(prod_config.payos_webhook_url(), BASE + "/api/checkout/v1/webhook/payos")
        self.assertEqual(checkout.return_urls(), (BASE + "/app/checkout/return", BASE + "/app/checkout/cancel"))
        os.environ["WELORA_PUBLIC_BASE_URL"] = BASE + "/"  # trailing slash tolerated
        self.assertEqual(prod_config.absolute_url("app/x"), BASE + "/app/x")

    def test_dev_fallback_is_relative(self):
        self.assertEqual(prod_config.absolute_url("/app/x"), "/app/x")  # documented dev / test fallback
        self.assertEqual(checkout.return_urls()[0], "/app/checkout/return")

    def test_renewal_link_and_push_url_use_the_base_url(self):
        self.prod()
        from welora.db.connection import get_connection

        checkout.ensure_schema()
        conn = get_connection()
        try:
            link = checkout.create_renewal_link(conn, user_id="u-cutover", plan_id="ACA", billing_cycle="month")
        finally:
            conn.close()
        self.assertTrue(link.startswith(BASE + "/app/checkout/renew#t="), link)

    def test_no_hard_coded_public_host_on_the_prod_path(self):
        pat = re.compile(r"onrender\.com|welora\.vn|(?<![\w-])app[234]\.|localhost")
        allowed = {  # documented dev / test fallbacks and comments
            ("welora/auth_ratelimit.py", "*.onrender.com"),
            ("welora/db/migrate.py", "localhost:5432"),
        }
        hits = []
        files = [p for p in (ROOT / "welora").rglob("*") if p.suffix in (".py", ".html", ".js", ".json", ".yaml")]
        files += [ROOT / "start.sh"]
        for p in files:
            rel = str(p.relative_to(ROOT))
            for i, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                m = pat.search(line)
                if m and not any(rel == f and frag in line for f, frag in allowed):
                    hits.append(f"{rel}:{i}: {line.strip()[:100]}")
        self.assertEqual(hits, [])

    def test_mail_bodies_carry_no_host(self):
        from welora import contact_verify

        for body in (contact_verify.MAIL_BODY, contact_verify.ADMIN_NOTICE_BODY):
            self.assertNotRegex(body, r"https?://")


# ----------------------------------------------------------------------------- CORS / host
class TestCors(_Env):
    def _preflight(self, client: TestClient, origin: str):
        return client.options("/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"})

    def test_production_allows_only_env_origins(self):
        self.prod(WELORA_CORS_ORIGINS="*, https://partner.example.test, not-an-origin")
        self.assertEqual(prod_config.cors_origins(), ["https://partner.example.test", BASE])
        c = TestClient(create_app())
        ok = self._preflight(c, BASE)
        self.assertEqual(ok.headers.get("access-control-allow-origin"), BASE)
        for bad in ("https://app2.welora.vn", "https://app3.welora.vn", "https://www.welora.vn", "https://evil.example"):
            r = self._preflight(c, bad)
            self.assertNotEqual(r.headers.get("access-control-allow-origin"), bad, bad)
            self.assertNotEqual(r.headers.get("access-control-allow-origin"), "*", bad)
        g = c.get("/health", headers={"Origin": "https://evil.example"})
        self.assertIsNone(g.headers.get("access-control-allow-origin"))

    def test_production_base_only(self):
        self.prod()
        self.assertEqual(prod_config.cors_origins(), [BASE])

    def test_staging_default_unchanged(self):
        os.environ["WELORA_ENV"] = "staging"
        self.assertEqual(prod_config.cors_origins(), ["*"])
        os.environ["WELORA_CORS_ORIGINS"] = "https://a.example, https://b.example"
        self.assertEqual(prod_config.cors_origins(), ["https://a.example", "https://b.example"])

    def test_allowed_hosts_opt_in(self):
        c = TestClient(create_app())
        self.assertEqual(c.get("/health", headers={"Host": "anything.example"}).status_code, 200)  # unset → no check
        os.environ["WELORA_ALLOWED_HOSTS"] = "app4.welora.vn"
        self.assertEqual(c.get("/app/login", headers={"Host": "app4.welora.vn"}).status_code, 200)
        self.assertEqual(c.get("/app/login", headers={"Host": "app2.welora.vn"}).status_code, 400)
        self.assertEqual(c.get("/health", headers={"Host": "10.0.0.5:10000"}).status_code, 200)  # health exempt


# ----------------------------------------------------------------------------- cookies / client IP
class TestSessionAndIp(_Env):
    def test_server_sets_no_cookie(self):
        """Auth is a Bearer token kept by the page (no server cookie), so there is no cookie Domain
        that could point at www/app2/app3; Secure/SameSite have nothing to apply to."""
        self.prod()
        with TestClient(create_app(), base_url=BASE) as c:
            for r in (c.get("/health"), c.post("/auth/device", json={"device_id": "cutover-dev-0001"}),
                      c.post("/auth/register", json={"email": "cut@example.test", "password": "Matkhau-dai-123"}),
                      c.get("/app/login")):
                self.assertNotIn("set-cookie", {k.lower() for k in r.headers.keys()}, r.url)
            self.assertIn("max-age=", c.get("/health").headers.get("strict-transport-security", ""))

    def test_client_ip_behind_render_proxy(self):
        self.prod()
        # Render's proxy reaches the app from a private / CGNAT peer and appends the client to XFF
        for peer in ("10.214.3.7", "100.64.0.9"):
            self.assertEqual(auth_ratelimit.client_ip(peer, headers={"X-Forwarded-For": "203.0.113.50"}), "203.0.113.50")
            self.assertEqual(auth_ratelimit.client_ip(peer, headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.50"}),
                             "203.0.113.50")  # leftmost (forgeable) hop never trusted
        self.assertEqual(auth_ratelimit.client_ip("198.51.100.7", headers={"X-Forwarded-For": "203.0.113.50"}),
                         "198.51.100.7")  # direct (untrusted) peer → headers ignored
        start = Path(ROOT / "start.sh").read_text(encoding="utf-8")
        self.assertIn("--no-proxy-headers", start)

    def test_login_rate_limit_per_ip_kept(self):
        self.prod(WELORA_RL_LOGIN_IP_MAX="2")
        app = create_app()

        async def via_render_proxy(scope, receive, send):  # TCP peer = Render's internal proxy
            if scope["type"] == "http":
                scope = dict(scope, client=("10.214.3.7", 5000))
            await app(scope, receive, send)

        with TestClient(via_render_proxy, base_url=BASE) as c:
            h = {"X-Forwarded-For": "203.0.113.77"}
            codes = [c.post("/auth/login", json={"email": f"nobody{i}@example.test", "password": "sai-mat-khau-1"},
                            headers=h).status_code for i in range(3)]
            other = c.post("/auth/login", json={"email": "nobody9@example.test", "password": "sai-mat-khau-1"},
                           headers={"X-Forwarded-For": "203.0.113.78"}).status_code
        self.assertEqual(codes[-1], 429, codes)
        self.assertNotEqual(other, 429)


# ----------------------------------------------------------------------------- boot guard
class TestProductionBoot(_Env):
    def boot_error(self) -> str:
        try:
            with TestClient(create_app()):
                pass
        except Exception as e:  # ProdConfigError or OtpKeyError
            return f"{type(e).__name__}: {e}"
        return ""

    def test_good_config_boots_and_health_reports(self):
        self.prod()
        self.assertEqual(prod_config.production_boot_errors(), [])
        with TestClient(create_app()) as c:
            h = c.get("/health").json()
        self.assertEqual(h["env"], "production")
        self.assertEqual(h["otp_hmac_key"], "env")
        self.assertEqual(h["auth_test_flags_ignored"], [])
        self.assertTrue(h["git_sha"])
        self.assertEqual((h["gate_months"], h["hard_deny"], h["guest_academy"]), (3, True, False))
        self.assertFalse(h["entitlements"]["checkout_enabled"])
        self.assertNotIn("k" * 48, str(h))

    def test_each_condition_fails_boot(self):
        cases = [
            ({"WELORA_OTP_ECHO": "1"}, "WELORA_OTP_ECHO"),
            ({"WELORA_OTP_ECHO": "0"}, "WELORA_OTP_ECHO"),  # "is set" — any value
            ({"WELORA_GUEST_DEMO": "1"}, "WELORA_GUEST_DEMO"),
            ({"WELORA_OTP_FIXED": "1"}, "WELORA_OTP_FIXED"),
            ({"WELORA_RESET_ECHO": "1"}, "WELORA_RESET_ECHO"),
            ({"WELORA_CHECKOUT_TEST_HOOKS": "1"}, "WELORA_CHECKOUT_TEST_HOOKS"),
            ({"WELORA_RL_IP_MAX": "0"}, "WELORA_RL_IP_MAX"),
            ({"WELORA_RL_WINDOW_S": "-5"}, "WELORA_RL_WINDOW_S"),
            ({"WELORA_PUBLIC_BASE_URL": "http://app4.welora.vn"}, "WELORA_PUBLIC_BASE_URL"),
            ({"WELORA_PUBLIC_BASE_URL": BASE + "/app"}, "WELORA_PUBLIC_BASE_URL"),
            ({"WELORA_CHECKOUT_ENABLED": "1"}, "WELORA_CHECKOUT_ENABLED"),
            ({"WELORA_CHECKOUT_ENABLED": "true"}, "WELORA_CHECKOUT_ENABLED"),
            ({"WELORA_CHECKOUT_ENABLED": "On"}, "WELORA_CHECKOUT_ENABLED"),
        ]
        for extra, name in cases:
            with self.subTest(extra=extra):
                for k in TOUCHED:
                    if k not in ("WELORA_STORE", "WELORA_DB_URL", "WELORA_DEMO_AUTOSEED"):
                        os.environ.pop(k, None)
                self.prod(**extra)
                err = self.boot_error()
                self.assertIn("ProdConfigError", err)
                self.assertIn(name, err)
                self.assertNotIn("k" * 48, err)

    def test_missing_settings_fail_boot(self):
        for name in ("WELORA_GUEST_DEMO", "WELORA_OTP_HMAC_KEY", "WELORA_ADMIN_TOTP_SECRETS", "WELORA_PUBLIC_BASE_URL"):
            with self.subTest(missing=name):
                self.prod()
                os.environ.pop(name)
                self.assertIn(name, self.boot_error())
        self.prod(WELORA_ADMIN_TOTP_SECRETS="no-colon-here")
        self.assertIn("WELORA_ADMIN_TOTP_SECRETS", self.boot_error())

    def test_all_problems_listed_at_once(self):
        os.environ.update({"WELORA_ENV": "production", "WELORA_OTP_HMAC_KEY": "k" * 48, "WELORA_OTP_ECHO": "1"})
        errs = " ".join(prod_config.production_boot_errors())
        for name in ("WELORA_OTP_ECHO", "WELORA_GUEST_DEMO", "WELORA_ADMIN_TOTP_SECRETS", "WELORA_PUBLIC_BASE_URL"):
            self.assertIn(name, errs)

    def test_checkout_off_values_boot(self):
        for v in ("0", "false", "off", ""):
            with self.subTest(value=v):
                self.prod(WELORA_CHECKOUT_ENABLED=v)
                self.assertEqual(prod_config.production_boot_errors(), [])
        self.prod(WELORA_CHECKOUT_ENABLED="yes")
        self.assertIn("WELORA_CHECKOUT_ENABLED", " ".join(prod_config.production_boot_errors()))

    def test_staging_never_fails(self):
        os.environ.update({"WELORA_ENV": "staging", "WELORA_OTP_ECHO": "1", "WELORA_RL_IP_MAX": "0",
                           "WELORA_CHECKOUT_ENABLED": "1"})
        self.assertEqual(prod_config.production_boot_errors(), [])
        self.assertEqual(self.boot_error(), "")


# ----------------------------------------------------------------------------- runbook
class TestRunbook(unittest.TestCase):
    def test_runbook_has_env_table_neon_and_smoke(self):
        text = (ROOT / "docs" / "runbook" / "cutover-app4.md").read_text(encoding="utf-8")
        for name in ("WELORA_ENV", "WELORA_PUBLIC_BASE_URL", "WELORA_OTP_HMAC_KEY", "WELORA_GUEST_DEMO",
                     "WELORA_ADMIN_TOTP_SECRETS", "WELORA_ADMIN_EMAILS", "WELORA_DB_URL", "WELORA_CORS_ORIGINS",
                     "WELORA_ALLOWED_HOSTS", "RESEND_API_KEY", "WELORA_MAIL_FROM", "WELORA_TRIAL_OTP_STUB",
                     "WELORA_CHECKOUT_ENABLED"):
            self.assertIn(f"`{name}`", text, name)
        for word in ("welora-prod", "Neon", "python -m welora.db.migrate", "Smoke", "https://app4.welora.vn",
                     "pre-cutover-YYYYMMDD", "OK migrate", "OK up-to-date", "Starter", "Singapore", "Hạn chế đã biết"):
            self.assertIn(word, text, word)
        self.assertNotRegex(text, r"re_[A-Za-z0-9]{16,}")  # no Resend key
        self.assertNotRegex(text, r"postgres(ql)?://[^<\s`]*:[^<\s`@]+@")  # no DSN with a password


if __name__ == "__main__":
    unittest.main()
