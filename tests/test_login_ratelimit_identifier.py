"""Hotfix after PR #237 — /auth/login rate-limit identifier bypass + concurrency burst.

1. {email: junk<N>, phone: victim} used a fresh key per request while the lookup fell back to the
   victim's phone (CoS reproduced 15 failures, no block). Now: both identifiers → 400; buckets key
   on the RESOLVED account (user_id), so a user's email and phone share one budget.
2. Check and record straddled the password hash, so a parallel burst overshot the limit. Now the
   attempt is reserved (insert, commit, count) before hashing.
Runs on SQLite, or PG17 via WELORA_TEST_POSTGRES_URL.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import unittest

from fastapi.testclient import TestClient

from tests._db_target import db_env
from welora import auth as auth_svc
from welora import auth_ratelimit as rl
from welora.api.app import create_app
from welora.db.connection import get_connection
from welora.safety_gate import TARGET_MONTHS

ENV_KEYS = (
    "WELORA_ENV", "WELORA_STORE", "WELORA_DB_URL", "WELORA_GUEST_DEMO", "WELORA_RL_WINDOW_S",
    "WELORA_RL_TARGET_MAX", "WELORA_RL_IP_MAX", "WELORA_RL_LOGIN_PAIR_MAX", "WELORA_RL_LOGIN_ACCOUNT_MAX",
    "WELORA_RL_LOGIN_IP_MAX",
)
PW = "matkhau-dai-1"
BAD = "sai-mat-khau-1"
V_EMAIL, V_PHONE = "victim@example.test", "0987654321"


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="welora-rlid-")
        os.environ.update({"WELORA_ENV": "staging", "WELORA_GUEST_DEMO": "1", "WELORA_RL_IP_MAX": "1000",
                           "WELORA_RL_TARGET_MAX": "1000", **db_env(self.tmp)})
        self.client = TestClient(create_app())
        r = self.client.post("/auth/register", json={"email": V_EMAIL, "phone": V_PHONE, "password": PW},
                             headers={"CF-Connecting-IP": "203.0.113.200"})
        self.assertEqual(r.status_code, 201, r.text)
        self.victim = r.json()["user_id"]

    def tearDown(self) -> None:
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def login(self, ip="198.51.100.7", password=PW, **ident):
        return self.client.post("/auth/login", json={**ident, "password": password}, headers={"CF-Connecting-IP": ip})

    def fail_rows(self) -> int:
        conn = get_connection(None)
        try:
            return conn.execute("SELECT COUNT(*) AS n FROM auth_rate_events WHERE action='login_fail'").fetchone()["n"]
        finally:
            conn.close()


class TestIdentifierBypass(_Base):
    def test_junk_email_plus_victim_phone_is_400(self):
        for i in range(15):  # CoS repro: 15 × fresh junk email + victim phone
            r = self.login(email=f"junk{i}@x.yz", phone=V_PHONE, password=BAD)
            self.assertEqual(r.status_code, 400, r.text)
            self.assertEqual(r.json()["detail"], auth_svc.LOGIN_ONE_IDENTIFIER_MSG)
        # even with the right password — one identifier only
        self.assertEqual(self.login(email=V_EMAIL, phone=V_PHONE).status_code, 400)
        self.assertEqual(self.fail_rows(), 0)  # no password was ever checked
        self.assertEqual(self.login(phone=V_PHONE).status_code, 200)

    def test_blank_second_identifier_is_fine(self):
        self.assertEqual(self.login(email=V_EMAIL, phone="").status_code, 200)
        self.assertEqual(self.login(email="  ", phone=V_PHONE).status_code, 200)

    def test_email_and_phone_share_pair_budget(self):
        codes = [self.login(ip="198.51.100.1", password=BAD, **({"email": V_EMAIL} if i % 2 else {"phone": V_PHONE})).status_code
                 for i in range(10)]
        self.assertEqual(codes, [401] * 10)
        self.assertEqual(self.login(ip="198.51.100.1", phone=V_PHONE).status_code, 429)
        self.assertEqual(self.login(ip="198.51.100.1", email=V_EMAIL).status_code, 429)
        self.assertEqual(self.login(ip="198.51.100.2", phone=V_PHONE).status_code, 200)  # other IP fine

    def test_email_and_phone_share_account_budget_50(self):
        os.environ["WELORA_RL_LOGIN_IP_MAX"] = "0"
        for i in range(50):
            ip = f"198.51.{100 + i // 9}.{i % 9 + 1}"  # ≤ 9 per IP → never a pair lock
            ident = {"email": V_EMAIL} if i % 2 else {"phone": V_PHONE}
            self.assertEqual(self.login(ip=ip, password=BAD, **ident).status_code, 401, i)
        self.assertEqual(self.login(ip="203.0.113.9", phone=V_PHONE).status_code, 429)
        self.assertEqual(self.login(ip="203.0.113.9", email=V_EMAIL).status_code, 429)

    def test_rate_key_resolution(self):
        self.assertEqual(auth_svc.login_rate_key(email="VICTIM@example.test "), "user:" + self.victim)
        self.assertEqual(auth_svc.login_rate_key(phone="0987 654 321"), "user:" + self.victim)
        self.assertEqual(auth_svc.login_rate_key(email="nobody@example.test"), "email:nobody@example.test")
        self.assertEqual(auth_svc.login_rate_key(phone="0900 000 111"), "phone:0900000111")
        self.assertEqual(auth_svc.login_rate_key(), "")

    def test_unknown_accounts_count_per_identifier_and_ip_without_oracle(self):
        os.environ.update({"WELORA_RL_LOGIN_PAIR_MAX": "3", "WELORA_RL_LOGIN_IP_MAX": "5"})
        ghost = [self.login(ip="192.0.2.1", email="ghost@example.test", password=BAD) for _ in range(4)]
        real = [self.login(ip="192.0.2.2", email=V_EMAIL, password=BAD) for _ in range(4)]
        self.assertEqual([r.status_code for r in ghost], [401, 401, 401, 429])
        self.assertEqual([r.status_code for r in real], [401, 401, 401, 429])
        self.assertEqual(ghost[0].json(), real[0].json())  # same body: existence not revealed
        self.assertEqual(ghost[3].json(), real[3].json())
        # per-IP ceiling also counts unknown accounts
        codes = [self.login(ip="192.0.2.3", email=f"g{i}@example.test", password=BAD).status_code for i in range(6)]
        self.assertEqual(codes, [401] * 5 + [429])

    def test_phone_only_and_email_only_still_work(self):
        a = self.login(phone=V_PHONE)
        b = self.login(email=V_EMAIL)
        self.assertEqual((a.status_code, b.status_code), (200, 200))
        self.assertEqual(a.json()["user_id"], b.json()["user_id"])

    def test_twenty_correct_logins_never_429_and_leave_no_rows(self):
        codes = [self.login(ip="203.0.113.5", **({"email": V_EMAIL} if i % 2 else {"phone": V_PHONE})).status_code
                 for i in range(20)]
        self.assertEqual(codes, [200] * 20)
        self.assertEqual(self.fail_rows(), 0)

    def test_login_html_sends_one_identifier(self):
        from pathlib import Path

        html = (Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "login.html").read_text(encoding="utf-8")
        self.assertIn("if(v.includes('@')) return {email:v};", html)
        self.assertIn("return {phone:v};", html)
        self.assertIn("const body={password,...parts};", html)

    def test_constraints(self):
        self.assertEqual(TARGET_MONTHS, 3)


class TestConcurrencyBurst(_Base):
    N = 24
    LIMIT = 5

    def _burst(self, fn):
        start = threading.Barrier(self.N)
        out: list = []
        lock = threading.Lock()

        def run():
            start.wait()
            res = fn()
            with lock:
                out.append(res)

        threads = [threading.Thread(target=run) for _ in range(self.N)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        return out

    def test_reserve_level_burst_never_exceeds_limit(self):
        os.environ["WELORA_RL_LOGIN_PAIR_MAX"] = str(self.LIMIT)

        def attempt():
            try:
                a = rl.login_reserve(ip="192.0.2.77", account="user:" + self.victim)
            except rl.RateLimited:
                return "429"
            time.sleep(0.05)  # the password hash
            rl.login_commit_failure(a)
            return "401"

        res = self._burst(attempt)
        self.assertEqual(len(res), self.N)
        self.assertLessEqual(res.count("401"), self.LIMIT)
        self.assertGreaterEqual(res.count("401"), 1)

    def test_http_burst_of_wrong_passwords_never_exceeds_limit(self):
        os.environ["WELORA_RL_LOGIN_PAIR_MAX"] = str(self.LIMIT)
        # warm-up: login_guest lazily seeds the partner demo row; concurrent FIRST logins race on that
        # insert (pre-existing, see PR Follow-up) — not what this test measures
        self.assertEqual(self.login(ip="192.0.2.79", phone=V_PHONE).status_code, 200)
        res = self._burst(lambda: self.login(ip="192.0.2.78", phone=V_PHONE, password=BAD).status_code)
        self.assertEqual(len(res), self.N)
        self.assertEqual(set(res) - {401, 429}, set(), res)
        self.assertLessEqual(res.count(401), self.LIMIT, res)
        self.assertGreaterEqual(res.count(401), 1)
        # every 401 left exactly one pair row; every 429 left none (refused reservations are removed)
        self.assertEqual(self.fail_rows() // 3, res.count(401))
        print(f"\n[burst N={self.N} limit={self.LIMIT}] 401={res.count(401)} 429={res.count(429)}")


if __name__ == "__main__":
    unittest.main()
