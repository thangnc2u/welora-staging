"""P2 Native UI /app/otp — OTP phone, no JSON dump, no raw secrets."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"


class TestP2OtpUi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_get_app_otp_200(self):
        r = self.client.get("/app/otp")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('id="phone"', body)
        self.assertIn('id="btnRequest"', body)
        self.assertIn('id="phoneMasked"', body)
        self.assertIn('id="pilotCode"', body)
        self.assertIn('id="code"', body)
        self.assertIn('id="btnVerify"', body)
        self.assertIn('id="status"', body)
        self.assertIn('id="navHome"', body)
        self.assertIn("Đã xác thực", body)
        self.assertNotIn("JSON.stringify(d)", body)
        self.assertNotIn("JSON.stringify(data)", body)
        self.assertNotIn("textContent=user_id", body)
        self.assertNotIn("textContent=token", body)
        self.assertNotIn("textContent=challenge_id", body)
        self.assertNotIn("textContent=challenge", body)

    def test_get_app_otp_slash_200(self):
        r = self.client.get("/app/otp/")
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="phone"', r.text)

    def test_home_has_nav_otp(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        self.assertIn('id="navOtp"', html)
        self.assertIn('href="/app/otp"', html)

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
