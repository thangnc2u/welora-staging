"""P1 Welorademy Flow 1–2 + XP chỉ sau KUAT."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.academy import (
    XP_PER_PASS,
    QUESTIONS,
    mark_read,
    nodes_for_principle,
    os_nudge_for,
    reset_academy_store,
    submit_kuat,
)
from welora.api.app import create_app
from welora.onboarding import (
    complete_session,
    create_session,
    patch_step,
    reset_onboarding_stores,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
ACADEMY = ROOT / "welora" / "api" / "static" / "academy.html"
CONTENT = ROOT / "welora" / "api" / "static" / "content.html"
CONST = ROOT / "welora" / "api" / "static" / "constitution.html"


def _correct(node_id: str) -> list[dict]:
    return [{"question_id": q["id"], "choice": q["answer"]} for q in QUESTIONS[node_id]]


def _wrong(node_id: str) -> list[dict]:
    return [
        {"question_id": q["id"], "choice": (q["answer"] + 1) % max(2, len(q["choices"]))}
        for q in QUESTIONS[node_id]
    ]


class TestP1AcademyFlow12Xp(unittest.TestCase):
    def setUp(self):
        reset_academy_store()
        reset_onboarding_stores()

    def test_flow1_content_cta_hrefs(self):
        html = CONTENT.read_text(encoding="utf-8")
        self.assertIn("Học sâu hơn · Welorademy", html)
        self.assertIn("/app/academy", html)
        self.assertIn("Xây Hiến pháp Cá nhân", html)
        self.assertIn("/app/constitution", html)
        self.assertIn("from=pedia", html)
        self.assertNotIn("Welora Academy", html)
        self.assertNotIn("innerHTML", html)

    def test_flow1_academy_pedia_focus_no_500(self):
        html = ACADEMY.read_text(encoding="utf-8")
        self.assertIn("Welorademy", html)
        self.assertIn("from=pedia", html)
        self.assertIn("focusNode", html)
        self.assertIn("osNudge", html)
        self.assertIn("Tạo Goal trên WeloraOS", html)
        self.assertNotIn("Welora Academy", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn("N02-01", nodes_for_principle("SAFE-01"))
        client = TestClient(create_app())
        r = client.get("/app/academy")
        self.assertEqual(r.status_code, 200)
        r2 = client.get("/app/academy?from=pedia&key=SAFE-01")
        self.assertEqual(r2.status_code, 200)
        self.assertIn("Welorademy", r2.text)

    def test_flow2_n02_01_nudge_emergency_fund(self):
        out = submit_kuat("u-flow", "N02-01", _correct("N02-01"))
        self.assertTrue(out["kuat_result"]["passed"])
        self.assertTrue(out["awarded_xp"])
        nudge = out["os_nudge"]
        self.assertIsNotNone(nudge)
        self.assertEqual(nudge["kind"], "create_goal")
        self.assertEqual(nudge["goal_type"], "emergency_fund")
        self.assertEqual(nudge["href"], "/app/goals")
        self.assertEqual(nudge["principle_key"], "SAFE-01")

    def test_flow2_n02_05_nudge_debt_payoff(self):
        for nid in ("N02-01", "N02-02", "N02-03"):
            submit_kuat("u-debt", nid, _correct(nid))
        out = submit_kuat("u-debt", "N02-05", _correct("N02-05"))
        self.assertTrue(out["kuat_result"]["passed"])
        nudge = out["os_nudge"]
        self.assertEqual(nudge["goal_type"], "debt_payoff")
        self.assertEqual(nudge["href"], "/app/goals")
        self.assertEqual(nudge["principle_key"], "DEBT-01")

    def test_flow2_fail_kuat_no_nudge(self):
        out = submit_kuat("u-fail", "N02-01", _wrong("N02-01"))
        self.assertFalse(out["kuat_result"]["passed"])
        self.assertFalse(out["awarded_xp"])
        self.assertIsNone(out["os_nudge"])
        self.assertIsNone(os_nudge_for("N02-01", first_pass=False))

    def test_constitution_confirm_exposes_efund_cta(self):
        s = create_session("u-con")
        patch_step(s.session_id, 1, {
            "life_stage": "young_single",
            "income_stability": "stable",
            "family_context": "alone",
        })
        patch_step(s.session_id, 2, {"essential_expense_monthly": 10_000_000})
        out = complete_session(s.session_id)
        self.assertEqual(out["cta"]["code"], "create_emergency_fund_goal")
        self.assertEqual(out["cta"]["prefill_body"]["user_id"], "u-con")
        self.assertEqual(out["cta_goal"]["type"], "emergency_fund")
        self.assertEqual(out["cta_goal"]["months_of_expense"], 3)
        self.assertEqual(out["os_nudge"]["goal_type"], "emergency_fund")
        self.assertEqual(out["os_nudge"]["href"], "/app/goals")
        html = CONST.read_text(encoding="utf-8")
        self.assertIn('id="ctaOsGoal"', html)
        self.assertIn("/app/goals", html)

    def test_xp_only_after_kuat_once(self):
        r1 = mark_read("u-xp", "N02-01")
        self.assertEqual(r1["xp"], 0)
        self.assertFalse(r1["awarded_xp"])
        first = submit_kuat("u-xp", "N02-01", _correct("N02-01"))
        self.assertEqual(first["xp"], XP_PER_PASS)
        self.assertTrue(first["awarded_xp"])
        second = submit_kuat("u-xp", "N02-01", _correct("N02-01"))
        self.assertEqual(second["xp"], XP_PER_PASS)
        self.assertFalse(second["awarded_xp"])
        self.assertIsNone(second["os_nudge"])

    def test_gate_months_hard_3(self):
        self.assertEqual(TARGET_MONTHS, 3)
        client = TestClient(create_app())
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
