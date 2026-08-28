"""P2 Ticket AP — onboarding B1–B3 headings Vietnamese."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "onboarding.html"


class TestP2OnboardingB123Vi(unittest.TestCase):
    def test_headings(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("<h2>B1 · Danh tính</h2>", html)
        self.assertIn("<h2>B2 · Hiện trạng</h2>", html)
        self.assertIn("<h2>B3 · Hành vi</h2>", html)
        self.assertIn("\u00ed", html)
        self.assertIn("\u1ec7", html)
        self.assertIn("\u1ea1", html)
        self.assertIn("\u00e0", html)
        self.assertNotIn("Identity", html)
        self.assertNotIn("Snapshot", html)
        self.assertNotIn("Behavior", html)
        self.assertIn("<h2>B0 · Chào</h2>", html)
        self.assertIn("<h2>B4 · Hiến pháp</h2>", html)
        self.assertIn("B5 · Tóm tắt", html)
        for nid in (
            "navHome", "step0", "step1", "step2", "step3", "step4", "step5",
            "life_stage", "income_stability", "family_context",
            "next1", "next2", "next3", "next4", "ctaGoal",
        ):
            self.assertIn(f'id="{nid}"', html)
        self.assertIn('value="young_single"', html)
        self.assertIn('value="stable"', html)
        self.assertIn('value="advisor_only"', html)
        self.assertIn("\u1ed4n định", html)
        self.assertNotIn("\u1ed2n định", html)
        self.assertIn("/onboarding/session/", html)
        self.assertNotIn("innerHTML", html)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
