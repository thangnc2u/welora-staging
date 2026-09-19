"""P2 Onboarding — P1–P6 personas (PRD v2). Retire DNA-USER-2026-* / 4-persona."""

from __future__ import annotations

import re
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.fixtures import load_demo_personas, reset_all_stores
from welora.onboarding import (
    HOUSEHOLD_VALUES,
    create_session,
    patch_step,
    complete_session,
    reset_onboarding_stores,
)
from welora.personas import (
    AGENT_IS_PILLAR,
    DEMO_SEED_ORDER,
    DNA_SKELETON_IDS,
    HOUSEHOLD_TO_PERSONA,
    OS_GOAL_TYPES_FORBIDDEN,
    OS_GOAL_TYPES_MVP,
    PERSONA_IDS,
    PERSONAS,
    PRODUCT_PILLARS,
    RETIRED_DNA_USER_2026,
    assert_dna_skeleton_clean,
    assert_os_goals_mvp,
    demo_seed_personas,
    dna_skeleton,
    is_retired_dna_user_fixture,
    os_goal_types,
    pillars_for,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
ONBOARD = (ROOT / "welora" / "api" / "static" / "onboarding.html").read_text(encoding="utf-8")
DNA_HTML = (ROOT / "welora" / "api" / "static" / "dna.html").read_text(encoding="utf-8")
MONEYISH = re.compile(
    r"(?:\d{1,3}(?:[.,]\d{3})+|\d+\s*(?:tr|triệu|đ|vnd|vnđ))",
    re.IGNORECASE,
)


class TestP2PersonaP1P6V2(unittest.TestCase):
    def setUp(self) -> None:
        reset_onboarding_stores()
        reset_all_stores()
        self.client = TestClient(create_app())

    def test_catalog_six_personas_household(self):
        self.assertEqual(tuple(PERSONAS.keys()), PERSONA_IDS)
        for pid in PERSONA_IDS:
            p = PERSONAS[pid]
            self.assertEqual(p["persona_id"], pid)
            self.assertIn(p["household"], HOUSEHOLD_VALUES)
            self.assertEqual(HOUSEHOLD_TO_PERSONA[p["household"]], pid)
            self.assertIn("label_vi", p)
            self.assertIn("academy_emphasis", p)
            self.assertTrue(p["academy_emphasis"])

    def test_dna_skeleton_per_persona_le_7_no_money(self):
        for pid in PERSONA_IDS:
            answers = dna_skeleton(pid)
            self.assertLessEqual(len(answers), 7, pid)
            for k in DNA_SKELETON_IDS:
                self.assertIn(k, answers, msg=f"{pid} missing {k}")
                self.assertTrue(str(answers[k]).strip(), msg=f"{pid}.{k} empty")
                self.assertIsNone(MONEYISH.search(str(answers[k])), msg=f"{pid}.{k}")
            assert_dna_skeleton_clean(answers)

    def test_os_goals_only_ef_or_debt(self):
        for pid in PERSONA_IDS:
            types = os_goal_types(pid)
            self.assertTrue(types, pid)
            self.assertTrue(set(types) <= OS_GOAL_TYPES_MVP, msg=(pid, types))
            for t in types:
                self.assertNotIn(t, OS_GOAL_TYPES_FORBIDDEN)
            assert_os_goals_mvp(pid)
        # P4 debt first
        self.assertEqual(PERSONAS["P4"]["os_goals"][0]["type"], "debt_payoff")
        # education/retirement never OS goals
        for pid in PERSONA_IDS:
            blob = " ".join(PERSONAS[pid]["primary_goals"]).lower()
            # narrative may mention education/retirement; OS types must not
            self.assertNotIn("education", os_goal_types(pid))
            self.assertNotIn("retirement", os_goal_types(pid))

    def test_three_pillars_agent_not_pillar_4(self):
        self.assertFalse(AGENT_IS_PILLAR)
        self.assertEqual(PRODUCT_PILLARS, ("Welorapedia", "Welorademy", "WeloraOS"))
        for pid in PERSONA_IDS:
            pillars = pillars_for(pid)
            self.assertEqual(set(pillars.keys()), set(PRODUCT_PILLARS))
            self.assertNotIn("Agent", pillars)

    def test_demo_seed_prefers_p2_p4(self):
        self.assertEqual(DEMO_SEED_ORDER[:2], ("P2", "P4"))
        pri = demo_seed_personas(only_priority=True)
        self.assertEqual([p["persona_id"] for p in pri], ["P2", "P4"])
        loaded = load_demo_personas(priority_only=True)
        self.assertEqual(list(loaded.keys()), ["P2", "P4"])
        self.assertEqual(loaded["P2"]["household"], "young_family")
        self.assertEqual(loaded["P4"]["household"], "sandwich_3gen")
        self.assertEqual(loaded["P2"]["dna"]["identity_context"]["persona_id"], "P2")
        self.assertEqual(loaded["P4"]["dna"]["identity_context"]["persona_id"], "P4")

    def test_old_dna_user_2026_retired(self):
        self.assertEqual(RETIRED_DNA_USER_2026["status"], "retired")
        for fid in RETIRED_DNA_USER_2026["fixture_ids"]:
            self.assertTrue(is_retired_dna_user_fixture(fid))
        # No active fixture module should expose DNA-USER-2026 as live seed ids
        from welora.personas import list_active_fixture_ids

        for fid in list_active_fixture_ids():
            self.assertFalse(str(fid).startswith("DNA-USER-2026"))
        # Scan onboarding + fixtures + personas for accidental revival as active keys
        for rel in (
            "welora/personas.py",
            "welora/fixtures.py",
            "welora/seed_db.py",
            "welora/api/static/onboarding.html",
        ):
            body = (ROOT / rel).read_text(encoding="utf-8")
            # Allowed only inside RETIRED_* documentation
            if "DNA-USER-2026" in body:
                self.assertIn("retired", body.lower())

    def test_onboarding_household_chrome(self):
        for hh in (
            "solo",
            "young_family",
            "couple_no_kids",
            "sandwich_3gen",
            "pre_retire",
            "retire_companion",
        ):
            self.assertIn(f'value="{hh}"', ONBOARD)
        self.assertIn("Hộ gia đình", ONBOARD)
        self.assertIn("Agent không phải trụ 4", ONBOARD)
        # Old 4/6 life_stage values retired from visible select
        self.assertNotIn('value="young_single"', ONBOARD.split('id="household"')[1].split("</select>")[0])
        self.assertIn("solo", DNA_HTML)
        self.assertIn("young_family", DNA_HTML)
        self.assertIn("sandwich_3gen", DNA_HTML)

    def test_onboarding_api_household_sets_persona(self):
        s = create_session("u-p2-persona")
        patch_step(
            s.session_id,
            1,
            {
                "household": "young_family",
                "income_stability": "stable",
                "family_context": "with_family",
            },
        )
        patch_step(
            s.session_id,
            2,
            {
                "essential_expense_monthly": 12_000_000,
                "has_dangerous_debt_self": False,
                "near_term_priority": "safety",
            },
        )
        patch_step(
            s.session_id,
            3,
            {
                "surplus_habit": "hold",
                "risk_tolerance": 3,
                "agent_role_preference": "advisor_only",
            },
        )
        patch_step(s.session_id, 4, {})
        out = complete_session(s.session_id)
        ident = out["dna"]["identity_context"]
        self.assertEqual(ident["household"], "young_family")
        self.assertEqual(ident["persona_id"], "P2")
        self.assertEqual(ident["life_stage"], "young_family")

    def test_legacy_life_stage_still_maps(self):
        s = create_session("u-legacy-map")
        patch_step(
            s.session_id,
            1,
            {
                "life_stage": "young_single",
                "income_stability": "stable",
                "family_context": "alone",
            },
        )
        self.assertEqual(s.steps[1]["household"], "solo")
        self.assertEqual(s.steps[1]["persona_id"], "P1")

    def test_health_gate_months_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
