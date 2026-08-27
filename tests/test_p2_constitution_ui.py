"""P2 Native UI /app/constitution — Hiến pháp, no JSON dump, no raw user id."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"


class TestP2ConstitutionUi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_get_app_constitution_200(self):
        r = self.client.get("/app/constitution")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('id="articles"', body)
        self.assertIn('id="navHome"', body)
        self.assertIn('href="/app"', body)
        self.assertIn("welora_device_id", body)
        self.assertNotIn("JSON.stringify(d)", body)
        self.assertNotIn("JSON.stringify(data)", body)
        self.assertNotIn("'user='+", body)
        self.assertNotIn("textContent=user_id", body)
        self.assertNotIn("textContent = user_id", body)

    def test_get_app_constitution_slash_200(self):
        r = self.client.get("/app/constitution/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="articles"', r.text)

    def test_home_has_nav_constitution(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        self.assertIn('id="navConstitution"', html)
        self.assertIn('href="/app/constitution"', html)

    def test_empty_state_vietnamese(self):
        html = (STATIC / "constitution.html").read_text(encoding="utf-8")
        self.assertIn("Chưa có Hiến pháp", html)
        self.assertNotIn("constitution_id", html)

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
