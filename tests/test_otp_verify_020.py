"""Ticket "GP — Xác minh OTP sau đăng ký + phone OTP gắn tài khoản có sẵn" (migration 020).

1. POST /auth/register (e-mail or phone) → a verification code bound to THAT user_id (no second
   account); e-mail via the mailer, phone via welora.sms (disabled → no code, polite VI notice).
   /auth/verify/request (resend) + /auth/verify/confirm: bearer session only, hashed code, TTL,
   5 checks per code (atomic reserve), atomic consume, resend cooldown, per-user + per-IP limits.
2. Success sets users.email_verified_at / users.phone_verified_at → auth.has_verified_contact is true
   → the KUAT budgets use the verified kind (no guest-network buckets).
3. FE: /app/verify right after register + the «Xác minh tài khoản» banner (skippable).
4. Phone-OTP login attaches to the existing account matched by E.164 (legacy '0…' rows too) when
   that account's phone is verified; an unverified password account → 409 (takeover guard);
   phone_e164_conflicts numbers stay 409 PHONE_CONFLICT_USE_EMAIL.
5. Production refuses WELORA_OTP_ECHO / WELORA_OTP_FIXED / WELORA_RESET_ECHO in code; SMS disabled.
Enumeration: identical bodies + bounded timing for existing vs unknown targets.
Runs on SQLite, or PG17 via WELORA_TEST_POSTGRES_URL (tests/_db_target.py).
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import re
import shutil
import statistics
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient

from tests._db_target import db_env
from welora import auth as auth_svc
from welora import contact_verify as cv
from welora import mailer, sms
from welora.api.app import create_app
from welora.db.connection import detect_dialect, get_connection
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
PW = "matkhau-xacminh-1"
ENV_KEYS = (
    "WELORA_ENV", "WELORA_OTP_HMAC_KEY", "WELORA_STORE", "WELORA_DB_URL", "WELORA_GUEST_DEMO", "WELORA_OTP_FIXED", "WELORA_OTP_ECHO",
    "WELORA_RESET_ECHO", "WELORA_MAIL_SYNC", "WELORA_ADMIN_EMAILS", "WELORA_RL_WINDOW_S", "WELORA_RL_TARGET_MAX",
    "WELORA_RL_IP_MAX", "WELORA_RL_LOGIN_PAIR_MAX", "WELORA_RL_LOGIN_ACCOUNT_MAX", "WELORA_RL_LOGIN_IP_MAX",
    "WELORA_RL_VERIFY_TARGET_MAX", "WELORA_RL_VERIFY_IP_MAX", "WELORA_RL_VERIFY_SEND_USER_MAX",
    "WELORA_RL_VERIFY_SEND_IP_MAX", "WELORA_RL_VERIFY_CONFIRM_USER_MAX", "WELORA_RL_VERIFY_CONFIRM_IP_MAX",
    "WELORA_VERIFY_OTP_TTL_S", "WELORA_VERIFY_MAX_ATTEMPTS", "WELORA_VERIFY_RESEND_COOLDOWN_S",
    "WELORA_SMS_PROVIDER", "WELORA_MAIL_PROVIDER", "WELORA_DEMO_AUTOSEED", "WELORA_CHECKOUT_ENABLED",
    "WELORA_VERIFY_DAILY_SEND_MAX", "WELORA_VERIFY_DAILY_FAIL_MAX", "WELORA_ADMIN_TOTP_SECRETS", "WELORA_PUBLIC_BASE_URL",
)
CODE_RE = re.compile(r"\b(\d{6})\b")


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="welora-020-")
        os.environ.update({"WELORA_ENV": "staging", "WELORA_GUEST_DEMO": "1", "WELORA_MAIL_SYNC": "1",
                           "WELORA_DEMO_AUTOSEED": "0", **db_env(self.tmp)})
        self.mail: list[tuple[str, str, str]] = []
        self.texts: list[tuple[str, str]] = []
        mailer.set_sender(lambda to, sub, body: self.mail.append((to, sub, body)))  # fake provider (tests only)
        self.client = TestClient(create_app())
        auth_svc.ensure_auth_schema()

    def tearDown(self) -> None:
        mailer.set_sender(None)
        sms.set_sender(None)
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    # -- helpers
    def q(self, sql, params=()):
        conn = get_connection(None)
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def x(self, sql, params=()):
        conn = get_connection(None)
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    @staticmethod
    def ip(n=None):
        return {"CF-Connecting-IP": n or f"198.51.100.{uuid.uuid4().int % 250 + 1}"}

    def h(self, tok, ip=None):
        return {"Authorization": "Bearer " + tok, **self.ip(ip)}

    def sms_on(self):
        sms.set_sender(lambda phone, body: self.texts.append((phone, body)))  # fake SMS (tests only)

    def register(self, ident, password=PW, ip=None):
        body = {"password": password, **({"email": ident} if "@" in ident else {"phone": ident})}
        r = self.client.post("/auth/register", json=body, headers=self.ip(ip))
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def last_code(self, to=None):
        box = [m for m in self.mail if to is None or m[0] == to]
        self.assertTrue(box, "no verification mail captured")
        return CODE_RE.search(box[-1][2]).group(1)

    def last_sms_code(self):
        self.assertTrue(self.texts, "no SMS captured")
        return CODE_RE.search(self.texts[-1][1]).group(1)

    def confirm(self, tok, code, challenge_id=None, ip=None):
        body = {"code": code}
        if challenge_id is not None:
            body["challenge_id"] = challenge_id
        return self.client.post("/auth/verify/confirm", json=body, headers=self.h(tok, ip))

    def resend(self, tok, channel=None, ip=None):
        return self.client.post("/auth/verify/request", json=({"channel": channel} if channel else {}),
                                headers=self.h(tok, ip))

    def me(self, tok):
        r = self.client.get("/auth/me", headers={"Authorization": "Bearer " + tok})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def otp_login(self, phone, ip=None):
        os.environ["WELORA_OTP_FIXED"] = "1"  # tests only — production ignores it (TestProdGuard)
        hdr = self.ip(ip)
        ch = self.client.post("/auth/otp/request", json={"phone": phone}, headers=hdr)
        self.assertEqual(ch.status_code, 200, ch.text)
        return self.client.post("/auth/otp/verify", json={"challenge_id": ch.json()["challenge_id"], "code": "123456"},
                                headers=hdr)

    def users(self):
        return self.q("SELECT COUNT(*) AS n FROM users")[0]["n"]

    def kind(self, uid):
        from welora import academy_store

        conn = get_connection(None)
        try:
            buckets, kind = academy_store._keys(conn, uid, "N02-01", "203.0.113.77")
            return kind, sorted({b[0] for b in buckets})
        finally:
            conn.close()

    def verified(self, uid):
        conn = get_connection(None)
        try:
            row = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
            return auth_svc.has_verified_contact(conn, row)
        finally:
            conn.close()


# =========================================================================== item 1 + 2 (e-mail)
class TestEmailVerification(_Base):
    def test_register_issues_code_bound_to_the_new_account(self):
        n0 = self.users()
        out = self.register("lan.anh@example.test")
        self.assertEqual(self.users(), n0 + 1)  # no second account
        v = out["verification"]
        self.assertEqual((v["channel"], v["delivery"], v["sms_enabled"]), ("email", "email", False))
        self.assertEqual(v["target_masked"], mailer.mask_email("lan.anh@example.test"))
        self.assertNotIn("lan.anh@", json.dumps(v))
        self.assertTrue(re.search(r"[ạảãáàâầấậẩẫăằắặẳẵđêềếệểễôồốộổỗơờớợởỡưừứựửữ]", v["message"]))
        self.assertNotIn("code", v)
        self.assertNotIn("pilot_code", json.dumps(out))
        rows = self.q("SELECT * FROM contact_verifications WHERE user_id=?", (out["user_id"],))
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["channel"], rows[0]["target"], rows[0]["consumed"]), ("email", "lan.anh@example.test", 0))
        code = self.last_code("lan.anh@example.test")
        self.assertTrue(rows[0]["code_hash"].startswith("hmac256:"))
        self.assertNotIn(code, rows[0]["code_hash"])
        self.assertEqual(self.mail[-1][1], cv.MAIL_SUBJECT)
        self.assertIn("bỏ qua email này", self.mail[-1][2])

    def test_confirm_sets_email_verified_and_verified_budget(self):
        out = self.register("minh.chau@example.test")
        uid, tok = out["user_id"], out["token"]
        me = self.me(tok)
        self.assertEqual((me["verified"], me["email_verified"], me["verify_eligible"], me["can_verify_now"]),
                         (False, False, True, True))
        self.assertFalse(self.verified(uid))
        kind, scopes = self.kind(uid)
        self.assertEqual(kind, "unverified")
        self.assertIn("kuat_guest_ip", scopes)  # unverified accounts share the guest network bucket
        r = self.confirm(tok, self.last_code(), out["verification"]["challenge_id"])
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["verified"], r.json()["email_verified"]), (True, True))
        self.assertTrue(self.q("SELECT email_verified_at FROM users WHERE user_id=?", (uid,))[0]["email_verified_at"])
        self.assertTrue(self.verified(uid))  # auth.has_verified_contact
        kind, scopes = self.kind(uid)
        self.assertEqual(kind, "verified")  # KUAT: verified budget
        self.assertNotIn("kuat_guest_ip", scopes)
        self.assertEqual(self.me(tok)["verified"], True)
        # code is single-use
        again = self.confirm(tok, self.last_code())
        self.assertEqual((again.status_code, again.json()["detail"]["error_code"]), (400, "VERIFY_CODE_INVALID"))
        # already verified → resend refused politely
        r = self.resend(tok)
        self.assertEqual((r.status_code, r.json()["detail"]["error_code"]), (409, "ALREADY_VERIFIED"))

    def test_confirm_without_challenge_id_uses_latest_open_code(self):
        out = self.register("khong.id@example.test")
        r = self.confirm(out["token"], self.last_code())
        self.assertEqual(r.status_code, 200, r.text)

    def test_wrong_code_attempt_limit(self):
        out = self.register("sai.ma@example.test")
        tok, cid = out["token"], out["verification"]["challenge_id"]
        good = self.last_code()
        bad = "000000" if good != "000000" else "111111"
        codes = []
        for _ in range(5):
            r = self.confirm(tok, bad, cid)
            codes.append((r.status_code, r.json()["detail"]["error_code"]))
        self.assertEqual(codes, [(400, "VERIFY_CODE_INVALID")] * 4 + [(429, "VERIFY_TOO_MANY_ATTEMPTS")])
        r = self.confirm(tok, good, cid)  # the right code no longer helps
        self.assertEqual((r.status_code, r.json()["detail"]["error_code"]), (429, "VERIFY_TOO_MANY_ATTEMPTS"))
        self.assertEqual(self.q("SELECT attempts FROM contact_verifications WHERE challenge_id=?", (cid,))[0]["attempts"], 5)
        self.assertFalse(self.verified(out["user_id"]))
        self.assertIn("Gửi lại mã", r.json()["detail"]["message"])

    def test_expired_code_refused(self):
        out = self.register("het.han@example.test")
        cid = out["verification"]["challenge_id"]
        self.x("UPDATE contact_verifications SET expires_at=? WHERE challenge_id=?", ("2020-01-01T00:00:00.000000+00:00", cid))
        r = self.confirm(out["token"], self.last_code(), cid)
        self.assertEqual((r.status_code, r.json()["detail"]["error_code"]), (400, "VERIFY_CODE_INVALID"))
        self.assertFalse(self.verified(out["user_id"]))

    def test_ttl_env(self):
        os.environ["WELORA_VERIFY_OTP_TTL_S"] = "120"
        out = self.register("ttl@example.test")
        row = self.q("SELECT created_at, expires_at FROM contact_verifications WHERE user_id=?", (out["user_id"],))[0]
        self.assertAlmostEqual(cv._ts(row["expires_at"]) - cv._ts(row["created_at"]), 120, delta=1)

    def test_resend_cooldown_supersedes_and_rate_limit(self):
        out = self.register("gui.lai@example.test")
        tok = out["token"]
        first = self.last_code()
        r = self.resend(tok)
        self.assertEqual((r.status_code, r.json()["detail"]["error_code"]), (429, "VERIFY_RESEND_COOLDOWN"))
        self.assertIn("Retry-After", r.headers)
        os.environ["WELORA_VERIFY_RESEND_COOLDOWN_S"] = "0"
        r = self.resend(tok)
        self.assertEqual(r.status_code, 200, r.text)
        second = self.last_code()
        if first != second:
            old = self.confirm(tok, first, out["verification"]["challenge_id"])  # superseded
            self.assertEqual(old.status_code, 400)
        states = sorted(x["consumed"] for x in self.q("SELECT consumed FROM contact_verifications WHERE user_id=?",
                                                      (out["user_id"],)))
        self.assertEqual(states, [0, 2])  # one open, one superseded
        ok = self.confirm(tok, second, r.json()["challenge_id"])
        self.assertEqual(ok.status_code, 200, ok.text)
        # per-user send limit (DB-backed auth_rate_events)
        out2 = self.register("gioi.han@example.test")
        os.environ["WELORA_RL_VERIFY_SEND_USER_MAX"] = "2"
        st = [self.resend(out2["token"]).status_code for _ in range(3)]
        self.assertEqual(st, [200, 200, 429])
        self.assertEqual(self.resend(out2["token"]).json()["detail"]["error_code"], "RATE_LIMITED")
        self.assertGreater(self.q("SELECT COUNT(*) AS n FROM auth_rate_events WHERE action='verify_request'")[0]["n"], 0)

    def test_confirm_rate_limited_per_user_and_ip(self):
        os.environ["WELORA_RL_VERIFY_CONFIRM_USER_MAX"] = "3"
        out = self.register("rl.confirm@example.test")
        st = [self.confirm(out["token"], "000001").status_code for _ in range(4)]
        self.assertEqual(st[-1], 429)
        os.environ["WELORA_RL_VERIFY_CONFIRM_USER_MAX"] = "100"
        os.environ["WELORA_RL_VERIFY_CONFIRM_IP_MAX"] = "2"
        a = self.register("rl.ip.a@example.test")
        b = self.register("rl.ip.b@example.test")
        ip = "203.0.113.200"
        st = [self.confirm(t, "000001", ip=ip).status_code for t in (a["token"], b["token"], a["token"])]
        self.assertEqual(st[-1], 429)

    def test_requires_session(self):
        self.assertEqual(self.client.post("/auth/verify/request", json={}).status_code, 401)
        self.assertEqual(self.client.post("/auth/verify/confirm", json={"code": "123456"}).status_code, 401)
        self.assertEqual(self.client.get("/auth/verify/status").status_code, 401)

    def test_foreign_challenge_is_indistinguishable_from_unknown(self):
        a = self.register("chu.a@example.test")
        code_a = self.last_code("chu.a@example.test")
        b = self.register("chu.b@example.test")
        foreign = self.confirm(b["token"], code_a, a["verification"]["challenge_id"])
        unknown = self.confirm(b["token"], code_a, str(uuid.uuid4()))
        self.assertEqual((foreign.status_code, foreign.json()), (unknown.status_code, unknown.json()))
        self.assertFalse(self.verified(a["user_id"]))
        self.assertFalse(self.verified(b["user_id"]))
        # A's challenge untouched by B's tries
        self.assertEqual(self.q("SELECT attempts FROM contact_verifications WHERE challenge_id=?",
                                (a["verification"]["challenge_id"],))[0]["attempts"], 0)

    def test_contact_changed_after_send_refused(self):
        out = self.register("doi.email@example.test")
        self.x("UPDATE users SET email=? WHERE user_id=?", ("khac@example.test", out["user_id"]))
        r = self.confirm(out["token"], self.last_code())
        self.assertEqual(r.status_code, 400)
        self.assertFalse(self.q("SELECT email_verified_at FROM users WHERE user_id=?", (out["user_id"],))[0]["email_verified_at"])

    def test_demo_device_guest_not_offered(self):
        dev = self.client.post("/auth/device", json={"device_id": "web-" + uuid.uuid4().hex[:12]}).json()
        me = self.me(dev["token"])
        self.assertEqual((me["verify_eligible"], me["verified"]), (False, False))
        r = self.resend(dev["token"])
        self.assertEqual((r.status_code, r.json()["detail"]["error_code"]), (400, "VERIFY_NOT_ELIGIBLE"))
        demo = auth_svc.register_guest(email="persona@welora.demo", password=PW, role="demo")
        self.assertEqual(self.me(demo["token"])["verify_eligible"], False)
        self.assertEqual(self.resend(demo["token"]).status_code, 400)

    def test_mail_delivery_is_async_and_never_blocks_register(self):
        os.environ.pop("WELORA_MAIL_SYNC", None)
        gate = threading.Event()
        mailer.set_sender(lambda to, sub, body: gate.wait(3))  # slow provider
        t = time.perf_counter()
        self.register("cham@example.test")
        self.assertLess(time.perf_counter() - t, 2.0)
        gate.set()

    def test_status_endpoint(self):
        out = self.register("trang.thai@example.test")
        s = self.client.get("/auth/verify/status", headers=self.h(out["token"])).json()
        self.assertEqual(s["pending"]["challenge_id"], out["verification"]["challenge_id"])
        self.assertEqual(s["email_masked"], mailer.mask_email("trang.thai@example.test"))
        self.assertEqual(s["verify_channels"], ["email"])


# =========================================================================== SMS disabled / enabled
class TestSms(_Base):
    def test_sms_disabled_by_default_and_unknown_provider_stays_disabled(self):
        self.assertFalse(sms.enabled())
        self.assertFalse(auth_svc.sms_provider_configured())
        os.environ["WELORA_SMS_PROVIDER"] = "twilio"  # not implemented → still disabled
        self.assertEqual(sms.provider(), "none")
        self.assertFalse(sms.send("+84900000001", "x"))
        self.assertFalse(sms.enqueue("+84900000001", "x"))
        self.assertFalse(self.client.get("/health").json()["sms_enabled"])

    def test_phone_register_sms_off_no_code_polite_notice(self):
        out = self.register("0912000111")
        v = out["verification"]
        self.assertEqual((v["channel"], v["delivery"], v["challenge_id"], v["sms_enabled"]), ("phone", "none", None, False))
        self.assertIn("SMS", v["message"])
        self.assertIn("có thể xác minh sau", v["message"])
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM contact_verifications")[0]["n"], 0)
        me = self.me(out["token"])
        self.assertEqual((me["verified"], me["verify_eligible"], me["can_verify_now"]), (False, True, False))
        r = self.resend(out["token"])
        self.assertEqual((r.status_code, r.json()["delivery"], r.json()["challenge_id"]), (200, "none", None))
        ch = self.client.post("/auth/otp/request", json={"phone": "0912000111"}, headers=self.ip()).json()
        self.assertEqual((ch["sms_enabled"], ch["sms_sent"]), (False, False))
        self.assertEqual(self.texts, [])

    def test_phone_verification_when_sms_enabled_later(self):
        out = self.register("0912000222")
        self.sms_on()
        r = self.resend(out["token"], "phone")
        self.assertEqual((r.status_code, r.json()["delivery"]), (200, "sms"), r.text)
        self.assertEqual(self.texts[-1][0], "+84912000222")
        ok = self.confirm(out["token"], self.last_sms_code(), r.json()["challenge_id"])
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertTrue(ok.json()["phone_verified"])
        self.assertTrue(self.verified(out["user_id"]))
        self.assertEqual(self.kind(out["user_id"])[0], "verified")

    def test_email_and_phone_account_email_first_then_phone(self):
        self.sms_on()
        r = self.client.post("/auth/register", json={"email": "hai.kenh@example.test", "phone": "0912000333",
                                                     "password": PW}, headers=self.ip())
        out = r.json()
        self.assertEqual(out["verification"]["channel"], "email")
        self.assertEqual(self.confirm(out["token"], self.last_code()).status_code, 200)
        p = self.resend(out["token"], "phone")
        self.assertEqual((p.status_code, p.json()["channel"]), (200, "phone"))
        self.assertEqual(self.confirm(out["token"], self.last_sms_code()).status_code, 200)
        me = self.me(out["token"])
        self.assertEqual((me["email_verified"], me["phone_verified"]), (True, True))


# =========================================================================== item 4 (phone OTP login)
class TestPhoneOtpAttach(_Base):
    def _verify_phone(self, out):
        self.sms_on()
        r = self.resend(out["token"], "phone")
        self.assertEqual(self.confirm(out["token"], self.last_sms_code(), r.json()["challenge_id"]).status_code, 200)
        sms.set_sender(None)

    def test_verified_phone_account_gets_the_otp_login(self):
        out = self.register("0913000111")
        self._verify_phone(out)
        n0 = self.users()
        r = self.otp_login("+84 913 000 111")
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual((r.json()["user_id"], r.json()["attached"], r.json()["created"]), (out["user_id"], True, False))
        self.assertEqual(self.users(), n0)  # no separate account
        # the password still works for the same account
        login = self.client.post("/auth/login", json={"phone": "0913000111", "password": PW}, headers=self.ip())
        self.assertEqual(login.json()["user_id"], out["user_id"])

    def test_unverified_password_account_refused_no_session_no_account(self):
        out = self.register("0913000222")
        n0 = self.users()
        tokens0 = self.q("SELECT COUNT(*) AS n FROM auth_tokens")[0]["n"]
        r = self.otp_login("0913000222")
        self.assertEqual((r.status_code, r.json()["detail"]["error_code"]), (409, "PHONE_NOT_VERIFIED_USE_PASSWORD"))
        self.assertIn("đăng nhập bằng mật khẩu", r.json()["detail"]["message"])
        self.assertNotIn("token", r.json()["detail"])
        self.assertEqual(self.users(), n0)
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM auth_tokens")[0]["n"], tokens0)
        self.assertFalse(self.q("SELECT phone_verified_at FROM users WHERE user_id=?", (out["user_id"],))[0]["phone_verified_at"])
        # the owner logs in with the password, verifies the number → OTP login now attaches
        self._verify_phone(out)
        r = self.otp_login("0913000222")
        self.assertEqual((r.status_code, r.json()["user_id"]), (200, out["user_id"]))

    def test_legacy_local_format_rows(self):
        # verified legacy row stored as '0…' → attached + normalised to E.164
        self.x("INSERT INTO users(user_id, display_name, device_id, phone, password_hash, role, phone_verified_at) "
               "VALUES ('leg-ok','leg','guest:leg-ok','0914000111',?,'guest','2026-09-01T00:00:00+00:00')",
               (auth_svc._hash_password(PW),))
        r = self.otp_login("+84914000111")
        self.assertEqual((r.status_code, r.json()["user_id"]), (200, "leg-ok"), r.text)
        self.assertEqual(self.q("SELECT phone FROM users WHERE user_id='leg-ok'")[0]["phone"], "+84914000111")
        # unverified legacy '0…' password row → refused (takeover guard), nothing created
        self.x("INSERT INTO users(user_id, display_name, device_id, phone, password_hash, role) "
               "VALUES ('leg-no','leg','guest:leg-no','0914000222',?,'guest')", (auth_svc._hash_password(PW),))
        n0 = self.users()
        r = self.otp_login("+84914000222")
        self.assertEqual((r.status_code, r.json()["detail"]["error_code"]), (409, "PHONE_NOT_VERIFIED_USE_PASSWORD"))
        self.assertEqual(self.users(), n0)
        self.assertEqual(self.q("SELECT phone FROM users WHERE user_id='leg-no'")[0]["phone"], "0914000222")

    def test_new_number_creates_one_verified_account_reused_next_time(self):
        r1 = self.otp_login("0915000111")
        self.assertEqual((r1.status_code, r1.json()["created"]), (200, True))
        uid = r1.json()["user_id"]
        row = self.q("SELECT phone, phone_verified_at, password_hash FROM users WHERE user_id=?", (uid,))[0]
        self.assertEqual(row["phone"], "+84915000111")
        self.assertTrue(row["phone_verified_at"])
        self.assertTrue(self.verified(uid))
        r2 = self.otp_login("+84915000111")
        self.assertEqual((r2.json()["user_id"], r2.json()["created"], r2.json()["attached"]), (uid, False, True))
        # the number is now taken for password registration (one account per number)
        r = self.client.post("/auth/register", json={"phone": "0915000111", "password": PW}, headers=self.ip())
        self.assertEqual(r.status_code, 400)

    def test_legacy_phone_otp_account_kept(self):
        # pre-020 phone-OTP account: phone only in its consumed challenges
        self.x("INSERT INTO users(user_id, display_name, device_id) VALUES ('otp-old','0916000111','phone:abc')")
        self.x("INSERT INTO otp_challenges(challenge_id, phone, code, expires_at, consumed, user_id, created_at) "
               "VALUES ('old-ch','0916000111','x','2020-01-01T00:00:00+00:00',1,'otp-old','2020-01-01T00:00:00+00:00')")
        r = self.otp_login("+84916000111")
        self.assertEqual((r.status_code, r.json()["user_id"]), (200, "otp-old"))
        row = self.q("SELECT phone, phone_verified_at FROM users WHERE user_id='otp-old'")[0]
        self.assertEqual(row["phone"], "+84916000111")  # recorded on the row now
        self.assertTrue(row["phone_verified_at"])

    def test_legacy_otp_owner_wins_over_unverified_password_account(self):
        self.x("INSERT INTO users(user_id, display_name, device_id) VALUES ('otp-own','x','phone:def')")
        self.x("INSERT INTO otp_challenges(challenge_id, phone, code, expires_at, consumed, user_id, created_at) "
               "VALUES ('own-ch','+84916000222','x','2020-01-01T00:00:00+00:00',1,'otp-own','2020-01-01T00:00:00+00:00')")
        pw_acc = self.register("0916000222")  # someone registered the number with a password, unverified
        r = self.otp_login("0916000222")
        self.assertEqual((r.status_code, r.json()["user_id"]), (200, "otp-own"))  # existing behaviour
        row = self.q("SELECT phone, phone_verified_at FROM users WHERE user_id=?", (pw_acc["user_id"],))[0]
        self.assertFalse(row["phone_verified_at"])  # password account untouched
        self.assertFalse(self.q("SELECT phone FROM users WHERE user_id='otp-own'")[0]["phone"])  # number taken → not copied

    def test_conflicted_numbers_stay_blocked(self):
        self.x("INSERT INTO users(user_id, display_name, device_id, phone, password_hash, role, phone_verified_at) "
               "VALUES ('cf-a','a','guest:cf-a','0917000111',?,'guest','2026-09-01T00:00:00+00:00')",
               (auth_svc._hash_password(PW),))
        self.x("INSERT INTO phone_e164_conflicts(id, table_name, normalized, user_ids, raw_values, detected_at) "
               "VALUES ('c20','users','+84917000111','[\"cf-a\",\"cf-b\"]','[]','2026-10-01T00:00:00+00:00')")
        n0 = self.users()
        r = self.otp_login("0917000111")
        self.assertEqual((r.status_code, r.json()["detail"]["error_code"]), (409, "PHONE_CONFLICT_USE_EMAIL"))
        self.assertEqual(self.users(), n0)
        # verification of a conflicted number is refused as well
        self.x("INSERT INTO users(user_id, display_name, device_id, phone, password_hash, role) "
               "VALUES ('cf-c','c','guest:cf-c','+84917000222',?,'guest')", (auth_svc._hash_password(PW),))
        self.x("INSERT INTO phone_e164_conflicts(id, table_name, normalized, user_ids, raw_values, detected_at) "
               "VALUES ('c21','users','+84917000222','[\"cf-c\",\"cf-d\"]','[]','2026-10-01T00:00:00+00:00')")
        self.sms_on()
        with self.assertRaises(cv.VerifyError) as e:
            cv.issue("cf-c", "phone")
        self.assertEqual((e.exception.status, e.exception.code), (409, "PHONE_CONFLICT_USE_EMAIL"))
        # a code issued BEFORE the conflict was reported cannot verify the number afterwards
        self.x("DELETE FROM phone_e164_conflicts WHERE id='c21'")
        issued = cv.issue("cf-c", "phone")
        self.x("INSERT INTO phone_e164_conflicts(id, table_name, normalized, user_ids, raw_values, detected_at) "
               "VALUES ('c22','users','+84917000222','[\"cf-c\",\"cf-d\"]','[]','2026-10-01T00:00:00+00:00')")
        with self.assertRaises(cv.VerifyError) as e:
            cv.confirm("cf-c", self.last_sms_code(), issued["challenge_id"])
        self.assertEqual(e.exception.code, "PHONE_CONFLICT_USE_EMAIL")
        self.assertFalse(self.q("SELECT phone_verified_at FROM users WHERE user_id='cf-c'")[0]["phone_verified_at"])

    def test_admin_gate_still_applies(self):
        os.environ["WELORA_ADMIN_EMAILS"] = "boss@example.test"
        self.x("INSERT INTO users(user_id, display_name, device_id, email, phone, role, email_verified_at, phone_verified_at) "
               "VALUES ('adm','a','guest:adm','boss@example.test','+84918000111','admin','2026-09-01T00:00:00+00:00',"
               "'2026-09-01T00:00:00+00:00')")
        r = self.otp_login("0918000111")
        self.assertEqual(r.status_code, 403)


# =========================================================================== enumeration
def _strip(body, drop=("challenge_id", "expires_at")):
    if isinstance(body, dict):
        return {k: _strip(v) for k, v in body.items() if k not in drop}
    return body


class TestEnumeration(_Base):
    def setUp(self):
        super().setUp()
        for k in ("WELORA_RL_TARGET_MAX", "WELORA_RL_IP_MAX", "WELORA_RL_LOGIN_PAIR_MAX", "WELORA_RL_LOGIN_ACCOUNT_MAX",
                  "WELORA_RL_LOGIN_IP_MAX", "WELORA_RL_VERIFY_TARGET_MAX", "WELORA_RL_VERIFY_IP_MAX"):
            os.environ[k] = "100000"
        self.known_email = "co.that@example.test"
        self.known_phone = "0919000155"
        self.register(self.known_email)
        self.register(self.known_phone)
        # a verified phone account too (the attach path must not change the request side)
        self.x("INSERT INTO users(user_id, display_name, device_id, phone, password_hash, role, phone_verified_at) "
               "VALUES ('enum-v','v','guest:enum-v','+84919000255',?,'guest','2026-09-01T00:00:00+00:00')",
               (auth_svc._hash_password(PW),))

    def _timed(self, fn_a, fn_b, n=7):
        ta, tb, ra, rb = [], [], [], []
        fn_a(), fn_b()  # warm-up
        for _ in range(n):
            for fn, ts, rs in ((fn_a, ta, ra), (fn_b, tb, rb)):
                t = time.perf_counter()
                r = fn()
                ts.append(time.perf_counter() - t)
                rs.append(r)
        return statistics.median(ta), statistics.median(tb), ra, rb

    def assert_close(self, a, b):
        bound = max(0.05, 0.5 * max(a, b))  # generous: CI noise; a real oracle (hash vs no hash) is ≫
        self.assertLess(abs(a - b), bound, f"timing differs: {a:.4f}s vs {b:.4f}s")

    def test_otp_request_same_body_and_timing(self):
        for known, unknown in ((self.known_phone, "0919000955"), ("0919000255", "0919000855")):
            a, b, ra, rb = self._timed(
                lambda: self.client.post("/auth/otp/request", json={"phone": known}, headers=self.ip()),
                lambda: self.client.post("/auth/otp/request", json={"phone": unknown}, headers=self.ip()))
            self.assertEqual({r.status_code for r in ra + rb}, {200})
            sa = _strip(ra[0].json()); sb = _strip(rb[0].json())
            sa.pop("phone_masked"); sb.pop("phone_masked")
            self.assertEqual(sa, sb)
            self.assertEqual(sorted(ra[0].json()), sorted(rb[0].json()))
            self.assert_close(a, b)

    def test_otp_verify_wrong_code_same_body_and_timing(self):
        def wrong(phone):
            ch = self.client.post("/auth/otp/request", json={"phone": phone}, headers=self.ip()).json()
            return self.client.post("/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": "9999999"},
                                    headers=self.ip())
        a, b, ra, rb = self._timed(lambda: wrong(self.known_phone), lambda: wrong("0919000955"))
        self.assertEqual({(r.status_code, json.dumps(r.json(), sort_keys=True)) for r in ra + rb},
                         {(ra[0].status_code, json.dumps(ra[0].json(), sort_keys=True))})
        self.assert_close(a, b)

    def test_login_wrong_password_same_body_and_timing(self):
        for known, unknown in ((self.known_email, "khong.co@example.test"), (self.known_phone, "0919000955")):
            key = "email" if "@" in known else "phone"
            a, b, ra, rb = self._timed(
                lambda: self.client.post("/auth/login", json={key: known, "password": "sai-mat-khau-9"}, headers=self.ip()),
                lambda: self.client.post("/auth/login", json={key: unknown, "password": "sai-mat-khau-9"}, headers=self.ip()))
            self.assertEqual({(r.status_code, json.dumps(r.json(), sort_keys=True)) for r in ra + rb},
                             {(401, json.dumps(ra[0].json(), sort_keys=True))})
            self.assert_close(a, b)

    def test_forgot_password_same_body_and_timing(self):
        for known, unknown in ((self.known_email, "khong.co@example.test"), (self.known_phone, "0919000955")):
            key = "email" if "@" in known else "phone"
            a, b, ra, rb = self._timed(
                lambda: self.client.post("/auth/forgot-password", json={key: known}, headers=self.ip()),
                lambda: self.client.post("/auth/forgot-password", json={key: unknown}, headers=self.ip()))
            self.assertEqual({json.dumps(r.json(), sort_keys=True) for r in ra + rb}, {json.dumps(ra[0].json(), sort_keys=True)})
            self.assert_close(a, b)

    def test_verify_endpoints_take_no_identifier(self):
        a = self.register("ai.do@example.test")
        r = self.client.post("/auth/verify/request", json={"email": self.known_email}, headers=self.h(a["token"]))
        # the body cannot name another target — only the caller's own contact is used
        os.environ["WELORA_VERIFY_RESEND_COOLDOWN_S"] = "0"
        r = self.client.post("/auth/verify/request", json={"email": self.known_email}, headers=self.h(a["token"]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.mail[-1][0], "ai.do@example.test")
        self.assertEqual(r.json()["target_masked"], mailer.mask_email("ai.do@example.test"))

    def test_register_known_limit_documented_and_rate_limited(self):
        """Register signs the new account in immediately, so a duplicate e-mail/phone must answer
        differently (pre-existing, inherent) — bounded by the register rate limit; verification
        delivery is async and never changes register latency."""
        os.environ["WELORA_RL_TARGET_MAX"] = "3"  # setUp's own register already counted once
        st = [self.client.post("/auth/register", json={"email": self.known_email, "password": PW},
                               headers=self.ip()).status_code for _ in range(3)]
        self.assertEqual(st, [400, 400, 429])


# =========================================================================== item 5 (production guard)
class TestProdGuard(_Base):
    def test_production_refuses_otp_echo_fixed_and_reset_echo(self):
        os.environ.update({"WELORA_OTP_ECHO": "1", "WELORA_OTP_FIXED": "1", "WELORA_RESET_ECHO": "1"})
        self.assertTrue(auth_svc.otp_echo_enabled() and auth_svc.otp_fixed_enabled() and auth_svc.reset_echo_enabled())
        # production needs WELORA_OTP_HMAC_KEY (+ admin TOTP secrets, https base URL) to start at all
        os.environ.update({"WELORA_ENV": "production", "WELORA_GUEST_DEMO": "0", "WELORA_OTP_HMAC_KEY": "p" * 48,
                           "WELORA_ADMIN_TOTP_SECRETS": "admin@example.test:JBSWY3DPEHPK3PXP",
                           "WELORA_PUBLIC_BASE_URL": "https://app4.welora.vn"})
        # code layer: the flags are ignored in production whatever the env says
        self.assertFalse(auth_svc.otp_echo_enabled())
        self.assertFalse(auth_svc.otp_fixed_enabled())
        self.assertFalse(auth_svc.reset_echo_enabled())
        self.assertEqual(auth_svc.unsafe_auth_flags_ignored(), ["WELORA_OTP_ECHO", "WELORA_OTP_FIXED", "WELORA_RESET_ECHO"])
        # boot layer (cutover app4, LỆNH Forge 04/10): production refuses to START with them set
        from welora.prod_config import ProdConfigError

        with self.assertLogs("welora.auth", level="CRITICAL") as logs:
            with self.assertRaises(ProdConfigError) as e:
                with TestClient(create_app()):
                    pass
        self.assertIn("WELORA_OTP_ECHO", "\n".join(logs.output))
        for name in ("WELORA_OTP_ECHO", "WELORA_OTP_FIXED", "WELORA_RESET_ECHO"):
            self.assertIn(name, str(e.exception))
        for name in ("WELORA_OTP_ECHO", "WELORA_OTP_FIXED", "WELORA_RESET_ECHO"):
            os.environ.pop(name)
        with TestClient(create_app()) as c:
            health = c.get("/health").json()
            ch = c.post("/auth/otp/request", json={"phone": "0920000111"}, headers=self.ip()).json()
            fp = c.post("/auth/forgot-password", json={"email": "x@example.test"}, headers=self.ip()).json()
        self.assertEqual((health["env"], health["otp_hmac_key"]), ("production", "env"))
        self.assertEqual((health["otp_echo"], health["otp_fixed"], health["reset_echo"]), (False, False, False))
        self.assertEqual(health["auth_test_flags_ignored"], [])
        self.assertNotIn("pilot_code", ch)
        self.assertFalse(ch["otp_echo"])
        stored = self.q("SELECT code FROM otp_challenges WHERE challenge_id=?", (ch["challenge_id"],))[0]["code"]
        self.assertNotEqual(stored, auth_svc._otp_code_hash(ch["challenge_id"], auth_svc.FIXED_OTP))  # not 123456
        self.assertNotIn("reset_token", json.dumps(fp))

    def test_staging_default_flags_off(self):
        h = self.client.get("/health").json()
        self.assertEqual((h["otp_echo"], h["otp_fixed"], h["reset_echo"], h["sms_enabled"]), (False, False, False, False))
        self.assertEqual(h["auth_test_flags_ignored"], [])

    def test_verification_code_never_echoed_even_with_otp_echo(self):
        os.environ["WELORA_OTP_ECHO"] = "1"
        out = self.register("echo@example.test")
        code = self.last_code()
        self.assertNotIn(code, json.dumps(out))
        s = self.client.get("/auth/verify/status", headers=self.h(out["token"])).json()
        self.assertNotIn(code, json.dumps(s))

    def test_render_yaml_keeps_echo_off_for_staging(self):
        text = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"key: WELORA_OTP_ECHO\s*\n\s*value:")
        self.assertNotRegex(text, r"key: WELORA_OTP_FIXED")
        self.assertIn("WELORA_SMS_PROVIDER", text)


# =========================================================================== concurrency (real uvicorn)
class TestConcurrencyRealServer(unittest.TestCase):
    def setUp(self):
        from tests.test_p0b_kuat_academy import _Uvicorn

        self.tmp = tempfile.mkdtemp(prefix="welora-020c-")
        self.env = {"WELORA_GUEST_DEMO": "1", "WELORA_RL_VERIFY_CONFIRM_USER_MAX": "100000",
                    "WELORA_RL_VERIFY_CONFIRM_IP_MAX": "100000", "WELORA_RL_TARGET_MAX": "100000",
                    "WELORA_RL_IP_MAX": "100000", **db_env(self.tmp)}
        self.srv = _Uvicorn(self.env)
        self.prev = {k: os.environ.get(k) for k in ("WELORA_DB_URL", "WELORA_STORE")}
        os.environ.update({k: self.env[k] for k in ("WELORA_DB_URL", "WELORA_STORE")})

    def tearDown(self):
        self.srv.stop()
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _account(self, email):
        st, out = self.srv.call("/auth/register", {"email": email, "password": PW}, ip=f"203.0.113.{uuid.uuid4().int % 200 + 1}")
        assert st == 201, out
        cid = out["verification"]["challenge_id"]
        conn = get_connection(None)
        try:  # the server mails the code (log provider) — the test sets a known code on the row
            conn.execute("UPDATE contact_verifications SET code_hash=? WHERE challenge_id=?", (cv._code_hash(cid, "424242"), cid))
            conn.commit()
        finally:
            conn.close()
        return out, cid

    def test_parallel_right_codes_single_winner(self):
        out, cid = self._account("song.song@example.test")
        with ThreadPoolExecutor(10) as ex:
            res = list(ex.map(lambda _: self.srv.call("/auth/verify/confirm", {"code": "424242", "challenge_id": cid},
                                                      token=out["token"]), range(10)))
        codes = sorted(s for s, _ in res)
        self.assertEqual(codes.count(200), 1, res)
        self.assertEqual(set(codes) - {200}, {400})
        conn = get_connection(None)
        try:
            row = conn.execute("SELECT consumed, attempts FROM contact_verifications WHERE challenge_id=?", (cid,)).fetchone()
            self.assertEqual(int(row["consumed"]), 1)
            self.assertLessEqual(int(row["attempts"]), cv.max_attempts())
            u = conn.execute("SELECT email_verified_at FROM users WHERE user_id=?", (out["user_id"],)).fetchone()
            self.assertTrue(u["email_verified_at"])
        finally:
            conn.close()

    def test_parallel_wrong_codes_never_exceed_attempt_limit(self):
        out, cid = self._account("doan.ma@example.test")
        with ThreadPoolExecutor(12) as ex:
            res = list(ex.map(lambda i: self.srv.call("/auth/verify/confirm", {"code": "%06d" % (100000 + i), "challenge_id": cid},
                                                      token=out["token"]), range(24)))
        checked = [r for s, r in res if s == 400]
        self.assertLessEqual(len(checked), cv.max_attempts())
        self.assertTrue(all(s in (400, 429) for s, _ in res))
        conn = get_connection(None)
        try:
            row = conn.execute("SELECT consumed, attempts FROM contact_verifications WHERE challenge_id=?", (cid,)).fetchone()
            self.assertEqual(int(row["attempts"]), cv.max_attempts())
            self.assertEqual(int(row["consumed"]), 0)
        finally:
            conn.close()
        st, body = self.srv.call("/auth/verify/confirm", {"code": "424242", "challenge_id": cid}, token=out["token"])
        self.assertEqual((st, body["detail"]["error_code"]), (429, "VERIFY_TOO_MANY_ATTEMPTS"))


# =========================================================================== migration 020
class TestMigration020(_Base):
    def test_pre020_upgrade_and_rerun_twice(self):
        m = importlib.import_module("welora.db.migrate")
        dialect = detect_dialect(None)
        # fresh schema WITHOUT 020
        if dialect == "postgres":
            from tests._db_target import reset_postgres

            reset_postgres(os.environ["WELORA_DB_URL"])
        else:
            os.environ["WELORA_DB_URL"] = f"sqlite:///{self.tmp}/pre020.db"
        real_files, real_steps = m._list_migration_files, m._data_steps
        m._list_migration_files = lambda url=None: [p for p in real_files(url) if not p.stem.startswith("020")]
        m._data_steps = lambda: [s for s in real_steps() if not s[0].startswith("020")]
        try:
            pre = m.migrate(None)
        finally:
            m._list_migration_files, m._data_steps = real_files, real_steps

        def cols():
            if dialect == "sqlite":
                return [r["name"] for r in self.q("PRAGMA table_info(users)")]
            return [r["column_name"] for r in self.q(
                "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='users'")]

        def has_table():
            if dialect == "sqlite":
                return bool(self.q("SELECT name FROM sqlite_master WHERE type='table' AND name='contact_verifications'"))
            return bool(self.q("SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() "
                               "AND table_name='contact_verifications'"))

        self.assertFalse(any(v.startswith("020") for v in pre))
        self.assertNotIn("phone_verified_at", cols())
        self.assertFalse(has_table())
        self.x("INSERT INTO users(user_id, display_name, device_id, email, phone, password_hash, role, email_verified_at) "
               "VALUES ('pre-u','p','guest:pre-u','pre@example.test','0921000111','h','guest','2026-01-01T00:00:00+00:00')")
        self.assertEqual(m.migrate(None), ["020_contact_verification"])
        self.assertEqual(m.migrate(None), [])
        self.assertEqual(cols().count("phone_verified_at"), 1)
        self.assertTrue(has_table())
        row = self.q("SELECT email_verified_at, phone_verified_at, phone FROM users WHERE user_id='pre-u'")[0]
        self.assertEqual((row["email_verified_at"], row["phone_verified_at"], row["phone"]),
                         ("2026-01-01T00:00:00+00:00", None, "0921000111"))  # existing data kept
        self.x("INSERT INTO contact_verifications(challenge_id, user_id, channel, target, code_hash, created_at, expires_at) "
               "VALUES ('cv1','pre-u','email','pre@example.test','sha256:x','2026-01-01T00:00:00.000000+00:00',"
               "'2026-01-01T00:10:00.000000+00:00')")
        # version row removed → re-applied without error; step run twice by hand
        self.x("DELETE FROM schema_migrations WHERE version='020_contact_verification'")
        self.assertEqual(m.migrate(None), ["020_contact_verification"])
        conn = get_connection(None)
        try:
            cv.apply_contact_verification_schema(conn, dialect)
            cv.apply_contact_verification_schema(conn, dialect)
        finally:
            conn.close()
        if dialect == "postgres":
            import psycopg

            sql = (m.MIGRATIONS_ROOT / "postgres" / "020_contact_verification.sql").read_text(encoding="utf-8")
            with psycopg.connect(os.environ["WELORA_DB_URL"]) as pc:
                pc.execute(sql)
                pc.execute(sql)
        self.assertEqual(cols().count("phone_verified_at"), 1)
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM contact_verifications")[0]["n"], 1)  # rows kept
        self.assertEqual([v for v in m.current_version() if v.startswith("020")], ["020_contact_verification"])
        # channel constraint
        with self.assertRaises(Exception):
            self.x("INSERT INTO contact_verifications(challenge_id, user_id, channel, target, code_hash, created_at, expires_at) "
                   "VALUES ('cv2','pre-u','fax','x','sha256:x','a','b')")

    def test_pg_sql_file_is_idempotent_text(self):
        sql = (ROOT / "welora" / "db" / "migrations" / "postgres" / "020_contact_verification.sql").read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN IF NOT EXISTS phone_verified_at", sql)
        self.assertIn("CREATE TABLE IF NOT EXISTS contact_verifications", sql)
        self.assertIn("CREATE INDEX IF NOT EXISTS", sql)
        self.assertFalse((ROOT / "welora" / "db" / "migrations" / "020_contact_verification.sql").exists())  # SQLite = data step


# =========================================================================== item 3 (FE)
class TestFrontend(_Base):
    def test_verify_page_served_and_login_gated(self):
        r = self.client.get("/app/verify")
        self.assertEqual(r.status_code, 200)
        html = r.text
        for s in ("Xác minh tài khoản", "Gửi lại mã", "Để sau", "/auth/verify/confirm", "/auth/verify/request",
                  "/auth/verify/status", "one-time-code", "auth-gate.js"):
            self.assertIn(s, html)
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("pilot_code", html)
        gate = (STATIC / "auth-gate.js").read_text(encoding="utf-8")
        shell = (STATIC / "shell.js").read_text(encoding="utf-8")
        allow_gate = gate[gate.index("var allow"):gate.index("};", gate.index("var allow"))]
        allow_shell = shell[shell.index("var _authAllow"):shell.index("};", shell.index("var _authAllow"))]
        for allow in (allow_gate, allow_shell):  # /app/verify needs a session (not allowlisted)
            self.assertIn('"/app/login": 1', allow)
            self.assertNotIn("/app/verify", allow)

    def test_register_goes_to_verify_screen(self):
        html = (STATIC / "register.html").read_text(encoding="utf-8")
        self.assertIn("/app/verify?next=%2Fapp", html)
        self.assertIn("d.verification", html)

    def test_banner_in_shell_skippable(self):
        js = (STATIC / "shell.js").read_text(encoding="utf-8")
        self.assertIn("Xác minh tài khoản", js)
        self.assertIn("Để sau", js)
        self.assertIn("welora_verify_banner_until", js)
        self.assertIn("me.verify_eligible", js)
        self.assertIn("me.can_verify_now", js)
        self.assertNotIn("innerHTML =", js)
        self.assertIn('"/app/verify": 1', js[js.index("injectVerifyBanner"):])  # not shown on the verify page

    def test_next_param_same_origin_only(self):
        html = (STATIC / "verify.html").read_text(encoding="utf-8")
        self.assertIn('<script src="/static/safe-next.js"></script>', html)
        self.assertIn("WeloraSafeNext(qs.get('next'),'/app')", html)  # behaviour: test_otp_verify_020_r2

    def test_copy_is_vietnamese(self):
        vi = re.compile(r"[ạảãáàâầấậẩẫăằắặẳẵđêềếệểễôồốộổỗơờớợởỡưừứựửữìíịỉĩòóọỏõùúụủũỳýỵỷỹ]", re.I)
        for msg in (cv.MSG_INVALID, cv.MSG_TOO_MANY, cv.MSG_SMS_OFF, cv.MSG_VERIFIED, cv.MSG_COOLDOWN,
                    auth_svc.PHONE_UNVERIFIED_MSG, cv.MAIL_BODY):
            self.assertRegex(msg, vi)
        self.assertIn("Vui lòng", cv.MSG_INVALID + cv.MSG_TOO_MANY)


class TestConstraints(unittest.TestCase):
    def test_unchanged(self):
        from welora.checkout import checkout_enabled

        self.assertEqual(TARGET_MONTHS, 3)
        prev = os.environ.pop("WELORA_CHECKOUT_ENABLED", None)
        try:
            self.assertFalse(checkout_enabled())
        finally:
            if prev is not None:
                os.environ["WELORA_CHECKOUT_ENABLED"] = prev
        h = TestClient(create_app()).get("/health").json()
        self.assertEqual((h["hard_deny"], h["gate_months"]), (True, 3))
        start = (ROOT / "start.sh").read_text(encoding="utf-8")
        self.assertIn("--no-proxy-headers", start)


if __name__ == "__main__":
    unittest.main()
