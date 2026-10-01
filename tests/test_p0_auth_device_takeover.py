"""P0 — account takeover via POST /auth/device (CoS review of PR #236).

Internal users.device_id values used to be derived from public data
(guest:/phone:/email:/demo: + sha256(email|phone)[:16]) and /auth/device returned a token for
ANY matching row. Per user type: the guessable id, the row's real id, and an arbitrary id written
onto the row (legacy/rewritten) must never yield a token. Pure device guests keep working.
Runs on SQLite; set WELORA_TEST_POSTGRES_URL for PostgreSQL.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import tempfile
import unittest

from fastapi.testclient import TestClient

from tests._authz import admin_demo_seed
from tests._db_target import db_env
from welora import auth as auth_svc
from welora import checkout as co
from welora import entitlements as ent
from welora import mailer
from welora.api.app import create_app
from welora.db.connection import get_connection
from welora.safety_gate import TARGET_MONTHS

ENV_KEYS = (
    "WELORA_ENV", "WELORA_STORE", "WELORA_DB_URL", "WELORA_GUEST_DEMO", "WELORA_MAIL_SYNC", "WELORA_OTP_FIXED",
    "WELORA_ADMIN_EMAILS", "WELORA_ADMIN_TOTP_SECRETS", "WELORA_CHECKOUT_ENABLED", "WELORA_SMTP_HOST",
    "WELORA_OTP_ECHO", "WELORA_RESET_ECHO", "WELORA_RL_WINDOW_S", "WELORA_RL_TARGET_MAX", "WELORA_RL_IP_MAX",
    "WELORA_RL_VERIFY_TARGET_MAX", "WELORA_RL_VERIFY_IP_MAX",
)
FOUNDER = "founder@example.test"


def derived(prefix: str, value: str) -> str:
    """The pre-fix (guessable) internal device_id formula."""
    return prefix + hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="welora-dev-")
        os.environ.update({"WELORA_ENV": "staging", "WELORA_GUEST_DEMO": "1", "WELORA_MAIL_SYNC": "1", **db_env(self.tmp)})
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

    # helpers -----------------------------------------------------------
    def q1(self, sql, params=()):
        conn = get_connection(None)
        try:
            r = conn.execute(sql, params).fetchone()
            return dict(r) if r else None
        finally:
            conn.close()

    def x(self, sql, params=()):
        conn = get_connection(None)
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def device(self, device_id):
        return self.client.post("/auth/device", json={"device_id": device_id})

    def device_id_of(self, uid):
        return self.q1("SELECT device_id FROM users WHERE user_id=?", (uid,))["device_id"]

    def assert_no_token(self, r, victim_uid, *, codes=(403,)):
        self.assertIn(r.status_code, codes, r.text)
        self.assertNotIn("token", r.text.lower().replace("token_", ""))
        self.assertNotIn(victim_uid, r.text)

    def assert_takeover_blocked(self, uid, guessable, *, accounts_token=None):
        # 1) guessable pre-fix formula → reserved prefix → 403 DEVICE_ID_RESERVED (VI)
        r = self.device(guessable)
        self.assert_no_token(r, uid, codes=(403,))
        self.assertEqual(r.json()["detail"]["error_code"], "DEVICE_ID_RESERVED")
        self.assertEqual(r.json()["detail"]["message"], auth_svc.DEVICE_RESERVED_MSG)
        # 2) the row's real (now random) internal id → also reserved
        real = self.device_id_of(uid)
        self.assertTrue(auth_svc.is_reserved_device_id(real), real)
        self.assertNotEqual(real, guessable)  # new rows are random, not derived
        self.assert_no_token(self.device(real), uid, codes=(403,))
        # 3) legacy staging row still carrying the derived id → still blocked
        self.x("UPDATE users SET device_id=? WHERE user_id=?", (guessable, uid))
        self.assert_no_token(self.device(guessable), uid, codes=(403,))
        # 4) arbitrary non-prefixed id written onto the row → 403 DEVICE_NOT_GUEST, no token
        arb = "legacy-dev-" + uid[:8]
        self.x("UPDATE users SET device_id=? WHERE user_id=?", (arb, uid))
        r = self.device(arb)
        self.assert_no_token(r, uid, codes=(403,))
        self.assertEqual(r.json()["detail"]["error_code"], "DEVICE_NOT_GUEST")
        self.assertEqual(r.json()["detail"]["message"], auth_svc.DEVICE_NOT_GUEST_MSG)
        # no token was minted for the victim by any attempt
        n = self.q1("SELECT COUNT(*) AS n FROM auth_tokens WHERE user_id=? AND kind='device'", (uid,))["n"]
        self.assertEqual(n, 0)


class TestDeviceTakeoverPerUserType(_Base):
    def test_password_email_user(self):
        email = "victim.mail@example.test"
        r = self.client.post("/auth/register", json={"email": email, "password": "VictimPass1!"})
        self.assertEqual(r.status_code, 201, r.text)
        uid = r.json()["user_id"]
        self.assert_takeover_blocked(uid, derived("guest:", email))
        # owner login unaffected
        login = self.client.post("/auth/login", json={"email": email, "password": "VictimPass1!"})
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["user_id"], uid)

    def test_password_phone_user(self):
        phone = "0912345678"
        r = self.client.post("/auth/register", json={"phone": phone, "password": "VictimPass1!"})
        self.assertEqual(r.status_code, 201, r.text)
        uid = r.json()["user_id"]
        phone_n = self.q1("SELECT phone FROM users WHERE user_id=?", (uid,))["phone"]
        self.assert_takeover_blocked(uid, derived("guest:", phone_n))
        login = self.client.post("/auth/login", json={"phone": phone, "password": "VictimPass1!"})
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["user_id"], uid)

    def _otp(self, phone):
        os.environ["WELORA_OTP_ECHO"] = "1"  # staging demo flag: these tests read the echoed code
        req = self.client.post("/auth/otp/request", json={"phone": phone})
        self.assertEqual(req.status_code, 200, req.text)
        ver = self.client.post("/auth/otp/verify", json={"challenge_id": req.json()["challenge_id"], "code": req.json()["pilot_code"]})
        self.assertEqual(ver.status_code, 200, ver.text)
        return ver.json()

    def test_phone_otp_user(self):
        phone = "0987654321"
        first = self._otp(phone)
        uid = first["user_id"]
        self.assert_takeover_blocked(uid, derived("phone:", phone))
        # returning phone-OTP user is found by phone (OTP history), not by a derived device_id
        self.assertEqual(self._otp(phone)["user_id"], uid)

    def test_phone_otp_legacy_row_still_recognised(self):
        phone = "0901112223"
        uid = self._otp(phone)["user_id"]
        self.x("UPDATE users SET device_id=? WHERE user_id=?", (derived("phone:", phone), uid))  # pre-fix row
        self.assertEqual(self._otp(phone)["user_id"], uid)
        self.assert_no_token(self.device(derived("phone:", phone)), uid, codes=(403,))

    def test_demo_persona(self):
        seed = admin_demo_seed(self.client)
        self.assertEqual(seed.status_code, 200, seed.text)
        emails = seed.json()["rich"]["persona_emails"]
        for pid in ("P1", "P4"):
            email = emails[pid]
            login = self.client.post("/auth/login", json={"email": email, "password": auth_svc.DEMO_PASSWORD})
            self.assertEqual(login.status_code, 200, login.text)
            uid = login.json()["user_id"]
            with self.subTest(pid=pid):
                self.assert_takeover_blocked(uid, derived("demo:", email))
        # re-seed + login still work afterwards
        self.assertEqual(admin_demo_seed(self.client).status_code, 200)
        again = self.client.post("/auth/login", json={"email": emails["P1"], "password": auth_svc.DEMO_PASSWORD})
        self.assertEqual(again.status_code, 200, again.text)

    def test_email_otp_admin(self):
        os.environ["WELORA_ADMIN_EMAILS"] = FOUNDER
        n = len(self.mails)
        r = self.client.post("/auth/email-otp/request", json={"email": FOUNDER})
        self.assertEqual(r.status_code, 200, r.text)
        code = re.search(r"\b(\d{6})\b", self.mails[n:][-1][2]).group(1)
        v = self.client.post("/auth/email-otp/verify", json={"challenge_id": r.json()["challenge_id"], "code": code})
        self.assertEqual(v.status_code, 200, v.text)
        self.assertEqual(v.json()["role"], "admin")
        uid = v.json()["user_id"]
        self.assert_takeover_blocked(uid, derived("email:", FOUNDER))


class TestOtpEchoFlag(_Base):
    """pilot_code is echoed only with WELORA_OTP_ECHO=1 (default OFF)."""

    def _request(self, phone="0933334444"):
        r = self.client.post("/auth/otp/request", json={"phone": phone})
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def _stored_code(self, challenge_id):
        return self.q1("SELECT code FROM otp_challenges WHERE challenge_id=?", (challenge_id,))["code"]

    def test_default_off_no_echo_and_health_false(self):
        os.environ["WELORA_OTP_FIXED"] = "1"  # known code, so we can assert it never appears
        for val in (None, "", "0", "true", "yes", "on", " 2 "):
            if val is None:
                os.environ.pop("WELORA_OTP_ECHO", None)
            else:
                os.environ["WELORA_OTP_ECHO"] = val
            with self.subTest(flag=val):
                body = self._request(f"09{abs(hash(str(val))) % 10**8:08d}")
                self.assertNotIn("pilot_code", body)
                self.assertNotIn("pilot_note", body)
                self.assertNotIn(auth_svc.FIXED_OTP, str({k: v for k, v in body.items() if k != "challenge_id"}))
                self.assertIs(body["otp_echo"], False)
                self.assertIs(body["sms_enabled"], False)
                h = self.client.get("/health").json()
                self.assertIs(h["otp_echo"], False)
                self.assertIs(h["sms_enabled"], False)

    def test_flag_off_user_can_still_type_code_and_errors_do_not_leak(self):
        os.environ.pop("WELORA_OTP_ECHO", None)
        os.environ["WELORA_OTP_FIXED"] = "1"
        code = auth_svc.FIXED_OTP
        body = self._request("0944445555")
        stored = self._stored_code(body["challenge_id"])
        self.assertTrue(stored.startswith("sha256:"))  # hashed at rest
        self.assertNotIn(code, stored)
        bad = self.client.post("/auth/otp/verify", json={"challenge_id": body["challenge_id"], "code": "000000"})
        self.assertEqual(bad.status_code, 400)
        self.assertNotIn(code, bad.text)
        ok = self.client.post("/auth/otp/verify", json={"challenge_id": body["challenge_id"], "code": code})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertNotIn(code, ok.text.replace(ok.json()["token"], ""))
        reused = self.client.post("/auth/otp/verify", json={"challenge_id": body["challenge_id"], "code": code})
        self.assertNotEqual(reused.status_code, 200)
        self.assertNotIn(code, reused.text)

    def test_flag_on_echoes_code_and_health_true(self):
        os.environ["WELORA_OTP_ECHO"] = "1"
        body = self._request()
        self.assertRegex(body["pilot_code"], r"^\d{6}$")
        self.assertNotEqual(self._stored_code(body["challenge_id"]), body["pilot_code"])
        self.assertIs(body["otp_echo"], True)
        self.assertIs(self.client.get("/health").json()["otp_echo"], True)
        ok = self.client.post("/auth/otp/verify", json={"challenge_id": body["challenge_id"], "code": body["pilot_code"]})
        self.assertEqual(ok.status_code, 200, ok.text)

    def test_otp_page_notice_when_no_code(self):
        from pathlib import Path

        html = (Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "otp.html").read_text(encoding="utf-8")
        self.assertIn('id="otpNotice"', html)
        self.assertIn("Kênh SMS chưa bật", html)
        self.assertIn("Mã đã gửi qua SMS", html)
        self.assertIn("d.sms_enabled", html)
        self.assertIn('id="code"', html)  # code input stays available
        self.assertNotIn("innerHTML", html)

    def test_render_yaml_declares_flag_without_value(self):
        from pathlib import Path

        y = (Path(__file__).resolve().parents[1] / "render.yaml").read_text(encoding="utf-8")
        i = y.index("- key: WELORA_OTP_ECHO")
        self.assertIn("sync: false", y[i:i + 80])
        self.assertNotIn("value:", y[i:i + 80].split("- key:")[1])


class TestPureGuestAndPrefixes(_Base):
    def test_reserved_prefixes_rejected_any_case(self):
        for did in ("guest:abcd1234", "PHONE:abcd1234", "Email:abcd1234", "demo:abcd1234", "  guest:abcd1234"):
            r = self.device(did)
            with self.subTest(device_id=did):
                self.assertEqual(r.status_code, 403, r.text)
                self.assertEqual(r.json()["detail"]["error_code"], "DEVICE_ID_RESERVED")

    def test_pure_guest_gets_own_token_on_repeat(self):
        r1 = self.device("web-guest-abc123")
        self.assertEqual(r1.status_code, 200, r1.text)
        self.assertTrue(r1.json()["created"])
        r2 = self.device("web-guest-abc123")
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertFalse(r2.json()["created"])
        self.assertEqual(r1.json()["user_id"], r2.json()["user_id"])
        self.assertNotEqual(r1.json()["token"], r2.json()["token"])
        for tok in (r1.json()["token"], r2.json()["token"]):
            me = self.client.get("/auth/me", headers={"Authorization": "Bearer " + tok})
            self.assertEqual(me.json()["user_id"], r1.json()["user_id"])

    def test_guest_onboarding_flow_still_works(self):
        g = self.device("web-guest-onb-001").json()
        h = {"Authorization": "Bearer " + g["token"]}
        s = self.client.post("/onboarding/session", json={"user_id": g["user_id"]}, headers=h)
        self.assertEqual(s.status_code, 201, s.text)
        sid = s.json()["session_id"]
        r = self.client.patch(f"/onboarding/session/{sid}/step/1", json={"life_stage": "young_single", "income_stability": "stable", "family_context": "alone"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        r = self.client.patch(f"/onboarding/session/{sid}/step/2", json={"essential_expense_monthly": 8_000_000, "has_dangerous_debt_self": False, "near_term_priority": "safety"}, headers=h)
        self.assertEqual(r.status_code, 200, r.text)
        done = self.client.post(f"/onboarding/session/{sid}/complete", headers=h)
        self.assertEqual(done.status_code, 200, done.text)
        again = self.device("web-guest-onb-001").json()  # same device later → same guest, sees own DNA
        self.assertEqual(again["user_id"], g["user_id"])
        dna = self.client.get(f"/users/{g['user_id']}/dna", headers={"Authorization": "Bearer " + again["token"]})
        self.assertEqual(dna.status_code, 200, dna.text)

    def test_guest_row_with_other_login_history_not_reusable(self):
        g = self.device("web-guest-hist-01").json()
        conn = get_connection(None)
        try:
            auth_svc._issue_token(conn, g["user_id"], "password")
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(self.device("web-guest-hist-01").status_code, 403)

    def test_invariants(self):
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
