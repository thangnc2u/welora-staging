"""P2 Ticket AJ — onboarding option labels Vietnamese, values unchanged."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "onboarding.html"

VALUES = (
    "young_single",
    "family",
    "stable",
    "variable",
    "alone",
    "with_family",
    "hold",
    "spend",
    "safety",
    "debt",
    "advisor_only",
)
LABELS = (
    "Độc thân trẻ",
    "Gia đình",
    "Ồn định",
    "Không ổn định",
    "Sống một mình",
    "Sống cùng gia đình",
    "Giữ",
    "Tiêu",
    "An Toàn",
    "Trả nợ",
    "Chỉ tư vấn",
)


class TestP2OnboardingVi(unittest.TestCase):
    def test_labels_and_values(self):
        html = HTML.read_text(encoding="utf-8")
        for v in VALUES:
            self.assertIn(f'value="{v}"', html)
        for lab in LABELS:
            self.assertIn(lab, html)
        self.assertIn("selectedOptions[0].text", html)
        self.assertNotIn("Life stage:", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn('id="navHome"', html)
        self.assertIn("welora_device_id", html)
        self.assertIn("/onboarding/session/", html)
        self.assertIn("step/1", html)
        self.assertIn("type:'emergency_fund'", html)
        self.assertIn("linked_from_onboarding:true", html)
        self.assertIn('id="ctaGoal"', html)
        self.assertIn('id="step0"', html)
        self.assertIn('id="step5"', html)

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
