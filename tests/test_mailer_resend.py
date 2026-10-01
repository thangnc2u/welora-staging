"""Mail via Resend HTTP API (Render Free blocks outbound SMTP).

All HTTP is mocked (``httpx.post`` patched) — no network. Fake API key only.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import threading
import unittest
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from tests._db_target import db_env
from welora import checkout as co
from welora import entitlements as ent
from welora import mailer
from welora.api.app import create_app

FAKE_KEY = "re_FAKEtestKEY_0123456789abcdef"
FOUNDER = "founder@example.test"
MAIL_KEYS = ("WELORA_MAIL_PROVIDER", "RESEND_API_KEY", "WELORA_MAIL_FROM", "WELORA_SMTP_HOST", "WELORA_MAIL_SYNC")
APP_KEYS = (
    "WELORA_ENV", "WELORA_STORE", "WELORA_DB_URL", "WELORA_GUEST_DEMO", "WELORA_OTP_FIXED",
    "WELORA_ADMIN_EMAILS", "WELORA_ADMIN_TOTP_SECRETS", "WELORA_CHECKOUT_ENABLED",
)


def _resp(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, json=body, request=httpx.Request("POST", mailer.RESEND_URL))


class _EnvBase(unittest.TestCase):
    keys = MAIL_KEYS

    def setUp(self) -> None:
        self.prev = {k: os.environ.get(k) for k in self.keys}
        for k in self.keys:
            os.environ.pop(k, None)
        mailer.set_sender(None)

    def tearDown(self) -> None:
        mailer.set_sender(None)
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def resend_env(self, **extra) -> None:
        os.environ.update({"WELORA_MAIL_PROVIDER": "resend", "RESEND_API_KEY": FAKE_KEY, **extra})


class TestResendSend(_EnvBase):
    def test_success_payload_headers_timeout(self):
        self.resend_env(WELORA_MAIL_FROM="Welora <onboarding@resend.dev>")
        with mock.patch("httpx.post", return_value=_resp(200, {"id": "49a3999c"})) as post:
            ok = mailer.send("buyer@example.test", "Biên nhận", "Cảm ơn bạn.\nMã đơn WL123")
        self.assertTrue(ok)
        post.assert_called_once()
        args, kw = post.call_args
        self.assertEqual(args[0], "https://api.resend.com/emails")
        self.assertEqual(
            kw["json"],
            {"from": "Welora <onboarding@resend.dev>", "to": ["buyer@example.test"],
             "subject": "Biên nhận", "text": "Cảm ơn bạn.\nMã đơn WL123"},
        )
        self.assertEqual(kw["headers"]["Authorization"], f"Bearer {FAKE_KEY}")
        self.assertEqual(kw["headers"]["Content-Type"], "application/json")
        self.assertTrue(kw["headers"]["User-Agent"])
        self.assertEqual(kw["timeout"], 10.0)

    def test_default_from_when_mail_from_unset(self):
        self.resend_env()
        with mock.patch("httpx.post", return_value=_resp(200, {"id": "x"})) as post:
            mailer.send("a@example.test", "s", "b")
        self.assertEqual(post.call_args.kwargs["json"]["from"], "Welora <onboarding@resend.dev>")

    def test_enqueue_sync_and_async_use_resend(self):
        self.resend_env(WELORA_MAIL_SYNC="1")
        with mock.patch("httpx.post", return_value=_resp(200, {"id": "x"})) as post:
            mailer.enqueue("a@example.test", "s", "b")
            self.assertEqual(post.call_count, 1)
            os.environ.pop("WELORA_MAIL_SYNC")
            done = threading.Event()
            post.side_effect = lambda *a, **k: (done.set(), _resp(200, {"id": "y"}))[1]
            mailer.enqueue("a@example.test", "s", "b")
            self.assertTrue(done.wait(5))
        self.assertEqual(post.call_count, 2)

    def test_custom_sender_still_wins(self):
        self.resend_env()
        got = []
        mailer.set_sender(lambda to, s, b: got.append(to))
        with mock.patch("httpx.post") as post:
            self.assertTrue(mailer.send("a@example.test", "s", "b"))
        post.assert_not_called()
        self.assertEqual(got, ["a@example.test"])


class TestProviderSelection(_EnvBase):
    def sel(self, **env) -> str:
        for k in self.keys:
            os.environ.pop(k, None)
        os.environ.update(env)
        return mailer.mail_provider()

    def test_resolution_order(self):
        smtp = {"WELORA_SMTP_HOST": "smtp.gmail.com"}
        key = {"RESEND_API_KEY": FAKE_KEY}
        self.assertEqual(self.sel(), "log")
        self.assertEqual(self.sel(**smtp), "smtp")
        self.assertEqual(self.sel(**key), "resend")  # configured (provider unset)
        self.assertEqual(self.sel(**key, **smtp), "resend")  # resend > smtp
        self.assertEqual(self.sel(WELORA_MAIL_PROVIDER="resend", **key, **smtp), "resend")
        self.assertEqual(self.sel(WELORA_MAIL_PROVIDER="RESEND", **key), "resend")
        self.assertEqual(self.sel(WELORA_MAIL_PROVIDER="resend", **smtp), "smtp")  # no key → fallback
        self.assertEqual(self.sel(WELORA_MAIL_PROVIDER="resend"), "log")
        self.assertEqual(self.sel(WELORA_MAIL_PROVIDER="smtp", **key, **smtp), "smtp")  # explicit smtp
        self.assertEqual(self.sel(WELORA_MAIL_PROVIDER="smtp", **key), "log")
        self.assertEqual(self.sel(WELORA_MAIL_PROVIDER="log", **key, **smtp), "log")
        self.assertEqual(self.sel(RESEND_API_KEY="   ", **smtp), "smtp")  # blank key ignored

    def test_senders_dispatch(self):
        self.sel(**{"RESEND_API_KEY": FAKE_KEY})
        self.assertIs(mailer.current_sender(), mailer._resend_send)
        self.sel(WELORA_SMTP_HOST="smtp.example.test")
        self.assertIs(mailer.current_sender(), mailer._smtp_send)
        self.sel()
        self.assertIs(mailer.current_sender(), mailer._log_send)

    def test_resend_selected_without_key_warns_and_falls_back(self):
        self.sel(WELORA_MAIL_PROVIDER="resend")
        with mock.patch("httpx.post") as post, self.assertLogs("welora.mailer", "WARNING") as cm:
            self.assertTrue(mailer.send("a@example.test", "s", "b"))  # log-only "send" succeeds
        post.assert_not_called()
        self.assertIn("RESEND_API_KEY is not set", "\n".join(cm.output))


class TestFailureLogging(_EnvBase):
    BODY = "Mã đăng nhập quản trị Welora của bạn: 482913"

    def run_fail(self, **patch_kw):
        self.resend_env()
        root = logging.getLogger()
        with mock.patch("httpx.post", **patch_kw), self.assertLogs(root, "DEBUG") as cm:
            ok = mailer.send(FOUNDER, "Welora · Mã đăng nhập quản trị", self.BODY)
        self.assertFalse(ok)
        out = "\n".join(cm.output)
        self.assertNotIn(FAKE_KEY, out)
        self.assertNotIn("482913", out)
        self.assertNotIn(self.BODY, out)
        self.assertNotIn(FOUNDER, out)
        self.assertIn("f***@example.test", out)
        warn = [r for r in cm.records if r.levelno == logging.WARNING and r.name == "welora.mailer"]
        self.assertEqual(len(warn), 1, out)
        return warn[0].getMessage()

    def test_http_403_logs_status_and_error_name_only(self):
        body = {"statusCode": 403, "name": "validation_error",
                "message": f"You can only send testing emails to your own email address ({FOUNDER})."}
        msg = self.run_fail(return_value=_resp(403, body))
        self.assertIn("provider=resend", msg)
        self.assertIn("status=403", msg)
        self.assertIn("error=validation_error", msg)
        self.assertNotIn("testing emails", msg)  # free-text provider message never logged

    def test_http_429_and_500(self):
        self.assertIn("status=429", self.run_fail(return_value=_resp(429, {"name": "rate_limit_exceeded"})))
        self.assertIn("status=500", self.run_fail(
            return_value=httpx.Response(500, text="oops", request=httpx.Request("POST", mailer.RESEND_URL))))

    def test_network_error_logs_class_name(self):
        msg = self.run_fail(side_effect=httpx.ConnectTimeout(f"timed out Bearer {FAKE_KEY}"))
        self.assertIn("provider=resend", msg)
        self.assertIn("error=ConnectTimeout", msg)

    def test_smtp_failure_also_masked(self):
        os.environ["WELORA_SMTP_HOST"] = "smtp.example.test"
        with mock.patch("smtplib.SMTP", side_effect=OSError("Network is unreachable")), \
                self.assertLogs("welora.mailer", "WARNING") as cm:
            self.assertFalse(mailer.send(FOUNDER, "s", self.BODY))
        out = "\n".join(cm.output)
        self.assertIn("provider=smtp", out)
        self.assertIn("error=OSError", out)
        self.assertNotIn(FOUNDER, out)


class _AppBase(_EnvBase):
    keys = MAIL_KEYS + APP_KEYS

    def setUp(self) -> None:
        super().setUp()
        self.tmp = tempfile.mkdtemp(prefix="welora-mail-")
        os.environ.update({"WELORA_ENV": "staging", "WELORA_GUEST_DEMO": "0", "WELORA_MAIL_SYNC": "1",
                           **db_env(self.tmp)})
        ent.reset_state_for_tests()
        co.reset_for_tests()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        ent.reset_state_for_tests()
        co.reset_for_tests()
        super().tearDown()
        shutil.rmtree(self.tmp, ignore_errors=True)


class TestAdminOtpViaResend(_AppBase):
    def test_otp_delivered_through_resend_then_login_admin(self):
        self.resend_env(WELORA_ADMIN_EMAILS=FOUNDER)
        with mock.patch("httpx.post", return_value=_resp(200, {"id": "x"})) as post:
            r = self.client.post("/auth/email-otp/request", json={"email": FOUNDER})
        self.assertEqual(r.status_code, 200)
        post.assert_called_once()
        sent = post.call_args.kwargs["json"]
        self.assertEqual(sent["to"], [FOUNDER])
        code = re.search(r"\b(\d{6})\b", sent["text"]).group(1)
        self.assertNotIn(code, r.text)
        v = self.client.post("/auth/email-otp/verify", json={"challenge_id": r.json()["challenge_id"], "code": code})
        self.assertEqual(v.status_code, 200, v.text)
        self.assertEqual(v.json()["role"], "admin")

    def test_otp_response_generic_when_resend_fails(self):
        self.resend_env(WELORA_ADMIN_EMAILS=FOUNDER)

        def shape(r):
            self.assertEqual(r.status_code, 200)
            b = r.json()
            return sorted(b), b["message"]

        root = logging.getLogger()
        with mock.patch("httpx.post", return_value=_resp(200, {"id": "x"})):
            ok_shape = shape(self.client.post("/auth/email-otp/request", json={"email": FOUNDER}))
        for kw in ({"return_value": _resp(403, {"name": "validation_error"})},
                   {"side_effect": httpx.ConnectError("boom")}):
            with mock.patch("httpx.post", **kw) as post, self.assertLogs(root, "DEBUG") as cm:
                failed = self.client.post("/auth/email-otp/request", json={"email": FOUNDER})
            post.assert_called_once()
            self.assertEqual(shape(failed), ok_shape)
            out = "\n".join(cm.output)
            self.assertIn("mail send failed provider=resend", out)
            self.assertNotIn(FAKE_KEY, out)
            self.assertIsNone(re.search(r"\b\d{6}\b", out.replace("f***@example.test", "")), out)
        with mock.patch("httpx.post") as post:
            unlisted = self.client.post("/auth/email-otp/request", json={"email": "nobody@example.test"})
        post.assert_not_called()
        self.assertEqual(shape(unlisted), ok_shape)


class TestHealthMailProvider(_AppBase):
    def test_health_reports_provider_without_secrets(self):
        cases = [
            ({}, "log"),
            ({"WELORA_SMTP_HOST": "smtp.gmail.com"}, "smtp"),
            ({"WELORA_MAIL_PROVIDER": "resend", "RESEND_API_KEY": FAKE_KEY, "WELORA_SMTP_HOST": "smtp.gmail.com"}, "resend"),
            ({"WELORA_MAIL_PROVIDER": "resend"}, "log"),
        ]
        for env, want in cases:
            for k in MAIL_KEYS:
                if k != "WELORA_MAIL_SYNC":
                    os.environ.pop(k, None)
            os.environ.update(env)
            body = self.client.get("/health").json()
            self.assertEqual(body["mail_provider"], want, env)
            self.assertIn(body["mail_provider"], mailer.PROVIDERS)
            self.assertNotIn(FAKE_KEY, json.dumps(body))
            self.assertEqual(body["entitlements"]["checkout_enabled"], False)


class TestRenderYamlAndConstraints(unittest.TestCase):
    def test_render_yaml_sync_false_no_secret(self):
        from pathlib import Path
        yml = (Path(__file__).resolve().parents[1] / "render.yaml").read_text(encoding="utf-8")
        for k in ("WELORA_MAIL_PROVIDER", "RESEND_API_KEY"):
            m = re.search(rf"- key: {k}\n\s+sync: false", yml)
            self.assertIsNotNone(m, k)
        self.assertNotRegex(yml, r"re_[A-Za-z0-9]{8,}")
        self.assertNotIn("WELORA_CHECKOUT_ENABLED", yml)


if __name__ == "__main__":
    unittest.main()
