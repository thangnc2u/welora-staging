"""P2 Native UI /app/goals — quỹ khẩn cấp, no JSON dump, no raw ids."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"


class TestP2GoalsUi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_get_app_goals_200(self):
        r = self.client.get("/app/goals")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('id="goalList"', body)
        self.assertIn('id="navHome"', body)
        self.assertIn('href="/app"', body)
        self.assertIn('id="addAmount"', body)
        self.assertIn('id="addBtn"', body)
        self.assertIn("ctaOnboarding", body)
        self.assertIn("welora_device_id", body)
        self.assertIn("Chưa có quỹ khẩn cấp", body)
        self.assertIn("add_amount", body)
        self.assertNotIn("JSON.stringify(d)", body)
        self.assertNotIn("JSON.stringify(data)", body)
        self.assertNotIn("textContent=user_id", body)
        self.assertNotIn("textContent=goal_id", body)
        self.assertNotIn('name="months"', body)

    def test_get_app_goals_slash_200(self):
        r = self.client.get("/app/goals/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="goalList"', r.text)

    def test_home_has_nav_goals(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        self.assertIn('id="navGoals"', html)
        self.assertIn('href="/app/goals"', html)

    def test_no_create_goal_from_page(self):
        html = (STATIC / "goals.html").read_text(encoding="utf-8")
        self.assertEqual(html.count("method:'POST'"), 1)
        self.assertIn("Chưa có quỹ khẩn cấp", html)
        self.assertIn("ctaOnboarding", html)
        self.assertIn("/app/onboarding", html)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
