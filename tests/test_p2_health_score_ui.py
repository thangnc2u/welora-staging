"""P2 Ticket AD — Native UI /app/health-score."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HS = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "healthscore.html"
HOME = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "home.html"
SAFETY = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html"


class TestP2HealthScoreUi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_app_health_score_html(self):
        r = self.client.get("/app/health-score")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('id="navHome"', body)
        self.assertIn('href="/app"', body)
        self.assertIn("welora_device_id", body)
        self.assertIn('id="hsScore"', body)
        self.assertIn('id="hsLevel"', body)
        self.assertIn("Điểm không bypass Cổng An Toàn", body)
        self.assertNotIn("innerHTML", body)
        self.assertNotIn("JSON.stringify(j)", body)

    def test_home_nav_health(self):
        html = HOME.read_text(encoding="utf-8")
        self.assertIn('id="navHealth"', html)
        self.assertIn("/app/health-score", html)

    def test_safety_mastery_untouched(self):
        html = SAFETY.read_text(encoding="utf-8")
        self.assertIn("masteryState", html)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
