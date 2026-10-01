"""GP P0 — mastery chỉ từ server (chặn tự mở Cổng an toàn) + 3 lỗi nhỏ.

* PATCH /users/{id}/mastery is closed for everyone (403 VI, no body accepted); the only writer
  is the Academy KUAT graded on the server (or the startup demo seed / in-process internals).
* user_flags.mastery_source provenance: rows without a trusted source never open the gate.
* goal progress alone (self-reported amounts) can never pass the gate.
* Demo seed: P2 passed, P4 not_passed (SQLite + PG via WELORA_TEST_POSTGRES_URL).
* (a) onboarding result reads the nested goal shape; (b) claim counts DNA moved;
  (c) onboarding validation messages are Vietnamese.
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

from tests._authz import authed, bearer
from tests._db_target import db_env
from welora import goals_api, mastery
from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
NODE = shutil.which("node")
ENGLISH = re.compile(r"\b(must be|is required|requires|not found|unknown|invalid|already completed)\b", re.I)


def run_scenario(name: str, env: dict, timeout: int = 300) -> dict:
    full = {k: v for k, v in os.environ.items() if not k.startswith("WELORA_")}
    full.update({"PYTHONPATH": str(ROOT), "WELORA_DEMO_AUTOSEED": "0", "WELORA_ENV": "staging",
                 "WELORA_GUEST_DEMO": "1"})
    full.update(env)
    p = subprocess.run([sys.executable, "-m", "tests._mastery_dbmode", name], cwd=str(ROOT), env=full,
                       capture_output=True, text=True, timeout=timeout)
    for line in reversed(p.stdout.splitlines()):
        if line.startswith("RESULT="):
            return json.loads(line[len("RESULT="):])
    raise AssertionError(f"scenario {name} failed rc={p.returncode}\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}")


# --------------------------------------------------------------------------- DB (SQLite / PG17)
class TestMasteryServerOnlyDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.out = run_scenario("mastery_server_only", db_env(cls.tmp))

    def test_patch_mastery_refused(self):
        self.assertEqual(self.out["patch"], [403, "MASTERY_SERVER_ONLY"])
        self.assertEqual(self.out["patch_mastered_bad_body"], 403)
        self.assertEqual(self.out["patch_no_token"], 401)
        self.assertEqual(self.out["mastery_after_exploit"], "not_started")
        self.assertIsNone(self.out["row_after_exploit"])

    def test_goal_progress_cannot_pass_gate_without_mastery(self):
        self.assertEqual(self.out["progress"], 200)  # fund reaches 3 months of expenses
        self.assertEqual(self.out["gate_after_exploit"], ["not_passed", ["mastery_missing"]])

    def test_legacy_row_without_source_is_untrusted(self):
        self.assertEqual(self.out["legacy_gate"], ["not_passed", ["mastery_missing"]])
        self.assertEqual(self.out["legacy_mastery"], "not_started")

    def test_academy_kuat_is_the_only_way_and_persists(self):
        o = self.out
        self.assertEqual(o["kuat_locked"], 403)
        self.assertEqual(o["kuat_prereq"], [200, True])
        self.assertEqual(o["gate_after_prereq"], ["not_passed", ["mastery_missing"]])
        self.assertEqual(o["kuat_wrong"], [200, False])
        self.assertEqual(o["gate_after_wrong"], ["not_passed", ["mastery_missing"]])
        self.assertEqual(o["kuat_gate"], [200, True])
        self.assertEqual(o["gate_after_kuat"], ["passed", []])
        self.assertEqual(o["row_after_kuat"][:2], ["apply", "academy"])
        self.assertEqual(o["gate_after_restart"], ["passed", []])
        m = o["mastery_after_restart"]
        self.assertEqual((m["state"], m["meets_gate"], m["read_only"], m["updated_by"]),
                         ("apply", True, True, "academy"))
        self.assertEqual(m["academy_href"], "/app/academy")

    def test_debt_progress_keeps_mastery_and_source(self):
        before, after = self.out["debt_sync_row"]
        self.assertEqual(before[:2], ["apply", "academy"])
        self.assertEqual(after[:2], ["apply", "academy"])


class TestDemoSeedGatesDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.out = run_scenario("demo_seed_gates", db_env(cls.tmp))

    def test_p2_passed_p4_not_passed(self):
        for k in ("first", "fresh"):
            self.assertEqual(self.out[k]["P2"][0], "passed", k)
            self.assertEqual(self.out[k]["P4"][0], "not_passed", k)

    def test_seed_rows_are_sourced_seed(self):
        self.assertEqual(self.out["sources"], ["seed"])
        self.assertEqual(self.out["p2_row"][:2], ["apply", "seed"])
        self.assertEqual(self.out["p4_row"][1], "seed")


class TestClaimCountsDb(unittest.TestCase):
    def test_dna_and_constitution_counted(self):
        out = run_scenario("claim_counts", db_env(tempfile.mkdtemp()))
        self.assertEqual(out["code"], 200)
        self.assertGreaterEqual(out["moved"]["dna_profiles"], 1)
        self.assertGreaterEqual(out["moved"]["constitutions"], 1)
        self.assertEqual(out["dna_status"], 200)


# --------------------------------------------------------------------------- in-process (memory)
class TestMasteryPatchClosedMemory(unittest.TestCase):
    def setUp(self):
        goals_api.USER_FLAGS.clear()
        mastery.reset_mastery_store()
        self.c = TestClient(create_app())

    def test_owner_and_any_body_get_403_vi(self):
        uid = "u-mastery-own"
        for body in ({"state": "apply"}, {"state": "apply", "node_id": "no_efund_invest"},
                     {"state": "not_started"}, {}):
            r = self.c.patch(f"/users/{uid}/mastery", json=body, headers=bearer(uid))
            self.assertEqual(r.status_code, 403, body)
            d = r.json()["detail"]
            self.assertEqual(d["error_code"], "MASTERY_SERVER_ONLY")
            self.assertIn("Welorademy", d["message"])
            self.assertNotRegex(d["message"], ENGLISH)
        self.assertEqual(goals_api.effective_mastery_state(uid), "not_started")

    def test_other_user_and_no_token(self):
        self.assertEqual(self.c.patch("/users/victim/mastery", json={"state": "apply"},
                                      headers=bearer("attacker")).status_code, 403)
        self.assertEqual(self.c.patch("/users/victim/mastery", json={"state": "apply"}).status_code, 401)
        self.assertEqual(goals_api.effective_mastery_state("victim"), "not_started")

    def test_get_is_read_only(self):
        d = self.c.get("/users/u-ro/mastery", headers=bearer("u-ro")).json()
        self.assertEqual((d["state"], d["meets_gate"], d["read_only"]), ("not_started", False, True))

    def test_service_patch_always_refuses(self):
        code, body = mastery.service_patch_mastery("u1", {"state": "apply"})
        self.assertEqual(code, 403)
        self.assertEqual(body["error_code"], "MASTERY_SERVER_ONLY")
        self.assertEqual(goals_api.effective_mastery_state("u1"), "not_started")

    def test_untrusted_source_rejected(self):
        with self.assertRaises(ValueError):
            mastery.record_mastery("u2", "apply", source="user")
        from welora.db import repos

        with self.assertRaises(ValueError):
            repos.set_user_flags_db("u2", has_dangerous_debt=False, mastery_no_efund_invest="apply",
                                    mastery_source="user", url="sqlite:///" + tempfile.mkdtemp() + "/x.db")
        self.assertEqual(goals_api.effective_mastery_state("u2"), "not_started")

    def test_set_user_flags_default_does_not_grant_mastery(self):
        goals_api.set_user_flags("u3", has_dangerous_debt=False)
        self.assertEqual(goals_api.effective_mastery_state("u3"), "not_started")

    def test_progress_only_exploit_memory(self):
        c = authed(TestClient(create_app()))
        uid = "u-exploit-mem"
        g = c.post("/goals", json={"user_id": uid, "type": "emergency_fund",
                                   "essential_expense_monthly": 10_000_000, "current_amount": 0}).json()
        c.patch(f"/goals/{g['goal_id']}/progress", json={"user_id": uid, "set_amount": 30_000_000})
        c.patch(f"/users/{uid}/mastery", json={"state": "apply"})
        gate = c.get(f"/users/{uid}/safety-gate").json()
        self.assertEqual(gate["status"], "not_passed")
        self.assertIn("mastery_missing", gate["reasons"])

    def test_constraints_unchanged(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(self.c.get("/health").json().get("gate_months"), 3)


# --------------------------------------------------------------------------- static audit guard
WRITERS = re.compile(r"\b(record_mastery|set_user_mastery_db|set_user_flags_db|set_user_flags|grant_from_academy)\(")
ALLOWED_WRITER_FILES = {
    "welora/mastery.py",            # record_mastery / grant_from_academy (definition)
    "welora/academy.py",            # _wire_mastery → grant_from_academy (KUAT graded server-side)
    "welora/goals_api.py",          # set_user_flags (internal) + _sync_debt_flags (mastery kept)
    "welora/db/repos.py",           # DB writers (trusted source required)
    "welora/seed_db.py",            # demo seed (source 'seed')
    "welora/partner_demo_seed.py",  # demo seed (source 'seed')
    "welora/fixtures.py",           # in-process test fixtures
}


class TestMasteryWriteAudit(unittest.TestCase):
    def test_only_allowlisted_modules_write_mastery(self):
        found = set()
        for p in (ROOT / "welora").rglob("*.py"):
            if WRITERS.search(p.read_text(encoding="utf-8")):
                found.add(p.relative_to(ROOT).as_posix())
        self.assertEqual(found - ALLOWED_WRITER_FILES, set(),
                         "new mastery writer — make sure it is server-side only and update the audit")

    def test_no_sql_writes_mastery_outside_repos(self):
        pat = re.compile(r"(UPDATE\s+user_flags|INSERT\s+INTO\s+user_flags|INSERT\s+INTO\s+mastery_nodes)", re.I)
        found = {p.relative_to(ROOT).as_posix() for p in (ROOT / "welora").rglob("*.py")
                 if pat.search(p.read_text(encoding="utf-8"))}
        self.assertLessEqual(found, {"welora/db/repos.py", "welora/guest_claim.py"})

    def test_api_route_has_no_body(self):
        src = (ROOT / "welora" / "api" / "app.py").read_text(encoding="utf-8")
        self.assertNotIn("MasteryPatchBody", src)

    def test_frontend_never_patches_mastery(self):
        for p in STATIC.rglob("*"):
            if p.suffix not in (".html", ".js"):
                continue
            s = p.read_text(encoding="utf-8")
            for m in re.finditer(r"/mastery", s):
                window = s[max(0, m.start() - 300): m.end() + 300]
                self.assertNotRegex(window, r"method\s*:\s*['\"]PATCH", f"{p.name} still PATCHes mastery")

    def test_safety_page_read_only(self):
        s = (STATIC / "safety.html").read_text(encoding="utf-8")
        self.assertIn('id="masteryReadOnly"', s)
        self.assertRegex(s, r'id="masteryState"[^>]*\bdisabled\b')
        self.assertIn("/app/academy", s)


# --------------------------------------------------------------------------- (a) result page
def _result_page_script() -> str:
    html = (STATIC / "onboarding-result.html").read_text(encoding="utf-8")
    blocks = re.findall(r"<script>(.*?)</script>", html, re.S)
    return max(blocks, key=len)


SHIM = r"""
const vm=require('vm');
function el(id){return {id,hidden:false,className:'',textContent:'',children:[],style:{},
  appendChild(c){this.children.push(c);return c;}};}
const els={};
const document={getElementById:(id)=>els[id]||(els[id]=el(id)),createElement:(t)=>el(t)};
function texts(n){return [n.textContent].concat(...n.children.map(texts)).filter(Boolean);}
const GOAL=__GOAL__;
const ctx={document,location:{search:''},localStorage:{setItem(){}},console,Number,Math,String,
  URLSearchParams,encodeURIComponent,
  WeloraSession:{token:()=>'' ,resolveUserId:async()=>'u1'},
  WeloraErrors:{fromResponse:async()=>'err'},
  fetch:async(u)=>u.startsWith('/goals')?{ok:true,status:200,json:async()=>({items:[GOAL]})}
                                         :{ok:false,status:404,json:async()=>({})}};
ctx.window=ctx;
vm.createContext(ctx);
vm.runInContext(__SRC__,ctx);
setTimeout(()=>{const b=els.goalBody;const dl=b.children[0]||{children:[]};const bar=b.children[1];
  console.log('RESULT='+JSON.stringify({texts:texts(b),width:bar&&bar.children[0].style.width}));},50);
"""


def _render_goal(goal: dict) -> dict:
    script = SHIM.replace("__GOAL__", json.dumps(goal)).replace("__SRC__", json.dumps(_result_page_script()))
    p = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60)
    for line in p.stdout.splitlines():
        if line.startswith("RESULT="):
            return json.loads(line[7:])
    raise AssertionError(p.stdout + p.stderr)


@unittest.skipUnless(NODE, "node not installed")
class TestResultPageGoalShape(unittest.TestCase):
    def test_nested_api_shape(self):
        out = _render_goal({"target": {"amount": 30_000_000, "months_of_expense": 3},
                            "current": {"amount": 15_000_000, "percent": 50}})
        joined = " | ".join(out["texts"])
        self.assertIn("30.000.000", joined)
        self.assertIn("15.000.000", joined)
        self.assertIn("3 tháng", joined)
        self.assertEqual(out["width"], "50%")

    def test_flat_shape_still_supported(self):
        out = _render_goal({"target_amount": 20_000_000, "current_amount": 5_000_000})
        joined = " | ".join(out["texts"])
        self.assertIn("20.000.000", joined)
        self.assertEqual(out["width"], "25%")

    def test_source_reads_nested_fields(self):
        s = _result_page_script()
        self.assertIn("tgt.amount", s)
        self.assertIn("cur.amount", s)


# --------------------------------------------------------------------------- (b) claim (memory)
class TestClaimCountsMemory(unittest.TestCase):
    def test_memory_claim_counts(self):
        run = run_scenario("claim_counts", {"WELORA_STORE": "memory", "WELORA_DB_URL": "sqlite:///"
                                            + tempfile.mkdtemp() + "/m.db"})
        self.assertEqual(run["code"], 200)
        self.assertGreaterEqual(run["moved"]["dna_profiles"], 1)


# --------------------------------------------------------------------------- (c) onboarding VI
class TestOnboardingMessagesVi(unittest.TestCase):
    def setUp(self):
        self.c = authed(TestClient(create_app()))
        self.uid = "u-ob-vi"
        self.sid = self.c.post("/onboarding/session", json={"user_id": self.uid}).json()["session_id"]

    def _err(self, r):
        d = r.json().get("detail")
        return d if isinstance(d, str) else json.dumps(d, ensure_ascii=False)

    def _step(self, n, body):
        return self.c.patch(f"/onboarding/session/{self.sid}/step/{n}", json=body)

    def test_step2_not_a_number(self):
        r = self._step(2, {"essential_expense_monthly": "abc"})
        self.assertEqual(r.status_code, 400)
        msg = self._err(r)
        self.assertIn("Chi tiêu thiết yếu mỗi tháng phải là một số", msg)
        self.assertNotRegex(msg, ENGLISH)

    def test_step2_non_positive_and_missing(self):
        for body in ({"essential_expense_monthly": 0}, {"essential_expense_monthly": -5}, {}):
            r = self._step(2, body)
            self.assertEqual(r.status_code, 400, body)
            self.assertNotRegex(self._err(r), ENGLISH)
            self.assertIn("Chi tiêu thiết yếu", self._err(r))

    def test_step1_missing_and_bad_enum(self):
        r = self._step(1, {"family_context": "alone", "household": "solo"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Bước 1", self._err(r))
        r = self._step(1, {"income_stability": "weird", "family_context": "alone", "household": "solo"})
        self.assertEqual(r.status_code, 422)
        self.assertNotRegex(self._err(r), ENGLISH)
        r = self._step(1, {"income_stability": "stable", "family_context": "alone", "household": "martian"})
        self.assertIn(r.status_code, (400, 422))
        self.assertNotRegex(self._err(r), ENGLISH)

    def test_step3_risk_and_range(self):
        r = self._step(3, {"risk_tolerance": "x"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("Mức chấp nhận rủi ro", self._err(r))
        r = self._step(9, {})
        self.assertEqual(r.status_code, 400)
        self.assertNotRegex(self._err(r), ENGLISH)

    def test_complete_too_early_and_unknown_session(self):
        r = self.c.post(f"/onboarding/session/{self.sid}/complete")
        self.assertEqual(r.status_code, 400)
        self.assertNotRegex(self._err(r), ENGLISH)
        r = self.c.patch("/onboarding/session/nope/step/1", json={}, headers=bearer(self.uid))
        self.assertIn(r.status_code, (403, 404))
        self.assertNotRegex(self._err(r), ENGLISH)

    def test_service_level_messages_vi(self):
        from welora import onboarding_api as oa

        for code, body in (oa.service_patch_step("nope", 1, {}), oa.service_complete("nope"),
                           oa.service_create_session({})):
            self.assertGreaterEqual(code, 400)
            self.assertNotRegex(json.dumps(body, ensure_ascii=False), ENGLISH)


if __name__ == "__main__":
    unittest.main()
