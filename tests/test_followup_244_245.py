"""Ticket "🛡️ GP follow-up sau OTP #244 + Academy #245" — group (B) items 1–14 (PR A).

1 resend in cooldown is not counted (429 body retry_after_s) · 2 «Để sau» per account on the server
(migration 021) · 3 HMAC server key for every stored OTP (+ legacy codes until expiry) · 4 atomic
attempts on /auth/otp/verify · 5 promotion clears password_hash · 6 contact change clears verified
timestamps · 7 daily fail cap reserves atomically · 8 real per-user lock · 9 bounded session cache ·
10 cross-worker invalidation · 11 pushState on the 429 «ôn lại bài» link · 12 Welorapedia for
guests (flag only) · 13 «reset tiến độ demo của tôi» · 14 Safety Gate / mastery per demo session.
Runs on SQLite, or PG17 via WELORA_TEST_POSTGRES_URL (tests/_db_target.py).
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from tests._db_target import db_env
from tests.test_kuat_demo_019 import TestAuthGateJsBehaviour
from tests.test_otp_verify_020 import PW, _Base
from welora import auth as auth_svc
from welora import contact_verify as cv
from welora import otp_hash
from welora.db.connection import detect_dialect, get_connection, lock_user

ROOT = pathlib.Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"


def run(name: str, env: dict, timeout: int = 300) -> dict:
    full = {k: v for k, v in os.environ.items() if not k.startswith("WELORA_")}
    full.update({"PYTHONPATH": str(ROOT), "WELORA_DEMO_AUTOSEED": "0", "WELORA_ENV": "staging",
                 "WELORA_GUEST_DEMO": "1"})
    full.update(env)
    p = subprocess.run([sys.executable, "-m", "tests._fu245_dbmode", name], cwd=str(ROOT), env=full,
                       capture_output=True, text=True, timeout=timeout)
    for line in reversed(p.stdout.splitlines()):
        if line.startswith("RESULT="):
            return json.loads(line[len("RESULT="):])
    raise AssertionError(f"scenario {name} failed rc={p.returncode}\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}")


# =========================================================================== item 1
class TestResendCooldownNotCounted(_Base):
    def test_cooldown_resends_do_not_use_the_send_budget(self):
        out = self.register("cooldown.free@example.test")
        tok = out["token"]
        for _ in range(8):  # > the per-user budget of 5 — every one refused by the cooldown
            r = self.resend(tok)
            d = r.json()["detail"]
            self.assertEqual((r.status_code, d["error_code"]), (429, "VERIFY_RESEND_COOLDOWN"))
            self.assertGreater(d["retry_after_s"], 0)
            self.assertEqual(str(d["retry_after_s"]), r.headers["Retry-After"])
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM auth_rate_events WHERE action='verify_request' "
                                "AND scope='target'")[0]["n"], 0)
        # the per-IP backstop row stays (a client hammering the endpoint is still bounded)
        self.assertGreater(self.q("SELECT COUNT(*) AS n FROM auth_rate_events WHERE action='verify_request' "
                                  "AND scope='ip'")[0]["n"], 0)
        # the 5 real sends are all still available after the cooldown
        os.environ["WELORA_VERIFY_RESEND_COOLDOWN_S"] = "0"
        st = [self.resend(tok).status_code for _ in range(6)]
        self.assertEqual(st, [200] * 5 + [429])  # limit unchanged: 5 per 15 min

    def test_rate_limited_body_carries_retry_after_s(self):
        os.environ["WELORA_VERIFY_RESEND_COOLDOWN_S"] = "0"
        os.environ["WELORA_RL_VERIFY_SEND_USER_MAX"] = "1"
        out = self.register("rl.body@example.test")
        self.assertEqual(self.resend(out["token"]).status_code, 200)
        r = self.resend(out["token"])
        d = r.json()["detail"]
        self.assertEqual((r.status_code, d["error_code"]), (429, "RATE_LIMITED"))
        self.assertIsInstance(d["retry_after_s"], int)
        self.assertGreater(d["retry_after_s"], 0)
        self.assertEqual(str(d["retry_after_s"]), r.headers["Retry-After"])
        # other auth endpoints too (shared helper)
        os.environ["WELORA_RL_TARGET_MAX"] = "1"
        hdr = self.ip()
        self.client.post("/auth/otp/request", json={"phone": "0912000001"}, headers=hdr)
        r = self.client.post("/auth/otp/request", json={"phone": "0912000001"}, headers=hdr)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(str(r.json()["detail"]["retry_after_s"]), r.headers["Retry-After"])

    def test_release_never_raises(self):
        from welora import auth_ratelimit as rl

        rl.release([])
        rl.release(["does-not-exist"])
        rl.release([None, ""])  # type: ignore[list-item]

    def test_verify_page_uses_retry_after_s(self):
        self.assertIn("retry_after_s", (STATIC / "verify.html").read_text(encoding="utf-8"))


# =========================================================================== item 2
class TestSnoozeServerSide(_Base):
    def test_snooze_is_per_account_across_sessions_and_expires(self):
        out = self.register("de.sau@example.test")
        me = self.me(out["token"])
        self.assertFalse(me["verify_snoozed"])
        self.assertTrue(me["verify_pending"] if "verify_pending" in me else True)
        r = self.client.post("/auth/verify/snooze", headers=self.h(out["token"]))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["snooze_s"], 24 * 3600)
        # a second session (another device / browser) of the same account sees the snooze
        login = self.client.post("/auth/login", json={"email": "de.sau@example.test", "password": PW}, headers=self.ip())
        self.assertEqual(login.status_code, 200, login.text)
        me2 = self.me(login.json()["token"])
        self.assertTrue(me2["verify_snoozed"])
        until = cv._ts(me2["verify_snoozed_until"])
        self.assertAlmostEqual(until - time.time(), 24 * 3600, delta=60)
        # another account is not affected
        other = self.register("khac@example.test")
        self.assertFalse(self.me(other["token"])["verify_snoozed"])
        # 24 h later → reminder back
        self.x("UPDATE users SET verify_snooze_until=? WHERE user_id=?", (cv._iso(time.time() - 1), out["user_id"]))
        self.assertFalse(self.me(out["token"])["verify_snoozed"])
        self.assertIsNone(self.me(out["token"])["verify_snoozed_until"])

    def test_requires_session(self):
        self.assertEqual(self.client.post("/auth/verify/snooze").status_code, 401)

    def test_frontend_posts_snooze(self):
        shell = (STATIC / "shell.js").read_text(encoding="utf-8")
        verify = (STATIC / "verify.html").read_text(encoding="utf-8")
        self.assertIn("/auth/verify/snooze", shell)
        self.assertIn("verify_snoozed", shell)
        self.assertIn("/auth/verify/snooze", verify)


class TestMigration021(_Base):
    def test_pre021_upgrade_and_rerun_twice(self):
        m = importlib.import_module("welora.db.migrate")
        dialect = detect_dialect(None)
        if dialect == "postgres":
            from tests._db_target import reset_postgres

            reset_postgres(os.environ["WELORA_DB_URL"])
        else:
            os.environ["WELORA_DB_URL"] = f"sqlite:///{self.tmp}/pre021.db"
        real_files, real_steps = m._list_migration_files, m._data_steps
        m._list_migration_files = lambda url=None: [p for p in real_files(url) if not p.stem.startswith("021")]
        m._data_steps = lambda: [s for s in real_steps() if not s[0].startswith("021")]
        try:
            pre = m.migrate(None)
        finally:
            m._list_migration_files, m._data_steps = real_files, real_steps

        def cols():
            if dialect == "sqlite":
                return [r["name"] for r in self.q("PRAGMA table_info(users)")]
            return [r["column_name"] for r in self.q(
                "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='users'")]

        self.assertFalse(any(v.startswith("021") for v in pre))
        self.assertNotIn("verify_snooze_until", cols())
        self.x("INSERT INTO users(user_id, display_name, device_id, email, password_hash, role, email_verified_at) "
               "VALUES ('pre-21','p','guest:pre-21','pre21@example.test','h','guest','2026-01-01T00:00:00+00:00')")
        self.assertEqual(m.migrate(None), ["021_verify_snooze"])
        self.assertEqual(m.migrate(None), [])
        self.x("DELETE FROM schema_migrations WHERE version='021_verify_snooze'")  # forced re-run
        self.assertEqual(m.migrate(None), ["021_verify_snooze"])
        conn = get_connection(None)
        try:
            self.assertFalse(cv.apply_verify_snooze_schema(conn, dialect)["verify_snooze_until_added"])
            cv.apply_verify_snooze_schema(conn, dialect)
        finally:
            conn.close()
        if dialect == "postgres":
            import psycopg

            sql = (m.MIGRATIONS_ROOT / "postgres" / "021_verify_snooze.sql").read_text(encoding="utf-8")
            with psycopg.connect(os.environ["WELORA_DB_URL"]) as pc:
                pc.execute(sql)
                pc.execute(sql)
        self.assertEqual(cols().count("verify_snooze_until"), 1)
        row = self.q("SELECT email_verified_at, verify_snooze_until FROM users WHERE user_id='pre-21'")[0]
        self.assertEqual((row["email_verified_at"], row["verify_snooze_until"]), ("2026-01-01T00:00:00+00:00", None))
        self.assertEqual([v for v in m.current_version() if v.startswith("021")], ["021_verify_snooze"])

    def test_pg_sql_file_text(self):
        sql = (ROOT / "welora" / "db" / "migrations" / "postgres" / "021_verify_snooze.sql").read_text(encoding="utf-8")
        self.assertIn("ADD COLUMN IF NOT EXISTS verify_snooze_until", sql)
        self.assertNotRegex(sql, r"(?i)\b(DROP|DELETE|TRUNCATE)\b")
        self.assertFalse((ROOT / "welora" / "db" / "migrations" / "021_verify_snooze.sql").exists())  # SQLite = data step
        names = sorted(p.name for p in (ROOT / "welora" / "db" / "migrations" / "postgres").glob("*.sql"))
        self.assertEqual(names[-1], "021_verify_snooze.sql")
        self.assertEqual(sum(n.startswith("021") for n in names), 1)


# =========================================================================== item 3
class TestOtpHmac(_Base):
    def setUp(self):
        self._key = os.environ.pop("WELORA_OTP_HMAC_KEY", None)
        super().setUp()

    def tearDown(self):
        super().tearDown()
        os.environ.pop("WELORA_OTP_HMAC_KEY", None)
        if self._key is not None:
            os.environ["WELORA_OTP_HMAC_KEY"] = self._key

    def test_format_key_and_legacy_rules(self):
        h = otp_hash.code_hash("d", "c1", "123456")
        self.assertTrue(h.startswith("hmac256:"))
        self.assertNotEqual(h[8:], otp_hash.legacy_hash("d", "c1", "123456")[7:])  # not the plain sha256
        self.assertTrue(otp_hash.matches("d", "c1", h, "123456"))
        self.assertFalse(otp_hash.matches("d", "c1", h, "123457"))
        self.assertFalse(otp_hash.matches("d", "c2", h, "123456"))  # salted per challenge
        self.assertFalse(otp_hash.matches("other", "c1", h, "123456"))  # domain-separated
        os.environ["WELORA_OTP_HMAC_KEY"] = "k" * 40
        self.assertFalse(otp_hash.matches("d", "c1", h, "123456"))  # the key matters
        h2 = otp_hash.code_hash("d", "c1", "123456")
        self.assertNotEqual(h, h2)
        self.assertTrue(otp_hash.matches("d", "c1", h2, "123456"))
        # legacy formats — accepted only where they existed before
        leg = otp_hash.legacy_hash("d", "c1", "123456")
        self.assertTrue(otp_hash.matches("d", "c1", leg, "123456"))
        self.assertFalse(otp_hash.matches("d", "c1", leg[7:], "123456"))
        self.assertTrue(otp_hash.matches("d", "c1", leg[7:], "123456", legacy_bare_hex=True))
        self.assertFalse(otp_hash.matches("d", "c1", "123456", "123456"))
        self.assertTrue(otp_hash.matches("d", "c1", "123456", "123456", legacy_plain=True))
        self.assertFalse(otp_hash.matches("d", "c1", "", ""))

    def test_key_source_and_startup_check(self):
        os.environ.pop("WELORA_OTP_HMAC_KEY", None)
        self.assertEqual(otp_hash.key_source(), "derived")  # db_env sets WELORA_DB_URL
        db = os.environ.pop("WELORA_DB_URL")
        try:
            self.assertEqual(otp_hash.key_source(), "dev")
        finally:
            os.environ["WELORA_DB_URL"] = db
        os.environ["WELORA_ENV"] = "production"
        with self.assertLogs("welora.otp_hash", level="CRITICAL") as lg:
            self.assertTrue(otp_hash.startup_check())
        self.assertIn("WELORA_OTP_HMAC_KEY", "\n".join(lg.output))
        os.environ["WELORA_OTP_HMAC_KEY"] = "short"
        with self.assertLogs("welora.otp_hash", level="CRITICAL"):
            self.assertTrue(otp_hash.startup_check())
        os.environ["WELORA_OTP_HMAC_KEY"] = "x" * 48
        self.assertEqual(otp_hash.startup_check(), [])
        self.assertEqual(otp_hash.key_source(), "env")
        os.environ["WELORA_ENV"] = "staging"
        os.environ.pop("WELORA_OTP_HMAC_KEY")
        with self.assertLogs("welora.otp_hash", level="WARNING") as lg:
            otp_hash.startup_check()
        self.assertTrue(all(r.levelno == logging.WARNING for r in lg.records))

    def test_production_without_key_still_starts_and_health_reports_source(self):
        from fastapi.testclient import TestClient
        from welora.api.app import create_app

        os.environ["WELORA_ENV"] = "production"
        os.environ.pop("WELORA_OTP_HMAC_KEY", None)
        with TestClient(create_app()) as c:  # lifespan runs startup_check — no exception
            h = c.get("/health").json()
        self.assertEqual(h["otp_hmac_key"], "derived")
        os.environ["WELORA_OTP_HMAC_KEY"] = "secret-value-" + "z" * 40
        h = self.client.get("/health").json()
        self.assertEqual(h["otp_hmac_key"], "env")
        self.assertNotIn("secret-value", json.dumps(h))

    def test_render_yaml_documents_key_without_value(self):
        y = (ROOT / "render.yaml").read_text(encoding="utf-8")
        m = re.search(r"- key: WELORA_OTP_HMAC_KEY\n(\s+)(\S[^\n]*)", y)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(2).strip(), "sync: false")
        self.assertNotRegex(y, r"WELORA_OTP_HMAC_KEY\n\s+value:")

    # -- every stored code is HMAC'd; old rows verify until they expire
    def _otp_request(self, phone):
        os.environ["WELORA_OTP_FIXED"] = "1"
        hdr = self.ip()
        ch = self.client.post("/auth/otp/request", json={"phone": phone}, headers=hdr)
        self.assertEqual(ch.status_code, 200, ch.text)
        return ch.json()["challenge_id"], hdr

    def test_phone_otp_stored_hmac_and_legacy_rows_still_verify(self):
        cid, hdr = self._otp_request("0913000001")
        stored = self.q("SELECT code FROM otp_challenges WHERE challenge_id=?", (cid,))[0]["code"]
        self.assertTrue(stored.startswith("hmac256:"))
        self.assertNotIn("123456", stored)
        r = self.client.post("/auth/otp/verify", json={"challenge_id": cid, "code": "123456"}, headers=hdr)
        self.assertEqual(r.status_code, 200, r.text)
        for i, legacy in enumerate(("sha256", "plain")):
            cid, hdr = self._otp_request(f"091300001{i}")
            val = otp_hash.legacy_hash("welora-phone-otp", cid, "123456") if legacy == "sha256" else "123456"
            self.x("UPDATE otp_challenges SET code=? WHERE challenge_id=?", (val, cid))
            bad = self.client.post("/auth/otp/verify", json={"challenge_id": cid, "code": "654321"}, headers=hdr)
            self.assertEqual(bad.status_code, 400, legacy)
            ok = self.client.post("/auth/otp/verify", json={"challenge_id": cid, "code": "123456"}, headers=hdr)
            self.assertEqual(ok.status_code, 200, (legacy, ok.text))

    def test_contact_codes_hmac_legacy_and_key_rotation(self):
        out = self.register("hmac.cv@example.test")
        cid, code = out["verification"]["challenge_id"], self.last_code()
        stored = self.q("SELECT code_hash FROM contact_verifications WHERE challenge_id=?", (cid,))[0]["code_hash"]
        self.assertTrue(stored.startswith("hmac256:"))
        # issued before the deploy (sha256:) → still verifies until it expires
        self.x("UPDATE contact_verifications SET code_hash=? WHERE challenge_id=?",
               (otp_hash.legacy_hash("welora-contact-verify", cid, code), cid))
        self.assertEqual(self.confirm(out["token"], code, cid).status_code, 200)
        # rotating the key only invalidates the codes open at that moment
        out2 = self.register("hmac.rot@example.test")
        cid2, code2 = out2["verification"]["challenge_id"], self.last_code("hmac.rot@example.test")
        os.environ["WELORA_OTP_HMAC_KEY"] = "rotated-" + "r" * 40
        self.assertEqual(self.confirm(out2["token"], code2, cid2).status_code, 400)
        # an expired legacy row is refused like any expired code
        out3 = self.register("hmac.exp@example.test")
        cid3, code3 = out3["verification"]["challenge_id"], self.last_code("hmac.exp@example.test")
        self.x("UPDATE contact_verifications SET code_hash=?, expires_at=? WHERE challenge_id=?",
               (otp_hash.legacy_hash("welora-contact-verify", cid3, code3), "2020-01-01T00:00:00.000000+00:00", cid3))
        self.assertEqual(self.confirm(out3["token"], code3, cid3).status_code, 400)

    def test_admin_email_otp_hmac_and_bare_hex_legacy(self):
        from welora import admin_bootstrap as ab

        h = ab._code_hash("c9", "111222")
        self.assertTrue(h.startswith("hmac256:"))
        self.assertTrue(ab._code_matches("c9", h, "111222"))
        legacy = otp_hash.legacy_hash("welora-email-otp", "c9", "111222")[7:]
        self.assertTrue(ab._code_matches("c9", legacy, "111222"))
        self.assertFalse(ab._code_matches("c9", "111222", "111222"))  # never plaintext for admin


# =========================================================================== item 4
class TestOtpVerifyAtomicAttempts(_Base):
    def test_parallel_wrong_codes_never_exceed_the_limit(self):
        os.environ["WELORA_OTP_FIXED"] = "1"
        ch = auth_svc.request_otp("0914000001")
        cid = ch["challenge_id"]
        errors: list[str] = []
        lock = threading.Lock()

        def wrong(i):
            try:
                auth_svc.verify_otp(cid, "%06d" % (200000 + i))
            except Exception as e:  # ValueError("invalid code" / "too many attempts")
                with lock:
                    errors.append(str(e))

        with ThreadPoolExecutor(12) as ex:
            list(ex.map(wrong, range(30)))
        self.assertLessEqual(errors.count("invalid code"), auth_svc.OTP_MAX_ATTEMPTS)
        self.assertEqual(set(errors) - {"invalid code", "too many attempts"}, set(), errors)
        row = self.q("SELECT attempts, consumed FROM otp_challenges WHERE challenge_id=?", (cid,))[0]
        self.assertEqual(int(row["attempts"]), auth_svc.OTP_MAX_ATTEMPTS)
        self.assertFalse(row["consumed"])
        with self.assertRaises(ValueError):  # the right code no longer helps
            auth_svc.verify_otp(cid, "123456")

    def test_right_code_after_wrong_ones(self):
        os.environ["WELORA_OTP_FIXED"] = "1"
        cid = auth_svc.request_otp("0914000002")["challenge_id"]
        for _ in range(4):
            with self.assertRaises(ValueError):
                auth_svc.verify_otp(cid, "000001")
        self.assertTrue(auth_svc.verify_otp(cid, "123456")["token"])
        with self.assertRaisesRegex(ValueError, "already used"):
            auth_svc.verify_otp(cid, "123456")

    def test_source_has_no_read_then_increment(self):
        src = (ROOT / "welora" / "auth.py").read_text(encoding="utf-8")
        body = src[src.index("def verify_otp("):src.index("def verify_otp(") + 4000]
        self.assertIn("attempts=attempts+1 WHERE challenge_id=? AND consumed=0 AND attempts<?", body)
        self.assertNotIn("SET attempts=? ", body)


# =========================================================================== item 5
from tests.test_admin_bootstrap import FOUNDER, _Base as _AdminBase  # noqa: E402


class TestPromotionClearsPassword(_AdminBase):
    def test_pre_registered_listed_account_loses_its_password_on_promotion(self):
        os.environ["WELORA_ADMIN_EMAILS"] = FOUNDER
        pre = auth_svc.register_guest(email=FOUNDER, password="Preset-Pass1!")
        self.assertTrue(self.q("SELECT password_hash FROM users WHERE user_id=?", (pre["user_id"],))[0]["password_hash"])
        out = self.otp_login(FOUNDER)
        self.assertEqual((out["user_id"], out["role"]), (pre["user_id"], "admin"))
        self.assertIsNone(self.q("SELECT password_hash FROM users WHERE user_id=?", (pre["user_id"],))[0]["password_hash"])
        detail = json.loads(self.audit("admin_role_granted")[0]["detail"])
        self.assertTrue(detail["password_cleared"])
        self.assertNotIn("Preset", json.dumps(detail))
        r = self.client.post("/auth/login", json={"email": FOUNDER, "password": "Preset-Pass1!"})
        self.assertEqual(r.status_code, 401)

    def test_admin_without_password_audit_says_not_cleared(self):
        os.environ["WELORA_ADMIN_EMAILS"] = FOUNDER
        out = self.otp_login(FOUNDER)
        self.assertEqual(out["role"], "admin")
        self.assertFalse(json.loads(self.audit("admin_role_granted")[0]["detail"])["password_cleared"])


# =========================================================================== item 6
class TestContactChangeClearsVerified(_Base):
    def _user(self, email="doi@example.test", phone="+84915000001"):
        uid = "cc-" + uuid.uuid4().hex[:8]
        self.x("INSERT INTO users(user_id, display_name, device_id, email, phone, role, email_verified_at, phone_verified_at) "
               "VALUES (?,?,?,?,?,?,?,?)", (uid, "x", "guest:" + uid, email, phone, "guest",
                                             "2026-09-01T00:00:00+00:00", "2026-09-01T00:00:00+00:00"))
        return uid

    def _set(self, uid, **kw):
        conn = get_connection(None)
        try:
            out = auth_svc.set_user_contact(conn, uid, **kw)
            conn.commit()
            return out
        finally:
            conn.close()

    def _row(self, uid):
        return self.q("SELECT email, phone, email_verified_at, phone_verified_at FROM users WHERE user_id=?", (uid,))[0]

    def test_change_clears_only_that_channel(self):
        uid = self._user()
        self.assertEqual(self._set(uid, email="moi@example.test"), {"email_changed": True, "phone_changed": False})
        r = self._row(uid)
        self.assertEqual((r["email"], r["email_verified_at"]), ("moi@example.test", None))
        self.assertEqual(r["phone_verified_at"], "2026-09-01T00:00:00+00:00")
        self.assertEqual(self._set(uid, phone="+84915000002")["phone_changed"], True)
        self.assertIsNone(self._row(uid)["phone_verified_at"])

    def test_same_value_keeps_verified(self):
        uid = self._user()
        self.assertEqual(self._set(uid, email="DOI@Example.test", phone="0915000001"),
                         {"email_changed": False, "phone_changed": False})
        r = self._row(uid)
        self.assertEqual((r["email_verified_at"], r["phone_verified_at"]),
                         ("2026-09-01T00:00:00+00:00", "2026-09-01T00:00:00+00:00"))

    def test_clearing_and_open_codes_superseded(self):
        out = self.register("cu@example.test")
        cid, code = out["verification"]["challenge_id"], self.last_code()
        self._set(out["user_id"], email="moi.hon@example.test")
        self.assertEqual(int(self.q("SELECT consumed FROM contact_verifications WHERE challenge_id=?", (cid,))[0]["consumed"]), 2)
        self.assertEqual(self.confirm(out["token"], code, cid).status_code, 400)  # old address's code is dead
        uid = self._user(email="x@example.test")
        self._set(uid, email=None)
        self.assertEqual((self._row(uid)["email"], self._row(uid)["email_verified_at"]), (None, None))
        self.assertEqual(self._set("missing-user", email="a@b.test"), {"email_changed": False, "phone_changed": False})

    def test_every_direct_contact_write_is_allowlisted(self):
        """grep: a write of users.email / users.phone outside set_user_contact must be a
        proof-of-possession write of the SAME number (it sets *_verified_at itself)."""
        pat = re.compile(r"UPDATE\s+users\s+SET(?:(?!WHERE)[\s\S]){0,300}?(?<![_a-z])(email|phone)\s*=", re.I)
        found: dict[str, int] = {}
        for p in sorted((ROOT / "welora").rglob("*.py")):
            n = len(pat.findall(p.read_text(encoding="utf-8")))
            if n:
                found[str(p.relative_to(ROOT))] = n
        self.assertEqual(found, {
            "welora/auth.py": 2,            # phone-OTP attach / legacy owner: code just proved this number
            "welora/contact_verify.py": 1,  # verification success: E.164 form of the verified number
            "welora/phone_migration.py": 1,  # 014 normalisation of the SAME number to E.164
        })
        seed = (ROOT / "welora" / "partner_demo_seed.py").read_text(encoding="utf-8")
        self.assertGreaterEqual(seed.count("set_user_contact("), 2)


# =========================================================================== items 7 + 8
class TestDailyFailCapAtomic(_Base):
    def test_parallel_wrong_checks_never_exceed_the_daily_cap(self):
        os.environ["WELORA_VERIFY_DAILY_FAIL_MAX"] = "3"
        os.environ["WELORA_RL_VERIFY_CONFIRM_USER_MAX"] = "1000"
        os.environ["WELORA_RL_VERIFY_CONFIRM_IP_MAX"] = "1000"
        out = self.register("daily.cap@example.test")
        uid, cid = out["user_id"], out["verification"]["challenge_id"]
        res: list[str] = []
        lock = threading.Lock()

        def wrong(i):
            try:
                cv.confirm(uid, "%06d" % (300000 + i), cid)
                code = "OK"
            except cv.VerifyError as e:
                code = e.code
            with lock:
                res.append(code)

        with ThreadPoolExecutor(10) as ex:
            list(ex.map(wrong, range(20)))
        self.assertLessEqual(res.count("VERIFY_CODE_INVALID"), 3, res)
        self.assertEqual(set(res) - {"VERIFY_CODE_INVALID", "VERIFY_DAILY_LIMIT"}, set(), res)
        total = sum(int(r["attempts"]) for r in self.q("SELECT attempts FROM contact_verifications WHERE user_id=?", (uid,)))
        self.assertEqual(total, 3)
        with self.assertRaises(cv.VerifyError) as e:  # even the right code waits for the window
            cv.confirm(uid, self.last_code(), cid)
        self.assertEqual(e.exception.code, "VERIFY_DAILY_LIMIT")


class TestUserLock(_Base):
    def test_no_updated_at_touch_trick_left(self):
        for p in (ROOT / "welora").rglob("*.py"):
            code = "\n".join(ln for ln in p.read_text(encoding="utf-8").splitlines() if "execute(" in ln or ln.strip().startswith('"'))
            self.assertNotRegex(code, r"SET\s+updated_at\s*=\s*updated_at", str(p))
        for name in ("contact_verify.py", "guest_claim.py"):
            self.assertIn("lock_user(", (ROOT / "welora" / name).read_text(encoding="utf-8"), name)

    def test_lock_blocks_a_second_transaction_until_commit(self):
        out = self.register("khoa@example.test")
        uid = out["user_id"]
        a = get_connection(None)
        waited: list[float] = []
        try:
            lock_user(a, uid)
            a.execute("SELECT 1 FROM users WHERE user_id=?", (uid,)).fetchone()

            def second():
                b = get_connection(None)  # own thread (sqlite3 objects are thread-bound)
                try:
                    t0 = time.time()
                    lock_user(b, uid)
                    waited.append(time.time() - t0)
                    b.commit()
                finally:
                    b.close()

            th = threading.Thread(target=second)
            th.start()
            time.sleep(0.6)
            self.assertTrue(th.is_alive())  # still waiting for A's lock
            a.commit()  # release
            th.join(10)
            self.assertFalse(th.is_alive())
            self.assertGreaterEqual(waited[0], 0.5)
        finally:
            a.close()

    def test_lock_needs_no_users_row_and_is_released_by_rollback(self):
        a = get_connection(None)
        b = get_connection(None)
        try:
            lock_user(a, "no-such-user")
            a.rollback()
            t0 = time.time()
            lock_user(b, "no-such-user")
            b.commit()
            self.assertLess(time.time() - t0, 2)
        finally:
            a.close()
            b.close()

    def test_postgres_other_users_do_not_wait(self):
        if detect_dialect(None) != "postgres":
            self.skipTest("SQLite has a single database write lock")
        a = get_connection(None)
        b = get_connection(None)
        try:
            lock_user(a, "user-a")
            t0 = time.time()
            lock_user(b, "user-b")
            self.assertLess(time.time() - t0, 1)
            b.commit()
            a.commit()
        finally:
            a.close()
            b.close()

    def test_parallel_issue_one_open_code(self):
        """issue() under the new lock: a burst of resends of one account leaves exactly one open code."""
        os.environ["WELORA_VERIFY_RESEND_COOLDOWN_S"] = "0"
        out = self.register("burst.issue@example.test")
        uid = out["user_id"]

        def go(_):
            try:
                cv.issue(uid, None)
            except cv.VerifyError:
                pass

        with ThreadPoolExecutor(8) as ex:
            list(ex.map(go, range(8)))
        opens = self.q("SELECT COUNT(*) AS n FROM contact_verifications WHERE user_id=? AND consumed=0", (uid,))[0]["n"]
        self.assertEqual(opens, 1)


# =========================================================================== items 9, 10, 13, 14 (DB subprocesses)
class TestAcademySessionScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gate = run("session_gate", db_env(tempfile.mkdtemp()))
        cls.gate_off = run("session_gate_flag_off", db_env(tempfile.mkdtemp()))
        cls.reset = run("demo_reset", db_env(tempfile.mkdtemp()))
        cls.xw = run("cross_worker", db_env(tempfile.mkdtemp()))
        cls.lru = run("session_lru", {**db_env(tempfile.mkdtemp()), "WELORA_ACADEMY_SESSION_CACHE_MAX": "16"})

    # item 14
    def test_session_gate_is_per_tester(self):
        g = self.gate
        self.assertEqual(g["passes"], [[200, True], [200, True]])
        learning = {"m": "learning", "mastery_reason": True, "block": "learning"}
        self.assertEqual(g["before"], [learning, learning])
        self.assertEqual(g["after"][0], {"m": "apply", "mastery_reason": False, "block": "apply"})  # tester A
        self.assertEqual(g["after"][1], learning)  # tester B (same persona) unchanged
        self.assertEqual(g["mastery_api"], ["apply", "learning"])
        self.assertEqual(g["pre_rule_ctx"], ["apply", "learning"])
        self.assertEqual(g["flags"], {"m": "learning", "s": "seed"})  # persona's shared gate unchanged
        self.assertEqual(g["no_request_session"], "learning")
        self.assertEqual(g["hs_status"], [200, 200])
        self.assertIsNone(g["foreign_uid"])

    def test_regular_accounts_unchanged(self):
        self.assertEqual(self.gate["regular"], ["apply", {"m": "apply", "s": "academy"}])

    def test_flag_off_no_overlay(self):
        o = self.gate_off
        self.assertEqual(o["key"], o["uid"])
        self.assertEqual(o["overlay"], "learning")

    # item 13
    def test_demo_reset_only_this_session(self):
        r = self.reset
        self.assertEqual(r["flag"], [True, True])
        self.assertEqual(r["a_before"]["status"]["N02-01"], "mastered")
        self.assertEqual(r["reset"][0], 200)
        self.assertEqual(r["reset"][1], ["message", "ok", "tree"])
        self.assertEqual(r["a_after"]["status"], {"N01-01": "available", "N02-01": "available", "N02-02": "locked",
                                                  "N02-03": "locked"})  # back to the P4 seed
        self.assertEqual(r["a_after"]["xp"], 0)
        self.assertEqual(r["b_after"], r["b_before"])  # other tester untouched
        self.assertEqual((r["rows_before"], r["rows_after"]), (2, 1))
        self.assertTrue(r["events_unchanged"])  # KUAT start/fail budgets NOT reset
        self.assertEqual(r["p2_after_reset"][0], 200)
        self.assertEqual(r["p2_after_reset"][1]["status"]["N02-02"], "mastered")  # P2 seed has the gate

    def test_demo_reset_refused_outside_demo_sessions(self):
        r = self.reset
        self.assertEqual(r["regular"]["detail"]["error_code"], "DEMO_RESET_NOT_ALLOWED")
        self.assertFalse(r["regular_flag"])
        self.assertEqual(r["guest_status"], 403)
        self.assertEqual(r["anon_status"], 401)

    def test_demo_reset_button_in_academy_page(self):
        html = (STATIC / "academy.html").read_text(encoding="utf-8")
        self.assertIn('id="btnDemoReset"', html)
        self.assertIn("reset tiến độ demo của tôi", html.lower())
        self.assertIn("/academy/demo/reset", html)
        self.assertIn("window.confirm(", html)
        self.assertIn("demo_session", html)
        self.assertRegex(html, r'id="btnDemoReset"[^>]*\bhidden\b')

    # item 10
    def test_cross_worker_invalidation(self):
        x = self.xw
        self.assertEqual(x["cached"], "mastered")
        self.assertEqual(x["after_delete"], "available")  # row deleted elsewhere → seed state here too
        self.assertEqual(x["same_rev_rewrite"][1:], [7, "available"])  # same rev, new updated_at → reloaded
        self.assertEqual(x["base_after_rewrite"], 40)
        self.assertEqual(len(x["version_fn"]), 2)

    # item 9
    def test_session_cache_bounded(self):
        o = self.lru
        self.assertEqual(o["max"], 16)
        self.assertLessEqual(o["size"], 16)
        self.assertLessEqual(o["size_after"], 16)
        self.assertFalse(o["first_cached"])  # evicted
        self.assertEqual(o["first_read_back"], "kuat_pending")  # progress back from the DB
        self.assertTrue(o["regular_cached"])  # non-session profiles are not evicted by the LRU

    def test_session_cache_env_bounds(self):
        from welora import academy

        prev = os.environ.get("WELORA_ACADEMY_SESSION_CACHE_MAX")
        try:
            os.environ.pop("WELORA_ACADEMY_SESSION_CACHE_MAX", None)
            self.assertEqual(academy.session_cache_max(), 512)
            os.environ["WELORA_ACADEMY_SESSION_CACHE_MAX"] = "1"
            self.assertEqual(academy.session_cache_max(), 16)
            os.environ["WELORA_ACADEMY_SESSION_CACHE_MAX"] = "abc"
            self.assertEqual(academy.session_cache_max(), 512)
        finally:
            if prev is None:
                os.environ.pop("WELORA_ACADEMY_SESSION_CACHE_MAX", None)
            else:
                os.environ["WELORA_ACADEMY_SESSION_CACHE_MAX"] = prev


# =========================================================================== item 11
class TestCooldownReviewLink(unittest.TestCase):
    def test_push_state_and_popstate(self):
        html = (STATIC / "academy.html").read_text(encoding="utf-8")
        i = html.index("function showCooldown")
        body = html[i:i + 6000]
        self.assertIn("history.pushState", body)
        self.assertIn("preventDefault", body)
        self.assertIn("addEventListener('popstate'", html)
        self.assertIn("/app/academy?node=", body)


# =========================================================================== item 12
class TestWelorapediaGuests(unittest.TestCase):
    def _client(self, guest_demo: str, env="staging"):
        from fastapi.testclient import TestClient
        from welora.api.app import create_app

        if not hasattr(self, "_prev"):  # first call only — a second call must not save the first call's env
            self._prev = {k: os.environ.get(k) for k in ("WELORA_GUEST_DEMO", "WELORA_ENV", "WELORA_DB_URL",
                                                        "WELORA_STORE", "WELORA_DEMO_AUTOSEED")}
        self.tmp = tempfile.mkdtemp()
        self._tmps = getattr(self, "_tmps", []) + [self.tmp]
        os.environ.update({"WELORA_GUEST_DEMO": guest_demo, "WELORA_ENV": env, "WELORA_DEMO_AUTOSEED": "0",
                           **db_env(self.tmp)})
        return TestClient(create_app())

    def tearDown(self):
        for k, v in getattr(self, "_prev", {}).items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        for t in getattr(self, "_tmps", []):
            shutil.rmtree(t, ignore_errors=True)

    def test_content_pages_marker_only_with_flag(self):
        c = self._client("1")
        for path in ("/app/content", "/app/content/no_efund_invest", "/app/content/module/m01"):
            r = c.get(path)
            if r.status_code == 404:
                continue
            self.assertIn('name="welora-guest-academy" content="1"', r.text, path)
            self.assertIn("no-store", r.headers.get("cache-control", ""), path)
        c = self._client("0")
        r = c.get("/app/content")
        self.assertNotIn('welora-guest-academy" content="1"', r.text)

    def test_client_gates(self):
        js = TestAuthGateJsBehaviour()
        js.setUp() if hasattr(js, "setUp") else None
        for f in ("auth-gate.js", "shell.js"):
            self.assertIsNone(js._run(f, "/app/content", "1"), f)
            self.assertIsNone(js._run(f, "/app/content/no_efund_invest", "1"), f)
            self.assertEqual(js._run(f, "/app/content", "0"), "/app/login", f)  # prod: guests blocked
            self.assertEqual(js._run(f, "/app/contentx", "1"), "/app/login", f)
            self.assertEqual(js._run(f, "/app/goals", "1"), "/app/login", f)
        self.assertIn("/app/content", (STATIC / "session.js").read_text(encoding="utf-8"))


# =========================================================================== constraints
class TestConstraints(unittest.TestCase):
    def test_untouched_rules(self):
        from welora import safety_gate

        self.assertEqual(safety_gate.TARGET_MONTHS, 3)
        from welora import checkout

        prev = os.environ.pop("WELORA_CHECKOUT_ENABLED", None)
        try:
            self.assertFalse(checkout.checkout_enabled())  # checkout stays OFF by default
        finally:
            if prev is not None:
                os.environ["WELORA_CHECKOUT_ENABLED"] = prev
        render = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertNotRegex(render, r"WELORA_CHECKOUT_ENABLED\n\s+value: \"?(1|true)")
        for flag in ("WELORA_OTP_ECHO", "WELORA_RESET_ECHO", "WELORA_OTP_FIXED"):
            m = re.search(flag + r"\n\s+value: \"?([^\"\n]*)\"?", render)
            if m:
                self.assertIn(m.group(1), ("0", "false", ""), flag)

    def test_production_still_ignores_test_flags(self):
        prev = {k: os.environ.get(k) for k in ("WELORA_ENV", "WELORA_OTP_ECHO", "WELORA_OTP_FIXED", "WELORA_RESET_ECHO")}
        try:
            os.environ.update({"WELORA_ENV": "production", "WELORA_OTP_ECHO": "1", "WELORA_OTP_FIXED": "1",
                               "WELORA_RESET_ECHO": "1"})
            self.assertFalse(auth_svc.otp_echo_enabled())
            self.assertFalse(auth_svc.otp_fixed_enabled())
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_limits_not_loosened(self):
        from welora import auth_ratelimit as rl

        prev = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("WELORA_RL_") or k.startswith("WELORA_VERIFY_")}
        try:
            self.assertEqual(rl.limits("verify_request"), (5, 20))
            self.assertEqual(rl.limits("verify_confirm"), (10, 40))
            self.assertEqual(rl.window_s(), 900)
            self.assertEqual((cv.max_attempts(), cv.daily_fail_max(), cv.daily_send_max()), (5, 30, 10))
            self.assertEqual(auth_svc.OTP_MAX_ATTEMPTS, 5)
        finally:
            os.environ.update(prev)


if __name__ == "__main__":
    unittest.main()
