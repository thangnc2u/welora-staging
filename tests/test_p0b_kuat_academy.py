"""GP P0b — siết KUAT + lưu tiến độ Academy.

1. KUAT: no per-question correctness anywhere; DB-backed attempt limit + cooldown (429 VI + retry
   time); random draw from a bigger bank + shuffled options graded against a server-held,
   single-use, expiring attempt.
2. Academy progress persisted (SQLite + PG17) — survives a fresh process.
3. Health Score reads the same flags as /safety-gate (cold process after restart).
4. Guest claim onto an account with an untrusted flags row carries the guest's real mastery.
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
FORBIDDEN = {"correct", "is_correct", "answer", "answers", "perm", "served", "served_json"}
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
        self.assertEqual(self.r["last_kuat_keys"], ["node_id", "passed", "principle_keys", "question_count",
                                                    "score", "ts"])
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


class TestServerHeldAttempt(_Env):
    def test_grading_uses_served_permutation_and_ignores_client_picks(self):
        served = [{"q": "q02a", "perm": [1, 0]}, {"q": "q02b", "perm": [2, 0, 1]}, {"q": "q02c", "perm": [1, 0]},
                  {"q": "q02d", "perm": [0, 2, 1]}, {"q": "q02e", "perm": [1, 2, 0]}]
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

    def test_attempt_single_use_owner_node_and_superseded(self):
        uid, other = _uid(), _uid()
        a = self.start(uid).json()
        self.assertEqual([q["id"] for q in a["questions"]], [f"k{i}" for i in range(1, 6)])
        self.assertFalse(keys(a) & FORBIDDEN)
        ans = solve("N02-01", a["questions"])
        self.assertEqual(self.submit(other, "N02-01", a["attempt_id"], ans).status_code, 409)  # not theirs
        b = self.start(uid).json()  # supersedes a
        r = self.submit(uid, "N02-01", a["attempt_id"], ans)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["error_code"], "KUAT_ATTEMPT_INVALID")
        self.assertRegex(r.json()["detail"]["message"], VI)
        r = self.submit(uid, "N02-01", b["attempt_id"], solve("N02-01", b["questions"]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["kuat_result"]["passed"])
        self.assertEqual(self.submit(uid, "N02-01", b["attempt_id"], solve("N02-01", b["questions"])).status_code, 409)

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
        r = self.c.post("/academy/kuat", json={"user_id": uid, "node_id": "N02-01", "answers": []}, headers=self.h(uid))
        self.assertEqual(r.status_code, 409)  # nothing open any more

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
        self.assertEqual(sorted(r["kuat_result"]), ["node_id", "passed", "principle_keys", "question_count",
                                                     "score", "ts"])
        seen |= keys(self.c.get("/academy/tree", params={"user_id": uid}, headers=self.h(uid)).json())
        seen |= keys(self.c.get("/academy/nodes/N02-01", params={"user_id": uid}, headers=self.h(uid)).json())
        self.assertFalse(seen & FORBIDDEN, seen & FORBIDDEN)
        self.assertFalse(keys(academy._PROFILES[uid]) & FORBIDDEN)

    def test_in_process_outputs_and_legacy_profiles_sanitised(self):
        uid = _uid()
        out = academy.submit_kuat(uid, "N02-01", [])
        self.assertFalse(keys(out) & FORBIDDEN)
        p = academy._profile(uid)  # an old in-memory profile still carrying per-question details
        p["nodes"]["N02-01"]["last_kuat"] = {"node_id": "N02-01", "score": 0.3, "passed": False, "ts": "x",
                                             "answers": [{"id": "q01a", "correct": True}]}
        p["attempts"].append({"node_id": "N02-01", "answers": [{"id": "q01a", "correct": False}]})
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
    ENV = {"WELORA_KUAT_MAX_STARTS": "3"}

    def test_start_limit_and_node_get_still_serves_lesson(self):
        uid = _uid()
        for _ in range(3):
            self.assertEqual(self.start(uid).status_code, 200)
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
