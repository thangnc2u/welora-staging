"""GP P0b — siết KUAT + lưu tiến độ Academy.

1. KUAT: no per-question correctness anywhere; DB-backed attempt limit + cooldown (429 VI + retry
   time); random draw from a bigger bank + shuffled options graded against a server-held,
   single-use, expiring attempt.
2. Academy progress persisted (SQLite + PG17) — survives a fresh process.
3. Health Score reads the same flags as /safety-gate (cold process after restart).
4. Guest claim onto an account with an untrusted flags row carries the guest's real mastery.
Round 2 (CoS review of 7f02a10): pass / fail ONLY (no score oracle), guest limits aggregated per IP
and per device, one open attempt per user + node, fail slot reserved before grading (real uvicorn
concurrency tests), length-balanced content + Monte Carlo guessing test, no "hard" marker, GET node
reuses the open attempt, stale tab → 409 KUAT_RELOAD (not counted).
DB scenarios run in subprocesses (tests/_p0b_dbmode.py) on SQLite, or PG via WELORA_TEST_POSTGRES_URL.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from tests._authz import bearer
from tests._db_target import db_env
from tests._kuat import solve
from welora import academy, academy_store, goals_api, mastery
from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
FORBIDDEN = {"correct", "is_correct", "answer", "answers", "perm", "served", "served_json",
             "score", "hard", "correct_count", "percent"}
VI = re.compile(r"[ạảãáàâầấậẩẫăằắặẳẵđêềếệểễôồốộổỗơờớợởỡưừứựửữìíịỉĩòóọỏõùúụủũỳýỵỷỹ]", re.I)


def run(name: str, env: dict, state: dict | None = None, timeout: int = 300) -> dict:
    full = {k: v for k, v in os.environ.items() if not k.startswith("WELORA_")}
    full.update({"PYTHONPATH": str(ROOT), "WELORA_DEMO_AUTOSEED": "0", "WELORA_ENV": "staging",
                 "WELORA_GUEST_DEMO": "1", "P0B_STATE": json.dumps(state or {})})
    full.update(env)
    p = subprocess.run([sys.executable, "-m", "tests._p0b_dbmode", name], cwd=str(ROOT), env=full,
                       capture_output=True, text=True, timeout=timeout)
    for line in reversed(p.stdout.splitlines()):
        if line.startswith("RESULT="):
            return json.loads(line[len("RESULT="):])
    raise AssertionError(f"scenario {name} failed rc={p.returncode}\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}")


def keys(obj, found=None):
    found = set() if found is None else found
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.add(k)
            keys(v, found)
    elif isinstance(obj, list):
        for v in obj:
            keys(v, found)
    return found


# =========================================================================== DB (SQLite / PG17)
class TestBruteForceLockedOutDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run("bruteforce", db_env(tempfile.mkdtemp()))

    def test_script_locked_after_three_failures(self):
        self.assertEqual(self.out["log"], [[200, False]] * 3)
        lk = self.out["locked"]
        self.assertEqual((lk["where"], lk["status"]), ("start", 429))
        self.assertEqual(lk["retry_after_header"], "1800")
        d = lk["detail"]
        self.assertEqual(d["error_code"], "KUAT_COOLDOWN")
        self.assertRegex(d["message"], VI)
        self.assertIn("30 phút", d["message"])
        self.assertTrue(d["retry_at"])
        self.assertEqual(self.out["submit_while_locked"], 429)
        self.assertEqual(self.out["node_questions"], 0)
        self.assertEqual(self.out["node_cooldown"]["error_code"], "KUAT_COOLDOWN")
        self.assertEqual(self.out["mastery"], "not_started")

    def test_no_per_question_signal_in_any_response(self):
        self.assertEqual(self.out["forbidden_keys"], [])
        self.assertEqual(self.out["canonical_ids"], [])  # served slots are k1…kN, never bank ids

    def test_other_user_same_ip_not_blocked(self):
        self.assertEqual(self.out["other_user_same_ip"], [200, True])


class TestAcademyPersistsAcrossProcessesDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = db_env(tempfile.mkdtemp())
        cls.w = run("persist_write", env)
        cls.r = run("persist_read", env, cls.w)  # fresh process = restart / another instance

    def test_progress_survives_restart(self):
        self.assertEqual(self.w["p1"], [200, True])
        self.assertEqual(self.w["fail"], [200, False])
        self.assertEqual(self.r["before"], self.w["tree"])
        self.assertEqual(self.r["before"]["xp"], 20)
        self.assertEqual(self.r["before"]["status"]["N02-01"], "mastered")
        self.assertEqual(self.r["before"]["status"]["N02-02"], "kuat_pending")
        self.assertTrue(self.r["read_kept"])

    def test_server_held_attempt_valid_after_restart_and_single_use(self):
        self.assertEqual(self.r["submit"], [200, True])
        self.assertEqual(self.r["again"], [409, "KUAT_ATTEMPT_INVALID"])
        self.assertEqual(self.r["after"]["status"]["N02-02"], "mastered")
        self.assertEqual(self.r["after"]["xp"], 40)
        self.assertEqual(self.r["mastery"], "apply")

    def test_nothing_per_question_stored(self):
        self.assertEqual(self.r["profile_forbidden"], [])
        self.assertEqual(self.r["last_kuat_keys"], ["node_id", "passed", "principle_keys", "ts"])
        self.assertEqual(self.r["attempt_scores"], [None] * len(self.r["attempt_scores"]))  # no score stored
        self.assertFalse({"correct", "answers", "detail"} & set(self.r["attempt_columns"]))
        self.assertIn("failed", self.r["outcomes"])


class TestHealthScoreMatchesGateAfterRestartDb(unittest.TestCase):
    def test_health_score_equals_safety_gate_in_cold_process(self):
        env = db_env(tempfile.mkdtemp())
        w = run("health_write", env)
        self.assertEqual((w["gate"], w["health_gate"]), ("passed", "passed"))
        r = run("health_read", env, w)
        self.assertEqual(r["gate"], "passed")
        self.assertEqual(r["health_gate"], r["gate"])


class TestGuestClaimUntrustedAccountDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run("claim_untrusted_account", db_env(tempfile.mkdtemp()))

    def test_untrusted_account_row_receives_real_guest_mastery(self):
        o = self.out
        self.assertEqual(o["a_before"], "not_started")
        self.assertEqual(o["a_claim"], [200, 1, None])
        self.assertEqual(o["a_row"], ["apply", "academy", 1])  # account's own debt flag kept
        self.assertEqual(o["a_mastery"], "apply")
        self.assertEqual(o["a_tree"]["status"]["N02-02"], "mastered")

    def test_trusted_account_row_wins(self):
        self.assertEqual(self.out["b_claim"], [200, None, "account_has_flags"])
        self.assertEqual(self.out["b_row"][:2], ["familiar", "academy"])

    def test_untrusted_guest_mastery_never_transfers(self):
        self.assertEqual(self.out["c_claim"], [200, None])
        self.assertEqual(self.out["c_mastery"], "not_started")

    def test_academy_progress_merged(self):
        self.assertEqual(self.out["d_claim"], [200, 1])
        self.assertEqual(self.out["d_tree"], {"xp": 40, "N01-01": "mastered", "N02-01": "mastered"})


class TestGuestLimitsAggregatedDb(unittest.TestCase):
    """Round 2 blocking 1: single-use guests no longer reset the budget."""

    @classmethod
    def setUpClass(cls):
        cls.out = run("guest_limits", db_env(tempfile.mkdtemp()))

    def test_all_guests_on_one_ip_share_six_fails(self):
        self.assertEqual(self.out["per_guest"], [[200, False]] * 6 + [[429, "guest_ip"]])
        self.assertEqual(self.out["guest_ip_reason"], "guest_ip")
        self.assertRegex(self.out["guest_ip_msg"], VI)
        self.assertIn("giờ", self.out["guest_ip_msg"])  # retry time ~24 h

    def test_real_account_and_other_ip_unaffected(self):
        self.assertEqual(self.out["real_same_ip"], [200, False])
        self.assertEqual(self.out["other_ip_guest"], [200, False])

    def test_guest_device_capped_across_nodes(self):
        self.assertEqual(self.out["device"], [[200, False]] * 6)
        self.assertEqual(self.out["device_next"], [429, "device"])
        self.assertRegex(self.out["device_msg"], VI)


class TestStaleTabAndOpenAttemptDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = run("stale_tab", db_env(tempfile.mkdtemp()))

    def test_get_node_and_start_return_the_same_open_attempt(self):
        self.assertTrue(self.out["same_attempt"])

    def test_old_style_ids_409_reload_not_counted(self):
        self.assertEqual(self.out["stale"], [[409, "KUAT_RELOAD"]] * 5)
        self.assertEqual(self.out["slot"][:2], [409, "KUAT_RELOAD"])
        self.assertIn("Vui lòng tải lại trang", self.out["slot"][2])
        self.assertEqual(self.out["fails_recorded"], 0)
        self.assertEqual(self.out["then_pass"], [200, True])  # the open attempt was not burnt


# --------------------------------------------------------------------------- real uvicorn concurrency
def _free_port() -> int:
    import socket

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Uvicorn:
    """The app under a REAL uvicorn (start.sh: 1 worker, threadpool → truly parallel requests)."""

    def __init__(self, env: dict) -> None:
        import urllib.request

        self.env = env
        self.port = _free_port()
        full = {k: v for k, v in os.environ.items() if not k.startswith("WELORA_")}
        full.update(env)
        full.update({"PORT": str(self.port), "PYTHONPATH": str(ROOT), "WELORA_ENV": "staging",
                     "WELORA_DEMO_AUTOSEED": "0", "WELORA_RL_DEVICE_NEW_IP_MAX": "1000",
                     "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")})
        self.proc = subprocess.Popen(["bash", str(ROOT / "start.sh")], cwd=str(ROOT), env=full,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise AssertionError("server exited: " + self.proc.stdout.read().decode("utf-8", "replace")[-3000:])
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1)
                return
            except Exception:
                time.sleep(0.1)
        self.stop()
        raise AssertionError("server did not start")

    def call(self, path, body, token=None, ip="203.0.113.9"):
        import urllib.error
        import urllib.request

        h = {"Content-Type": "application/json", "X-Forwarded-For": ip}
        if token:
            h["Authorization"] = "Bearer " + token
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode(), headers=h)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def guest(self, ip):
        st, j = self.call("/auth/device", {"device_id": "web-" + uuid.uuid4().hex[:14]}, ip=ip)
        assert st == 200, (st, j)
        return j["user_id"], j["token"]

    def start(self, uid, tok, node, ip):
        self.call(f"/academy/nodes/{node}/read", {"user_id": uid, "node_id": node}, tok, ip)
        return self.call("/academy/kuat/start", {"user_id": uid, "node_id": node}, tok, ip)

    def wrong(self, uid, tok, node, att, ip):
        return self.call("/academy/kuat", {"user_id": uid, "node_id": node, "attempt_id": att["attempt_id"],
                                           "answers": solve(node, att["questions"], correct=False)}, tok, ip)

    def q(self, sql, params=()):
        url = self.env["WELORA_DB_URL"]
        if url.startswith("sqlite"):
            import sqlite3

            c = sqlite3.connect(url.split("sqlite:///", 1)[1])
            try:
                return c.execute(sql, params).fetchall()
            finally:
                c.close()
        import psycopg

        with psycopg.connect(url) as c:
            return c.execute(sql.replace("?", "%s"), params).fetchall()

    def fails(self, scope, key):
        from welora.auth_ratelimit import _key_hash

        return self.q("SELECT COUNT(*) FROM auth_rate_events WHERE action='kuat_fail' AND scope=? AND key_hash=?",
                      (scope, _key_hash(scope, key)))[0][0]

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


class TestRealConcurrencyDb(unittest.TestCase):
    """Round 2 blocking 2 (PG17 when WELORA_TEST_POSTGRES_URL is set, else SQLite): parallel starts
    and submits through a real uvicorn never open a 2nd attempt nor exceed a fail cap."""

    @classmethod
    def setUpClass(cls):
        cls.srv = _Uvicorn({**db_env(tempfile.mkdtemp()), "WELORA_KUAT_GUEST_DEVICE_MAX_FAILS": "3"})

    @classmethod
    def tearDownClass(cls):
        cls.srv.stop()

    def test_parallel_starts_one_open_attempt_and_parallel_submits_one_graded(self):
        from concurrent.futures import ThreadPoolExecutor

        ip = "203.0.113.21"
        uid, tok = self.srv.guest(ip)
        self.srv.call("/academy/nodes/N02-01/read", {"user_id": uid, "node_id": "N02-01"}, tok, ip)
        with ThreadPoolExecutor(25) as ex:
            starts = list(ex.map(lambda _i: self.srv.call("/academy/kuat/start", {"user_id": uid, "node_id": "N02-01"},
                                                          tok, ip), range(25)))
        self.assertEqual({s for s, _ in starts}, {200})
        self.assertEqual(len({a["attempt_id"] for _, a in starts}), 1)
        self.assertEqual(self.srv.q("SELECT COUNT(*) FROM academy_kuat_attempts WHERE user_id=? AND used_at IS NULL",
                                    (uid,))[0][0], 1)
        att = starts[0][1]
        with ThreadPoolExecutor(25) as ex:
            subs = list(ex.map(lambda _i: self.srv.wrong(uid, tok, "N02-01", att, ip), range(25)))
        self.assertEqual(sorted(s for s, _ in subs), [200] + [409] * 24)
        self.assertEqual(self.srv.fails("kuat_user_node", f"user:{uid}|node:N02-01"), 1)
        self.assertEqual(self.srv.q("SELECT COUNT(*) FROM academy_kuat_attempts WHERE user_id=? AND outcome='failed'",
                                    (uid,))[0][0], 1)

    def test_parallel_submits_of_many_guests_on_one_ip_capped(self):
        from concurrent.futures import ThreadPoolExecutor

        from welora.auth_ratelimit import ip_bucket

        ip = "203.0.113.22"
        atts = []
        for _ in range(14):
            uid, tok = self.srv.guest(ip)
            st, a = self.srv.start(uid, tok, "N02-01", ip)
            self.assertEqual(st, 200)
            atts.append((uid, tok, a))
        with ThreadPoolExecutor(14) as ex:
            subs = list(ex.map(lambda t: self.srv.wrong(t[0], t[1], "N02-01", t[2], ip), atts))
        graded = sum(1 for s, _ in subs if s == 200)
        self.assertLessEqual(graded, 6)
        self.assertGreaterEqual(graded, 1)
        self.assertEqual(graded + sum(1 for s, _ in subs if s == 429), 14)
        self.assertLessEqual(self.srv.fails("kuat_guest_ip", ip_bucket(ip)), 6)
        self.assertEqual(self.srv.fails("kuat_guest_ip", ip_bucket(ip)), graded)

    def test_parallel_submits_of_one_guest_across_nodes_capped_by_device(self):
        from concurrent.futures import ThreadPoolExecutor

        ip = "203.0.113.23"
        uid, tok = self.srv.guest(ip)
        atts = []
        for node in ("N01-01", "N02-01", "N03-01", "N04-01", "N05-01"):
            st, a = self.srv.start(uid, tok, node, ip)
            self.assertEqual(st, 200)
            atts.append((node, a))
        with ThreadPoolExecutor(5) as ex:
            subs = list(ex.map(lambda t: self.srv.wrong(uid, tok, t[0], t[1], ip), atts))
        graded = sum(1 for s, _ in subs if s == 200)
        self.assertLessEqual(graded, 3)  # WELORA_KUAT_GUEST_DEVICE_MAX_FAILS=3 for this server
        self.assertEqual(graded + sum(1 for s, _ in subs if s == 429), 5)
        dev = self.srv.q("SELECT device_id FROM users WHERE user_id=?", (uid,))[0][0]
        self.assertEqual(self.srv.fails("kuat_guest_device", dev), graded)


# =========================================================================== in-process
def _uid() -> str:
    return "u-p0b-" + uuid.uuid4().hex[:10]


class _Env(unittest.TestCase):
    ENV: dict = {}

    def setUp(self):
        self._prev = {k: os.environ.get(k) for k in self.ENV}
        os.environ.update(self.ENV)
        academy.reset_academy_store()
        mastery.reset_mastery_store()
        goals_api.USER_FLAGS.clear()
        self.c = TestClient(create_app())

    def tearDown(self):
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def h(self, uid, ip=None):
        out = bearer(uid)
        if ip:
            out["CF-Connecting-IP"] = ip
        return out

    def start(self, uid, node="N02-01", ip=None):
        return self.c.post("/academy/kuat/start", json={"user_id": uid, "node_id": node}, headers=self.h(uid, ip))

    def submit(self, uid, node, attempt_id, answers, ip=None):
        return self.c.post("/academy/kuat", json={"user_id": uid, "node_id": node, "attempt_id": attempt_id,
                                                  "answers": answers}, headers=self.h(uid, ip))


class TestQuestionBank(unittest.TestCase):
    def test_gate_banks_bigger_and_valid(self):
        for nid in ("N02-01", "N02-02"):
            bank = academy.QUESTIONS[nid]
            self.assertGreaterEqual(len(bank), 12, nid)
            self.assertGreaterEqual(sum(q["hard"] for q in bank), 4, nid)
            self.assertEqual(len({q["prompt"] for q in bank}), len(bank))
            for q in bank:
                self.assertTrue(0 <= q["answer"] < len(q["choices"]), q["id"])
                self.assertEqual(len(set(q["choices"])), len(q["choices"]), q["id"])
                self.assertRegex(q["prompt"] + " ".join(q["choices"]), VI, q["id"])
        ids = [q["id"] for qs in academy.QUESTIONS.values() for q in qs]
        self.assertEqual(len(ids), len(set(ids)))

    def test_pass_rule_threshold_unchanged(self):
        self.assertEqual(academy.KUAT_PASS_THRESHOLD, 0.70)
        v = academy._verdict
        self.assertTrue(v([(True, True), (True, True), (True, False), (True, False), (False, False)])[1])  # 4/5
        self.assertFalse(v([(True, True), (True, True), (True, False), (False, False), (False, False)])[1])  # 3/5
        self.assertFalse(v([(False, True), (True, True), (True, False), (True, False), (True, False)])[1])  # hard wrong
        self.assertFalse(v([(True, True), (True, False), (False, False)])[1])  # 2/3 as before
        self.assertTrue(v([(True, True), (True, False), (True, False)])[1])

    def test_draw_random_subset_and_shuffled_options(self):
        subsets, perms = set(), set()
        for _ in range(40):
            served = academy._draw("N02-02")
            self.assertEqual(len(served), academy.KUAT_DRAW)
            self.assertGreaterEqual(sum(1 for s in served if next(q for q in academy.QUESTIONS["N02-02"]
                                                                  if q["id"] == s["q"])["hard"]), 2)
            subsets.add(tuple(sorted(s["q"] for s in served)))
            perms.update(tuple(s["perm"]) for s in served)
        self.assertGreater(len(subsets), 5)
        self.assertTrue(any(list(p) != sorted(p) for p in perms))
        self.assertEqual(len(academy._draw("N02-03")), 3)  # small banks: all questions, shuffled


class TestGuessingStrategiesMonteCarlo(unittest.TestCase):
    """Round 2 blocking 3: over the real draw / shuffle / grader, length heuristics and random
    guessing pass ≤ 2 % on the gate KUATs (before: N02-02 'longest' passed 100 %)."""

    TRIALS = 4000

    def _rate(self, node, strategy, rng):
        by_id = {q["id"]: q for q in academy.QUESTIONS[node]}
        passed = 0
        for _ in range(self.TRIALS):
            served = academy._draw(node)
            answers = []
            for i, slot in enumerate(served):
                shown = [by_id[slot["q"]]["choices"][j] for j in slot["perm"]]
                order = sorted(range(len(shown)), key=lambda k: (len(shown[k]), rng.random()))
                pick = {"longest": order[-1], "shortest": order[0], "middle": order[len(order) // 2],
                        "random": rng.randrange(len(shown))}[strategy]
                answers.append({"question_id": f"k{i + 1}", "choice": pick})
            passed += academy._grade_served(node, served, answers)[1]
        return passed / self.TRIALS

    def test_strategies_pass_at_most_two_percent(self):
        import random

        rng = random.Random(241)
        for node in ("N02-01", "N02-02"):
            for strategy in ("longest", "shortest", "middle", "random"):
                rate = self._rate(node, strategy, rng)
                self.assertLessEqual(rate, 0.02, (node, strategy, rate))

    def test_answer_length_rank_balanced(self):
        """Deterministic guarantee: the right option is the longest / 2nd / 3rd / shortest in at most 3
        of the 12 questions each → any fixed length-rank strategy gets ≤ 3 of 5 right → never passes."""
        for node in ("N02-01", "N02-02"):
            ranks = []
            for q in academy.QUESTIONS[node]:
                lens = [len(c) for c in q["choices"]]
                self.assertEqual(len(lens), 4, q["id"])
                self.assertEqual(len(set(lens)), 4, q["id"])  # no ties
                ranks.append(sorted(lens, reverse=True).index(lens[q["answer"]]))
            for r in range(4):
                self.assertLessEqual(ranks.count(r), 3, (node, r, ranks))


class TestContentRound2(unittest.TestCase):
    def _lesson(self, name):
        return (ROOT / "content" / name).read_text(encoding="utf-8")

    def test_q01h_inclusive_and_q01i_consistent_with_six_month_personas(self):
        q = {x["id"]: x for x in academy.QUESTIONS["N02-01"]}
        self.assertNotIn("gia đình", q["q01h"]["choices"][q["q01h"]["answer"]])
        self.assertIn("nếu có", q["q01h"]["choices"][q["q01h"]["answer"]])
        self.assertIn("6 tháng", q["q01i"]["choices"][q["q01i"]["answer"]])
        self.assertNotIn("2 rồi 3", json.dumps(q["q01i"], ensure_ascii=False))
        wa = self._lesson("WA-02-01-xay-dung-quy-khan-cap.md")
        self.assertIn("thường khoảng 6 tháng", wa)
        self.assertIn("tối thiểu **3 tháng**", wa)  # gate floor unchanged

    def test_n02_02_questions_grounded_in_lesson(self):
        wa = self._lesson("WA-02-02-nguyen-tac-su-dung-quy-khan-cap.md")
        q = {x["id"]: x for x in academy.QUESTIONS["N02-02"]}
        self.assertNotIn("khẩn cấp ở điểm nào", q["q02k"]["prompt"])  # 'gấp' vs 'khẩn cấp' removed
        for phrase in ("Hai câu hỏi trước khi rút", "bất ngờ", "cần thiết", "xe hỏng nặng", "quỹ mục tiêu riêng",
                       "học phí năm sau", "bắt đáy", "nằm yên", "xây lại đủ 3 tháng", "Điểm sức khỏe tài chính cao"):
            self.assertIn(phrase, wa, phrase)


class TestServerHeldAttempt(_Env):
    def test_grading_uses_served_permutation_and_ignores_client_picks(self):
        served = [{"q": "q02a", "perm": [1, 0, 3, 2]}, {"q": "q02b", "perm": [2, 0, 1, 3]},
                  {"q": "q02c", "perm": [3, 1, 0, 2]}, {"q": "q02d", "perm": [0, 2, 1, 3]},
                  {"q": "q02e", "perm": [1, 2, 3, 0]}]
        right = [{"question_id": f"k{i + 1}", "choice": s["perm"].index(
            next(q for q in academy.QUESTIONS["N02-02"] if q["id"] == s["q"])["answer"])} for i, s in enumerate(served)]
        self.assertEqual(academy._grade_served("N02-02", served, right), (1.0, True))
        canonical = [{"question_id": s["q"], "choice": next(q for q in academy.QUESTIONS["N02-02"]
                                                            if q["id"] == s["q"])["answer"]} for s in served]
        self.assertFalse(academy._grade_served("N02-02", served, canonical)[1])  # bank ids → ignored
        raw_index = [{"question_id": f"k{i + 1}", "choice": next(q for q in academy.QUESTIONS["N02-02"]
                                                                 if q["id"] == s["q"])["answer"]}
                     for i, s in enumerate(served)]
        self.assertFalse(academy._grade_served("N02-02", served, raw_index)[1])  # unshuffled index → wrong

    def test_attempt_single_use_owner_node_and_reused_while_open(self):
        uid, other = _uid(), _uid()
        a = self.start(uid).json()
        self.assertEqual([q["id"] for q in a["questions"]], [f"k{i}" for i in range(1, 6)])
        self.assertFalse(keys(a) & FORBIDDEN)
        ans = solve("N02-01", a["questions"])
        self.assertEqual(self.submit(other, "N02-01", a["attempt_id"], ans).status_code, 409)  # not theirs
        b = self.start(uid).json()  # round 2: the SAME open attempt (another tab / reload)
        self.assertEqual((b["attempt_id"], b["questions"]), (a["attempt_id"], a["questions"]))
        r = self.submit(uid, "N02-01", a["attempt_id"], ans)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["kuat_result"]["passed"])
        r = self.submit(uid, "N02-01", a["attempt_id"], ans)  # single use
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["error_code"], "KUAT_ATTEMPT_INVALID")
        self.assertRegex(r.json()["detail"]["message"], VI)
        self.assertNotEqual(self.start(uid).json()["attempt_id"], a["attempt_id"])  # used → a new one

    def test_attempt_expires(self):
        uid = _uid()
        a = academy.start_attempt(uid, "N02-01")
        later = time.time() + academy_store.attempt_ttl_s() + 1
        self.assertIsNone(academy_store.consume_attempt(a["attempt_id"], uid, "N02-01", now=later))
        self.assertIsNone(academy_store.consume_attempt(a["attempt_id"], uid, "N02-02"))  # other node
        self.assertIsNotNone(academy_store.consume_attempt(a["attempt_id"], uid, "N02-01"))

    def test_old_client_without_attempt_id_uses_lesson_attempt(self):
        uid = _uid()
        n = self.c.get("/academy/nodes/N02-01", params={"user_id": uid}, headers=self.h(uid)).json()
        self.assertTrue(n["kuat"]["attempt_id"])
        self.assertEqual(n["kuat"]["question_count"], 5)
        self.assertEqual(n["kuat"]["threshold"], 0.70)
        r = self.c.post("/academy/kuat", json={"user_id": uid, "node_id": "N02-01",
                                               "answers": solve("N02-01", n["questions"])}, headers=self.h(uid))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["kuat_result"]["passed"])
        r = self.c.post("/academy/kuat", json={"user_id": uid, "node_id": "N02-01",
                                               "answers": [{"question_id": "k1", "choice": 0}]}, headers=self.h(uid))
        self.assertEqual(r.status_code, 409)  # nothing open any more
        self.assertEqual(r.json()["detail"]["error_code"], "KUAT_ATTEMPT_INVALID")

    def test_locked_node_issues_no_attempt(self):
        uid = _uid()
        n = self.c.get("/academy/nodes/N02-02", params={"user_id": uid}, headers=self.h(uid)).json()
        self.assertEqual(n["status"], "locked")
        self.assertEqual(n["questions"], [])
        self.assertNotIn("attempt_id", n["kuat"])
        self.assertEqual(self.start(uid, "N02-02").status_code, 403)


class TestNoPerQuestionCorrectness(_Env):
    def test_every_response_only_pass_fail_and_total(self):
        uid = _uid()
        seen = set()
        a = self.start(uid).json()
        seen |= keys(a)
        r = self.submit(uid, "N02-01", a["attempt_id"], solve("N02-01", a["questions"], correct=False)).json()
        seen |= keys(r)
        self.assertEqual(sorted(r["kuat_result"]), ["node_id", "passed", "principle_keys", "ts"])
        seen |= keys(self.c.get("/academy/tree", params={"user_id": uid}, headers=self.h(uid)).json())
        seen |= keys(self.c.get("/academy/nodes/N02-01", params={"user_id": uid}, headers=self.h(uid)).json())
        self.assertFalse(seen & FORBIDDEN, seen & FORBIDDEN)
        self.assertFalse(keys(academy._PROFILES[uid]) & FORBIDDEN)

    def test_pass_also_pass_fail_only(self):
        uid = _uid()
        a = self.start(uid).json()
        r = self.submit(uid, "N02-01", a["attempt_id"], solve("N02-01", a["questions"])).json()
        self.assertEqual(r["kuat_result"]["passed"], True)
        self.assertEqual(sorted(r["kuat_result"]), ["node_id", "passed", "principle_keys", "ts"])
        self.assertFalse(keys(r) & FORBIDDEN)

    def test_served_questions_carry_no_hard_marker(self):
        uid = _uid()
        a = self.start(uid).json()
        for q in a["questions"]:
            self.assertEqual(sorted(q), ["choices", "id", "prompt"])
        n = self.c.get("/academy/nodes/N02-01", params={"user_id": uid}, headers=self.h(uid)).json()
        for q in n["questions"]:
            self.assertEqual(sorted(q), ["choices", "id", "prompt"])

    def test_in_process_outputs_and_legacy_profiles_sanitised(self):
        uid = _uid()
        out = academy.submit_kuat(uid, "N02-01", [])
        self.assertFalse(keys(out) & FORBIDDEN)
        p = academy._profile(uid)  # an old in-memory profile still carrying per-question details
        p["nodes"]["N02-01"]["last_kuat"] = {"node_id": "N02-01", "score": 0.3, "passed": False, "ts": "x",
                                             "question_count": 5, "answers": [{"id": "q01a", "correct": True}]}
        p["attempts"].append({"node_id": "N02-01", "score": 0.6, "answers": [{"id": "q01a", "correct": False}]})
        self.assertFalse(keys(academy.get_tree(uid)) & FORBIDDEN)
        self.assertFalse(keys(academy._profile(uid)) & FORBIDDEN)


class TestCooldownWindows(_Env):
    ENV = {"WELORA_KUAT_MAX_FAILS": "3", "WELORA_KUAT_COOLDOWN_S": "1800"}

    def _fail(self, uid, ip=None, node="N02-01"):
        a = self.start(uid, node, ip)
        if a.status_code != 200:
            return a
        return self.submit(uid, node, a.json()["attempt_id"], solve(node, a.json()["questions"], correct=False), ip)

    def test_cooldown_lifts_after_window(self):
        uid = _uid()
        for _ in range(3):
            self.assertEqual(self._fail(uid).status_code, 200)
        r = self.start(uid)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.headers["Retry-After"], "1800")
        with self.assertRaises(academy_store.KuatCooldown):
            academy_store.check_kuat_allowed(uid, "N02-01")
        academy_store.check_kuat_allowed(uid, "N02-01", now=time.time() + 1801)  # no raise
        academy_store.check_kuat_allowed(uid, "N01-01")  # other node unaffected

    def test_passing_does_not_count(self):
        uid = _uid()
        for _ in range(4):
            a = self.start(uid).json()
            self.assertTrue(self.submit(uid, "N02-01", a["attempt_id"], solve("N02-01", a["questions"]))
                            .json()["kuat_result"]["passed"])


class TestDailyCap(_Env):
    ENV = {"WELORA_KUAT_MAX_FAILS": "100", "WELORA_KUAT_DAILY_MAX_FAILS": "2"}

    def test_daily_cap(self):
        uid = _uid()
        for _ in range(2):
            a = self.start(uid).json()
            self.submit(uid, "N02-01", a["attempt_id"], solve("N02-01", a["questions"], correct=False))
        r = self.start(uid)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json()["detail"]["reason"], "daily")
        self.assertIn("giờ", r.json()["detail"]["message"])


class TestIpCap(_Env):
    ENV = {"WELORA_KUAT_IP_MAX_FAILS": "4"}

    def test_many_guests_one_ip(self):
        ip = "203.0.113.%d" % (uuid.uuid4().int % 250 + 1)
        for _ in range(2):
            uid = _uid()
            for _ in range(2):
                a = self.start(uid, ip=ip).json()
                self.submit(uid, "N02-01", a["attempt_id"], solve("N02-01", a["questions"], correct=False), ip)
        r = self.start(_uid(), ip=ip)
        self.assertEqual(r.status_code, 429)
        self.assertEqual(r.json()["detail"]["reason"], "ip")
        self.assertEqual(self.start(_uid(), ip="203.0.113.251" if not ip.endswith(".251") else "203.0.113.252")
                         .status_code, 200)


class TestStartLimit(_Env):
    ENV = {"WELORA_KUAT_MAX_STARTS": "3", "WELORA_KUAT_MAX_FAILS": "100", "WELORA_KUAT_DAILY_MAX_FAILS": "100"}

    def test_reopening_the_open_attempt_costs_nothing(self):
        uid = _uid()
        ids = {self.start(uid).json()["attempt_id"] for _ in range(10)}
        ids |= {self.c.get("/academy/nodes/N02-01", params={"user_id": uid}, headers=self.h(uid)).json()
                ["kuat"]["attempt_id"] for _ in range(5)}
        self.assertEqual(len(ids), 1)

    def test_start_limit_and_node_get_still_serves_lesson(self):
        uid = _uid()
        for _ in range(3):  # three NEW attempts (each used up by a failed submit)
            a = self.start(uid)
            self.assertEqual(a.status_code, 200)
            self.submit(uid, "N02-01", a.json()["attempt_id"], solve("N02-01", a.json()["questions"], correct=False))
        self.assertEqual(self.start(uid).status_code, 429)
        n = self.c.get("/academy/nodes/N02-01", params={"user_id": uid}, headers=self.h(uid))
        self.assertEqual(n.status_code, 200)
        self.assertTrue(n.json()["body_markdown"])
        self.assertEqual(n.json()["kuat"]["cooldown"]["reason"], "starts")


class TestMemoryClaimAndHealth(_Env):
    def test_memory_claim_merges_academy_and_mastery(self):
        from welora import guest_claim

        g, a = _uid(), _uid()
        academy.submit_kuat(g, "N02-01", [{"question_id": q["id"], "choice": q["answer"]}
                                          for q in academy.QUESTIONS["N02-01"]])
        academy.submit_kuat(a, "N01-01", [{"question_id": q["id"], "choice": q["answer"]}
                                          for q in academy.QUESTIONS["N01-01"]])
        goals_api.USER_FLAGS[g] = {"has_dangerous_debt": False, "debt_on_track": True, "mastery_no_efund_invest": "apply"}
        goals_api.USER_FLAGS[a] = {"has_dangerous_debt": True, "debt_on_track": False,
                                   "mastery_no_efund_invest": "not_started"}
        moved: dict = {}
        guest_claim._move_memory(g, a, moved, {})
        self.assertEqual(goals_api.USER_FLAGS[a]["mastery_no_efund_invest"], "apply")
        self.assertTrue(goals_api.USER_FLAGS[a]["has_dangerous_debt"])
        t = academy.get_tree(a)
        st = {n["node_id"]: n["status"] for n in t["nodes"]}
        self.assertEqual((st["N01-01"], st["N02-01"], t["xp"]), ("mastered", "mastered", 40))

    def test_health_score_uses_gate_flags(self):
        src = (ROOT / "welora" / "health_score.py").read_text(encoding="utf-8")
        self.assertIn("goals_api.gate_flags(user_id)", src)
        self.assertNotIn("goals_api.get_user_flags(user_id)", src)


class TestFrontendAcademy(unittest.TestCase):
    def test_academy_page_uses_attempts_and_handles_429(self):
        s = (STATIC / "academy.html").read_text(encoding="utf-8")
        self.assertIn("attempt_id:current.attempt_id", s)
        self.assertIn("/academy/kuat/start", s)
        self.assertIn("r.status===429", s)
        self.assertIn("retry_at", s)
        self.assertIn("r.status===409", s)
        self.assertNotRegex(s, r"\.correct\b|\.answers\b|last_kuat\.answers")
        # round 2: pass / fail only — no score / percent on the page, stale tab handled
        self.assertNotRegex(s, r"\.score\b|\*100\)?\s*\+\s*'%'")
        self.assertIn("'CHƯA ĐẠT — ôn lại bài", s)
        self.assertIn("KUAT_RELOAD", s)
        self.assertIn("Hãy chọn đáp án cho mọi câu trước khi nộp.", s)

    @unittest.skipUnless(__import__("shutil").which("node"), "node not installed")
    def test_academy_script_parses(self):
        s = (STATIC / "academy.html").read_text(encoding="utf-8")
        js = max(re.findall(r"<script>(.*?)</script>", s, re.S), key=len)
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(js)
        p = subprocess.run([__import__("shutil").which("node"), "--check", f.name], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)

    def test_api_route_never_calls_in_process_grader(self):
        src = (ROOT / "welora" / "api" / "app.py").read_text(encoding="utf-8")
        self.assertNotRegex(src, r"academy_svc\.submit_kuat\(")
        self.assertIn("academy_svc.service_submit_kuat(", src)
        self.assertIn("submit_kuat_attempt(user_id, node_id", (ROOT / "welora" / "academy.py").read_text(encoding="utf-8"))

    def test_constraints(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(TestClient(create_app()).get("/health").json().get("gate_months"), 3)


if __name__ == "__main__":
    unittest.main()
