"""P0 follow-up #4–#6 — login/register rate limits + real client IP, token expiry, atomic OTP verify.

SQLite by default; real PostgreSQL when WELORA_TEST_POSTGRES_URL is set (tests/_db_target.py).
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from starlette.datastructures import Headers

from tests._db_target import db_env
from welora import admin_bootstrap, mailer
from welora import auth as auth_svc
from welora import auth_ratelimit as rl
from welora.api.app import create_app
from welora.db.connection import get_connection
from welora.safety_gate import TARGET_MONTHS

ENV_KEYS = (
    "WELORA_ENV", "WELORA_STORE", "WELORA_DB_URL", "WELORA_GUEST_DEMO", "WELORA_OTP_FIXED", "WELORA_OTP_ECHO",
    "WELORA_RESET_ECHO", "WELORA_MAIL_SYNC", "WELORA_ADMIN_EMAILS", "WELORA_TOKEN_TTL_DAYS",
    "WELORA_DEVICE_TOKEN_TTL_DAYS", "WELORA_RL_WINDOW_S", "WELORA_RL_TARGET_MAX", "WELORA_RL_IP_MAX",
    "WELORA_RL_VERIFY_TARGET_MAX", "WELORA_RL_VERIFY_IP_MAX", "WELORA_RL_LOGIN_TARGET_MAX", "WELORA_RL_LOGIN_IP_MAX",
)
PW = "matkhau-dai-1"


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="welora-fu-")
        os.environ.update({"WELORA_ENV": "staging", "WELORA_GUEST_DEMO": "1", "WELORA_MAIL_SYNC": "1", **db_env(self.tmp)})
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        mailer.set_sender(None)
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

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

    def tok_row(self, token):
        return self.q("SELECT * FROM auth_tokens WHERE token=?", (token,))[0]

    def days_left(self, token) -> float:
        exp = auth_svc._parse_ts(self.tok_row(token)["expires_at"])
        return (exp - datetime.now(timezone.utc)).total_seconds() / 86400

    def register(self, email, ip="198.51.100.7"):
        return self.client.post("/auth/register", json={"email": email, "password": PW},
                                headers={"CF-Connecting-IP": ip})

    def login(self, email, ip="198.51.100.7", password=PW):
        return self.client.post("/auth/login", json={"email": email, "password": password},
                                headers={"CF-Connecting-IP": ip})


# ---------------------------------------------------------------- #5 token expiry
class TestTokenExpiry(_Base):
    def test_every_login_kind_gets_expires_at(self):
        tokens = {}
        r = self.register("exp-a@example.test")
        self.assertEqual(r.status_code, 201, r.text)
        tokens["password"] = r.json()["token"]
        tokens["password_login"] = self.login("exp-a@example.test").json()["token"]
        tokens["device"] = self.client.post("/auth/device", json={"device_id": "web-exp00001"}).json()["token"]
        os.environ["WELORA_OTP_FIXED"] = "1"
        ch = self.client.post("/auth/otp/request", json={"phone": "+84901110001"}).json()
        tokens["otp"] = self.client.post("/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": "123456"}).json()["token"]
        # demo partner account → password-kind token for a demo-role user
        self.assertEqual(self.client.post("/auth/demo/seed").status_code, 200)
        d = self.client.post("/auth/login", json={"email": auth_svc.DEMO_EMAIL, "password": auth_svc.DEMO_PASSWORD})
        self.assertEqual(d.status_code, 200, d.text)
        tokens["demo"] = d.json()["token"]
        # admin email OTP (WELORA_ADMIN_EMAILS) → kind email_otp
        mails = []
        mailer.set_sender(lambda to, s, b: mails.append(b))
        os.environ["WELORA_ADMIN_EMAILS"] = "founder-fu@example.test"
        req = self.client.post("/auth/email-otp/request", json={"email": "founder-fu@example.test"}).json()
        code = re.search(r"\b(\d{6})\b", mails[-1]).group(1)
        adm = self.client.post("/auth/email-otp/verify", json={"challenge_id": req["challenge_id"], "code": code})
        self.assertEqual(adm.status_code, 200, adm.text)
        tokens["email_otp"] = adm.json()["token"]

        kinds = {name: self.tok_row(t)["kind"] for name, t in tokens.items()}
        self.assertEqual(kinds["device"], "device")
        self.assertEqual(kinds["otp"], "otp")
        self.assertEqual(kinds["email_otp"], "email_otp")
        for name, t in tokens.items():
            self.assertIsNotNone(self.tok_row(t)["expires_at"], name)
            self.assertAlmostEqual(self.days_left(t), 30, delta=0.01, msg=name)
            self.assertEqual(self.client.get("/auth/me", headers={"Authorization": f"Bearer {t}"}).status_code, 200, name)

    def test_ttl_env_and_separate_device_ttl(self):
        os.environ["WELORA_TOKEN_TTL_DAYS"] = "2"
        t = self.register("exp-b@example.test").json()["token"]
        self.assertAlmostEqual(self.days_left(t), 2, delta=0.01)
        dev = self.client.post("/auth/device", json={"device_id": "web-exp00002"}).json()["token"]
        self.assertAlmostEqual(self.days_left(dev), 2, delta=0.01)  # default: same as login TTL
        os.environ["WELORA_DEVICE_TOKEN_TTL_DAYS"] = "0.5"
        dev2 = self.client.post("/auth/device", json={"device_id": "web-exp00002"}).json()["token"]
        self.assertAlmostEqual(self.days_left(dev2), 0.5, delta=0.01)
        os.environ["WELORA_TOKEN_TTL_DAYS"] = "garbage"
        self.assertEqual(auth_svc.token_ttl_days(), 30)

    def test_expired_token_401_vietnamese(self):
        r = self.register("exp-c@example.test").json()
        tok, uid = r["token"], r["user_id"]
        h = {"Authorization": f"Bearer {tok}"}
        self.assertEqual(self.client.get("/goals", params={"user_id": uid}, headers=h).status_code, 200)
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        self.x("UPDATE auth_tokens SET expires_at=? WHERE token=?", (past, tok))
        g = self.client.get("/goals", params={"user_id": uid}, headers=h)
        self.assertEqual(g.status_code, 401)
        self.assertEqual(g.json()["detail"]["error_code"], "TOKEN_EXPIRED")
        self.assertEqual(g.json()["detail"]["message"], "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")
        me = self.client.get("/auth/me", headers=h)
        self.assertEqual(me.status_code, 401)
        self.assertEqual(me.json()["detail"]["error_code"], "TOKEN_EXPIRED")
        # revoked / unknown tokens keep the generic AUTH_REQUIRED code
        self.client.post("/auth/logout", headers={"Authorization": f"Bearer {self.login('exp-c@example.test').json()['token']}"})
        bad = self.client.get("/goals", params={"user_id": uid}, headers={"Authorization": "Bearer nope"})
        self.assertEqual(bad.json()["detail"]["error_code"], "AUTH_REQUIRED")

    def _legacy(self, uid, age_days, kind="password"):
        token = "legacy-" + os.urandom(6).hex()
        created = (datetime.now(timezone.utc) - timedelta(days=age_days)).strftime("%Y-%m-%d %H:%M:%S")
        self.x("INSERT INTO auth_tokens(token, user_id, device_id, kind, created_at, expires_at) VALUES (?,?,?,?,?,NULL)",
               (token, uid, None, kind, created))
        return token

    def test_legacy_null_tokens_not_logged_out_abruptly(self):
        uid = self.register("exp-d@example.test").json()["user_id"]
        recent = self._legacy(uid, 1)
        old = self._legacy(uid, 60)
        dev = self._legacy(uid, 45, kind="device")
        for t in (recent, old, dev):
            self.assertEqual(auth_svc.resolve_token(t), uid)  # all still valid right after the deploy
        self.assertAlmostEqual(self.days_left(recent), 29, delta=0.01)  # created_at + 30 d
        self.assertAlmostEqual(self.days_left(old), 7, delta=0.01)  # grace: now + 7 d
        self.assertAlmostEqual(self.days_left(dev), 7, delta=0.01)
        first = self.tok_row(old)["expires_at"]
        auth_svc.resolve_token(old)
        self.assertEqual(self.tok_row(old)["expires_at"], first)  # written once — no sliding

    def test_backfill_idempotent(self):
        uid = self.register("exp-e@example.test").json()["user_id"]
        a, b = self._legacy(uid, 3), self._legacy(uid, 90)
        self.assertEqual(auth_svc.backfill_legacy_token_expiry(), 2)
        snap = (self.tok_row(a)["expires_at"], self.tok_row(b)["expires_at"])
        self.assertEqual(auth_svc.backfill_legacy_token_expiry(), 0)
        self.assertEqual((self.tok_row(a)["expires_at"], self.tok_row(b)["expires_at"]), snap)
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM auth_tokens WHERE expires_at IS NULL")[0]["n"], 0)


# ---------------------------------------------------------------- #6 atomic OTP verify
class TestAtomicOtpVerify(_Base):
    def test_concurrent_verifies_only_one_wins(self):
        os.environ["WELORA_OTP_FIXED"] = "1"
        for rnd in range(3):
            ch = auth_svc.request_otp(f"+8490222000{rnd}")
            n = 4
            barrier = threading.Barrier(n)
            results: list = []

            def go():
                barrier.wait()
                try:
                    results.append(("ok", auth_svc.verify_otp(ch["challenge_id"], "123456")["token"]))
                except Exception as e:
                    results.append(("err", f"{type(e).__name__}: {e}"))

            threads = [threading.Thread(target=go) for _ in range(n)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(60)
            oks = [r for r in results if r[0] == "ok"]
            self.assertEqual(len(oks), 1, results)
            for r in results:
                if r[0] == "err":
                    self.assertIn("already used", r[1])
            uid = self.q("SELECT user_id FROM otp_challenges WHERE challenge_id=?", (ch["challenge_id"],))[0]["user_id"]
            self.assertEqual(len(self.q("SELECT token FROM auth_tokens WHERE user_id=? AND kind='otp'", (uid,))), 1)

    def test_replay_after_success_rejected(self):
        os.environ["WELORA_OTP_FIXED"] = "1"
        ch = self.client.post("/auth/otp/request", json={"phone": "+84902223333"}).json()
        body = {"challenge_id": ch["challenge_id"], "code": "123456"}
        self.assertEqual(self.client.post("/auth/otp/verify", json=body).status_code, 200)
        again = self.client.post("/auth/otp/verify", json=body)
        self.assertEqual(again.status_code, 400)
        self.assertIn("already used", again.text)

    def test_wrong_code_does_not_consume(self):
        os.environ["WELORA_OTP_FIXED"] = "1"
        ch = auth_svc.request_otp("+84902224444")
        with self.assertRaises(ValueError):
            auth_svc.verify_otp(ch["challenge_id"], "000000")
        self.assertTrue(auth_svc.verify_otp(ch["challenge_id"], "123456")["token"])


# ---------------------------------------------------------------- #4 rate limits + client IP
class TestLoginRegisterRateLimit(_Base):
    def test_login_per_target(self):
        os.environ.update({"WELORA_RL_LOGIN_TARGET_MAX": "3", "WELORA_RL_LOGIN_IP_MAX": "100"})
        self.register("rl-a@example.test")
        codes = [self.login("rl-a@example.test", ip=f"203.0.113.{i}").status_code for i in range(1, 5)]
        self.assertEqual(codes, [200, 200, 200, 429])
        r = self.login("rl-a@example.test", ip="203.0.113.99")
        self.assertEqual(r.json()["detail"]["error_code"], "RATE_LIMITED")
        self.assertEqual(r.json()["detail"]["message"], rl.RATE_LIMIT_MSG)
        self.assertTrue(r.headers.get("Retry-After"))
        # wrong passwords count too (brute force), and another account is unaffected
        self.register("rl-b@example.test")
        self.assertEqual(self.login("rl-b@example.test").status_code, 200)

    def test_login_per_ip_uses_real_client_ip_not_shared_proxy(self):
        os.environ.update({"WELORA_RL_LOGIN_TARGET_MAX": "100", "WELORA_RL_LOGIN_IP_MAX": "3"})
        self.register("rl-c@example.test")
        for _ in range(3):
            self.assertEqual(self.login("rl-c@example.test", ip="192.0.2.10", password="sai-mat-khau").status_code, 401)
        self.assertEqual(self.login("rl-c@example.test", ip="192.0.2.10").status_code, 429)
        # same Cloudflare edge / Render proxy (same XFF tail), different real client → own bucket
        other = self.client.post("/auth/login", json={"email": "rl-c@example.test", "password": PW},
                                 headers={"CF-Connecting-IP": "192.0.2.11", "X-Forwarded-For": "192.0.2.10, 172.71.1.1"})
        self.assertEqual(other.status_code, 200, other.text)

    def test_register_per_target_and_ip(self):
        os.environ.update({"WELORA_RL_TARGET_MAX": "2", "WELORA_RL_IP_MAX": "3"})
        self.assertEqual(self.register("rl-d@example.test", ip="192.0.2.20").status_code, 201)
        self.assertEqual(self.register("rl-d@example.test", ip="192.0.2.21").status_code, 400)  # exists
        self.assertEqual(self.register("rl-d@example.test", ip="192.0.2.22").status_code, 429)  # per email
        self.assertEqual(self.register("rl-e@example.test", ip="192.0.2.30").status_code, 201)
        self.assertEqual(self.register("rl-f@example.test", ip="192.0.2.30").status_code, 201)
        self.assertEqual(self.register("rl-g@example.test", ip="192.0.2.30").status_code, 201)
        self.assertEqual(self.register("rl-h@example.test", ip="192.0.2.30").status_code, 429)  # per IP
        self.assertEqual(self.register("rl-h@example.test", ip="192.0.2.31").status_code, 201)

    def test_phone_target_normalised(self):
        os.environ.update({"WELORA_RL_LOGIN_TARGET_MAX": "2"})
        p = lambda phone: self.client.post("/auth/login", json={"phone": phone, "password": "x" * 8},
                                           headers={"CF-Connecting-IP": "192.0.2.40"}).status_code
        self.assertEqual([p("+84 912 345 678"), p("0912345678"), p("+84912345678")], [401, 401, 429])

    def test_no_raw_pii_stored(self):
        self.register("rl-pii@example.test", ip="192.0.2.50")
        blob = repr(self.q("SELECT * FROM auth_rate_events"))
        self.assertNotIn("rl-pii", blob)
        self.assertNotIn("192.0.2.50", blob)


class TestClientIp(unittest.TestCase):
    def test_header_priority(self):
        h = {"CF-Connecting-IP": "198.51.100.1", "True-Client-IP": "198.51.100.2", "X-Forwarded-For": "198.51.100.3, 10.0.0.1"}
        self.assertEqual(rl.client_ip("10.0.0.5", headers=h), "198.51.100.1")
        h.pop("CF-Connecting-IP")
        self.assertEqual(rl.client_ip("10.0.0.5", headers=h), "198.51.100.2")
        h.pop("True-Client-IP")
        self.assertEqual(rl.client_ip("10.0.0.5", headers=h), "198.51.100.3")
        self.assertEqual(rl.client_ip("10.0.0.5", headers={}), "10.0.0.5")

    def test_starlette_headers_case_insensitive(self):
        h = Headers({"cf-connecting-ip": "2001:db8::1", "x-forwarded-for": "198.51.100.3"})
        self.assertEqual(rl.client_ip("127.0.0.1", headers=h), "2001:db8::1")

    def test_public_peer_headers_ignored(self):
        h = {"CF-Connecting-IP": "198.51.100.1", "X-Forwarded-For": "1.2.3.4"}
        self.assertEqual(rl.client_ip("8.8.8.8", headers=h), "8.8.8.8")

    def test_invalid_values_skipped(self):
        h = {"CF-Connecting-IP": "not-an-ip", "True-Client-IP": "", "X-Forwarded-For": "junk, 198.51.100.9"}
        self.assertEqual(rl.client_ip("10.0.0.5", headers=h), "10.0.0.5")
        self.assertEqual(rl.client_ip("10.0.0.5", headers={"X-Forwarded-For": " 198.51.100.9 , 10.0.0.1"}), "198.51.100.9")

    def test_legacy_signature(self):
        self.assertEqual(rl.client_ip("10.0.0.3", "1.2.3.4, 10.0.0.3"), "1.2.3.4")
        self.assertEqual(rl.client_ip("8.8.8.8", "1.2.3.4"), "8.8.8.8")

    def test_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health").json()
        self.assertEqual(r["gate_months"], 3)
        self.assertTrue(r["hard_deny"])
        self.assertIn("token_ttl_days", r)
        self.assertIn("demo_seed", r)


if __name__ == "__main__":
    unittest.main()
