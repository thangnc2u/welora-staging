"""Ticket "GP — Academy follow-up sau 019 (guest + KUAT polish)".

1. Demo persona progress per login session (WELORA_GUEST_DEMO on): one tester never sees another's
   read lessons / KUAT results / XP / badges; every session starts from the persona's demo seed
   (P2/P3/P6 gate path mastered, P1/P4/P5 empty); the shared gate mastery never moves; the demo
   seed drops the session profiles; regular accounts unchanged.
2. The «ôn lại bài» link of a KUAT notice opens the lesson in the Academy (/app/academy?node=…),
   which follows the Academy guest gate — not /app/content (always login).
3. /app/learn (Academy alias) opens to device guests exactly like /app/academy (server marker only
   while WELORA_GUEST_DEMO is on; production blocks).
4. Non-gate start caps: per account (all accounts) + per network for accounts without a verified
   contact only — verified learners behind one NAT are never blocked as a network; gate limits unchanged.
5. N01-01 / N03-01 / N04-01 banks at the N02 standard (12 × 4, 5 drawn per server-issued
   single-use attempt, no per-question correctness); attempts from the old banks are retired.
6. Academy header: no fixed «KUAT ≥ 70%» — ĐẠT / CHƯA ĐẠT + the real pass rule from the code.
DB scenarios run in subprocesses (tests/_acfu_dbmode.py) on SQLite, or PG17 via WELORA_TEST_POSTGRES_URL.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from fastapi.testclient import TestClient

from tests._db_target import db_env
from tests.test_kuat_demo_019 import TestAuthGateJsBehaviour
from welora import academy, academy_store
from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
VI = re.compile(r"[ạảãáàâầấậẩẫăằắặẳẵđêềếệểễôồốộổỗơờớợởỡưừứựửữìíịỉĩòóọỏõùúụủũỳýỵỷỹ]", re.I)
NUDGE = re.compile(r"(?i)đăng nhập|đăng ký|login|OTP|xác thực|xác minh")
NEW_BANKS = ("N01-01", "N03-01", "N04-01")


def run(name: str, env: dict, state: dict | None = None, timeout: int = 300) -> dict:
    full = {k: v for k, v in os.environ.items() if not k.startswith("WELORA_")}
    full.update({"PYTHONPATH": str(ROOT), "WELORA_DEMO_AUTOSEED": "0", "WELORA_ENV": "staging",
                 "WELORA_GUEST_DEMO": "1", "ACFU_STATE": json.dumps(state or {})})
    full.update(env)
    p = subprocess.run([sys.executable, "-m", "tests._acfu_dbmode", name], cwd=str(ROOT), env=full,
                       capture_output=True, text=True, timeout=timeout)
    for line in reversed(p.stdout.splitlines()):
        if line.startswith("RESULT="):
            return json.loads(line[len("RESULT="):])
    raise AssertionError(f"scenario {name} failed rc={p.returncode}\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}")


SEED_EMPTY = {"N01-01": "available", "N02-01": "available", "N02-02": "locked", "N02-03": "locked"}
SEED_GATE = {"N01-01": "available", "N02-01": "mastered", "N02-02": "mastered", "N02-03": "available"}


def _env(key: str, value: str | None):
    prev = os.environ.get(key)
    if value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = value
    return prev


# =========================================================================== item 1
class TestDemoProgressPerSessionDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = db_env(tempfile.mkdtemp())
        cls.o = run("demo_progress", env)
        st = cls.o["state"]
        cls.read = run("demo_progress_read", env, st)  # fresh process = restart / other instance
        cls.reseed = run("demo_progress_reseed", env, st)
        cls.off = run("demo_progress_flag_off", db_env(tempfile.mkdtemp()))

    def test_sessions_start_from_the_persona_seed(self):
        self.assertEqual(self.o["a0"], {"xp": 0, "status": SEED_EMPTY, "badges": []})  # P4
        self.assertEqual(self.o["b0"], self.o["a0"])
        self.assertEqual(self.o["p0"], {"xp": 40, "status": SEED_GATE, "badges": []})  # P2: gate path mastered
        self.assertEqual(self.o["rows_after_views"], [])  # views never write a session row

    def test_one_tester_never_sees_another_testers_progress(self):
        o = self.o
        self.assertEqual(o["a_pass"], [[200, True], [200, True]])
        self.assertEqual(o["a1"]["xp"], 40)
        self.assertEqual(o["a1"]["status"]["N02-02"], "mastered")
        self.assertEqual(o["a1"]["status"]["N01-01"], "kuat_pending")  # A read the lesson
        self.assertEqual(o["b1"], o["b0"])  # B: still the seed state
        self.assertEqual((o["a_read_node"], o["b_read_node"]), ("kuat_pending", "available"))
        self.assertEqual(o["p_pass_n0203"], [200, True])
        self.assertEqual(o["p1"]["status"]["N02-03"], "mastered")
        self.assertEqual(o["q1"], o["p0"])  # another P2 session: seed state only

    def test_shared_gate_mastery_never_moves(self):
        o = self.o
        # follow-up #244/#245 item 14: session A (passed N02-02) sees ITS gate mastery; session B and
        # the persona's shared flags stay at the seed state
        self.assertEqual(o["p4_mastery_after_a"], ["apply", "learning"])
        self.assertEqual(o["p4_gate_after_a"], "not_passed")
        self.assertEqual(o["flags_source"], {"m": "learning", "s": "seed"})
        self.assertEqual(o["base_p4_profile_xp"], 0)  # the persona's own (seed) profile is untouched

    def test_storage_session_keys_hold_only_a_hash(self):
        o = self.o
        self.assertEqual(len(o["rows"]), 2)  # A (P4) and P (P2) made progress; B / Q only viewed
        for r in o["rows"]:
            uid, scope = r.split("#", 1)
            self.assertIn(uid, (o["uids"]["P4"], o["uids"]["P2"]))
            self.assertRegex(scope, r"^s:[0-9a-f]{32}$")
        self.assertTrue(o["rows_hold_no_token"])
        self.assertEqual(sorted(o["base_rows"]), sorted([o["uids"]["P2"], o["uids"]["P4"]]))

    def test_regular_accounts_unchanged(self):
        self.assertEqual(self.o["regular_other_login"], "mastered")  # 2 logins, 1 profile
        self.assertEqual(self.o["regular_rows"], [])

    def test_persisted_across_processes(self):
        r = self.read
        self.assertEqual(r["a"]["xp"], 40)
        self.assertEqual(r["a"]["status"]["N02-02"], "mastered")
        self.assertEqual(r["b"], {"xp": 0, "status": SEED_EMPTY, "badges": []})
        self.assertEqual(r["p"]["status"]["N02-03"], "mastered")

    def test_demo_seed_resets_every_session(self):
        r = self.reseed
        self.assertEqual(r["rows"], [])
        self.assertEqual(r["a"], {"xp": 0, "status": SEED_EMPTY, "badges": []})
        self.assertEqual(r["p"], {"xp": 40, "status": SEED_GATE, "badges": []})

    def test_guest_demo_off_keeps_one_profile_per_user(self):
        self.assertEqual(self.off["key"], self.off["uid"])


class TestProfileKeyUnit(unittest.TestCase):
    def test_regular_and_flag_off_keys_are_the_user_id(self):
        prev = _env("WELORA_GUEST_DEMO", "1")
        try:
            self.assertEqual(academy.profile_key("u-regular-acfu", session="tok-1", ip="203.0.113.5"), "u-regular-acfu")
            self.assertEqual(academy.profile_key(""), "")
            self.assertEqual(academy.profile_key("x#s:abc", session="t"), "x#s:abc")  # never nested
        finally:
            _env("WELORA_GUEST_DEMO", prev)
        prev = _env("WELORA_GUEST_DEMO", "0")
        try:
            demo = next(iter(academy_store.demo_persona_ids()))
            self.assertEqual(academy.profile_key(demo, session="tok-1"), demo)
        finally:
            _env("WELORA_GUEST_DEMO", prev)

    def test_demo_session_never_writes_gate_mastery(self):
        import inspect

        src = inspect.getsource(academy._apply_result)
        self.assertIn("not is_session_key(key)", src)


# =========================================================================== items 2 + 4 (DB)
class TestNonGateCapsDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.o = run("nongate_caps", {**db_env(tempfile.mkdtemp()), "WELORA_KUAT_NONGATE_IP_MAX_STARTS": "3",
                                     "WELORA_KUAT_NONGATE_USER_MAX_STARTS": "4"})
        cls.demo = run("demo_user_cap", {**db_env(tempfile.mkdtemp()), "WELORA_KUAT_NONGATE_USER_MAX_STARTS": "3"})

    def test_verified_accounts_behind_one_nat_are_never_blocked_as_a_network(self):
        o = self.o
        self.assertEqual(o["verified_starts"], [200] * 5)  # > the network cap of 3
        self.assertEqual(o["verified_net_events"], 0)
        self.assertEqual(o["verified_after_guest_cap"], 200)  # guests filled the network → verified still OK

    def test_network_backstop_for_guests_kept(self):
        o = self.o
        self.assertEqual(o["guest_starts"], [[200, None]] * 3 + [[429, "ip_starts"]])
        self.assertEqual(o["guest_other_network"], 200)
        c = o["guest_cap"]
        self.assertEqual(c["error_code"], "KUAT_COOLDOWN")
        self.assertRegex(c["message"], VI)
        self.assertNotRegex(c["message"], NUDGE)

    def test_per_account_cap(self):
        o = self.o
        self.assertEqual(o["user_seq"], [200, 200, 200, 429])  # 4 new non-gate attempts, the 5th refused
        c = o["user_cap"]
        self.assertEqual((c["error_code"], c["reason"]), ("KUAT_COOLDOWN", "user_starts"))
        self.assertRegex(c["message"], VI)
        self.assertIn("giờ Việt Nam", c["message"])
        self.assertNotRegex(c["message"], NUDGE)
        self.assertEqual(o["user_cap_gate_node"], 200)  # gate nodes: own budgets, never this one
        self.assertEqual(o["user_events_before_after_gate"][0], o["user_events_before_after_gate"][1])

    def test_demo_persona_per_account_cap_is_per_network(self):
        self.assertEqual(self.demo["net_a"], [200, 200, 200, 429])  # two sessions, one network
        self.assertEqual(self.demo["net_b"], 200)

    def test_lesson_link_in_the_429_opens_the_academy(self):
        self.assertEqual(self.o["guest_cap"]["lesson_href"], "/app/academy?node=N03-01")
        self.assertEqual(self.o["user_cap"]["lesson_href"], "/app/academy?node=N01-01")


class TestStartBucketsUnit(unittest.TestCase):
    def test_defaults_and_gate_limits_unchanged(self):
        saved = {k: os.environ.pop(k, None) for k in list(os.environ) if k.startswith("WELORA_KUAT_")}
        try:
            self.assertEqual(academy_store.nongate_user_max_starts(), 120)
            self.assertEqual(academy_store.nongate_ip_max_starts(), 300)
            self.assertEqual(academy_store.nongate_ip_start_window_s(), 3600)
            # #242 / #243 gate budgets: unchanged defaults
            self.assertEqual((academy_store.max_fails(), academy_store.daily_max_fails(), academy_store.ip_max_fails(),
                              academy_store.ip_day_max_fails(), academy_store.guest_ip_max_fails(),
                              academy_store.guest_device_max_fails(), academy_store.max_starts()),
                             (3, 10, 30, 60, 6, 6, 30))
            self.assertEqual(academy_store.GATE_KUAT_NODES, ("N02-01", "N02-02"))
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v

    def test_bucket_composition_per_identity(self):
        from unittest import mock

        ip = "203.0.113.77"
        for kind, scopes in ((academy_store.VERIFIED, ["kuat_start", "kuat_nongate_user_start"]),
                             (academy_store.GUEST, ["kuat_start", "kuat_nongate_user_start", "kuat_nongate_ip_start"]),
                             (academy_store.UNVERIFIED, ["kuat_start", "kuat_nongate_user_start", "kuat_nongate_ip_start"]),
                             (academy_store.DEMO, ["kuat_start", "kuat_nongate_user_start", "kuat_nongate_ip_start"])):
            with mock.patch.object(academy_store, "_identity", return_value=(kind, None)):
                got = [b[0] for b in academy_store._start_buckets(None, "u-x", "N03-01", ip)]
                gate = [b[0] for b in academy_store._start_buckets(None, "u-x", "N02-01", ip)]
            self.assertEqual(got, scopes, kind)
            self.assertEqual(gate, ["kuat_start"], kind)  # gate nodes: only their (unchanged) per-user start limit

    def test_user_starts_copy(self):
        d = academy.cooldown_payload(academy_store.KuatCooldown(3600, "user_starts"), "N04-01")
        self.assertRegex(d["message"], VI)
        self.assertNotRegex(d["message"], NUDGE)
        self.assertIn("«Hiểu bền vững tài chính»", d["message"])
        self.assertEqual(d["lesson_href"], "/app/academy?node=N04-01")


# =========================================================================== item 2
class TestLessonLink(unittest.TestCase):
    def test_every_node_links_into_the_academy(self):
        for n in academy.NODES:
            d = academy.cooldown_payload(academy_store.KuatCooldown(60, "fails"), n["node_id"])
            self.assertEqual(d["lesson_href"], "/app/academy?node=" + n["node_id"])
            self.assertNotIn("/app/content", json.dumps(d))

    def test_link_page_follows_the_academy_guest_gate(self):
        for flag, meta in (("1", True), ("0", False)):
            prev = _env("WELORA_GUEST_DEMO", flag)
            try:
                r = TestClient(create_app()).get("/app/academy?node=N02-01")
            finally:
                _env("WELORA_GUEST_DEMO", prev)
            self.assertEqual(r.status_code, 200)
            self.assertEqual('name="welora-guest-academy"' in r.text, meta, flag)

    def test_academy_page_opens_the_deep_linked_lesson(self):
        html = (STATIC / "academy.html").read_text(encoding="utf-8")
        self.assertIn("params.get('node')", html)
        self.assertIn("/^N0[1-5]-0[1-9]$/", html)  # only a node id, nothing else from the query
        self.assertIn("if(hit&&hit.status!=='locked') await openNode(deepNode);", html)
        self.assertIn("scrollIntoView({behavior:'smooth',block:'start'})", html)  # same lesson → no reload
        self.assertIn("href.indexOf('/app/')===0", html)  # same-origin app links only

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_deep_link_node_regex(self):
        html = (STATIC / "academy.html").read_text(encoding="utf-8")
        line = next(x for x in html.splitlines() if x.startswith("const deepNode="))
        js = ("const params={get:()=>process.argv[1]};" + line + "console.log(JSON.stringify(deepNode));")
        for raw, want in (("N02-01", "N02-01"), ("n03-01", "N03-01"), ("N02-01x", ""), ("../x", ""),
                          ("javascript:alert(1)", ""), ("N09-01", ""), ("", "")):
            p = subprocess.run([shutil.which("node"), "-e", js, raw], capture_output=True, text=True, timeout=30)
            self.assertEqual(json.loads(p.stdout.strip()), want, raw)


# =========================================================================== item 3
class TestLearnAlias(unittest.TestCase):
    def _get(self, flag, path):
        prev = _env("WELORA_GUEST_DEMO", flag)
        try:
            return TestClient(create_app()).get(path)
        finally:
            _env("WELORA_GUEST_DEMO", prev)

    def test_server_marks_learn_like_academy(self):
        for path in ("/app/learn", "/app/learn/"):
            on, off = self._get("1", path), self._get("0", path)
            self.assertEqual((on.status_code, off.status_code), (200, 200), path)
            self.assertEqual(on.text.count('<meta name="welora-guest-academy" content="1"/>'), 1)
            self.assertLess(on.text.index('name="welora-guest-academy"'), on.text.index("/static/auth-gate.js"))
            self.assertNotIn("welora-guest-academy", off.text)  # production: no marker → login required
            self.assertEqual(on.headers.get("cache-control"), "no-store")

    def test_static_scripts_know_the_alias_and_stay_marker_gated(self):
        for f in ("auth-gate.js", "shell.js", "session.js"):
            s = (STATIC / f).read_text(encoding="utf-8")
            self.assertIn('"/app/learn"', s, f)
            self.assertNotIn('"/app/learn": 1', s, f)  # never unconditionally allowlisted
            self.assertIn('meta[name="welora-guest-academy"]', s, f)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TestLearnAliasJs(unittest.TestCase):
    _run = TestAuthGateJsBehaviour._run
    HARNESS = TestAuthGateJsBehaviour.HARNESS

    def test_auth_gate_and_shell(self):
        for f in ("auth-gate.js", "shell.js"):
            for path in ("/app/learn", "/app/learn/"):
                self.assertIsNone(self._run(f, path, "1"), (f, path))  # guest demo on → open
                self.assertEqual(self._run(f, path, "0"), "/app/login", (f, path))  # production
                self.assertIsNone(self._run(f, path, "0", "tok"), (f, path))  # logged in
            self.assertEqual(self._run(f, "/app/learning", "1"), "/app/login")  # exact alias only
            # follow-up #244/#245 item 12: Welorapedia follows the same marker rule now
            self.assertIsNone(self._run(f, "/app/content", "1"))
            self.assertEqual(self._run(f, "/app/content", "0"), "/app/login")


class TestGuestDemoOffBlocksGuestsOnLearn(unittest.TestCase):
    def test_device_guest_academy_api_refused_when_off(self):
        prev = _env("WELORA_GUEST_DEMO", "0")
        try:
            c = TestClient(create_app())
            g = c.post("/auth/device", json={"device_id": "web-acfu-off-1"}).json()
            r = c.get("/academy/tree", params={"user_id": g["user_id"]}, headers={"Authorization": "Bearer " + g["token"]})
            self.assertEqual(r.status_code, 403)
            self.assertEqual(r.json()["detail"]["error_code"], "ACADEMY_LOGIN_REQUIRED")
        finally:
            _env("WELORA_GUEST_DEMO", prev)


# =========================================================================== item 5
def _openings(text: str) -> set[str]:
    words = [w for w in (re.sub(r"[^\w]", "", x.lower()) for x in text.split()) if w]
    return {words[0], " ".join(words[:2])} if words else set()


GROUNDING = {
    "N01-01": ["hệ thống niềm tin và thái độ", "mạnh hơn cả kiến thức kỹ thuật", "công cụ phục vụ mục tiêu sống",
               "luôn thấy không đủ, sợ mất tiền", "thực tế và có chủ đích", "đối chiếu với hành vi tháng này",
               "agent không quyết thay", "quỹ 3 tháng", "hình thành qua nhiều năm", "40 triệu ₫/tháng",
               "thiếu minh bạch", "phán xét và phản tác dụng"],
    "N03-01": ["khả năng lựa chọn", "đủ để trang trải mức sống mong muốn", "liên tục chèo", "cánh buồm hoặc động cơ",
               "khoảng cách", "có quỹ khẩn cấp, không còn nợ lãi suất cao", "đi từng mức một",
               "đi ngược lại mục tiêu", "không phải đích đến một lần rồi xong", "khác nhau giữa các gia đình",
               "25 triệu", "độc lập một phần"],
    "N04-01": ["qua nhiều giai đoạn cuộc sống", "khả năng chịu đựng và thích ứng lâu dài", "bảo vệ", "duy trì",
               "chuyển giao", "hàng rào và hệ thống tưới cơ bản", "sống được qua nhiều mùa",
               "bền vững không đòi hỏi phải giàu", "bảo hiểm y tế", "dạy con những thói quen tiền bạc cơ bản",
               "chuyên gia có chuyên môn", "ốm đau, tai nạn, mất thu nhập"],
}


class TestNewBanksStandard(unittest.TestCase):
    def test_shape_like_n02(self):
        ids = [q["id"] for qs in academy.QUESTIONS.values() for q in qs]
        self.assertEqual(len(ids), len(set(ids)))
        for nid in NEW_BANKS:
            bank = academy.QUESTIONS[nid]
            self.assertEqual(len(bank), 12, nid)
            self.assertEqual(sum(q["hard"] for q in bank), 6, nid)
            self.assertEqual(len({q["prompt"] for q in bank}), 12, nid)
            for q in bank:
                self.assertEqual(len(q["choices"]), 4, q["id"])
                self.assertEqual(len(set(q["choices"])), 4, q["id"])
                self.assertTrue(0 <= q["answer"] < 4, q["id"])
                self.assertRegex(q["prompt"] + " ".join(q["choices"]), VI, q["id"])
                for c in q["choices"]:
                    self.assertNotRegex(c, r"(?i)^không,\s*trừ khi|chắc lời|cam kết lãi", q["id"])
            info = academy.kuat_info(nid)
            self.assertEqual((info["question_count"], info["bank_size"]), (5, 12))
        for q in academy.QUESTIONS["N01-01"] + academy.QUESTIONS["N03-01"] + academy.QUESTIONS["N04-01"]:
            self.assertFalse(q["id"] in {"q101a", "q301a", "q401a"})

    def test_answer_length_rank_balanced(self):
        for nid in NEW_BANKS:
            ranks = []
            for q in academy.QUESTIONS[nid]:
                lens = [len(c) for c in q["choices"]]
                self.assertEqual(len(set(lens)), 4, q["id"])  # no ties
                ranks.append(sorted(lens, reverse=True).index(lens[q["answer"]]))
            self.assertEqual([ranks.count(r) for r in range(4)], [3, 3, 3, 3], nid)

    def test_no_opening_marks_the_answer(self):
        for nid in NEW_BANKS:
            right = Counter(sorted(_openings(q["choices"][q["answer"]]), key=len)[0] for q in academy.QUESTIONS[nid])
            self.assertLessEqual(max(right.values()), 1, (nid, right.most_common(3)))

    def test_answers_grounded_in_the_served_lesson(self):
        for nid in NEW_BANKS:
            n = academy._NODE_BY_ID[nid]
            body = academy._lesson_body_markdown(n["lesson_id"], n["principle_key"]).replace("**", "").lower()
            self.assertGreater(len(body), 1500, nid)
            for phrase in GROUNDING[nid]:
                self.assertIn(phrase, body, (nid, phrase))

    def test_draw_five_with_two_core_shuffled(self):
        for nid in NEW_BANKS:
            by_id = {q["id"]: q for q in academy.QUESTIONS[nid]}
            subsets = set()
            for _ in range(30):
                served = academy._draw(nid)
                self.assertEqual(len(served), 5)
                self.assertGreaterEqual(sum(by_id[s["q"]]["hard"] for s in served), 2)
                self.assertTrue(academy.served_valid(nid, served))
                subsets.add(tuple(sorted(s["q"] for s in served)))
                pub = academy._served_public(nid, served)
                self.assertEqual(sorted({k for q in pub for k in q}), ["choices", "id", "prompt"])
            self.assertGreater(len(subsets), 5)

    def test_served_valid_rejects_old_bank_attempts(self):
        self.assertFalse(academy.served_valid("N01-01", [{"q": "q101a", "perm": [0, 1, 2]}]))
        self.assertFalse(academy.served_valid("N01-01", [{"q": "q101-01", "perm": [0, 1, 2]}]))  # 3 options
        self.assertFalse(academy.served_valid("N01-01", []))
        self.assertTrue(academy.served_valid("N01-01", [{"q": "q101-01", "perm": [3, 1, 0, 2]}]))


class TestNewBanksMonteCarlo(unittest.TestCase):
    """Like the N02 banks (P0b r2/r3): length heuristics, random guessing and opening-word
    strategies pass ≤ 2 % over the real draw / shuffle / grader."""

    TRIALS = 3000

    def _rate(self, node, choose, rng):
        by_id = {q["id"]: q for q in academy.QUESTIONS[node]}
        passed = 0
        for _ in range(self.TRIALS):
            served = academy._draw(node)
            answers = []
            for i, slot in enumerate(served):
                shown = [by_id[slot["q"]]["choices"][j] for j in slot["perm"]]
                answers.append({"question_id": f"k{i + 1}", "choice": choose(shown, rng)})
            passed += academy._grade_served(node, served, answers)[1]
        return passed / self.TRIALS

    def test_length_and_random_strategies(self):
        def by_len(pos):
            def f(shown, rng):
                order = sorted(range(len(shown)), key=lambda k: (len(shown[k]), rng.random()))
                return {"longest": order[-1], "shortest": order[0], "middle": order[len(order) // 2],
                        "random": rng.randrange(len(shown))}[pos]
            return f

        rng = random.Random(2019)
        for node in NEW_BANKS:
            for s in ("longest", "shortest", "middle", "random"):
                rate = self._rate(node, by_len(s), rng)
                self.assertLessEqual(rate, 0.02, (node, s, rate))

    def test_opening_strategies(self):
        rng = random.Random(20191)

        def pick(p):
            return lambda shown, r: r.choice([i for i, x in enumerate(shown) if p in _openings(x)] or list(range(4)))

        def avoid(ps):
            return lambda shown, r: r.choice([i for i, x in enumerate(shown) if not (_openings(x) & ps)] or list(range(4)))

        for node in NEW_BANKS:
            total, wrong = Counter(), Counter()
            for q in academy.QUESTIONS[node]:
                for i, c in enumerate(q["choices"]):
                    for p in _openings(c):
                        total[p] += 1
                        wrong[p] += i != q["answer"]
            repeated = [p for p, n in total.items() if n >= 2]
            never_right = {p for p in repeated if wrong[p] == total[p]}
            strategies = [(f"pick {p}", pick(p)) for p in repeated] + [(f"avoid {p}", avoid({p})) for p in repeated]
            strategies.append(("avoid never-right", avoid(never_right)))
            for name, fn in strategies:
                rate = self._rate(node, fn, rng)
                self.assertLessEqual(rate, 0.02, (node, name, rate))


class TestNewBanksDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = run("new_banks_http", db_env(tempfile.mkdtemp()))
        cls.stale = run("stale_bank_attempt", db_env(tempfile.mkdtemp()))

    def test_http_attempts_pass_fail_only(self):
        for node in NEW_BANKS:
            o = self.http[node]
            self.assertEqual((o["count"], o["choices"], o["bank_size"], o["question_count"]), (5, [4], 12, 5), node)
            self.assertEqual(o["keys"], ["choices", "id", "prompt"], node)  # no answer / hard / correctness
            self.assertEqual(o["fail"], [200, False], node)
            self.assertEqual(o["fail_result_keys"], ["node_id", "passed", "principle_keys", "ts"], node)
            self.assertEqual(o["pass"], [200, True], node)

    def test_attempts_from_the_old_bank_are_retired(self):
        s = self.stale["start"]
        self.assertEqual(s, {"status": 200, "new_attempt": True, "five_current": True, "old_outcome": "expired", "open": 1})
        u = self.stale["submit"]
        self.assertEqual((u["status"], u["code"], u["fails"], u["old_outcome"]), (409, "KUAT_ATTEMPT_INVALID", 0, "expired"))


# =========================================================================== item 6
class TestHeaderCopy(unittest.TestCase):
    def test_header_matches_the_pass_rule_in_code(self):
        html = (STATIC / "academy.html").read_text(encoding="utf-8")
        self.assertNotIn("KUAT ≥ 70%", html)
        self.assertNotRegex(html, r"KUAT\s*[≥>]=?\s*\d")
        m = re.search(r'<p class="muted" id="kuatRule">([^<]+)</p>', html)
        self.assertTrue(m)
        copy = m.group(1)
        self.assertIn("ĐẠT / CHƯA ĐẠT", copy)
        self.assertIn(academy.PASS_RULE_VI, copy)  # the same sentence the server returns
        self.assertIn(f"{round(academy.KUAT_PASS_THRESHOLD * 100)}%", academy.PASS_RULE_VI)
        self.assertIn("pass_rule", html)  # the page refreshes it from /academy/tree

    def test_rule_text_matches_the_grader(self):
        v = academy._verdict
        self.assertEqual(academy.KUAT_PASS_THRESHOLD, 0.70)
        self.assertTrue(v([(True, True), (True, True), (True, False), (True, False), (False, False)])[1])  # 4/5
        self.assertFalse(v([(True, True), (True, True), (True, False), (False, False), (False, False)])[1])  # 3/5
        self.assertFalse(v([(False, True), (True, True), (True, False), (True, False), (True, False)])[1])  # core wrong

    def test_tree_returns_the_rule(self):
        prev = _env("WELORA_GUEST_DEMO", "1")
        try:
            c = TestClient(create_app())
            g = c.post("/auth/device", json={"device_id": "web-acfu-rule-1"}).json()
            t = c.get("/academy/tree", params={"user_id": g["user_id"]},
                      headers={"Authorization": "Bearer " + g["token"]}).json()
        finally:
            _env("WELORA_GUEST_DEMO", prev)
        self.assertEqual(t["pass_rule"], academy.PASS_RULE_VI)
        self.assertEqual(t["threshold"], 0.70)


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
        h = TestClient(create_app()).get("/health").json()
        self.assertEqual((h.get("hard_deny"), h.get("gate_months")), (True, 3))

    def test_no_test_flags_in_render_yaml(self):
        y = (ROOT / "render.yaml").read_text(encoding="utf-8")
        for key in ("WELORA_OTP_ECHO", "WELORA_RESET_ECHO", "WELORA_OTP_FIXED"):
            self.assertNotRegex(y, rf"key: {key}\s*\n\s*value:", key)
        self.assertNotRegex(y, r"key: WELORA_RL_\w+\s*\n\s*value:\s*['\"]?-?0")

    def test_no_new_migration_file(self):
        names = sorted(p.name for p in (ROOT / "welora" / "db" / "migrations").glob("*.sql"))
        self.assertEqual(names[-1], "018_kuat_one_open_attempt.sql")
        pg = sorted(p.name for p in (ROOT / "welora" / "db" / "migrations" / "postgres").glob("*.sql"))
        # this ticket added none (later tickets may: 021_verify_snooze = follow-up #244/#245 item 2)
        self.assertFalse([n for n in pg if n[:3] > "020" and ("academy" in n or "kuat" in n)])


if __name__ == "__main__":
    unittest.main()
