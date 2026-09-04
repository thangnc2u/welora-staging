"""P2 UX — onboarding CTA Goal treats 409 as already-has quỹ."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "onboarding.html"


class TestP2OsOnboardingGoalCta409(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.html = HTML.read_text(encoding="utf-8")

    def test_cta_disables_while_calling(self):
        self.assertIn('id="ctaGoal"', self.html)
        self.assertIn("ctaBusy", self.html)
        self.assertIn("btn.disabled=true", self.html)
        self.assertIn("btn.disabled=false", self.html)

    def test_409_redirects_like_success(self):
        self.assertIn("r.status===409", self.html)
        self.assertIn("/app/safety?user_id=", self.html)
        self.assertIn("if(r.ok || r.status===409)", self.html)

    def test_other_error_shows_json_detail(self):
        self.assertIn("body.detail", self.html)
        self.assertIn("body.error", self.html)
        self.assertIn("Không tạo được quỹ khẩn cấp", self.html)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        b = self.client.get("/health").json()
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        r = self.client.get("/app/onboarding")
        self.assertEqual(r.status_code, 200)
        self.assertIn("ctaGoal", r.text)


if __name__ == "__main__":
    unittest.main()
