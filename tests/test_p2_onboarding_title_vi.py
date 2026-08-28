"""P2 Ticket AW — onboarding title + muted Vietnamese."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "onboarding.html"


class TestP2OnboardingTitleVi(unittest.TestCase):
    def test_title_muted(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("<title>Welora · Hiến pháp Cá nhân</title>", html)
        self.assertIn("<h1>Hiến pháp Cá nhân</h1>", html)
        self.assertIn("B0–B5 · DNA · Goal quỹ 3 tháng", html)
        self.assertNotIn("<title>Welora Onboarding</title>", html)
        self.assertNotIn("DNA Self", html)
        self.assertIn("\u1ebf", html)
        self.assertIn("\u00e1", html)
        self.assertIn("\u00e2", html)
        self.assertIn("\u1ed4n định", html)
        self.assertIn("<h2>B1 · Danh tính</h2>", html)
        self.assertIn("<h2>B2 · Hiện trạng</h2>", html)
        self.assertIn("<h2>B3 · Hành vi</h2>", html)
        self.assertIn("/onboarding/session", html)
        self.assertIn("linked_from_onboarding", html)
        self.assertIn('value="young_single"', html)
        self.assertIn('value="stable"', html)
        self.assertIn("welora_device_id", html)
        self.assertNotIn("innerHTML", html)
        for nid in (
            "navHome", "step0", "step1", "step2", "step3", "step4", "step5",
            "life_stage", "income_stability", "family_context",
            "next1", "next2", "next3", "next4", "ctaGoal",
        ):
            self.assertIn(f'id="{nid}"', html)

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
