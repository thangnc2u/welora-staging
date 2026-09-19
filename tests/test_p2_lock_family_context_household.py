"""P2 Onboarding — lock family_context by household (P1–P6)."""

from __future__ import annotations

import re
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.onboarding import create_session, patch_step, reset_onboarding_stores
from welora.onboarding_api import service_create_session, service_patch_step
from welora.personas import (
    FAMILY_CONTEXT_MISMATCH_VI,
    FAMILY_CONTEXT_VALUES,
    HOUSEHOLD_ALLOWED_FAMILY_CONTEXT,
    HOUSEHOLD_DEFAULT_FAMILY_CONTEXT,
    HOUSEHOLD_VALUES,
    allowed_family_contexts,
    default_family_context,
    validate_household_family_context,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
ONBOARD = (ROOT / "welora" / "api" / "static" / "onboarding.html").read_text(encoding="utf-8")
FC_JS = (ROOT / "welora" / "api" / "static" / "family_context.js").read_text(encoding="utf-8")

# Full matrix: household × family_context → ok?
MATRIX = []
for hh in sorted(HOUSEHOLD_VALUES):
    for fc in sorted(FAMILY_CONTEXT_VALUES):
        MATRIX.append((hh, fc, fc in HOUSEHOLD_ALLOWED_FAMILY_CONTEXT[hh]))


class TestP2LockFamilyContextHousehold(unittest.TestCase):
    def setUp(self) -> None:
        reset_onboarding_stores()
        self.client = TestClient(create_app())

    def test_allowed_helper_matrix(self):
        self.assertEqual(
            HOUSEHOLD_ALLOWED_FAMILY_CONTEXT["solo"], frozenset({"alone"})
        )
        self.assertEqual(
            HOUSEHOLD_ALLOWED_FAMILY_CONTEXT["young_family"],
            frozenset({"with_family"}),
        )
        self.assertEqual(
            HOUSEHOLD_ALLOWED_FAMILY_CONTEXT["couple_no_kids"],
            frozenset({"with_family"}),
        )
        self.assertEqual(
            HOUSEHOLD_ALLOWED_FAMILY_CONTEXT["sandwich_3gen"],
            frozenset({"with_family"}),
        )
        self.assertEqual(
            HOUSEHOLD_ALLOWED_FAMILY_CONTEXT["retire_companion"],
            frozenset({"with_family"}),
        )
        self.assertEqual(
            HOUSEHOLD_ALLOWED_FAMILY_CONTEXT["pre_retire"],
            frozenset({"alone", "with_family"}),
        )
        self.assertEqual(default_family_context("pre_retire"), "with_family")
        # Fail closed on unknown
        self.assertEqual(allowed_family_contexts("NOT_A_HOUSEHOLD"), frozenset())
        with self.assertRaises(ValueError) as cm:
            validate_household_family_context("solo", "with_family")
        self.assertEqual(str(cm.exception), FAMILY_CONTEXT_MISMATCH_VI)

    def test_matrix_patch_step_and_api_400(self):
        for hh, fc, ok in MATRIX:
            with self.subTest(household=hh, family_context=fc, ok=ok):
                s = create_session(f"u-fc-{hh}-{fc}")
                payload = {
                    "household": hh,
                    "income_stability": "stable",
                    "family_context": fc,
                }
                if ok:
                    patch_step(s.session_id, 1, payload)
                    self.assertEqual(s.steps[1]["family_context"], fc)
                    self.assertEqual(s.steps[1]["household"], hh)
                else:
                    with self.assertRaises(ValueError) as cm:
                        patch_step(s.session_id, 1, payload)
                    self.assertIn("không khớp", str(cm.exception))

                # HTTP adapter
                code, sess = service_create_session({"user_id": f"u-http-{hh}-{fc}"})
                self.assertEqual(code, 201)
                c, body = service_patch_step(sess["session_id"], 1, payload)
                if ok:
                    self.assertEqual(c, 200, body)
                else:
                    self.assertEqual(c, 400, body)
                    self.assertIn("không khớp", body["error"])

                # FastAPI path
                r = self.client.post(
                    "/onboarding/session", json={"user_id": f"u-app-{hh}-{fc}"}
                )
                self.assertEqual(r.status_code, 201)
                sid = r.json()["session_id"]
                r2 = self.client.patch(
                    f"/onboarding/session/{sid}/step/1", json=payload
                )
                if ok:
                    self.assertEqual(r2.status_code, 200, r2.text)
                else:
                    self.assertEqual(r2.status_code, 400, r2.text)
                    detail = r2.json().get("detail") or r2.json().get("error") or ""
                    self.assertIn("không khớp", str(detail))

    def test_legacy_life_stage_maps_then_same_rule(self):
        # young_single → solo → alone only
        s = create_session("u-legacy-ok")
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

        s2 = create_session("u-legacy-bad")
        with self.assertRaises(ValueError):
            patch_step(
                s2.session_id,
                1,
                {
                    "life_stage": "young_single",
                    "income_stability": "stable",
                    "family_context": "with_family",
                },
            )

        # family → young_family → with_family only
        s3 = create_session("u-legacy-fam")
        patch_step(
            s3.session_id,
            1,
            {
                "life_stage": "family",
                "income_stability": "stable",
                "family_context": "with_family",
            },
        )
        self.assertEqual(s3.steps[1]["household"], "young_family")
        s4 = create_session("u-legacy-fam-bad")
        with self.assertRaises(ValueError):
            patch_step(
                s4.session_id,
                1,
                {
                    "life_stage": "family",
                    "income_stability": "stable",
                    "family_context": "alone",
                },
            )

        # pre_retire legacy key is also canonical household — both alone + with_family
        for fc in ("alone", "with_family"):
            s5 = create_session(f"u-pr-{fc}")
            patch_step(
                s5.session_id,
                1,
                {
                    "life_stage": "pre_retire",
                    "income_stability": "stable",
                    "family_context": fc,
                },
            )
            self.assertEqual(s5.steps[1]["household"], "pre_retire")

    def test_ui_lock_smoke(self):
        self.assertIn("/static/family_context.js", ONBOARD)
        self.assertIn("family_context_wrap", ONBOARD)
        self.assertIn("syncFamilyContextLock", ONBOARD)
        self.assertIn("WeloraFamilyContext", ONBOARD)
        self.assertIn('id="household"', ONBOARD)
        self.assertIn('id="family_context"', ONBOARD)
        # JS mirrors Python allowlists
        for hh, allowed in HOUSEHOLD_ALLOWED_FAMILY_CONTEXT.items():
            self.assertIn(hh, FC_JS)
            for fc in allowed:
                # e.g. solo: ["alone"]
                self.assertRegex(
                    FC_JS,
                    re.compile(rf'{hh}\s*:\s*\[[^\]]*"{fc}"'),
                )
        for hh, dfc in HOUSEHOLD_DEFAULT_FAMILY_CONTEXT.items():
            self.assertRegex(
                FC_JS,
                re.compile(rf'{hh}\s*:\s*"{dfc}"'),
            )
        # Static served
        r = self.client.get("/static/family_context.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("allowedFamilyContexts", r.text)
        r2 = self.client.get("/app/onboarding")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("family_context.js", r2.text)

    def test_health_gate_months_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
