"""P0 follow-up #1 (guests onboard before login) + #5 FE 401 handling.

* Page level: auth-gate.js / shell.js exempt /app/onboarding (and nothing else new); the gate and
  session.js are executed under node:vm (tests/js/fe_harness.js) — skipped if node is missing.
* API flow: /auth/device guest token → onboarding session → complete → emergency-fund goal,
  in-process (memory store) and in a DB-store subprocess (SQLite, or PG via WELORA_TEST_POSTGRES_URL).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests._db_target import db_env
from tests._followup_dbmode import run_scenario
from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
HARNESS = ROOT / "tests" / "js" / "fe_harness.js"
NODE = shutil.which("node")


def fe(scenario: str) -> dict:
    p = subprocess.run([NODE, str(HARNESS), scenario], capture_output=True, text=True, timeout=60)
    for line in p.stdout.splitlines():
        if line.startswith("RESULT="):
            return json.loads(line[7:])
    raise AssertionError(p.stderr)


def allowlist(src: str, var: str) -> set[str]:
    block = re.search(var + r"\s*=\s*\{([^}]*)\}", src).group(1)
    return set(re.findall(r'"(/app[^"]*)"\s*:\s*1', block))


class TestGuestOnboardingPage(unittest.TestCase):
    def test_gates_exempt_onboarding_only(self):
        gate = allowlist((STATIC / "auth-gate.js").read_text(encoding="utf-8"), "allow")
        shell = allowlist((STATIC / "shell.js").read_text(encoding="utf-8"), "_authAllow")
        self.assertIn("/app/onboarding", gate)
        self.assertIn("/app/onboarding", shell)
        auth_pages = {"/app/login", "/app/register", "/app/forgot-password", "/app/reset-password", "/app/otp"}
        # P0 follow-up 2: the guest result page (/app/onboarding/result) is exempt too.
        guest_pages = {"/app/onboarding", "/app/onboarding/result"}
        self.assertEqual(gate, auth_pages | {"/app/admin/login"} | guest_pages)
        self.assertEqual(shell, auth_pages | guest_pages)

    def test_onboarding_html_guest_flow_wired(self):
        r = TestClient(create_app()).get("/app/onboarding")
        self.assertEqual(r.status_code, 200)
        html = r.text
        self.assertIn('<script src="/static/auth-gate.js"></script>', html)
        self.assertLess(html.index("/static/session.js"), html.index("document.getElementById('auth').onclick"))
        self.assertIn("WeloraSession.resolveUserId", html)
        self.assertIn("type:'emergency_fund'", html)
        self.assertIn("linked_from_onboarding:true", html)
        self.assertNotIn("localStorage.setItem('welora_token'", html)  # guest token never persisted

    @unittest.skipUnless(NODE, "node not installed")
    def test_auth_gate_executed(self):
        out = fe("gate_guest_onboarding")
        self.assertIsNone(out["/app/onboarding"]["redirect"])
        self.assertIsNone(out["/app/onboarding/"]["redirect"])
        self.assertEqual(out["/app/onboarding+tok"], {"redirect": None, "token_kept": "T1"})
        for p in ("/app/goals", "/app/safety", "/app/pre-rule"):
            self.assertEqual(out[p]["redirect"], "/app/login", p)

    @unittest.skipUnless(NODE, "node not installed")
    def test_guest_without_token_uses_in_memory_device_token(self):
        out = fe("guest_onboarding_no_token")
        self.assertEqual(out["uid"], "guest-2")
        self.assertEqual(out["goal"], 201)
        self.assertEqual(out["redirect"], [])
        self.assertIsNone(out["stored"])
        self.assertEqual(out["auths"], ["/auth/device=", "/goals=Bearer DEV2"])


class TestFrontend401(unittest.TestCase):
    @unittest.skipUnless(NODE, "node not installed")
    def test_expired_token_cleared_and_sent_to_login(self):
        out = fe("expired_on_app_page")
        self.assertEqual(out["status"], 401)
        self.assertEqual(out["sent"], "Bearer OLD")
        self.assertEqual(out["redirect"], ["/app/login"])
        self.assertIsNone(out["token"])
        self.assertEqual(out["device"], "dev-x")  # device identity kept
        self.assertEqual(out["notice"], "expired")

    @unittest.skipUnless(NODE, "node not installed")
    def test_expired_token_on_onboarding_continues_as_guest(self):
        out = fe("expired_on_onboarding_guest_continues")
        self.assertEqual(out["redirect"], [])
        self.assertIsNone(out["token"])
        self.assertEqual(out["uid"], "guest-1")
        self.assertEqual((out["session"], out["goal"]), (201, 201))
        self.assertEqual(out["auths"][-2:], ["/onboarding/session=Bearer DEV1", "/goals=Bearer DEV1"])

    @unittest.skipUnless(NODE, "node not installed")
    def test_other_401_codes_left_to_the_page(self):
        out = fe("other_401_codes_untouched")
        self.assertEqual(out, {"status": 401, "redirect": [], "token": "ADM"})

    def test_login_page_shows_expiry_notice(self):
        html = (STATIC / "login.html").read_text(encoding="utf-8")
        self.assertIn('id="authNotice"', html)
        self.assertIn("welora_auth_notice", html)
        self.assertIn("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", html)
        self.assertNotIn("innerHTML", html)


class TestGuestOnboardingApi(unittest.TestCase):
    def _check(self, out: dict) -> None:
        self.assertEqual(out["page"], 200)
        self.assertTrue(out["page_gate"])
        self.assertEqual(out["device"], 200)
        self.assertEqual(out["session"], 201)
        self.assertEqual(out["steps"], [200, 200, 200, 200])
        self.assertEqual(out["complete"], 200)
        self.assertEqual(out["goal"], 201)
        self.assertEqual(out["goal_type"], "emergency_fund")
        self.assertEqual(out["goal_essential"], 12_000_000)
        self.assertTrue(out["goal_linked"])
        self.assertEqual(out["again"], 409)  # second click: already has one (FE treats 409 as ok)
        self.assertEqual(out["goals_count"], 1)
        self.assertEqual(out["gate"], 200)
        self.assertEqual(out["anon_goal"], 401)  # still no anonymous writes

    def test_flow_memory_store(self):
        keys = ("WELORA_DB_URL", "WELORA_STORE")
        prev = {k: os.environ.get(k) for k in keys}
        tmp = tempfile.mkdtemp()
        try:
            os.environ["WELORA_DB_URL"] = f"{tmp}/g.db"
            os.environ.pop("WELORA_STORE", None)
            from tests import _followup_dbmode as fu

            self._check(fu.scenario_guest_onboarding())
        finally:
            for k, v in prev.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            shutil.rmtree(tmp, ignore_errors=True)

    def test_flow_db_store(self):
        tmp = tempfile.mkdtemp()
        try:
            self._check(run_scenario("guest_onboarding", {"WELORA_GUEST_DEMO": "0", **db_env(tmp)}))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_constraints(self):
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
