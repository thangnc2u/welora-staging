"""PR #244 round 2 (CoS review of 57274b6).

B1  open redirect on /app/verify?next=… — shared helper /static/safe-next.js (run in node) + the
    server-side twin ``welora.api.app.safe_next_path`` (the route drops an unsafe ?next=).
R1  e-mails in WELORA_ADMIN_EMAILS are never verified by the post-register flow (same response
    shape, no code mailed, confirm always refuses) + startup promotion requires the ADMIN e-mail OTP;
    per-user daily caps on codes sent / wrong checks (WELORA_VERIFY_DAILY_SEND_MAX / _FAIL_MAX).
R2  parallel resends → exactly ONE open code and ONE mail (per-user lock + partial unique index
    uq_contact_verif_open in migration 020), SQLite + PG17 (threads) and a real uvicorn burst.
"""

from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import tempfile
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from tests._db_target import db_env
from tests.test_otp_verify_020 import PW, _Base
from welora import admin_bootstrap
from welora import auth as auth_svc
from welora import contact_verify as cv
from welora.api.app import safe_next_path
from welora.db.connection import detect_dialect, get_connection

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"

ATTACKS = [
    "/\\evil.com", "/%5Cevil.com", "/%5cevil.com", "/\t/evil.com", "/%09/evil.com", "/\n/evil.com", "//evil.com",
    "///evil.com", "https://evil.com", "http://evil.com/app", "javascript:alert(1)", "JaVaScRiPt:alert(1)",
    "data:text/html,x", "evil.com", "", " /app", "/app\\..\\evil", "/%2F%2Fevil.com", "/app/../evil", "/evil",
    "\\\\evil.com", "/ /evil.com",
]
SAFE = ["/app", "/app/", "/app/goals", "/app/academy?node=N02-01", "/app/safety#top", "/app/verify?next=%2Fapp"]


# =========================================================================== B1
@unittest.skipUnless(shutil.which("node"), "node not installed")
class TestSafeNextJs(unittest.TestCase):
    """Runs the REAL /static/safe-next.js in node with a browser-like window (WHATWG URL)."""

    HARNESS = r"""
const vm = require('vm'); const fs = require('fs');
const [file, casesJson] = process.argv.slice(2);
const ctx = { location: { origin: 'https://welora-staging.onrender.com', href: 'https://welora-staging.onrender.com/app/verify' }, URL };
ctx.window = ctx;
vm.runInNewContext(fs.readFileSync(file, 'utf8'), ctx);
const out = {};
for (const c of JSON.parse(casesJson)) {
  // what verify.html does: URLSearchParams decodes the query value first
  const decoded = new URLSearchParams('next=' + encodeURIComponent(c)).get('next');
  const viaQuery = new URLSearchParams('next=' + c).get('next');
  out[c] = [ctx.WeloraSafeNext(decoded, '/app'), ctx.WeloraSafeNext(viaQuery, '/app')];
}
console.log(JSON.stringify(out));
"""

    def run_js(self, cases):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(self.HARNESS)
        p = subprocess.run([shutil.which("node"), f.name, str(STATIC / "safe-next.js"), json.dumps(cases)],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])

    def test_attacks_fall_back_to_app(self):
        out = self.run_js(ATTACKS)
        for c in ATTACKS:
            self.assertEqual(out[c], ["/app", "/app"], c)

    def test_same_origin_app_paths_kept(self):
        out = self.run_js(SAFE)
        for c in SAFE:
            self.assertEqual(out[c][0], c if c != "/app/" else "/app/", c)

    def test_result_never_leaves_origin(self):
        """Whatever the helper returns, resolving it against our origin stays on our origin."""
        out = self.run_js(ATTACKS + SAFE)
        for c, (a, b) in out.items():
            for v in (a, b):
                self.assertTrue(v.startswith("/app") and not v.startswith("//") and "\\" not in v, (c, v))


class TestSafeNextServer(_Base):
    def test_server_twin(self):
        for c in ATTACKS:
            self.assertEqual(safe_next_path(c), "/app", repr(c))
        for c in SAFE:
            self.assertEqual(safe_next_path(c), c)

    def test_verify_route_drops_unsafe_next(self):
        for raw in ("/%5Cevil.com", "/%09/evil.com", "//evil.com", "https://evil.com", "javascript:alert(1)",
                    "%2F%5Cevil.com"):
            r = self.client.get("/app/verify?next=" + raw, follow_redirects=False)
            self.assertEqual((r.status_code, r.headers.get("location")), (302, "/app/verify"), raw)
        ok = self.client.get("/app/verify?next=%2Fapp%2Fgoals", follow_redirects=False)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.get("/app/verify", follow_redirects=False).status_code, 200)

    def test_static_pages_use_the_helper(self):
        """Only verify.html reads a ?next= target; every page that redirects to a query value must
        go through WeloraSafeNext (grep guard for future pages)."""
        import re

        for f in sorted(STATIC.glob("*.html")) + sorted(STATIC.glob("*.js")):
            t = f.read_text(encoding="utf-8")
            if re.search(r"""\.get\(\s*['"](next|return|returnTo|redirect|redirect_to|continue)['"]\s*\)""", t):
                self.assertIn("WeloraSafeNext(", t, f.name)
        self.assertIn("/static/safe-next.js", (STATIC / "verify.html").read_text(encoding="utf-8"))
        r = self.client.get("/static/safe-next.js")
        self.assertEqual(r.status_code, 200)


# =========================================================================== R1 admin e-mails
class TestAdminListedEmail(_Base):
    BOSS = "boss.admin@example.test"

    def setUp(self):
        super().setUp()
        os.environ["WELORA_ADMIN_EMAILS"] = self.BOSS

    def test_register_listed_email_same_shape_no_code_never_verified(self):
        normal = self.register("binh.thuong@example.test")
        n_mail = len(self.mail)
        out = self.register(self.BOSS)
        v, w = out["verification"], normal["verification"]
        self.assertEqual(sorted(v), sorted(w))  # identical response shape → admin list not disclosed
        self.assertEqual({k: v[k] for k in ("channel", "delivery", "sms_enabled", "max_attempts", "attempts_left")},
                         {k: w[k] for k in ("channel", "delivery", "sms_enabled", "max_attempts", "attempts_left")})
        self.assertTrue(v["challenge_id"])
        self.assertEqual(sorted(out), sorted(normal))
        # a notice (no code) reaches the admin mailbox instead of a verification code
        self.assertEqual(len(self.mail), n_mail + 1)
        to, sub, body = self.mail[-1]
        self.assertEqual((to, sub), (self.BOSS, cv.ADMIN_NOTICE_SUBJECT))
        self.assertIsNone(cv.CODE_RE.search(body) if hasattr(cv, "CODE_RE") else __import__("re").search(r"\b\d{6}\b", body))
        # even the right code (forced onto the row) never verifies it
        cid = v["challenge_id"]
        self.x("UPDATE contact_verifications SET code_hash=? WHERE challenge_id=?", (cv._code_hash(cid, "424242"), cid))
        r = self.confirm(out["token"], "424242", cid)
        self.assertEqual((r.status_code, r.json()["detail"]["error_code"]), (400, "VERIFY_CODE_INVALID"))
        self.assertFalse(self.q("SELECT email_verified_at FROM users WHERE user_id=?", (out["user_id"],))[0]["email_verified_at"])
        self.assertEqual(admin_bootstrap.startup_sync()["granted"], 0)
        self.assertEqual(self.q("SELECT role FROM users WHERE user_id=?", (out["user_id"],))[0]["role"], "guest")
        # the wrong-code answer is the same as for a normal account
        rn = self.confirm(normal["token"], "000001" if self.last_code("binh.thuong@example.test") != "000001" else "000002")
        rb = self.confirm(out["token"], "000001")
        self.assertEqual((rn.status_code, rn.json()["detail"]["error_code"]), (rb.status_code, rb.json()["detail"]["error_code"]))

    def test_direct_confirm_refused_for_listed_target(self):
        out = self.register(self.BOSS)
        cid = out["verification"]["challenge_id"]
        self.x("UPDATE contact_verifications SET code_hash=? WHERE challenge_id=?", (cv._code_hash(cid, "135790"), cid))
        with self.assertRaises(cv.VerifyError):
            cv.confirm(out["user_id"], "135790", cid)

    def test_startup_promotion_requires_admin_email_otp(self):
        # a listed address verified by anything but the admin e-mail OTP is never promoted
        u = auth_svc.register_guest(email=self.BOSS, password=PW)
        self.x("UPDATE users SET email_verified_at='2026-10-01T00:00:00+00:00' WHERE user_id=?", (u["user_id"],))
        self.assertEqual(admin_bootstrap.startup_sync()["granted"], 0)
        self.assertEqual(self.q("SELECT role FROM users WHERE user_id=?", (u["user_id"],))[0]["role"], "guest")
        # the real admin path still works: e-mail OTP → same row becomes admin
        req = self.client.post("/auth/email-otp/request", json={"email": self.BOSS}).json()
        import re

        code = re.search(r"\b(\d{6})\b", self.mail[-1][2]).group(1)
        out = self.client.post("/auth/email-otp/verify", json={"challenge_id": req["challenge_id"], "code": code}).json()
        self.assertEqual((out["user_id"], out["role"]), (u["user_id"], "admin"))
        # and stays admin across restarts
        self.assertEqual(admin_bootstrap.startup_sync(), {"granted": 0, "revoked": 0})
        self.assertEqual(self.q("SELECT role FROM users WHERE user_id=?", (u["user_id"],))[0]["role"], "admin")

    def test_existing_admin_row_kept(self):
        """Founder's staging admin (role admin, verified, listed) is untouched by the new rule."""
        self.x("INSERT INTO users(user_id, display_name, device_id, email, role, email_verified_at) "
               "VALUES ('founder','f','email:x',?,'admin','2026-09-30T00:00:00+00:00')", (self.BOSS,))
        self.assertEqual(admin_bootstrap.startup_sync(), {"granted": 0, "revoked": 0})
        self.assertEqual(self.q("SELECT role FROM users WHERE user_id='founder'")[0]["role"], "admin")
        me_flags = cv.flags(get_connection(None), self.q("SELECT * FROM users WHERE user_id='founder'")[0])
        self.assertFalse(me_flags["verify_eligible"])  # admins never see the verification flow


# =========================================================================== R1 daily caps
class TestDailyCaps(_Base):
    def test_daily_send_cap(self):
        os.environ.update({"WELORA_VERIFY_DAILY_SEND_MAX": "3", "WELORA_VERIFY_RESEND_COOLDOWN_S": "0",
                           "WELORA_RL_VERIFY_SEND_USER_MAX": "1000"})
        out = self.register("gioi.han.ngay@example.test")  # code 1 (register)
        st = [self.resend(out["token"]).status_code for _ in range(2)]  # codes 2, 3
        self.assertEqual(st, [200, 200])
        n_mail = len(self.mail)
        r = self.resend(out["token"])
        self.assertEqual((r.status_code, r.json()["detail"]["error_code"]), (429, "VERIFY_DAILY_LIMIT"))
        self.assertIn("24 giờ", r.json()["detail"]["message"])
        self.assertGreater(int(r.headers["Retry-After"]), 23 * 3600)
        self.assertEqual(len(self.mail), n_mail)  # nothing sent
        # rows older than 24 h no longer count
        self.x("UPDATE contact_verifications SET created_at='2020-01-01T00:00:00.000000+00:00' WHERE user_id=?", (out["user_id"],))
        self.assertEqual(self.resend(out["token"]).status_code, 200)

    def test_daily_wrong_attempt_cap(self):
        os.environ.update({"WELORA_VERIFY_DAILY_FAIL_MAX": "7", "WELORA_VERIFY_RESEND_COOLDOWN_S": "0",
                           "WELORA_RL_VERIFY_CONFIRM_USER_MAX": "1000"})
        out = self.register("sai.nhieu@example.test")
        bad = lambda: "000000" if self.last_code() != "000000" else "111111"  # noqa: E731
        codes = [self.confirm(out["token"], bad()).status_code for _ in range(5)]
        self.assertEqual(codes[-1], 429)  # per-code limit
        self.assertEqual(self.resend(out["token"]).status_code, 200)
        self.assertEqual([self.confirm(out["token"], bad()).status_code for _ in range(2)], [400, 400])  # 7 wrong
        r = self.confirm(out["token"], self.last_code())  # even the right code: daily cap reached
        self.assertEqual((r.status_code, r.json()["detail"]["error_code"]), (429, "VERIFY_DAILY_LIMIT"))
        self.assertFalse(self.verified(out["user_id"]))
        self.x("UPDATE contact_verifications SET created_at='2020-01-01T00:00:00.000000+00:00' "
               "WHERE user_id=? AND consumed<>0", (out["user_id"],))
        self.x("UPDATE contact_verifications SET attempts=0 WHERE user_id=? AND consumed=0", (out["user_id"],))
        self.assertEqual(self.confirm(out["token"], self.last_code()).status_code, 200)

    def test_defaults(self):
        self.assertEqual((cv.daily_send_max(), cv.daily_fail_max()), (10, 30))


# =========================================================================== R2 parallel resend
class TestParallelResend(_Base):
    def _burst(self, uid, n=12):
        self.x("UPDATE contact_verifications SET created_at=? WHERE user_id=?", ("2026-01-01T00:00:00.000000+00:00", uid))
        self.mail.clear()
        start = threading.Barrier(n)

        def one(_):
            start.wait()
            try:
                return cv.issue(uid)["challenge_id"]
            except cv.VerifyError as e:
                return e.code

        with ThreadPoolExecutor(n) as ex:
            return list(ex.map(one, range(n)))

    def test_burst_resend_one_open_code_one_mail(self):
        out = self.register("song.song.gui@example.test")
        res = self._burst(out["user_id"])
        ok = [r for r in res if r not in ("VERIFY_RESEND_COOLDOWN",)]
        self.assertEqual(len(ok), 1, res)
        self.assertEqual(set(res) - set(ok), {"VERIFY_RESEND_COOLDOWN"})
        opened = self.q("SELECT challenge_id FROM contact_verifications WHERE user_id=? AND consumed=0", (out["user_id"],))
        self.assertEqual([r["challenge_id"] for r in opened], ok)
        self.assertEqual(len(self.mail), 1)
        self.assertEqual(self.confirm(out["token"], self.last_code(), ok[0]).status_code, 200)

    def test_unique_index_backstop(self):
        out = self.register("chi.mot.ma@example.test")
        with self.assertRaises(Exception) as e:
            self.x("INSERT INTO contact_verifications(challenge_id, user_id, channel, target, code_hash, created_at, expires_at) "
                   "VALUES ('dup','%s','email','x','sha256:x','2026-01-01T00:00:00.000000+00:00','2099-01-01T00:00:00.000000+00:00')"
                   % out["user_id"])
        self.assertTrue(auth_svc._is_unique_violation(e.exception), repr(e.exception))
        # another channel / a used code is not affected
        self.x("INSERT INTO contact_verifications(challenge_id, user_id, channel, target, code_hash, created_at, expires_at, consumed) "
               "VALUES ('used','%s','email','x','sha256:x','2026-01-01T00:00:00.000000+00:00','2099-01-01T00:00:00.000000+00:00',1)"
               % out["user_id"])

    def test_migration_dedupes_then_indexes(self):
        m = importlib.import_module("welora.db.migrate")
        out = self.register("trung.lap@example.test")
        self.x("DROP INDEX IF EXISTS uq_contact_verif_open")
        self.x("INSERT INTO contact_verifications(challenge_id, user_id, channel, target, code_hash, created_at, expires_at) "
               "VALUES ('zz-newer',?,'email','x','sha256:x','2099-01-01T00:00:00.000000+00:00','2099-01-01T00:10:00.000000+00:00')",
               (out["user_id"],))
        self.x("DELETE FROM schema_migrations WHERE version='020_contact_verification'")
        self.assertEqual(m.migrate(None), ["020_contact_verification"])
        opened = self.q("SELECT challenge_id FROM contact_verifications WHERE user_id=? AND consumed=0", (out["user_id"],))
        self.assertEqual([r["challenge_id"] for r in opened], ["zz-newer"])  # the newest open code is kept
        if detect_dialect(None) == "sqlite":
            idx = self.q("SELECT name FROM sqlite_master WHERE type='index' AND name='uq_contact_verif_open'")
        else:
            idx = self.q("SELECT indexname AS name FROM pg_indexes WHERE indexname='uq_contact_verif_open'")
        self.assertEqual(len(idx), 1)
        self.assertEqual(m.migrate(None), [])


class TestParallelResendRealServer(unittest.TestCase):
    def setUp(self):
        from tests.test_p0b_kuat_academy import _Uvicorn

        self.tmp = tempfile.mkdtemp(prefix="welora-020r2-")
        self.env = {"WELORA_GUEST_DEMO": "1", "WELORA_RL_VERIFY_SEND_USER_MAX": "100000",
                    "WELORA_RL_VERIFY_SEND_IP_MAX": "100000", **db_env(self.tmp)}
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

    def test_http_burst(self):
        st, out = self.srv.call("/auth/register", {"email": "http.burst@example.test", "password": PW})
        self.assertEqual(st, 201, out)
        conn = get_connection(None)
        try:
            conn.execute("UPDATE contact_verifications SET created_at=? WHERE user_id=?",
                         ("2026-01-01T00:00:00.000000+00:00", out["user_id"]))
            conn.commit()
        finally:
            conn.close()
        with ThreadPoolExecutor(12) as ex:
            res = list(ex.map(lambda _: self.srv.call("/auth/verify/request", {}, token=out["token"]), range(12)))
        codes = sorted(s for s, _ in res)
        self.assertEqual(codes.count(200), 1, res)  # one 200 = the only code created and mailed
        self.assertEqual(set(codes) - {200}, {429})
        conn = get_connection(None)
        try:
            rows = conn.execute("SELECT consumed FROM contact_verifications WHERE user_id=?", (out["user_id"],)).fetchall()
        finally:
            conn.close()
        self.assertEqual(sorted(int(r["consumed"]) for r in rows), [0, 2])  # register code superseded + 1 open


if __name__ == "__main__":
    unittest.main()
