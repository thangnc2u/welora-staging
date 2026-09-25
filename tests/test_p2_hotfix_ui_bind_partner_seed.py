"""Hotfix — UI binds partner demo seed via welora_token → /auth/me (not device guest).

DoD: after password login, /app · /app/accounts · /app/goals hydrate same user_id as seed.
Hard Deny · TARGET_MONTHS · gate_months=3 · login 1-ô · logout Hotfix untouched.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from welora.agent import (
    CONFIDENCE_THRESHOLD,
    HARD,
    PRIORITY,
    TARGET_MONTHS as AGENT_TARGET,
    run_hard_deny_suite,
)
from welora.api.app import create_app
from welora.auth import DEMO_EMAIL, DEMO_PASSWORD
from welora.fixtures import reset_all_stores
from welora.partner_demo_seed import DEMO_P4_EMAIL, DEMO_P4_USER_ID, PARTNER_USER_ID
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"

CORE_PAGES = ("home.html", "accounts.html", "goals.html", "safety.html")
OS_PAGES = CORE_PAGES + (
    "transactions.html",
    "categories.html",
    "budget.html",
    "healthscore.html",
    "dna.html",
    "chat.html",
)


class TestP2HotfixUiBindPartnerSeed(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_url = os.environ.get("WELORA_DB_URL")
        self._prev_demo = os.environ.get("WELORA_GUEST_DEMO")
        self._prev_store = os.environ.get("WELORA_STORE")
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        os.environ["WELORA_DB_URL"] = self._tmp.name
        os.environ["WELORA_GUEST_DEMO"] = "1"
        os.environ["WELORA_STORE"] = "memory"
        reset_all_stores()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass
        for key, prev in (
            ("WELORA_DB_URL", self._prev_url),
            ("WELORA_GUEST_DEMO", self._prev_demo),
            ("WELORA_STORE", self._prev_store),
        ):
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev

    def test_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(AGENT_TARGET, 3)
        self.assertEqual(CONFIDENCE_THRESHOLD, 0.80)
        self.assertEqual(HARD, {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"})
        self.assertEqual(
            PRIORITY,
            ["R01", "R03", "R02", "R08", "R09", "R06", "R07", "R04", "R05"],
        )
        passed_n, failed = run_hard_deny_suite()
        self.assertEqual(failed, [])
        self.assertEqual(passed_n, 8)

    def test_health_gate_months_3_hard_deny_true(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["gate_months"], 3)
        self.assertTrue(body["hard_deny"])

    def test_session_js_prefers_auth_me_over_device(self):
        js = (STATIC / "session.js").read_text(encoding="utf-8")
        self.assertIn("welora_token", js)
        self.assertIn("/auth/me", js)
        self.assertIn("Authorization", js)
        self.assertIn("Bearer", js)
        self.assertIn("resolveUserId", js)
        self.assertIn("/auth/device", js)
        self.assertLess(js.index("/auth/me"), js.index("/auth/device"))
        self.assertIn("me.user_id", js)
        self.assertNotIn("user_p2", js)
        self.assertNotIn("user_p4", js)

    def test_core_pages_load_session_and_resolve(self):
        for name in CORE_PAGES:
            html = (STATIC / name).read_text(encoding="utf-8")
            self.assertIn("/static/session.js", html, name)
            self.assertIn("WeloraSession.resolveUserId", html, name)
            self.assertLess(
                html.index("/static/session.js"),
                html.index("WeloraSession.resolveUserId"),
                name,
            )

    def test_os_pages_prefer_session_bind(self):
        for name in OS_PAGES:
            html = (STATIC / name).read_text(encoding="utf-8")
            self.assertIn("WeloraSession.resolveUserId", html, name)
            self.assertIn("/static/session.js", html, name)

    def test_shell_chat_gate_uses_session(self):
        js = (STATIC / "shell.js").read_text(encoding="utf-8")
        self.assertIn("WeloraSession.resolveUserId", js)
        self.assertIn("WeloraSession.clearCache", js)

    def test_login_1o_and_logout_untouched_markers(self):
        login = (STATIC / "login.html").read_text(encoding="utf-8")
        self.assertIn('id="identifier"', login)
        self.assertIn("splitIdentifier", login)
        self.assertNotIn("/static/session.js", login)
        # Hotfix logout belt still present
        self.assertIn('removeItem("welora_token")', login)
        shell = (STATIC / "shell.js").read_text(encoding="utf-8")
        self.assertIn('removeItem("welora_token")', shell)
        self.assertIn('location.replace("/app/login")', shell)
        gate = (STATIC / "auth-gate.js").read_text(encoding="utf-8")
        self.assertIn("welora_token", gate)

    def test_seed_login_me_matches_accounts_goals_gate(self):
        seed = self.client.post("/auth/demo/seed")
        self.assertEqual(seed.status_code, 200, seed.text)
        seed2 = self.client.post("/auth/demo/seed")
        self.assertEqual(seed2.status_code, 200, seed2.text)
        body2 = seed2.json()
        self.assertTrue(body2.get("already") or body2.get("seeded") is False)

        login = self.client.post(
            "/auth/login",
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        )
        self.assertEqual(login.status_code, 200, login.text)
        tok = login.json()["token"]
        uid = login.json()["user_id"]
        self.assertEqual(uid, PARTNER_USER_ID)

        me = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(me.status_code, 200, me.text)
        self.assertEqual(me.json()["user_id"], uid)

        acc = self.client.get(f"/os/accounts?user_id={uid}")
        self.assertEqual(acc.status_code, 200, acc.text)
        accounts = acc.json().get("accounts") or []
        self.assertGreaterEqual(len(accounts), 2, acc.text)
        bals = []
        for a in accounts:
            bals.append(
                a.get("balance_vnd")
                or a.get("balance")
                or a.get("current_balance")
                or a.get("opening_balance")
                or 0
            )
        self.assertTrue(any(float(b or 0) != 0 for b in bals), bals)

        goals = self.client.get(f"/goals?user_id={uid}")
        self.assertEqual(goals.status_code, 200, goals.text)
        items = goals.json().get("items") or []
        types = {g.get("type") for g in items}
        self.assertIn("emergency_fund", types)
        self.assertIn("debt_payoff", types)

        gate = self.client.get(f"/users/{uid}/safety-gate")
        self.assertEqual(gate.status_code, 200, gate.text)
        self.assertEqual(gate.json().get("status"), "passed")

        login4 = self.client.post(
            "/auth/login",
            json={"email": DEMO_P4_EMAIL, "password": DEMO_PASSWORD},
        )
        self.assertEqual(login4.status_code, 200, login4.text)
        uid4 = login4.json()["user_id"]
        self.assertEqual(uid4, DEMO_P4_USER_ID)
        acc4 = self.client.get(f"/os/accounts?user_id={uid4}")
        self.assertGreaterEqual(len(acc4.json().get("accounts") or []), 2)
        gate4 = self.client.get(f"/users/{uid4}/safety-gate")
        self.assertEqual(gate4.json().get("status"), "not_passed")


if __name__ == "__main__":
    unittest.main()
