"""P0 (CoS final scope) — password-reset echo gate + single-use/expiry, shared-DB rate limits
on /auth/otp/request · /auth/otp/verify · /auth/forgot-password, phone-OTP codes hashed at rest.
SQLite by default; WELORA_TEST_POSTGRES_URL → PostgreSQL.
"""

from __future__ import annotations

import os
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_p0_auth_device_takeover import _Base
from welora import auth as auth_svc
from welora import auth_ratelimit as rl
from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]


class TestPasswordReset(_Base):
    PW = "ResetPass1!"

    def _register(self, email="reset.target@example.test", phone=None):
        body = {"email": email, "password": self.PW} if email else {"phone": phone, "password": self.PW}
        r = self.client.post("/auth/register", json=body)
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def _forgot(self, **body):
        return self.client.post("/auth/forgot-password", json=body)

    def test_flag_off_no_token_and_identical_for_existing_and_missing(self):
        os.environ.pop("WELORA_RESET_ECHO", None)
        self._register("exists@example.test")
        self._register(email=None, phone="0915556666")
        r_exist = self._forgot(email="exists@example.test")
        r_missing = self._forgot(email="nobody.here@example.test")
        r_phone = self._forgot(phone="0915556666")
        r_phone_missing = self._forgot(phone="0919999999")
        bodies = [r.json() for r in (r_exist, r_missing, r_phone, r_phone_missing)]
        self.assertEqual({r.status_code for r in (r_exist, r_missing, r_phone, r_phone_missing)}, {200})
        self.assertTrue(all(b == bodies[0] for b in bodies), bodies)
        self.assertNotIn("reset_token", bodies[0])
        self.assertIs(bodies[0]["reset_echo"], False)
        self.assertEqual(bodies[0]["message"], auth_svc.RESET_GENERIC_MSG)
        self.assertEqual(self.q1("SELECT COUNT(*) AS n FROM password_reset_tokens")["n"], 0)
        self.assertIs(self.client.get("/health").json()["reset_echo"], False)
        for val in ("0", "true", "yes", " 2"):
            os.environ["WELORA_RESET_ECHO"] = val
            self.assertNotIn("reset_token", self._forgot(email=f"exists{val.strip()}@example.test").json())

    def test_flag_on_token_present_and_missing_account_same_shape(self):
        os.environ["WELORA_RESET_ECHO"] = "1"
        self._register("exists@example.test")
        r = self._forgot(email="exists@example.test")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["reset_token"])
        self.assertIs(r.json()["reset_echo"], True)
        missing = self._forgot(email="nobody.here@example.test").json()
        self.assertNotIn("reset_token", missing)
        self.assertEqual(missing["message"], r.json()["message"])
        self.assertIs(self.client.get("/health").json()["reset_echo"], True)

    def _token(self, email="exists@example.test"):
        os.environ["WELORA_RESET_ECHO"] = "1"
        return self._forgot(email=email).json()["reset_token"]

    def test_expired_token_rejected(self):
        self._register("exists@example.test")
        tok = self._token()
        self.x("UPDATE password_reset_tokens SET expires_at=? WHERE token=?", ("2020-01-01T00:00:00+00:00", tok))
        r = self.client.post("/auth/reset-password", json={"reset_token": tok, "new_password": "NewPass1!x"})
        self.assertEqual(r.status_code, 400, r.text)
        self.assertEqual(self.client.post("/auth/login", json={"email": "exists@example.test", "password": self.PW}).status_code, 200)

    def test_token_single_use_and_siblings_voided(self):
        self._register("exists@example.test")
        t1, t2 = self._token(), self._token()
        ok = self.client.post("/auth/reset-password", json={"reset_token": t1, "new_password": "NewPass1!x"})
        self.assertEqual(ok.status_code, 200, ok.text)
        again = self.client.post("/auth/reset-password", json={"reset_token": t1, "new_password": "Other1!xyz"})
        self.assertEqual(again.status_code, 400, again.text)
        sibling = self.client.post("/auth/reset-password", json={"reset_token": t2, "new_password": "Other1!xyz"})
        self.assertEqual(sibling.status_code, 400, sibling.text)
        self.assertEqual(self.client.post("/auth/login", json={"email": "exists@example.test", "password": "NewPass1!x"}).status_code, 200)

    def test_ttl_is_short(self):
        self.assertLessEqual(auth_svc.RESET_TTL_MINUTES, 30)

    def test_forgot_page_degrades_and_render_yaml(self):
        html = (ROOT / "welora/api/static/forgot-password.html").read_text(encoding="utf-8")
        self.assertIn('id="resetNotice"', html)
        self.assertIn("Kênh gửi mã đặt lại (email/SMS) chưa bật", html)
        y = (ROOT / "render.yaml").read_text(encoding="utf-8")
        i = y.index("- key: WELORA_RESET_ECHO")
        self.assertIn("sync: false", y[i:i + 60])
        self.assertNotIn("value:", y[i:i + 60])


class TestRateLimits(_Base):
    def setUp(self) -> None:
        super().setUp()
        os.environ.update({"WELORA_RL_TARGET_MAX": "3", "WELORA_RL_IP_MAX": "5",
                           "WELORA_RL_VERIFY_TARGET_MAX": "4", "WELORA_RL_VERIFY_IP_MAX": "6"})

    def otp_req(self, phone, ip="203.0.113.7", client=None):
        return (client or self.client).post("/auth/otp/request", json={"phone": phone}, headers={"X-Forwarded-For": ip})

    def assert_429(self, r):
        self.assertEqual(r.status_code, 429, r.text)
        self.assertEqual(r.json()["detail"]["error_code"], "RATE_LIMITED")
        self.assertEqual(r.json()["detail"]["message"], rl.RATE_LIMIT_MSG)
        self.assertGreaterEqual(int(r.headers["retry-after"]), 1)

    def test_otp_request_per_target(self):
        for i in range(3):
            self.assertEqual(self.otp_req("0911000111", ip=f"198.51.100.{i}").status_code, 200)
        self.assert_429(self.otp_req("0911000111", ip="198.51.100.99"))  # new IP, same phone
        self.assert_429(self.otp_req("+84 911 000 111", ip="198.51.100.98"))  # same phone, other format
        self.assertEqual(self.otp_req("0911000222", ip="198.51.100.97").status_code, 200)  # other phone OK

    def test_otp_request_per_ip(self):
        for i in range(5):
            self.assertEqual(self.otp_req(f"09120000{i:02d}").status_code, 200)
        self.assert_429(self.otp_req("0912000099"))
        self.assertEqual(self.otp_req("0912000099", ip="203.0.113.8").status_code, 200)

    def test_shared_across_instances(self):
        other = TestClient(create_app())  # second app instance, same DB
        self.assertEqual(self.otp_req("0913000111").status_code, 200)
        self.assertEqual(self.otp_req("0913000111", client=other).status_code, 200)
        self.assertEqual(self.otp_req("0913000111").status_code, 200)
        self.assert_429(self.otp_req("0913000111", client=other))

    def test_window_expiry_and_disable(self):
        for _ in range(3):
            self.otp_req("0914000111")
        self.assert_429(self.otp_req("0914000111"))
        self.x("UPDATE auth_rate_events SET created_at=?", ("2020-01-01T00:00:00.000000+00:00",))
        self.assertEqual(self.otp_req("0914000111").status_code, 200)
        os.environ["WELORA_RL_TARGET_MAX"] = "0"
        os.environ["WELORA_RL_IP_MAX"] = "0"
        for _ in range(8):
            self.assertEqual(self.otp_req("0914000111").status_code, 200)

    def test_otp_verify_limited(self):
        os.environ["WELORA_RL_TARGET_MAX"] = "50"
        cids = [self.otp_req("0916000111").json()["challenge_id"] for _ in range(3)]
        codes = []
        for i in range(4):
            r = self.client.post("/auth/otp/verify", json={"challenge_id": cids[i % 3], "code": "000000"},
                                 headers={"X-Forwarded-For": f"192.0.2.{i}"})
            codes.append(r.status_code)
        self.assertNotIn(429, codes)
        self.assert_429(self.client.post("/auth/otp/verify", json={"challenge_id": cids[0], "code": "000000"},
                                         headers={"X-Forwarded-For": "192.0.2.50"}))

    def test_forgot_password_limited_even_for_missing_account(self):
        for i in range(3):
            r = self.client.post("/auth/forgot-password", json={"email": "ghost@example.test"},
                                 headers={"X-Forwarded-For": f"198.51.100.{i}"})
            self.assertEqual(r.status_code, 200, r.text)
        self.assert_429(self.client.post("/auth/forgot-password", json={"email": "GHOST@example.test"},
                                         headers={"X-Forwarded-For": "198.51.100.77"}))

    def test_no_raw_pii_stored(self):
        self.otp_req("0917000111")
        rows = self.x_all("SELECT key_hash FROM auth_rate_events")
        self.assertTrue(rows)
        self.assertFalse(any("0917000111" in r["key_hash"] or "203.0.113" in r["key_hash"] for r in rows))

    def x_all(self, sql):
        from welora.db.connection import get_connection

        conn = get_connection(None)
        try:
            return [dict(r) for r in conn.execute(sql).fetchall()]
        finally:
            conn.close()

    def test_client_ip_rules(self):
        self.assertEqual(rl.client_ip("8.8.8.8", "1.2.3.4"), "8.8.8.8")  # public peer: XFF ignored
        self.assertEqual(rl.client_ip("10.0.0.3", "1.2.3.4, 10.0.0.3"), "1.2.3.4")  # behind proxy
        self.assertEqual(rl.client_ip("10.0.0.3", None), "10.0.0.3")


class TestPhoneOtpHashing(_Base):
    def test_hashed_at_rest_and_legacy_plaintext_row_refused(self):
        os.environ["WELORA_OTP_ECHO"] = "1"
        r = self.client.post("/auth/otp/request", json={"phone": "0918000111"}).json()
        stored = self.q1("SELECT code FROM otp_challenges WHERE challenge_id=?", (r["challenge_id"],))["code"]
        self.assertTrue(stored.startswith("hmac256:"))
        self.assertNotIn(r["pilot_code"], stored)
        # a plaintext row (pre-HMAC format) is no longer accepted: fails like a wrong code
        # (follow-up sau #246/#247 item 3)
        cid = str(uuid.uuid4())
        self.x("INSERT INTO otp_challenges(challenge_id, phone, code, expires_at) VALUES (?,?,?,?)",
               (cid, "0918000222", "654321", "2099-01-01T00:00:00+00:00"))
        bad = self.client.post("/auth/otp/verify", json={"challenge_id": cid, "code": "111111"})
        self.assertEqual(bad.status_code, 400)
        right = self.client.post("/auth/otp/verify", json={"challenge_id": cid, "code": "654321"})
        self.assertEqual((right.status_code, right.json()), (400, bad.json()))
        # a hashed row cannot be verified by sending the stored hash itself
        r2 = self.client.post("/auth/otp/request", json={"phone": "0918000333"}).json()
        h = self.q1("SELECT code FROM otp_challenges WHERE challenge_id=?", (r2["challenge_id"],))["code"]
        self.assertEqual(self.client.post("/auth/otp/verify", json={"challenge_id": r2["challenge_id"], "code": h}).status_code, 400)

    def test_invariants(self):
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
