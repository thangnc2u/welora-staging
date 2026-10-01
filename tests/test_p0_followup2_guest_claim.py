"""P0 follow-up 2 — item 1 (guest result page + guest → account claim) and item 2 (onboarding
errors rendered as Vietnamese text, never "[object Object]").

DB claim scenarios run in a fresh interpreter (tests/_followup2_dbmode.py) on SQLite, or PG when
WELORA_TEST_POSTGRES_URL is set; the memory-store variant runs too. Static JS is executed under node.
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
from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
NODE = shutil.which("node")


def run2(name: str, env: dict, timeout: int = 300) -> dict:
    full = {k: v for k, v in os.environ.items() if not k.startswith("WELORA_")}
    full.update({"PYTHONPATH": str(ROOT), "WELORA_DEMO_AUTOSEED": "0", "WELORA_ENV": "staging"})
    full.update(env)
    p = subprocess.run([sys.executable, "-m", "tests._followup2_dbmode", name], cwd=str(ROOT), env=full,
                       capture_output=True, text=True, timeout=timeout)
    for line in reversed(p.stdout.splitlines()):
        if line.startswith("RESULT="):
            return json.loads(line[len("RESULT="):])
    raise AssertionError(f"scenario {name} failed rc={p.returncode}\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}")


def node(script: str) -> dict:
    p = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=60, cwd=str(STATIC))
    for line in p.stdout.splitlines():
        if line.startswith("RESULT="):
            return json.loads(line[7:])
    raise AssertionError(p.stdout + p.stderr)


class TestGuestClaimDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.out = run2("guest_claim", {"WELORA_GUEST_DEMO": "1", **db_env(cls.tmp)})

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_result_page_served_and_gate_exempt(self):
        self.assertEqual(self.out["page"], [200, True, True])

    def test_register_then_claim_moves_onboarding_and_goal(self):
        o = self.out
        self.assertEqual(o["x_before"], [])
        self.assertEqual(o["claim1"], [200, False, 1, 1, []])
        self.assertEqual(o["x_after"], [12_000_000])
        self.assertEqual(o["x_dna"], [200, True, 12_000_000])  # DNA JSON re-keyed to the account
        self.assertEqual((o["x_gate"], o["x_constitution"]), (200, 200))

    def test_idempotent_and_guest_session_closed(self):
        self.assertEqual(self.out["claim_again"], [200, True])
        self.assertEqual(self.out["x_after_again"], [12_000_000])
        self.assertEqual(self.out["guest_token_after"], 401)  # guest device tokens revoked

    def test_no_one_else_can_claim(self):
        self.assertEqual(self.out["other_account"], [409, "GUEST_ALREADY_CLAIMED", []])
        self.assertEqual(self.out["no_auth"], 401)
        self.assertEqual(self.out["password_token_as_guest"], [403, "INVALID_GUEST_TOKEN"])
        self.assertEqual(self.out["random_guest_token"], 403)
        self.assertEqual(self.out["guest_as_account"], [400, "CLAIM_SELF"])
        self.assertEqual(self.out["demo_target"], [403, "CLAIM_TARGET_NOT_ALLOWED"])
        self.assertEqual(self.out["g_still_own"], [12_000_000])  # refused claims change nothing

    def test_conflict_policy_account_data_wins(self):
        code, skipped, moved_goals = self.out["conflict"]
        self.assertEqual(code, 200)
        self.assertEqual(skipped, [["goal:emergency_fund", "account_has_goal"], ["onboarding", "account_has_onboarding"]])
        self.assertEqual(moved_goals, 0)
        self.assertEqual(self.out["x_after_conflict"], [12_000_000])
        self.assertEqual(self.out["b_goal_owner"], [True])  # skipped data stays on the claimed guest
        self.assertEqual(self.out["b_sessions_kept"], 1)
        self.assertEqual(self.out["claimed_rows"], [[True, True, True], [True, True, True]])

    def test_login_existing_account_claims(self):
        self.assertEqual(self.out["login_claim"], [200, 1, [12_000_000]])

    def test_concurrent_claims_single_winner(self):
        self.assertEqual(self.out["race"], ["('ok', False)", "(409, 'GUEST_ALREADY_CLAIMED')"])
        self.assertEqual(self.out["race_goals"], [0, 1])


class TestGuestClaimMemory(unittest.TestCase):
    def test_memory_store(self):
        tmp = tempfile.mkdtemp()
        try:
            out = run2("guest_claim_memory", {"WELORA_DB_URL": f"{tmp}/m.db"})
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(out["store"], "InMemoryEmergencyFundStore")
        self.assertEqual(out["claim"], [200, False])
        self.assertEqual(out["x_goals"], [12_000_000])
        self.assertEqual(out["x_dna"], 200)
        self.assertTrue(out["dna_cache_owner"])
        self.assertTrue(out["guest_cache_gone"])


class TestGuestResultFrontend(unittest.TestCase):
    def test_gates_allow_result_page(self):
        for f, var in (("auth-gate.js", "allow"), ("shell.js", "_authAllow"), ("session.js", "GUEST_OK")):
            src = (STATIC / f).read_text(encoding="utf-8")
            block = re.search(var + r"\s*=\s*\{([^}]*)\}", src).group(1)
            self.assertIn('"/app/onboarding/result"', block, f)

    @unittest.skipUnless(NODE, "node not installed")
    def test_auth_gate_executed_for_result_page(self):
        js = r"""
const fs=require('fs'),vm=require('vm');const src=fs.readFileSync('auth-gate.js','utf8');const out={};
for(const p of ['/app/onboarding/result','/app/onboarding/result/','/app/safety']){
  let redirect=null;const store={};
  const ctx={location:{pathname:p,replace:(u)=>{redirect=u;}},localStorage:{getItem:k=>store[k]||null,removeItem:k=>{delete store[k];},setItem:(k,v)=>{store[k]=v;}}};
  vm.runInNewContext(src,ctx);out[p]=redirect;}
console.log('RESULT='+JSON.stringify(out));"""
        out = node(js)
        self.assertEqual(out, {"/app/onboarding/result": None, "/app/onboarding/result/": None, "/app/safety": "/app/login"})

    def test_result_page_content(self):
        html = TestClient(create_app()).get("/app/onboarding/result").text
        self.assertIn('<script src="/static/auth-gate.js"></script>', html)
        self.assertLess(html.index("/static/session.js"), html.index("WeloraSession.resolveUserId"))
        self.assertIn("/users/'+encodeURIComponent(uid)+'/dna", html)
        self.assertIn("/goals?type=emergency_fund", html)
        self.assertIn('href="/app/register"', html)
        self.assertIn('href="/app/login"', html)
        self.assertIn("welora_guest_claim", html)
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("localStorage.setItem('welora_token'", html)

    def test_onboarding_sends_guest_to_result_not_login(self):
        html = (STATIC / "onboarding.html").read_text(encoding="utf-8")
        self.assertIn("location.href='/app/onboarding/result'", html)
        self.assertLess(html.index("if(isGuest())"), html.index("location.href='/app/safety?user_id='"))
        self.assertIn("localStorage.setItem('welora_guest_claim','1')", html)

    def test_auth_pages_run_claim(self):
        for f in ("login.html", "register.html", "otp.html"):
            html = (STATIC / f).read_text(encoding="utf-8")
            self.assertIn('<script src="/static/guest-claim.js"></script>', html, f)
            self.assertIn("WeloraGuestClaim.run(tok)", html, f)
        self.assertNotIn("/static/session.js", (STATIC / "login.html").read_text(encoding="utf-8"))

    @unittest.skipUnless(NODE, "node not installed")
    def test_guest_claim_js_flow(self):
        js = r"""
const fs=require('fs'),vm=require('vm');const src=fs.readFileSync('guest-claim.js','utf8');
async function run(store, claimStatus, deviceCreated){
  const calls=[];
  const ctx={window:{},setTimeout,Promise,JSON,localStorage:{getItem:k=>store[k]===undefined?null:store[k],setItem:(k,v)=>{store[k]=v;},removeItem:k=>{delete store[k];}}};
  ctx.window.localStorage=ctx.localStorage;
  ctx.fetch=async(url,init)=>{calls.push([url,(init.headers||{}).Authorization||'',init.body||'']);
    if(url==='/auth/device') return {ok:true,status:200,json:async()=>({token:'GUESTTOK',created:!!deviceCreated})};
    return {ok:claimStatus===200,status:claimStatus,json:async()=>({ok:claimStatus===200,already:false,moved:{goals:1},skipped:{}})};};
  vm.runInNewContext(src+';this.G=window.WeloraGuestClaim;',ctx);
  const res=await ctx.G.run('ACCTOK');
  return {calls, marker:store.welora_guest_claim||null, res:res&&res.status, summary:ctx.G.summary(res)};
}
(async()=>{
  const out={};
  out.ok=await run({welora_guest_claim:'1',welora_device_id:'web-abc'},200);
  out.rate=await run({welora_guest_claim:'1',welora_device_id:'web-abc'},429);
  out.taken=await run({welora_guest_claim:'1',welora_device_id:'web-abc'},409);
  out.none=await run({welora_device_id:'web-abc'},200);
  out.fresh=await run({welora_guest_claim:'1',welora_device_id:'web-new'},200,true);
  console.log('RESULT='+JSON.stringify(out));
})();"""
        out = node(js)
        ok = out["ok"]
        self.assertEqual([c[0] for c in ok["calls"]], ["/auth/device", "/auth/guest/claim"])
        self.assertEqual(ok["calls"][1][1], "Bearer ACCTOK")
        self.assertEqual(json.loads(ok["calls"][1][2]), {"guest_token": "GUESTTOK"})
        self.assertEqual(json.loads(ok["calls"][0][2]), {"device_id": "web-abc"})
        self.assertIsNone(ok["marker"])
        self.assertEqual(ok["summary"], "Đã lưu kết quả onboarding vào tài khoản.")
        self.assertEqual(out["rate"]["marker"], "1")  # retried at the next login
        self.assertIsNone(out["taken"]["marker"])
        self.assertEqual(out["none"]["calls"], [])  # no marker → nothing happens
        self.assertEqual([c[0] for c in out["fresh"]["calls"]], ["/auth/device"])  # nothing to claim
        self.assertIsNone(out["fresh"]["marker"])


class TestOnboardingErrorsVietnamese(unittest.TestCase):
    def test_no_raw_detail_rendering(self):
        html = (STATIC / "onboarding.html").read_text(encoding="utf-8")
        self.assertNotIn("msg=body.detail||body.error||body.message", html)
        self.assertIn('<script src="/static/api-errors.js"></script>', html)
        self.assertIn("WeloraErrors.message", html)
        for n in range(6):
            self.assertIn(f'id="err{n}"', html)
        for n in range(1, 5):
            self.assertIn(f"stepOk(r{n},'err{n}')", html)

    @unittest.skipUnless(NODE, "node not installed")
    def test_api_errors_js_messages(self):
        js = r"""
global.window={};require('./api-errors.js');const E=window.WeloraErrors;const cases={
 validation:E.message({detail:[{type:'missing',loc:['body','user_id'],msg:'Field required'},{type:'float_parsing',loc:['body','essential_expense_monthly'],msg:'x'}]},'fb',422),
 object_msg:E.message({detail:{error_code:'RATE_LIMITED',message:'Bạn đã thử quá nhiều lần. Vui lòng thử lại sau ít phút.'}},'fb',429),
 object_code:E.message({detail:{error_code:'TOKEN_EXPIRED'}},'fb',401),
 object_unknown:E.message({detail:{foo:{bar:1}}},'Không tạo được quỹ khẩn cấp',400),
 string_en:E.message({detail:'session not found'},'fb',404),
 string_vi:E.message({detail:'Người đồng hành phải khác chính bạn.'},'fb',400),
 error_obj:E.message({error:{error_code:'AUTH_REQUIRED',message:'Cần đăng nhập'}},'fb',401),
 empty_500:E.message(null,'',502),
 list_of_strings:E.message({detail:['a','b']},'fb',400)};
console.log('RESULT='+JSON.stringify(cases));"""
        out = node(js)
        self.assertEqual(out["validation"], "Thông tin chưa hợp lệ: người dùng còn thiếu; chi tiêu thiết yếu mỗi tháng phải là số.")
        self.assertEqual(out["object_msg"], "Bạn đã thử quá nhiều lần. Vui lòng thử lại sau ít phút.")
        self.assertEqual(out["object_code"], "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.")
        self.assertEqual(out["object_unknown"], "Không tạo được quỹ khẩn cấp")
        self.assertEqual(out["string_en"], "Không tìm thấy phiên onboarding — vui lòng bắt đầu lại.")
        self.assertEqual(out["string_vi"], "Người đồng hành phải khác chính bạn.")
        self.assertEqual(out["error_obj"], "Cần đăng nhập")
        self.assertEqual(out["empty_500"], "Hệ thống đang bận — vui lòng thử lại sau.")
        for k, v in out.items():
            self.assertNotIn("[object Object]", v, k)

    def test_constraints(self):
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
