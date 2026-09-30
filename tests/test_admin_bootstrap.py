"""Admin bootstrap by email (WELORA_ADMIN_EMAILS) + admin 2FA keyed by email.

Email OTP codes are captured from the mailer (fake sender) — no SMTP, no network.
Fake TOTP secrets only. Runs on SQLite by default; on real PostgreSQL when
WELORA_TEST_POSTGRES_URL is set (see tests/_db_target.py).
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import logging
import os
import re
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

from tests._db_target import db_env
from welora import admin_2fa, admin_bootstrap
from welora import auth as auth_svc
from welora import checkout as co
from welora import entitlements as ent
from welora import mailer
from welora.api.app import create_app
from welora.db.connection import get_connection
from welora.safety_gate import TARGET_MONTHS

FAKE_TOTP = "JBSWY3DPEHPK3PXPFAKEFAKEFAKEFAKE"
FOUNDER = "founder@example.test"
ENV_KEYS = (
    "WELORA_ENV", "WELORA_STORE", "WELORA_DB_URL", "WELORA_GUEST_DEMO", "WELORA_MAIL_SYNC", "WELORA_OTP_FIXED",
    "WELORA_ADMIN_EMAILS", "WELORA_ADMIN_TOTP_SECRETS", "WELORA_CHECKOUT_ENABLED", "WELORA_SMTP_HOST",
)


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="welora-adm-")
        os.environ.update({"WELORA_ENV": "staging", "WELORA_GUEST_DEMO": "0", "WELORA_MAIL_SYNC": "1", **db_env(self.tmp)})
        ent.reset_state_for_tests()
        co.reset_for_tests()
        self.mails: list[tuple[str, str, str]] = []
        mailer.set_sender(lambda to, s, b: self.mails.append((to, s, b)))
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        mailer.set_sender(None)
        ent.reset_state_for_tests()
        co.reset_for_tests()
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- helpers ----------------------------------------------------------
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

    def request_code(self, email):
        n = len(self.mails)
        r = self.client.post("/auth/email-otp/request", json={"email": email})
        self.assertEqual(r.status_code, 200, r.text)
        new = self.mails[n:]
        code = re.search(r"\b(\d{6})\b", new[-1][2]).group(1) if new else None
        return r.json(), code

    def otp_login(self, email):
        body, code = self.request_code(email)
        self.assertIsNotNone(code, "no OTP mail sent")
        r = self.client.post("/auth/email-otp/verify", json={"challenge_id": body["challenge_id"], "code": code})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def role(self, uid):
        return self.q("SELECT role FROM users WHERE user_id=?", (uid,))[0]["role"]

    def audit(self, action=None):
        rows = self.q("SELECT * FROM auth_audit ORDER BY created_at")
        return [r for r in rows if action is None or r["action"] == action]

    def h(self, token):
        return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# A · WELORA_ADMIN_EMAILS (email OTP only, fail-closed, audited)
# ===========================================================================


class TestAdminEmails(_Base):
    def test_listed_email_otp_login_becomes_admin_and_is_audited(self):
        os.environ["WELORA_ADMIN_EMAILS"] = f" other@example.test , {FOUNDER.upper()} "
        body, code = self.request_code("Founder@Example.test")
        self.assertEqual(len(self.mails), 1)
        self.assertEqual(self.mails[0][0], FOUNDER)
        self.assertNotIn(code, json.dumps(body))  # never echoed
        self.assertNotIn("pilot_code", body)
        out = self.client.post("/auth/email-otp/verify", json={"challenge_id": body["challenge_id"], "code": code}).json()
        self.assertEqual((out["role"], out["admin"], out["kind"]), ("admin", True, "email_otp"))
        self.assertEqual(self.role(out["user_id"]), "admin")
        self.assertTrue(self.q("SELECT email_verified_at FROM users WHERE user_id=?", (out["user_id"],))[0]["email_verified_at"])
        st = self.client.get("/api/admin/v1/2fa/status", headers=self.h(out["token"]))
        self.assertEqual(st.status_code, 200)  # _require_admin passes (TOTP still needed for checkout APIs)
        a = self.audit("admin_role_granted")
        self.assertEqual(len(a), 1)
        d = json.loads(a[0]["detail"])
        self.assertEqual((a[0]["user_id"], a[0]["actor"], d["via"]), (out["user_id"], "env:WELORA_ADMIN_EMAILS", "email_otp"))
        self.assertNotIn(FOUNDER, a[0]["detail"])  # masked
        self.assertNotIn(code, json.dumps(self.q("SELECT * FROM email_otp_challenges")))  # hashed only
        # the code is single-use
        again = self.client.post("/auth/email-otp/verify", json={"challenge_id": body["challenge_id"], "code": code})
        self.assertEqual(again.status_code, 400)

    def test_unlisted_email_gets_no_code_and_no_admin(self):
        os.environ["WELORA_ADMIN_EMAILS"] = FOUNDER
        listed, _ = self.request_code(FOUNDER)
        body, code = self.request_code("stranger@example.test")
        self.assertIsNone(code)  # nothing mailed
        self.assertEqual(sorted(body), sorted(listed))  # identical shape → list not disclosed
        self.assertEqual(body["message"], listed["message"])
        r = self.client.post("/auth/email-otp/verify", json={"challenge_id": body["challenge_id"], "code": "123456"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.q("SELECT * FROM users WHERE email=?", ("stranger@example.test",)), [])
        # a password user whose email is not listed stays guest
        g = auth_svc.register_guest(email="guest@example.test", password="Passw0rd!x")
        self.assertEqual(admin_bootstrap.startup_sync(), {"granted": 0, "revoked": 0})
        self.assertEqual(self.role(g["user_id"]), "guest")

    def test_empty_env_nobody_is_admin(self):
        u = auth_svc.register_guest(email=FOUNDER, password="Passw0rd!x")
        self.x("UPDATE users SET role='admin', email_verified_at='2026-09-30T00:00:00+00:00' WHERE user_id=?", (u["user_id"],))
        _, code = self.request_code(FOUNDER)
        self.assertIsNone(code)  # env unset → no OTP to anyone
        os.environ["WELORA_ADMIN_EMAILS"] = "  ,  "
        self.assertEqual(admin_bootstrap.admin_emails(), frozenset())
        self.assertEqual(admin_bootstrap.startup_sync()["revoked"], 1)
        self.assertEqual(self.role(u["user_id"]), "guest")
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM users WHERE role IN ('admin','ops','staff','superuser')")[0]["n"], 0)
        self.assertEqual(json.loads(self.audit("admin_role_revoked")[0]["detail"])["via"], "startup")

    def test_password_device_phone_paths_never_reach_admin(self):
        os.environ["WELORA_ADMIN_EMAILS"] = FOUNDER
        # attacker squats the founder's address via password sign-up (email unverified)
        sq = auth_svc.register_guest(email=FOUNDER, password="Squatter1!x")
        self.assertEqual(sq["role"], "guest")
        self.assertEqual(admin_bootstrap.startup_sync()["granted"], 0)  # unverified email → not promoted
        self.assertEqual(self.role(sq["user_id"]), "guest")
        # real founder proves the mailbox → same row becomes admin, squatter's session revoked
        out = self.otp_login(FOUNDER)
        self.assertEqual(out["user_id"], sq["user_id"])
        self.assertEqual(out["role"], "admin")
        self.assertIsNone(auth_svc.resolve_token(sq["token"]))
        self.assertEqual(json.loads(self.audit("admin_role_granted")[0]["detail"])["revoked_sessions"], 1)
        # password login into the admin account stays rejected
        r = self.client.post("/auth/login", json={"email": FOUNDER, "password": "Squatter1!x"})
        self.assertEqual(r.status_code, 403)
        # device flow with the (predictable) guest device key is refused
        dk = "guest:" + hashlib.sha256(FOUNDER.encode()).hexdigest()[:16]
        r = self.client.post("/auth/device", json={"device_id": dk})
        self.assertEqual(r.status_code, 403)
        # client can never self-elevate on register
        r = self.client.post("/auth/register", json={"email": "evil@example.test", "password": "Passw0rd!x", "role": "admin"})
        self.assertEqual(r.json()["role"], "guest")
        self.assertEqual(self.role(out["user_id"]), "admin")

    def test_fixed_otp_flag_does_not_apply_and_attempts_limited(self):
        os.environ["WELORA_ADMIN_EMAILS"] = FOUNDER
        os.environ["WELORA_OTP_FIXED"] = "1"
        body, code = self.request_code(FOUNDER)
        wrong = "000000" if code != "000000" else "111111"
        for _ in range(admin_bootstrap.OTP_MAX_ATTEMPTS):
            r = self.client.post("/auth/email-otp/verify", json={"challenge_id": body["challenge_id"], "code": wrong})
            self.assertEqual(r.status_code, 400)
        r = self.client.post("/auth/email-otp/verify", json={"challenge_id": body["challenge_id"], "code": code})
        self.assertEqual(r.status_code, 400)  # locked after 5 wrong attempts
        for _ in range(admin_bootstrap.OTP_RATE_MAX + 2):
            self.request_code(FOUNDER)
        self.assertEqual(len(self.mails), admin_bootstrap.OTP_RATE_MAX)  # rate-limited per 15 min

    def test_startup_promotes_existing_and_removal_demotes(self):
        os.environ["WELORA_ADMIN_EMAILS"] = FOUNDER
        uid = self.otp_login(FOUNDER)["user_id"]
        # removed from the env → demoted at startup (audited), 2FA sessions closed
        os.environ["WELORA_ADMIN_EMAILS"] = "someone.else@example.test"
        with TestClient(create_app()):  # app lifespan runs startup_sync
            pass
        self.assertEqual(self.role(uid), "guest")
        self.assertEqual(json.loads(self.audit("admin_role_revoked")[0]["detail"])["reason"], "email_not_listed")
        # re-added → existing (verified) user promoted at startup, no new login needed
        os.environ["WELORA_ADMIN_EMAILS"] = f"someone.else@example.test,{FOUNDER}"
        with TestClient(create_app()):
            pass
        self.assertEqual(self.role(uid), "admin")
        granted = self.audit("admin_role_granted")
        self.assertEqual([json.loads(g["detail"])["via"] for g in granted], ["email_otp", "startup"])

    def test_removed_email_demoted_at_next_login(self):
        os.environ["WELORA_ADMIN_EMAILS"] = FOUNDER
        self.client.post("/auth/register", json={"email": FOUNDER, "password": "Passw0rd!x"})
        uid = self.otp_login(FOUNDER)["user_id"]
        os.environ["WELORA_ADMIN_EMAILS"] = ""
        r = self.client.post("/auth/login", json={"email": FOUNDER, "password": "Passw0rd!x"})
        self.assertEqual(r.status_code, 200, r.text)  # de-listed → demoted, continues as a normal user
        self.assertEqual(r.json()["role"], "guest")
        self.assertEqual(self.role(uid), "guest")
        self.assertEqual(json.loads(self.audit("admin_role_revoked")[0]["detail"])["via"], "password_login")
        self.assertEqual(self.client.get("/api/admin/v1/2fa/status", headers=self.h(r.json()["token"])).status_code, 403)

    def test_admin_login_page(self):
        r = self.client.get("/app/admin/login")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/auth/email-otp/request", r.text)
        self.assertIn("/auth/email-otp/verify", r.text)
        self.assertNotIn("innerHTML", r.text)
        self.assertNotIn("password", r.text.lower())
        gate = self.client.get("/static/auth-gate.js").text
        self.assertIn('"/app/admin/login": 1', gate)


# ===========================================================================
# B · WELORA_ADMIN_TOTP_SECRETS email:BASE32
# ===========================================================================


class TestAdmin2FAByEmail(_Base):
    def test_email_keyed_secret_enroll_and_verify(self):
        os.environ["WELORA_ADMIN_EMAILS"] = FOUNDER
        os.environ["WELORA_ADMIN_TOTP_SECRETS"] = f"Founder@Example.test:{FAKE_TOTP}"
        out = self.otp_login(FOUNDER)
        h = self.h(out["token"])
        self.assertEqual(self.client.get("/api/admin/v1/2fa/status", headers=h).json(), {"enrolled": True, "session": False})
        buf = io.StringIO()
        handler = logging.StreamHandler(buf)
        logging.getLogger().addHandler(handler)
        prev_level = logging.getLogger().level
        logging.getLogger().setLevel(logging.DEBUG)
        try:
            r = self.client.post("/api/admin/v1/2fa/verify", json={"code": admin_2fa.totp(FAKE_TOTP)}, headers=h)
        finally:
            logging.getLogger().removeHandler(handler)
            logging.getLogger().setLevel(prev_level)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertNotIn(FAKE_TOTP, buf.getvalue())  # never logged
        self.assertTrue(admin_2fa.session_valid(out["user_id"], out["token"]))
        self.assertEqual(self.client.get("/api/admin/v1/2fa/status", headers=h).json(), {"enrolled": True, "session": True})
        # checkout admin API guard accepts it (admin role + live TOTP session); checkout stays off → 403 disabled, not 401
        r = self.client.get("/api/admin/v1/checkout/orders?q=1", headers=h)
        self.assertNotIn(r.status_code, (401,))
        self.assertNotEqual((r.json().get("detail") or {}).get("error_code") if r.status_code >= 400 else "", "ADMIN_2FA_REQUIRED")

    def test_email_secret_needs_verified_email_and_user_id_form_still_works(self):
        os.environ["WELORA_ADMIN_TOTP_SECRETS"] = f"{FOUNDER}:{FAKE_TOTP}"
        u = auth_svc.register_guest(email=FOUNDER, password="Passw0rd!x")  # email NOT verified
        self.assertFalse(admin_2fa.is_enrolled(u["user_id"]))
        with self.assertRaises(admin_2fa.TwoFactorError):
            admin_2fa.verify_code(u["user_id"], admin_2fa.totp(FAKE_TOTP))
        # legacy user_id:BASE32 unchanged
        os.environ["WELORA_ADMIN_TOTP_SECRETS"] = f"{FOUNDER}:{FAKE_TOTP},{u['user_id']}:{FAKE_TOTP}"
        self.assertTrue(admin_2fa.is_enrolled(u["user_id"]))
        admin_2fa.verify_code(u["user_id"], admin_2fa.totp(FAKE_TOTP))  # no raise
        self.assertFalse(admin_2fa.is_enrolled("nobody"))

    def test_gen_by_email_and_by_user_id(self):
        def run(*argv):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = admin_2fa._main(list(argv))
            return rc, buf.getvalue()

        rc, out = run("gen", "Founder@Example.test")
        self.assertEqual(rc, 0)
        line = [l for l in out.splitlines() if l.startswith(FOUNDER + ":")][0]
        secret = line.split(":", 1)[1]
        self.assertEqual(len(admin_2fa._b32decode(secret)), 20)
        self.assertIn("email:secret", out)
        self.assertIn("otpauth://totp/", out)
        rc, out = run("gen", "3f1c-user-id")
        self.assertEqual(rc, 0)
        self.assertIn("user_id:secret", out)
        self.assertTrue(any(l.startswith("3f1c-user-id:") for l in out.splitlines()))
        self.assertEqual(run("gen", "a:b")[0], 2)
        self.assertEqual(run("gen")[0], 2)


class TestConstraints(_Base):
    def test_constraints_unchanged(self):
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        self.assertFalse(h["entitlements"]["lifetime_enabled"])
        self.assertFalse(ent.load_pricing_module()["checkout_enabled"])
