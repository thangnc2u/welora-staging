"""P2 Ticket AP — onboarding B1–B3 chrome (P1–P6 household)."""

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
        self.assertIn("<h2>Bạn đang ở đâu trong đời?</h2>", html)
        self.assertIn("<h2>Chi tiêu mỗi tháng</h2>", html)
        self.assertIn("<h2>Cách bạn giữ tiền</h2>", html)
        self.assertIn("ả", html)
        self.assertIn("ộ", html)
        self.assertIn("ư", html)
        for nid in (
            "navHome", "step0", "step1", "step2", "step3", "step4", "step5",
            "household", "life_stage", "income_stability", "family_context",
            "next1", "next2", "next3", "next4", "ctaGoal",
        ):
            self.assertIn(f'id="{nid}"', html)
        self.assertIn('value="solo"', html)
        self.assertIn('value="young_family"', html)
        self.assertIn('value="stable"', html)
        self.assertIn('value="advisor_only"', html)
        self.assertIn("/onboarding/session/", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn("Agent không phải trụ 4", html)

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
