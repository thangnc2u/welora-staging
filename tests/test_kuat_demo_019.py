"""Ticket "GP — KUAT demo persona: tách lượt mở theo session/mạng (migration 019)".

1. Demo personas P1–P6 (one public login, many testers): the open KUAT attempt is per login session
   (fallback: client network) — two testers never see / consume / overwrite each other's attempt;
   regular accounts keep exactly ONE open attempt per user + node (unique index, migration 019);
   start / fail budgets unchanged (per persona + network, gate network buckets).
2. guest_ip / device 429 copy: no login / OTP nudge, review-the-lesson tone.
3. New attempts on NON-gate nodes capped per client network (WELORA_KUAT_NONGATE_IP_MAX_STARTS);
   the gate nodes' counters are untouched.
4. Demo seed writes academy_profiles matching the seeded mastery (P2/P3/P6 gate path mastered;
   P1/P4/P5 empty), idempotent, inside the seed transaction.
5. Device guests reach /app/academy only while WELORA_GUEST_DEMO is on (server marker + APIs);
   WELORA_GUEST_DEMO=0 blocks them server-side (403) and client-side (auth-gate.js redirect).
6. Read-time backfill: trusted mastery ≥ apply (source academy / seed) with an empty / partial
   profile → N02-01 + N02-02 mastered (+XP), never downgrading, idempotent.
DB scenarios run in subprocesses (tests/_k019_dbmode.py) on SQLite, or PG17 via WELORA_TEST_POSTGRES_URL.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests._db_target import db_env
from tests.test_p0b_kuat_academy import _Uvicorn
from welora import academy, academy_store
from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
VI = re.compile(r"[ạảãáàâầấậẩẫăằắặẳẵđêềếệểễôồốộổỗơờớợởỡưừứựửữìíịỉĩòóọỏõùúụủũỳýỵỷỹ]", re.I)
NUDGE = re.compile(r"(?i)đăng nhập|đăng ký|login|OTP|xác thực|xác minh")


def run(name: str, env: dict, state: dict | None = None, timeout: int = 300) -> dict:
    full = {k: v for k, v in os.environ.items() if not k.startswith("WELORA_")}
    full.update({"PYTHONPATH": str(ROOT), "WELORA_DEMO_AUTOSEED": "0", "WELORA_ENV": "staging",
                 "WELORA_GUEST_DEMO": "1", "K019_STATE": json.dumps(state or {})})
    full.update(env)
    p = subprocess.run([sys.executable, "-m", "tests._k019_dbmode", name], cwd=str(ROOT), env=full,
                       capture_output=True, text=True, timeout=timeout)
    for line in reversed(p.stdout.splitlines()):
        if line.startswith("RESULT="):
            return json.loads(line[len("RESULT="):])
    raise AssertionError(f"scenario {name} failed rc={p.returncode}\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}")


GATE_PATH_MASTERED = {"N02-01": "mastered", "N02-02": "mastered", "N02-03": "available"}
EMPTY = {"N02-01": "available", "N02-02": "locked", "N02-03": "locked"}


# =========================================================================== item 1 (+ migration)
class TestDemoSessionsDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = run("demo_sessions", db_env(tempfile.mkdtemp()))

    def test_two_sessions_of_one_persona_each_get_their_own_open_attempt(self):
        o = self.o
        self.assertTrue(o["same_user"])
        self.assertEqual(o["starts"], [200, 200])
        self.assertTrue(o["distinct_attempts"])
        self.assertTrue(o["a_again"])  # reload / other tab of the same session → same attempt
        self.assertTrue(o["b_node_same"])  # GET node reuses the session's open attempt
        self.assertTrue(o["a_on_ip_b"])  # scope = login session, not the current network
        self.assertEqual(o["open_count"], 2)
        self.assertTrue(o["open_scopes_distinct"])
        self.assertEqual(o["scope_prefixes"], ["s:"])
        self.assertTrue(o["token_not_stored"])  # only a hash of the bearer token

    def test_a_tester_cannot_consume_or_overwrite_the_other_testers_attempt(self):
        o = self.o
        self.assertEqual(o["a_submits_b_attempt"], [409, "KUAT_ATTEMPT_INVALID"])
        self.assertTrue(o["b_still_open"])
        self.assertEqual(o["a_submit_no_id"], [200, False])  # no attempt_id → A's own attempt
        self.assertEqual(o["a_consumed"], "failed")
        self.assertIsNone(o["b_after_a"])  # B's attempt untouched by A's submit
        self.assertEqual(o["b_pass"], [200, True])

    def test_no_session_falls_back_to_the_client_network(self):
        self.assertEqual(self.o["network_scope"], [True, True])
        self.assertEqual(self.o["network_scopes"], ["n:"])

    def test_regular_accounts_keep_exactly_one_open_attempt_per_node(self):
        o = self.o
        self.assertEqual(o["regular"]["two_tokens_same_user"], [True, True])
        self.assertTrue(o["regular"]["same_attempt"])  # two logins / networks of ONE account
        self.assertEqual(o["regular"]["open"], [""])
        self.assertTrue(o["guest_same_attempt"])
        self.assertEqual(o["guest_open"], [""])
        self.assertEqual(o["scope_regular"], ["", ""])
        self.assertIn(o["db_second_open_regular"], ("IntegrityError", "UniqueViolation"))


class TestDemoSessionBudgetDb(unittest.TestCase):
    """New logins buy no extra attempts: the start limit stays per (persona, node, network)."""

    @classmethod
    def setUpClass(cls):
        cls.o = run("demo_session_budget", {**db_env(tempfile.mkdtemp()), "WELORA_KUAT_MAX_STARTS": "3"})

    def test_start_budget_shared_by_all_sessions_on_one_network(self):
        self.assertEqual(self.o["starts"], [[200, None]] * 3 + [[429, "starts"]])
        self.assertEqual(self.o["other_network"], 200)


class TestMigration019TwiceDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = run("migrate_twice", db_env(tempfile.mkdtemp()))

    def test_pre019_database_upgraded(self):
        o = self.o
        self.assertFalse(o["pre_has_019"])
        self.assertFalse(o["pre_cols_scope"])
        self.assertEqual(o["pre_idx"], ["uq_academy_kuat_open"])
        self.assertEqual(o["first"], ["019_kuat_open_scope"])
        self.assertTrue(o["cols_scope"])
        self.assertEqual(o["idx"], ["uq_academy_kuat_open_scope"])  # 018's index replaced
        self.assertEqual(o["pre_row_scope"], "")  # existing attempts = regular scope

    def test_runs_twice_without_error(self):
        o = self.o
        self.assertEqual(o["second"], [])
        self.assertEqual(o["third"], ["019_kuat_open_scope"])  # version row removed → re-applied, no error
        self.assertEqual(o["step_twice"], "ok")
        if o["dialect"] == "postgres":
            self.assertEqual(o["sql_file_twice"], "ok")  # psql -f twice
        self.assertEqual(o["idx_after"], ["uq_academy_kuat_open_scope"])
        self.assertEqual(o["cols_after"], 1)
        self.assertEqual(o["versions_019"], ["019_kuat_open_scope"])

    def test_unique_per_user_node_scope(self):
        self.assertEqual(self.o["dup_regular"], "refused")
        self.assertEqual(self.o["other_scope"], "inserted")
        self.assertEqual(self.o["dup_other_scope"], "refused")


class TestDemoSessionsConcurrencyDb(unittest.TestCase):
    """Real uvicorn (parallel requests): two sessions of one persona bursting starts each end with
    exactly one open attempt; a regular account's burst over two logins → one; parallel submits of
    one attempt → exactly one graded (atomic consume unchanged)."""

    @classmethod
    def setUpClass(cls):
        import tests.test_p0b_kuat_academy as p0b

        env = db_env(tempfile.mkdtemp())
        p0b.run("seed_demo", env)
        cls.srv = _Uvicorn(env)

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def _login(self, email, pw, ip):
        st, j = self.srv.call("/auth/login", {"email": email, "password": pw}, ip=ip)
        self.assertEqual(st, 200, j)
        return j["user_id"], j["token"]

    def _burst_starts(self, sessions, node, n):
        from concurrent.futures import ThreadPoolExecutor

        jobs = [(uid, tok, ip) for uid, tok, ip in sessions for _ in range(n)]
        with ThreadPoolExecutor(len(jobs)) as ex:
            res = list(ex.map(lambda j: self.srv.call("/academy/kuat/start", {"user_id": j[0], "node_id": node}, j[1], j[2]), jobs))
        return [(jobs[i][1], st, b.get("attempt_id"), b) for i, (st, b) in enumerate(res)]

    def test_parallel_demo_sessions_and_regular_account(self):
        from concurrent.futures import ThreadPoolExecutor

        from tests._kuat import solve
        from welora import auth as auth_svc, partner_demo_seed

        email = partner_demo_seed.DEMO_PERSONA_ALIASES["P4"]["email"]
        s1 = (*self._login(email, auth_svc.DEMO_PASSWORD, "192.0.2.61"), "203.0.113.61")
        s2 = (*self._login(email, auth_svc.DEMO_PASSWORD, "192.0.2.62"), "198.51.100.62")
        self.assertEqual(s1[0], s2[0])
        res = self._burst_starts([s1, s2], "N02-01", 6)
        self.assertEqual({st for _t, st, _a, _b in res}, {200}, [b for _t, st, _a, b in res if st != 200][:1])
        per = {tok: {a for t, _s, a, _b in res if t == tok} for tok in (s1[1], s2[1])}
        self.assertEqual([len(v) for v in per.values()], [1, 1])  # one attempt per session
        self.assertNotEqual(per[s1[1]], per[s2[1]])
        rows = self.srv.q("SELECT scope_key FROM academy_kuat_attempts WHERE user_id=? AND node_id='N02-01' "
                          "AND used_at IS NULL", (s1[0],))
        self.assertEqual(len(rows), 2)
        # regular account: two logins, parallel burst from two networks → ONE open attempt
        from tests._followup2_dbmode import PW

        acc_email = "k019-conc@example.test"
        st, acc = self.srv.call("/auth/register", {"email": acc_email, "password": PW}, ip="192.0.2.63")
        self.assertEqual(st, 201, acc)
        r1 = (acc["user_id"], acc["token"], "203.0.113.63")
        r2 = (*self._login(acc_email, PW, "192.0.2.64"), "198.51.100.64")
        rres = self._burst_starts([r1, r2], "N02-01", 6)
        self.assertEqual({st for _t, st, _a, _b in rres}, {200})
        self.assertEqual(len({a for _t, _s, a, _b in rres}), 1)
        self.assertEqual(self.srv.q("SELECT COUNT(*) FROM academy_kuat_attempts WHERE user_id=? AND used_at IS NULL",
                                    (acc["user_id"],))[0][0], 1)
        # parallel submits of each demo session's attempt: exactly one graded per attempt
        atts = {t: b for t, _s, _a, b in res}
        jobs = []
        for uid, tok, ip in (s1, s2):
            b = atts[tok]
            body = {"user_id": uid, "node_id": "N02-01", "attempt_id": b["attempt_id"],
                    "answers": solve("N02-01", b["questions"], correct=False)}
            jobs += [(body, tok, ip)] * 4
        with ThreadPoolExecutor(len(jobs)) as ex:
            subs = list(ex.map(lambda j: self.srv.call("/academy/kuat", j[0], j[1], j[2]), jobs))
        for k in range(2):
            codes = sorted(st for st, _b in subs[k * 4:(k + 1) * 4])
            self.assertEqual(codes, [200, 409, 409, 409])


# =========================================================================== item 3
class TestNonGateStartCapDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = run("nongate_starts", {**db_env(tempfile.mkdtemp()), "WELORA_KUAT_NONGATE_IP_MAX_STARTS": "5"})

    def test_cap_per_network_on_non_gate_nodes(self):
        o = self.o
        self.assertEqual(o["starts"], [[200, None]] * 5 + [[429, "ip_starts"]])
        c = o["cap"]
        self.assertEqual((c["error_code"], c["reason"]), ("KUAT_COOLDOWN", "ip_starts"))
        self.assertRegex(c["message"], VI)
        self.assertIn("giờ Việt Nam", c["message"])
        self.assertIn("ôn lại bài", c["message"])
        self.assertNotRegex(c["message"], NUDGE)
        self.assertEqual(c["retry_after"], 3600)
        self.assertTrue(c["lesson_href"].startswith("/app/academy?node="))  # follow-up item 2 (was /app/content)
        self.assertEqual(o["nongate_events"], 5)

    def test_reload_other_network_and_gate_nodes_unaffected(self):
        o = self.o
        self.assertEqual(o["reload"], 200)  # the open attempt is reused — not a new start
        self.assertEqual(o["other_network"], 200)
        self.assertEqual(o["gate"], [200, 200, 200])  # N02-01 never counts against / is blocked by it
        self.assertEqual(o["gate_fail_events"], 0)


class TestNonGateStartCapDefaults(unittest.TestCase):
    def test_defaults_and_gate_budgets_unchanged(self):
        keys = ("WELORA_KUAT_NONGATE_IP_MAX_STARTS", "WELORA_KUAT_NONGATE_IP_START_WINDOW_S",
                "WELORA_KUAT_GUEST_IP_MAX_FAILS", "WELORA_KUAT_GUEST_DEVICE_MAX_FAILS", "WELORA_KUAT_IP_MAX_FAILS",
                "WELORA_KUAT_IP_DAY_MAX_FAILS", "WELORA_KUAT_MAX_STARTS", "WELORA_KUAT_MAX_FAILS",
                "WELORA_KUAT_DAILY_MAX_FAILS", "WELORA_KUAT_GUEST_WINDOW_S")
        prev = {k: os.environ.pop(k, None) for k in keys}
        try:
            self.assertEqual(academy_store.nongate_ip_max_starts(), 300)
            self.assertEqual(academy_store.nongate_ip_start_window_s(), 3600)
            # #242 budgets unchanged
            self.assertEqual((academy_store.guest_ip_max_fails(), academy_store.guest_device_max_fails(),
                              academy_store.ip_max_fails(), academy_store.ip_day_max_fails(),
                              academy_store.max_starts(), academy_store.max_fails(), academy_store.daily_max_fails(),
                              academy_store.guest_window_s()), (6, 6, 30, 60, 30, 3, 10, 86400))
            self.assertEqual(academy_store.GATE_KUAT_NODES, ("N02-01", "N02-02"))
        finally:
            for k, v in prev.items():
                if v is not None:
                    os.environ[k] = v


# =========================================================================== item 2
class TestGuestCopy(unittest.TestCase):
    def test_guest_ip_and_device_have_no_login_nudge(self):
        for reason in ("guest_ip", "device", "ip_starts"):
            e = academy_store.KuatCooldown(3 * 3600, reason)
            d = academy.cooldown_payload(e, "N02-01")
            self.assertEqual(d["reason"], reason)
            self.assertNotRegex(d["message"], NUDGE, reason)
            self.assertRegex(d["message"], VI)
            self.assertIn("ôn lại bài «", d["message"])  # review-the-lesson tone (+ lesson title)
            self.assertIn("giờ Việt Nam", d["message"])
            self.assertIn("3 giờ", d["message"])
        self.assertNotIn("Hãy đăng nhập", (ROOT / "welora" / "academy.py").read_text(encoding="utf-8"))
        for msg in academy.COOLDOWN_MSG_VI.values():
            self.assertNotRegex(msg, NUDGE)


# =========================================================================== item 4
class TestSeedProfilesDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = db_env(tempfile.mkdtemp())
        cls.o = run("seed_profiles", env)
        cls.r = run("seed_profiles_read", env)

    def test_profiles_match_seeded_mastery(self):
        f = self.o["first"]
        for pid in ("P2", "P3", "P6"):
            self.assertEqual(f[pid]["status"], GATE_PATH_MASTERED, pid)
            self.assertEqual(f[pid]["xp"], 40, pid)
        for pid in ("P1", "P4", "P5"):
            self.assertEqual(f[pid]["status"], EMPTY, pid)
            self.assertEqual(f[pid]["xp"], 0, pid)
        self.assertEqual((self.o["gate_p2"], self.o["mastery_p2"]), ("passed", "apply"))
        self.assertEqual(self.o["rows"], 6)

    def test_idempotent_and_persisted(self):
        self.assertEqual(self.o["second"]["P2"], self.o["first"]["P2"])
        self.assertEqual(self.o["second"]["P4"], self.o["first"]["P4"])
        self.assertEqual(self.r["P2"], self.o["first"]["P2"])  # fresh process
        self.assertEqual(self.r["P4"], self.o["first"]["P4"])


class TestSeedProfileInSeedTransactionDb(unittest.TestCase):
    def test_failed_seed_leaves_no_profile(self):
        o = run("seed_rollback", db_env(tempfile.mkdtemp()))
        self.assertTrue(o["failed"])
        self.assertEqual(o["profiles"], [])


# =========================================================================== item 6
class TestBackfillDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = db_env(tempfile.mkdtemp())
        cls.w = run("backfill_write", env)
        cls.r = run("backfill_read", env, {"users": cls.w["users"]})
        cls.p2 = run("backfill_demo_p2", db_env(tempfile.mkdtemp()))

    def test_trusted_mastery_without_profile_backfilled(self):
        t = self.w["trees"]
        for k in ("academy_apply", "seed_apply"):
            self.assertEqual(t[k]["status"], GATE_PATH_MASTERED, k)
            self.assertEqual(t[k]["xp"], 40, k)
        self.assertEqual(self.w["n02_03_after"], [200, True])  # the next node is open and works

    def test_untrusted_or_below_apply_not_backfilled(self):
        t = self.w["trees"]
        for k in ("untrusted_apply", "academy_familiar"):
            self.assertEqual(t[k]["status"], EMPTY, k)
            self.assertEqual(t[k]["xp"], 0, k)
        self.assertIsNone(self.w["rev_after_first_read"]["untrusted_apply"])

    def test_existing_profile_kept_and_never_downgraded(self):
        w = self.w
        self.assertEqual(w["trees"]["with_row"]["status"], GATE_PATH_MASTERED)
        self.assertEqual(w["trees"]["with_row"]["xp"], 60)  # N01-01 (20) kept + gate path (40)
        self.assertEqual(w["with_row_n01"], "mastered")
        self.assertEqual(w["with_row_read"], ["N01-01", "N02-01"])
        self.assertEqual(w["trees"]["already"]["xp"], 40)  # no double XP
        self.assertEqual(w["rev_after_first_read"]["already"], w["already_rev_before"])  # nothing written
        # the mastery flag itself is never touched
        self.assertEqual(w["mastery_after"], {"academy_apply": "apply", "seed_apply": "apply",
                                              "untrusted_apply": "not_started", "academy_familiar": "familiar",
                                              "with_row": "apply", "already": "apply"})
        self.assertEqual(w["sources_after"]["academy_apply"], "academy")
        self.assertIsNone(w["sources_after"]["untrusted_apply"])

    def test_idempotent_reads(self):
        w, r = self.w, self.r
        self.assertEqual(w["trees_again"], w["trees"])
        self.assertEqual(w["rev_after_second_read"], w["rev_after_first_read"])
        self.assertEqual(r["rev_after"], r["rev_before"])  # a fresh process does not write again
        for k in ("seed_apply", "with_row", "already", "untrusted_apply", "academy_familiar"):
            self.assertEqual(r["trees"][k], w["trees"][k], k)
        # academy_apply then passed N02-03 on top of the backfill — kept after the restart
        self.assertEqual(r["trees"]["academy_apply"]["status"], {"N02-01": "mastered", "N02-02": "mastered",
                                                                  "N02-03": "mastered"})
        self.assertEqual(r["trees"]["academy_apply"]["xp"], 60)

    def test_demo_p2_seeded_before_this_change(self):
        self.assertTrue(self.p2["uid_ok"])
        self.assertEqual(self.p2["p2"]["status"], GATE_PATH_MASTERED)
        self.assertEqual(self.p2["p2"]["xp"], 40)
        self.assertEqual(self.p2["p4"]["status"], EMPTY)


class TestBackfillOptimisticWrite(unittest.TestCase):
    def test_save_if_rev(self):
        prev = {k: os.environ.get(k) for k in ("WELORA_STORE", "WELORA_DB_URL")}
        d = tempfile.mkdtemp()
        os.environ.update({"WELORA_STORE": "sqlite", "WELORA_DB_URL": f"sqlite:///{d}/o.db"})
        try:
            self.assertEqual(academy_store.save_profile_if_rev("u-opt", {"xp": 1}, None), 1)
            self.assertIsNone(academy_store.save_profile_if_rev("u-opt", {"xp": 2}, None))  # row exists
            self.assertIsNone(academy_store.save_profile_if_rev("u-opt", {"xp": 2}, 7))  # stale rev
            self.assertEqual(academy_store.save_profile_if_rev("u-opt", {"xp": 3}, 1), 2)
            self.assertEqual(academy_store.load_profile("u-opt"), ({"xp": 3}, 2))
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v


# =========================================================================== item 5
class TestGuestAcademyDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.on = run("guest_academy", {**db_env(tempfile.mkdtemp()), "WELORA_GUEST_DEMO": "1"})
        cls.off = run("guest_academy", {**db_env(tempfile.mkdtemp()), "WELORA_GUEST_DEMO": "0"})

    def test_guest_demo_on_guests_use_academy(self):
        self.assertEqual(self.on["guest"], [200, 200, 200, 200])
        self.assertTrue(self.on["meta"])
        self.assertIs(self.on["health"], True)

    def test_production_guest_demo_off_blocks_guests_server_side(self):
        self.assertEqual(self.off["guest"], [403, 403, 403, 403])
        d = self.off["guest_detail"]
        self.assertEqual(d["error_code"], "ACADEMY_LOGIN_REQUIRED")
        self.assertRegex(d["message"], VI)
        self.assertEqual(self.off["account"], [200, 200, 200, 200])  # logged-in accounts unaffected
        self.assertFalse(self.off["meta"])
        self.assertIs(self.off["health"], False)


class TestGuestAcademyPage(unittest.TestCase):
    def _page(self, flag):
        prev = os.environ.get("WELORA_GUEST_DEMO")
        os.environ["WELORA_GUEST_DEMO"] = flag
        try:
            c = TestClient(create_app())
            return c.get("/app/academy"), c.get("/app/academy/"), c.get("/health").json()
        finally:
            if prev is None:
                os.environ.pop("WELORA_GUEST_DEMO", None)
            else:
                os.environ["WELORA_GUEST_DEMO"] = prev

    def test_marker_only_when_guest_demo_on_and_before_auth_gate(self):
        on, on_slash, h_on = self._page("1")
        off, _off_slash, h_off = self._page("0")
        for r in (on, on_slash):
            self.assertEqual(r.status_code, 200)
            t = r.text
            self.assertEqual(t.count('<meta name="welora-guest-academy" content="1"/>'), 1)
            self.assertLess(t.index('name="welora-guest-academy"'), t.index("/static/auth-gate.js"))
            self.assertEqual(r.headers.get("cache-control"), "no-store")
        self.assertNotIn("welora-guest-academy", off.text)
        self.assertIn("/static/auth-gate.js", off.text)
        self.assertEqual((h_on["guest_academy"], h_off["guest_academy"]), (True, False))
        self.assertEqual(h_on["gate_months"], 3)
        # /health exposes a boolean only — nothing else new
        self.assertIsInstance(h_on["guest_academy"], bool)

    def test_static_scripts_gate_academy_on_the_marker(self):
        ag = (STATIC / "auth-gate.js").read_text(encoding="utf-8")
        self.assertNotIn('"/app/academy": 1', ag)  # never unconditionally allowlisted
        self.assertIn('meta[name="welora-guest-academy"]', ag)
        for f in ("session.js", "shell.js"):
            s = (STATIC / f).read_text(encoding="utf-8")
            self.assertIn('meta[name="welora-guest-academy"]', s, f)
            self.assertNotIn('"/app/academy": 1', s, f)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TestAuthGateJsBehaviour(unittest.TestCase):
    """Run auth-gate.js (and shell.js' gate) in node with a fake DOM: client-side half of item 5."""

    HARNESS = r"""
const vm = require('vm'); const fs = require('fs');
const [file, path, meta, tok] = process.argv.slice(2);
let redirected = null;
const ctx = {
  location: { pathname: path, replace: (u) => { redirected = u; }, href: '' },
  localStorage: { getItem: (k) => (k === 'welora_token' && tok ? tok : null), removeItem: () => {}, setItem: () => {} },
  document: { querySelector: (sel) => (meta === '1' && sel.indexOf('welora-guest-academy') >= 0)
      ? { getAttribute: () => '1' } : null,
    currentScript: null, documentElement: { setAttribute: () => {} },
    body: { classList: { add: () => {} }, insertBefore: () => {}, firstChild: null, appendChild: () => {} },
    createElement: () => ({ setAttribute: () => {}, appendChild: () => {}, classList: { add: () => {} },
      addEventListener: () => {}, style: {} }), getElementById: () => null, querySelectorAll: () => [] },
  sessionStorage: { setItem: () => {} },
};
ctx.window = ctx;
try { vm.runInNewContext(fs.readFileSync(file, 'utf8'), ctx); } catch (e) { }
console.log(JSON.stringify({ redirected }));
"""

    def _run(self, file, path, meta, tok=""):
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(self.HARNESS)
        p = subprocess.run([shutil.which("node"), f.name, str(STATIC / file), path, meta, tok],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout.strip().splitlines()[-1])["redirected"]

    def test_auth_gate(self):
        self.assertIsNone(self._run("auth-gate.js", "/app/academy", "1"))  # guest demo on → open
        self.assertIsNone(self._run("auth-gate.js", "/app/academy/", "1"))
        self.assertEqual(self._run("auth-gate.js", "/app/academy", "0"), "/app/login")  # production
        self.assertEqual(self._run("auth-gate.js", "/app/goals", "1"), "/app/login")  # only the Academy
        self.assertIsNone(self._run("auth-gate.js", "/app/academy", "0", "tok"))  # logged in
        self.assertIsNone(self._run("auth-gate.js", "/app/onboarding", "0"))

    def test_shell_gate(self):
        self.assertIsNone(self._run("shell.js", "/app/academy", "1"))
        self.assertEqual(self._run("shell.js", "/app/academy", "0"), "/app/login")
        self.assertEqual(self._run("shell.js", "/app/goals", "1"), "/app/login")


# =========================================================================== constraints
class TestConstraintsUnchanged(unittest.TestCase):
    def test_constraints(self):
        from welora.checkout import checkout_enabled

        self.assertEqual(TARGET_MONTHS, 3)
        prev = os.environ.pop("WELORA_CHECKOUT_ENABLED", None)
        try:
            self.assertFalse(checkout_enabled())
        finally:
            if prev is not None:
                os.environ["WELORA_CHECKOUT_ENABLED"] = prev
        self.assertEqual(TestClient(create_app()).get("/health").json().get("hard_deny"), True)


if __name__ == "__main__":
    unittest.main()
