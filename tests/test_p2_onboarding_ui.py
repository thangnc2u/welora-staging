"""P2 Native UI /app/onboarding — B0–B5 + ctaGoal, no months < 3."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

OB_HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "onboarding.html"


class TestP2OnboardingUi(unittest.TestCase):
    def test_onboarding_html_has_steps_and_cta(self):
        html = OB_HTML.read_text(encoding="utf-8")
        for i in range(6):
            self.assertIn(f'id="step{i}"', html)
        self.assertIn('id="ctaGoal"', html)
        self.assertIn("emergency_fund", html)
        self.assertIn("linked_from_onboarding", html)
        self.assertIn("/app/safety", html)
        self.assertNotIn('<pre id="out"', html)

    def test_ui_has_no_months_target_below_three(self):
        html = OB_HTML.read_text(encoding="utf-8")
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertNotRegex(html, r'id=["\']months["\']')
        self.assertNotRegex(html, r'name=["\']months["\']')
        self.assertNotRegex(html, r'target_months')
        self.assertIn("3 tháng", html)

    def test_health_untouched(self):
        client = TestClient(create_app())
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
