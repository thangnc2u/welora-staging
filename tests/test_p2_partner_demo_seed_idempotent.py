"""P2 partner rich demo seed — idempotent P1–P6 fixtures + login aliases."""

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
    DEMO_P1_EMAIL,
    DEMO_P3_EMAIL,
    DEMO_P4_EMAIL,
    DEMO_P5_EMAIL,
    DEMO_P6_EMAIL,
    DEMO_PERSONA_ALIASES,
    PARTNER_USER_ID,
    seed_partner_rich_demo,
)
from welora.safety_gate import TARGET_MONTHS

SAFETY = Path(__file__).resolve().parents[1] / "welora" / "safety_gate.py"
SHELL_JS = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "shell.js"
PARTNER_SEED = Path(__file__).resolve().parents[1] / "welora" / "partner_demo_seed.py"
GOALS_HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "goals.html"

ALLOWED_GOAL_TYPES = frozenset({"emergency_fund", "debt_payoff"})
ALL_EMAILS = (
    DEMO_P1_EMAIL,
    DEMO_EMAIL,
    DEMO_P3_EMAIL,
    DEMO_P4_EMAIL,
    DEMO_P5_EMAIL,
    DEMO_P6_EMAIL,
)


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

    def test_seed_twice_all_six_personas_idempotent(self):
        first = seed_partner_rich_demo(url=self._tmp.name)
        self.assertTrue(first.get("seeded"))
        self.assertEqual(set(first["personas"].keys()), {"P1", "P2", "P3", "P4", "P5", "P6"})
        self.assertEqual(set(first["aliases"].keys()), {"P1", "P2", "P3", "P4", "P5", "P6"})

        partner_id = first["partner"]["user_id"]
        p4_id = first["demo_p4"]["user_id"]
        self.assertEqual(first.get("p4_exposure"), "alias")
        self.assertEqual(first.get("p4_login"), DEMO_P4_EMAIL)
        self.assertEqual(partner_id, PARTNER_USER_ID)

        counts1 = {
            pid: self._counts(first["personas"][pid]["user_id"])
            for pid in ("P1", "P2", "P3", "P4", "P5", "P6")
        }

        seed_partner_rich_demo(url=self._tmp.name)
        counts2 = {
            pid: self._counts(first["personas"][pid]["user_id"])
            for pid in ("P1", "P2", "P3", "P4", "P5", "P6")
        }
        self.assertEqual(counts1, counts2)

        # P2 / P4 parity preserved
        c2_p2 = counts2["P2"]
        c2_p4 = counts2["P4"]
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

        # All personas: accounts + goals allowlist only
        expected_hh = {
            "P1": "solo",
            "P2": "young_family",
            "P3": "couple_no_kids",
            "P4": "sandwich_3gen",
            "P5": "pre_retire",
            "P6": "retire_companion",
        }
        for pid, block in first["personas"].items():
            persona = block["persona"]
            self.assertEqual(persona["persona_id"], pid)
            self.assertEqual(persona["household"], expected_hh[pid])
            self.assertGreaterEqual(counts2[pid]["accounts"], 2)
            self.assertTrue(counts2[pid]["has_dna"])
            self.assertTrue(set(counts2[pid]["goal_types"]) <= ALLOWED_GOAL_TYPES)
            self.assertIn("emergency_fund", counts2[pid]["goal_types"])
            for gtype in (persona.get("goals") or {}):
                self.assertIn(gtype, ALLOWED_GOAL_TYPES)

        # P3 has ho-tro-gia-dinh category tag when schema supports tags
        from welora.os_categories import STORE as CAT

        p3_uid = first["personas"]["P3"]["user_id"]
        tags = []
        for c in CAT.list_for_user(p3_uid, include_disabled=True):
            tags.extend(getattr(c, "tags", None) or [])
        self.assertIn("ho-tro-gia-dinh", tags)

        # P6 prefer no debt goal
        self.assertEqual(counts2["P6"]["goal_types"], ["emergency_fund"])
        # P1 early/not_passed with optional card debt
        self.assertEqual(
            first["personas"]["P1"]["persona"]["safety_gate"]["status"], "not_passed"
        )
        self.assertEqual(set(counts2["P1"]["goal_types"]), {"emergency_fund", "debt_payoff"})

    def test_http_demo_seed_and_all_six_logins(self):
        r = self.client.post("/auth/demo/seed")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body.get("email"), DEMO_EMAIL)
        self.assertIn("rich", body)
        rich = body["rich"]
        self.assertEqual(rich.get("p2_gate"), "passed")
        self.assertEqual(rich.get("p4_gate"), "not_passed")
        self.assertEqual(rich.get("p4_exposure"), "alias")
        self.assertEqual(rich.get("demo_p4_email"), DEMO_P4_EMAIL)
        self.assertEqual(
            set((rich.get("persona_emails") or {}).keys()),
            {"P1", "P2", "P3", "P4", "P5", "P6"},
        )
        self.assertEqual(rich["persona_emails"]["P2"], DEMO_EMAIL)
        self.assertEqual(rich["persona_emails"]["P1"], DEMO_P1_EMAIL)

        user_ids = set()
        for email in ALL_EMAILS:
            login = self.client.post(
                "/auth/login",
                json={"email": email, "password": DEMO_PASSWORD},
            )
            self.assertEqual(login.status_code, 200, f"{email}: {login.text}")
            payload = login.json()
            self.assertEqual(payload["role"], "demo")
            user_ids.add(payload["user_id"])
        self.assertEqual(len(user_ids), 6)

    def test_alias_map_stable(self):
        self.assertEqual(DEMO_PERSONA_ALIASES["P2"]["email"], DEMO_EMAIL)
        self.assertEqual(DEMO_PERSONA_ALIASES["P4"]["email"], DEMO_P4_EMAIL)
        for pid in ("P1", "P2", "P3", "P4", "P5", "P6"):
            self.assertIn("email", DEMO_PERSONA_ALIASES[pid])
            self.assertIn("user_id", DEMO_PERSONA_ALIASES[pid])
            self.assertIn("household", DEMO_PERSONA_ALIASES[pid])

    def test_hard_deny_and_hotfix4_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        safety = SAFETY.read_text(encoding="utf-8")
        self.assertIn("TARGET_MONTHS = 3", safety)
        seed_src = PARTNER_SEED.read_text(encoding="utf-8")
        self.assertNotIn("TARGET_MONTHS =", seed_src)
        self.assertNotIn("shell.js", seed_src)
        self.assertTrue(SHELL_JS.is_file())

    def test_no_core_safe_debt_keys_in_goals_ui_excerpt(self):
        """Regression #226 — Học thêm excerpts scrub CORE/SAFE/DEBT; seed titles clean."""
        from welora.pedia_inline import pedia_cards_for_goal
        import re

        key_re = re.compile(r"\b(?:CORE|SAFE|DEBT)-\d+\b")
        html = GOALS_HTML.read_text(encoding="utf-8")
        self.assertIn("scrubInternalCodes", html)
        self.assertIn("stripFrontmatter", html)
        for goal_type in ("emergency_fund", "debt_payoff"):
            for card in pedia_cards_for_goal(goal_type):
                self.assertIsNone(key_re.search(card["excerpt"] or ""))
        seed_src = PARTNER_SEED.read_text(encoding="utf-8")
        for line in seed_src.splitlines():
            if "title=" in line and key_re.search(line):
                self.fail(f"goal title leaks key: {line}")


if __name__ == "__main__":
    unittest.main()
