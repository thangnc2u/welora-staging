"""P0 follow-up 2 — auth hardening: /auth/device rate limit (3), real client IP (4), partner demo
seed race (5), expires_at in responses (8), phone E.164 + migration (9), safe RL release and
dummy hash (10).

SQLite by default; real PostgreSQL when WELORA_TEST_POSTGRES_URL is set (tests/_db_target.py).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from tests._db_target import db_env
from welora import admin_bootstrap, mailer  # noqa: F401  (admin_bootstrap import registers helpers)
from welora import auth as auth_svc
from welora import auth_ratelimit as rl
from welora.api.app import create_app
from welora.db.connection import get_connection
from welora.db.migrate import migrate
from welora.phone import lookup_candidates, normalize_phone_e164
from welora.phone_migration import normalize_existing_phones
from welora.safety_gate import TARGET_MONTHS

ENV_KEYS = (
    "WELORA_ENV", "WELORA_STORE", "WELORA_DB_URL", "WELORA_GUEST_DEMO", "WELORA_OTP_FIXED", "WELORA_OTP_ECHO",
    "WELORA_RESET_ECHO", "WELORA_MAIL_SYNC", "WELORA_ADMIN_EMAILS", "WELORA_RL_WINDOW_S", "WELORA_RL_TARGET_MAX",
    "WELORA_RL_IP_MAX", "WELORA_RL_LOGIN_PAIR_MAX", "WELORA_RL_LOGIN_ACCOUNT_MAX", "WELORA_RL_LOGIN_IP_MAX",
    "WELORA_RL_DEVICE_IP_MAX", "WELORA_RL_DEVICE_NEW_IP_MAX", "WELORA_CF_IP_RANGES",
)
PW = "matkhau-dai-2"


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="welora-fu2-")
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

    def ip(self, addr):
        return {"CF-Connecting-IP": addr}

    def legacy_user(self, uid, phone, password=PW, email=None):
        auth_svc.ensure_auth_schema()
        self.x("INSERT INTO users(user_id, display_name, device_id, email, phone, password_hash, role) VALUES (?,?,?,?,?,?,?)",
               (uid, uid, "guest:" + uid, email, phone, auth_svc._hash_password(password), "guest"))


# --- item 4 ------------------------------------------------------------------------------------

class TestClientIpTrust(unittest.TestCase):
    def setUp(self):
        self.prev = os.environ.pop("WELORA_CF_IP_RANGES", None)

    def tearDown(self):
        if self.prev is not None:
            os.environ["WELORA_CF_IP_RANGES"] = self.prev
        else:
            os.environ.pop("WELORA_CF_IP_RANGES", None)

    def test_trusted_proxy_ranges(self):
        for a in ("10.1.2.3", "172.16.0.1", "192.168.1.1", "127.0.0.1", "100.64.0.1", "100.127.255.254",
                  "::1", "fd00::1", "::ffff:10.0.0.1", "testclient", ""):
            self.assertTrue(rl.is_trusted_proxy(a), a)
        for a in ("100.63.255.255", "100.128.0.1", "8.8.8.8", "198.51.100.1", "203.0.113.9", "192.0.2.1",
                  "172.70.1.1", "2606:4700::1", "169.254.1.1"):
            self.assertFalse(rl.is_trusted_proxy(a), a)

    def test_render_cgnat_peer_behind_cloudflare(self):
        # Cloudflare → Render proxy (100.64/10) → app: XFF = "<client chain>, <cf edge>"
        h = {"CF-Connecting-IP": "203.0.113.50", "X-Forwarded-For": "203.0.113.50, 172.70.10.10"}
        self.assertEqual(rl.client_ip("100.64.8.9", headers=h), "203.0.113.50")
        h6 = {"CF-Connecting-IP": "2001:db8::50", "X-Forwarded-For": "2001:db8::50, 2606:4700::9, 10.0.0.2"}
        self.assertEqual(rl.client_ip("100.70.0.1", headers=h6), "2001:db8::50")

    def test_spoof_direct_to_origin_cf_header_ignored(self):
        # attacker hits *.onrender.com directly and forges CF-Connecting-IP / XFF: Render appends
        # the real address, which is not Cloudflare → that is the client
        h = {"CF-Connecting-IP": "1.1.1.1", "True-Client-IP": "1.1.1.2",
             "X-Forwarded-For": "1.1.1.1, 172.70.1.1, 198.51.100.66"}
        self.assertEqual(rl.client_ip("100.64.0.7", headers=h), "198.51.100.66")

    def test_spoof_through_cloudflare_leftmost_xff_never_used(self):
        # attacker sends XFF through Cloudflare; CF appends the real client and sets CF-Connecting-IP
        h = {"CF-Connecting-IP": "198.51.100.77", "X-Forwarded-For": "9.9.9.9, 198.51.100.77, 104.16.0.5"}
        self.assertEqual(rl.client_ip("100.64.0.7", headers=h), "198.51.100.77")
        # no CF header at all → the CF edge itself (never the forged leftmost hop)
        self.assertEqual(rl.client_ip("100.64.0.7", headers={"X-Forwarded-For": "9.9.9.9, 104.16.0.5"}), "104.16.0.5")

    def test_missing_cf_header_no_arbitrary_xff_fallback(self):
        self.assertEqual(rl.client_ip("10.0.0.1", headers={"X-Forwarded-For": "6.6.6.6, 198.51.100.8"}), "198.51.100.8")
        self.assertEqual(rl.client_ip("10.0.0.1", headers={"X-Forwarded-For": "6.6.6.6, garbage, 10.0.0.9"}), "10.0.0.1")
        self.assertEqual(rl.client_ip("10.0.0.1", headers={"X-Forwarded-For": "10.0.0.8, 10.0.0.9"}), "10.0.0.1")

    def test_public_peer_ignores_all_headers(self):
        h = {"CF-Connecting-IP": "1.1.1.1", "X-Forwarded-For": "1.1.1.1"}
        self.assertEqual(rl.client_ip("100.128.0.1", headers=h), "100.128.0.1")
        self.assertEqual(rl.client_ip("172.71.0.1", headers=h), "172.71.0.1")  # a CF address as peer is still a peer

    def test_cf_ranges_env_override(self):
        os.environ["WELORA_CF_IP_RANGES"] = "198.18.0.0/15"
        h = {"CF-Connecting-IP": "203.0.113.1", "X-Forwarded-For": "203.0.113.1, 198.18.0.1"}
        self.assertEqual(rl.client_ip("10.0.0.1", headers=h), "203.0.113.1")
        h2 = {"CF-Connecting-IP": "203.0.113.1", "X-Forwarded-For": "203.0.113.1, 104.16.0.5"}
        self.assertEqual(rl.client_ip("10.0.0.1", headers=h2), "104.16.0.5")

    def test_embedded_ranges_match_cloudflare_list(self):
        self.assertIn("173.245.48.0/20", rl.CLOUDFLARE_RANGES)
        self.assertIn("2606:4700::/32", rl.CLOUDFLARE_RANGES)
        self.assertEqual(len(rl.CLOUDFLARE_RANGES), 22)


class TestClientIpHttpSpoof(_Base):
    def test_login_bucket_not_dodged_by_rotating_cf_header(self):
        os.environ["WELORA_RL_LOGIN_IP_MAX"] = "3"
        codes = []
        for i in range(5):
            h = {"CF-Connecting-IP": f"192.0.2.{i + 1}", "X-Forwarded-For": "203.0.113.200"}  # direct-to-origin spoof
            codes.append(self.client.post("/auth/login", json={"email": f"nobody{i}@example.test", "password": "x" * 9},
                                          headers=h).status_code)
        self.assertEqual(codes, [401, 401, 401, 429, 429])


# --- item 3 ------------------------------------------------------------------------------------

class TestDeviceRateLimit(_Base):
    def dev(self, device_id, ip):
        return self.client.post("/auth/device", json={"device_id": device_id}, headers=self.ip(ip))

    def code(self, device_id, ip):
        """'new' (guest created) | 'reuse' | HTTP status for refusals."""
        r = self.dev(device_id, ip)
        if r.status_code != 200:
            return r.status_code
        return "new" if r.json()["created"] else "reuse"

    def test_new_guests_per_ip_limited_returning_guest_never_locked(self):
        os.environ["WELORA_RL_DEVICE_NEW_IP_MAX"] = "3"
        codes = [self.code(f"web-new{i:05d}", "198.51.100.10") for i in range(4)]
        self.assertEqual(codes, ["new", "new", "new", 429])
        r = self.dev("web-new00009", "198.51.100.10")
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json()["detail"]["error_code"], "RATE_LIMITED")
        self.assertIn("Retry-After", r.headers)
        # the same IP re-using an existing device_id keeps working (normal guest page loads)
        for _ in range(20):
            self.assertEqual(self.code("web-new00000", "198.51.100.10"), "reuse")
        self.assertEqual(self.code("web-new00099", "198.51.100.11"), "new")  # other IP unaffected

    def test_total_calls_per_ip_limit(self):
        os.environ["WELORA_RL_DEVICE_IP_MAX"] = "5"
        codes = [self.code("web-same0001", "198.51.100.20") for _ in range(6)]
        self.assertEqual(codes, ["new", "reuse", "reuse", "reuse", "reuse", 429])
        self.assertEqual(self.code("web-same0001", "198.51.100.21"), "reuse")

    def test_defaults_allow_normal_guest_use(self):
        self.assertEqual(rl.limits("device"), (0, 300))
        self.assertEqual(rl.limits("device_new"), (0, 30))
        codes = [self.code("web-normal01", "198.51.100.30") for _ in range(40)]
        self.assertEqual(codes, ["new"] + ["reuse"] * 39)

    def test_limit_disabled_with_zero(self):
        os.environ["WELORA_RL_DEVICE_NEW_IP_MAX"] = "0"
        codes = {self.code(f"web-zero{i:05d}", "198.51.100.40") for i in range(35)}
        self.assertEqual(codes, {"new"})


# --- item 5 ------------------------------------------------------------------------------------

class TestPartnerSeedRace(_Base):
    def test_concurrent_first_logins_create_one_partner(self):
        auth_svc.ensure_auth_schema()
        n = 8
        barrier = threading.Barrier(n)
        results, errors = [], []

        def worker(i):
            try:
                barrier.wait(timeout=10)
                if i % 3 == 2:
                    from welora.partner_demo_seed import _upsert_demo_user

                    _upsert_demo_user(user_id=auth_svc.PARTNER_USER_ID, email=auth_svc.DEMO_EMAIL,
                                      phone=auth_svc.DEMO_PHONE, display_name=auth_svc.DEMO_DISPLAY)
                    results.append("seed")
                else:
                    out = auth_svc.login_guest(email=auth_svc.DEMO_EMAIL, password=auth_svc.DEMO_PASSWORD)
                    results.append(out["user_id"])
            except Exception as e:  # pragma: no cover - the bug
                errors.append(repr(e))

        ts = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(60)
        self.assertEqual(errors, [])
        self.assertEqual(len(results), n)
        rows = self.q("SELECT user_id FROM users WHERE email=? OR phone=?", (auth_svc.DEMO_EMAIL, auth_svc.DEMO_PHONE))
        self.assertEqual([r["user_id"] for r in rows], [auth_svc.PARTNER_USER_ID])
        self.assertTrue(all(r in ("seed", auth_svc.PARTNER_USER_ID) for r in results))

    def test_insert_conflict_is_not_a_500(self):
        auth_svc.ensure_auth_schema()
        # a winner already holds the partner phone (any unique conflict) → loser does not raise
        self.legacy_user("someone-else", auth_svc.DEMO_PHONE)
        out = auth_svc.seed_partner_demo()
        self.assertFalse(out["seeded"])
        self.assertTrue(out["already"])
        self.assertEqual(len(self.q("SELECT 1 FROM users WHERE phone=?", (auth_svc.DEMO_PHONE,))), 1)

    def test_seed_idempotent(self):
        a = auth_svc.seed_partner_demo()
        b = auth_svc.seed_partner_demo()
        self.assertTrue(a["seeded"])
        self.assertTrue(b["already"])
        self.assertEqual(a["user_id"], b["user_id"])


# --- item 8 ------------------------------------------------------------------------------------

class TestExpiresAtInResponses(_Base):
    def exp_of(self, tok):
        return self.q("SELECT expires_at FROM auth_tokens WHERE token=?", (tok,))[0]["expires_at"]

    def check(self, body, name):
        self.assertIn("expires_at", body, name)
        self.assertEqual(body["expires_at"], self.exp_of(body["token"]), name)
        exp = datetime.fromisoformat(body["expires_at"])
        self.assertGreater(exp, datetime.now(timezone.utc), name)

    def test_all_token_issuing_paths_and_me(self):
        reg = self.client.post("/auth/register", json={"email": "exp2@example.test", "password": PW}, headers=self.ip("192.0.2.80"))
        self.assertEqual(reg.status_code, 201)
        self.check(reg.json(), "register")
        log = self.client.post("/auth/login", json={"email": "exp2@example.test", "password": PW}, headers=self.ip("192.0.2.80"))
        self.check(log.json(), "login")
        dev = self.client.post("/auth/device", json={"device_id": "web-exp2-001"})
        self.check(dev.json(), "device")
        os.environ["WELORA_OTP_FIXED"] = "1"
        ch = self.client.post("/auth/otp/request", json={"phone": "0901110002"}).json()
        otp = self.client.post("/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": "123456"})
        self.check(otp.json(), "otp")
        mails = []
        mailer.set_sender(lambda to, s, b: mails.append(b))
        os.environ["WELORA_ADMIN_EMAILS"] = "founder-fu2@example.test"
        req = self.client.post("/auth/email-otp/request", json={"email": "founder-fu2@example.test"}).json()
        code = re.search(r"\b(\d{6})\b", mails[-1]).group(1)
        adm = self.client.post("/auth/email-otp/verify", json={"challenge_id": req["challenge_id"], "code": code})
        self.assertEqual(adm.status_code, 200, adm.text)
        self.check(adm.json(), "email_otp")
        for name, tok in (("login", log.json()["token"]), ("device", dev.json()["token"])):
            me = self.client.get("/auth/me", headers={"Authorization": "Bearer " + tok})
            self.assertEqual(me.status_code, 200)
            self.assertEqual(me.json()["expires_at"], self.exp_of(tok), name)


# --- item 9 ------------------------------------------------------------------------------------

class TestPhoneNormalize(unittest.TestCase):
    def test_vn_forms(self):
        for raw in ("0900012095", "0900 012 095", "090-001-2095", "(090) 0012095", "84900012095", "+84900012095",
                    "+84 900 012 095", "0084900012095", "+840900012095", "900012095"):
            self.assertEqual(normalize_phone_e164(raw), "+84900012095", raw)

    def test_international_and_invalid(self):
        self.assertEqual(normalize_phone_e164("+1 415 555 0100"), "+14155550100")
        self.assertEqual(normalize_phone_e164("0014155550100"), "+14155550100")
        self.assertIsNone(normalize_phone_e164("  "))
        for bad in ("abc", "+84abc", "12", "+0123456789", "09000120951234567"):
            with self.assertRaises(ValueError, msg=bad):
                normalize_phone_e164(bad)

    def test_candidates(self):
        self.assertEqual(lookup_candidates("+84900012095"), ["+84900012095", "0900012095", "84900012095"])
        self.assertEqual(lookup_candidates("+14155550100"), ["+14155550100", "14155550100"])


class TestPhoneE164Http(_Base):
    def reg(self, phone, ip="192.0.2.90"):
        return self.client.post("/auth/register", json={"phone": phone, "password": PW}, headers=self.ip(ip))

    def login(self, phone, password=PW, ip="192.0.2.91"):
        return self.client.post("/auth/login", json={"phone": phone, "password": password}, headers=self.ip(ip))

    def test_register_saves_e164_and_any_form_logs_in(self):
        r = self.reg("0900 012 095")
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["phone"], "+84900012095")
        self.assertEqual(self.q("SELECT phone FROM users WHERE user_id=?", (r.json()["user_id"],))[0]["phone"], "+84900012095")
        for form in ("0900012095", "+84900012095", "84900012095", "+84 900 012 095"):
            self.assertEqual(self.login(form).status_code, 200, form)
        self.assertEqual(self.reg("+84900012095").status_code, 400)  # duplicate in another form
        self.assertEqual(self.reg("84900012095").status_code, 400)

    def test_legacy_local_row_still_works(self):
        self.legacy_user("legacy-1", "0911222333")
        self.assertEqual(self.login("+84911222333").json()["user_id"], "legacy-1")
        self.assertEqual(self.login("0911222333").json()["user_id"], "legacy-1")
        self.assertEqual(self.reg("+84911222333").status_code, 400)
        self.assertEqual(auth_svc.login_rate_key(phone="+84 911 222 333"), "user:legacy-1")

    def test_exact_e164_wins_and_ambiguous_legacy_refused(self):
        self.legacy_user("e164-owner", "+84933444555")
        self.legacy_user("legacy-dup", "0933444555", password="khac-mat-khau-9")
        self.assertEqual(self.login("0933444555").json()["user_id"], "e164-owner")
        self.assertEqual(self.login("0933444555", password="khac-mat-khau-9").status_code, 401)
        self.legacy_user("amb-a", "0922333444")
        self.legacy_user("amb-b", "84922333444")
        self.assertEqual(self.login("0922333444").status_code, 401)  # two legacy rows → refused, never a guess
        self.assertEqual(self.reg("+84922333444").status_code, 400)

    def test_otp_normalized_and_legacy_challenge_owner_kept(self):
        os.environ["WELORA_OTP_FIXED"] = "1"
        ch = self.client.post("/auth/otp/request", json={"phone": "0944 555 666"}).json()
        self.assertEqual(self.q("SELECT phone FROM otp_challenges WHERE challenge_id=?", (ch["challenge_id"],))[0]["phone"], "+84944555666")
        self.assertEqual(ch["phone_masked"], "09****66")
        u1 = self.client.post("/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": "123456"}).json()["user_id"]
        ch2 = self.client.post("/auth/otp/request", json={"phone": "+84944555666"}).json()
        u2 = self.client.post("/auth/otp/verify", json={"challenge_id": ch2["challenge_id"], "code": "123456"}).json()["user_id"]
        self.assertEqual(u1, u2)
        # legacy consumed challenge stored as local form → same user after the switch
        self.x("INSERT INTO users(user_id, display_name, device_id) VALUES ('otp-legacy','0955666777','phone:abc')")
        self.x("INSERT INTO otp_challenges(challenge_id, phone, code, expires_at, consumed, user_id, created_at) "
               "VALUES ('old-ch','0955666777','x','2020-01-01T00:00:00+00:00',1,'otp-legacy','2020-01-01T00:00:00+00:00')")
        ch3 = self.client.post("/auth/otp/request", json={"phone": "+84955666777"}).json()
        u3 = self.client.post("/auth/otp/verify", json={"challenge_id": ch3["challenge_id"], "code": "123456"}).json()["user_id"]
        self.assertEqual(u3, "otp-legacy")

    def test_rate_limit_target_same_bucket_for_all_forms(self):
        self.assertEqual(rl.normalise_target("0900012095"), rl.normalise_target("+84 900 012 095"))
        self.assertEqual(rl.normalise_target("84900012095"), "phone:+84900012095")


class TestPhoneMigration(_Base):
    def rerun(self):
        self.x("DELETE FROM schema_migrations WHERE version='014_phone_e164_data'")
        return migrate(None)

    def test_normalizes_reports_collisions_and_is_idempotent(self):
        auth_svc.ensure_auth_schema()
        self.assertIn("014_phone_e164_data", [r["version"] for r in self.q("SELECT version FROM schema_migrations")])
        self.legacy_user("m-solo", "0900012095")            # → +84900012095
        self.legacy_user("m-solo2", "84 977 000 111")       # → +84977000111
        self.legacy_user("m-keep", "+84966000111")          # already E.164
        self.legacy_user("m-col-a", "0988000111")           # collision group ↓
        self.legacy_user("m-col-b", "+84988000111")
        self.legacy_user("m-bad", "not-a-phone")
        # otp: one owner across forms → normalized; two owners across forms → conflict
        for cid, ph, uid in (("o1", "0912000111", "m-solo"), ("o2", "+84912000111", "m-solo"),
                             ("o3", "0913000111", "m-col-a"), ("o4", "84913000111", "m-col-b")):
            self.x("INSERT INTO otp_challenges(challenge_id, phone, code, expires_at, consumed, user_id) VALUES (?,?,?,?,1,?)",
                   (cid, ph, "x", "2020-01-01T00:00:00+00:00", uid))
        self.assertEqual(self.rerun(), ["014_phone_e164_data"])
        phones = {r["user_id"]: r["phone"] for r in self.q("SELECT user_id, phone FROM users WHERE user_id LIKE 'm-%'")}
        self.assertEqual(phones, {"m-solo": "+84900012095", "m-solo2": "+84977000111", "m-keep": "+84966000111",
                                  "m-col-a": "0988000111", "m-col-b": "+84988000111", "m-bad": "not-a-phone"})
        conflicts = self.q("SELECT table_name, normalized, user_ids FROM phone_e164_conflicts ORDER BY table_name")
        self.assertEqual([(c["table_name"], c["normalized"], json.loads(c["user_ids"])) for c in conflicts],
                         [("otp_challenges", "+84913000111", ["m-col-a", "m-col-b"]),
                          ("users", "+84988000111", ["m-col-a", "m-col-b"])])
        otp = {r["challenge_id"]: r["phone"] for r in self.q("SELECT challenge_id, phone FROM otp_challenges")}
        self.assertEqual(otp, {"o1": "+84912000111", "o2": "+84912000111", "o3": "0913000111", "o4": "84913000111"})
        # idempotent: second run changes nothing and records no duplicate conflict rows
        self.assertEqual(self.rerun(), ["014_phone_e164_data"])
        self.assertEqual(len(self.q("SELECT id FROM phone_e164_conflicts")), 2)
        conn = get_connection(None)
        try:
            again = normalize_existing_phones(conn)
        finally:
            conn.close()
        self.assertEqual((again["users_updated"], again["otp_updated"]), (0, 0))
        # the collided accounts stay reachable: exact E.164 row wins, legacy row by its own form
        self.assertEqual(self.client.post("/auth/login", json={"phone": "0988000111", "password": PW}).json()["user_id"], "m-col-b")


# --- item 10 -----------------------------------------------------------------------------------

class TestLowPriority(_Base):
    def test_release_db_error_is_swallowed_and_row_expires(self):
        self.client.post("/auth/register", json={"email": "rel@example.test", "password": PW}, headers=self.ip("192.0.2.70"))
        orig = rl._delete_events

        def boom(conn, ids):
            raise RuntimeError("db down")

        rl._delete_events = boom
        try:
            r = self.client.post("/auth/login", json={"email": "rel@example.test", "password": PW}, headers=self.ip("192.0.2.70"))
        finally:
            rl._delete_events = orig
        self.assertEqual(r.status_code, 200)
        leaked = self.q("SELECT created_at FROM auth_rate_events WHERE action='login_fail'")
        # target + ip rows of the in-flight reservation leaked (the pair row is cleared separately)
        self.assertEqual(len(leaked), 2)
        # a leaked row only counts inside the window: shift it out → buckets empty again
        self.x("UPDATE auth_rate_events SET created_at='2000-01-01T00:00:00.000000+00:00'")
        att = rl.login_reserve(ip="192.0.2.70", account="user:x")
        rl.login_release(att)
        self.assertEqual(len(self.q("SELECT 1 FROM auth_rate_events WHERE created_at>'2001-01-01'")), 0)

    def test_commit_and_clear_errors_swallowed(self):
        att = rl.LoginAttempt(["nope"], url="postgresql://invalid-host-for-test:1/x")
        rl.login_commit_failure(att)
        rl.login_release(att)
        rl.login_clear_pair(ip="1.2.3.4", account="user:z", url="postgresql://invalid-host-for-test:1/x")

    def test_dummy_hash_for_unknown_and_passwordless_accounts(self):
        calls = []
        orig = auth_svc._verify_password

        def spy(pw, stored):
            calls.append(stored)
            return orig(pw, stored)

        auth_svc._verify_password = spy
        try:
            self.assertEqual(self.client.post("/auth/login", json={"email": "ghost@example.test", "password": PW}).status_code, 401)
            self.x("INSERT INTO users(user_id, email) VALUES ('nopw', 'nopw@example.test')")
            self.assertEqual(self.client.post("/auth/login", json={"email": "nopw@example.test", "password": PW}).status_code, 401)
        finally:
            auth_svc._verify_password = orig
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(c.startswith("pbkdf2_sha256$120000$") for c in calls))

    def test_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        self.assertFalse(h["entitlements"]["checkout_enabled"])


if __name__ == "__main__":
    unittest.main()
