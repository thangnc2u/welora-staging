"""P2 Native UI /app/dna — DNA tài chính, no JSON dump, no raw ids."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"


class TestP2DnaUi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_get_app_dna_200(self):
        r = self.client.get("/app/dna")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('id="dna"', body)
        self.assertIn('id="navHome"', body)
        self.assertIn('href="/app"', body)
        self.assertIn("welora_device_id", body)
        self.assertIn("life_stage", body)
        self.assertIn("income_stability", body)
        self.assertIn("essential_expense_monthly", body)
        self.assertIn("agent_role_preference", body)
        self.assertNotIn("JSON.stringify(d)", body)
        self.assertNotIn("JSON.stringify(data)", body)
        self.assertNotIn("'user='+", body)
        self.assertNotIn("textContent=user_id", body)
        self.assertNotIn("dna_id", body)
        self.assertIn("pick(psy,'surplus_habit')", body)
        self.assertIn("pick(psy,'agent_role_preference')", body)
        self.assertNotIn("pick(beh,'surplus_habit')", body)
        self.assertNotIn("desired_role", body)

    def test_get_app_dna_slash_200(self):
        r = self.client.get("/app/dna/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="dna"', r.text)

    def test_home_has_nav_dna(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        self.assertIn('id="navDna"', html)
        self.assertIn('href="/app/dna"', html)

    def test_empty_state_vietnamese(self):
        html = (STATIC / "dna.html").read_text(encoding="utf-8")
        self.assertIn("Chưa có DNA", html)

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
