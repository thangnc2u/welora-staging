"""P2 partner rich demo seed — idempotent P2/P4 fixtures."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.auth import DEMO_EMAIL, DEMO_PASSWORD
from welora.fixtures import reset_all_stores
from welora.partner_demo_seed import (
    DEMO_P4_EMAIL,
    PARTNER_USER_ID,
    seed_partner_rich_demo,
)
from welora.safety_gate import TARGET_MONTHS

SAFETY = Path(__file__).resolve().parents[1] / "welora" / "safety_gate.py"
SHELL_JS = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "shell.js"
PARTNER_SEED = Path(__file__).resolve().parents[1] / "welora" / "partner_demo_seed.py"


class TestPartnerDemoSeedIdempotent(unittest.TestCase):
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

    def _counts(self, user_id: str) -> dict:
        from welora import goals_api
        from welora.onboarding import get_dna
        from welora.os_accounts import STORE as ACC
        from welora.os_categories import STORE as CAT
        from welora.os_transactions import STORE as TX

        goals = [
            g
            for g in goals_api.STORE._by_id.values()
            if getattr(g, "user_id", None) == user_id
        ]
        return {
            "accounts": len(ACC.list_for_user(user_id, include_hidden=True)),
            "transactions": len(TX.list_for_user(user_id, include_hidden=True)),
            "categories": len(CAT.list_for_user(user_id, include_disabled=True)),
            "goals": len(goals),
            "goal_types": sorted({g.type for g in goals}),
            "has_dna": bool(get_dna(user_id)),
        }

    def test_seed_twice_counts_stable_and_fixtures_present(self):
        first = seed_partner_rich_demo(url=self._tmp.name)
        self.assertTrue(first.get("seeded"))
        partner_id = first["partner"]["user_id"]
        p4_id = first["demo_p4"]["user_id"]
        self.assertEqual(first.get("p4_exposure"), "alias")
        self.assertEqual(first.get("p4_login"), DEMO_P4_EMAIL)
        # Fresh DB should land on Founder stable partner id
        self.assertEqual(partner_id, PARTNER_USER_ID)

        c1_p2 = self._counts(partner_id)
        c1_p4 = self._counts(p4_id)

        seed_partner_rich_demo(url=self._tmp.name)
        c2_p2 = self._counts(partner_id)
        c2_p4 = self._counts(p4_id)
        self.assertEqual(c1_p2, c2_p2)
        self.assertEqual(c1_p4, c2_p4)

        self.assertGreaterEqual(c2_p2["accounts"], 3)
        self.assertGreaterEqual(c2_p2["transactions"], 3)
        self.assertGreaterEqual(c2_p2["categories"], 5)
        self.assertTrue(c2_p2["has_dna"])
        self.assertEqual(set(c2_p2["goal_types"]), {"emergency_fund", "debt_payoff"})
        self.assertEqual(first["partner"]["persona"]["safety_gate"]["status"], "passed")

        from welora.os_accounts import STORE as ACC

        bals = [a.balance for a in ACC.list_for_user(partner_id, include_hidden=True)]
        self.assertTrue(any(b != 0 for b in bals), bals)

        self.assertGreaterEqual(c2_p4["accounts"], 3)
        self.assertTrue(c2_p4["has_dna"])
        self.assertEqual(set(c2_p4["goal_types"]), {"emergency_fund", "debt_payoff"})
        self.assertEqual(first["demo_p4"]["persona"]["safety_gate"]["status"], "not_passed")

    def test_http_demo_seed_and_partner_login(self):
        r = self.client.post("/auth/demo/seed")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body.get("email"), DEMO_EMAIL)
        self.assertIn("rich", body)
        self.assertEqual(body["rich"].get("p2_gate"), "passed")
        self.assertEqual(body["rich"].get("p4_gate"), "not_passed")
        self.assertEqual(body["rich"].get("p4_exposure"), "alias")
        self.assertEqual(body["rich"].get("demo_p4_email"), DEMO_P4_EMAIL)

        login = self.client.post(
            "/auth/login",
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["role"], "demo")

        login_p4 = self.client.post(
            "/auth/login",
            json={"email": DEMO_P4_EMAIL, "password": DEMO_PASSWORD},
        )
        self.assertEqual(login_p4.status_code, 200, login_p4.text)
        self.assertEqual(login_p4.json()["role"], "demo")
        self.assertNotEqual(login_p4.json()["user_id"], login.json()["user_id"])

    def test_hard_deny_and_hotfix4_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        safety = SAFETY.read_text(encoding="utf-8")
        self.assertIn("TARGET_MONTHS = 3", safety)
        seed_src = PARTNER_SEED.read_text(encoding="utf-8")
        self.assertNotIn("TARGET_MONTHS =", seed_src)
        self.assertNotIn("shell.js", seed_src)
        self.assertTrue(SHELL_JS.is_file())


if __name__ == "__main__":
    unittest.main()
