"""P2 Ticket BS — OTP label Mã thử (staging)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "otp.html"


class TestP2OtpPilotVi(unittest.TestCase):
    def test_label(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Mã thử (staging)", html)
        self.assertIn("\u00e3", html)
        self.assertIn("\u1eed", html)
        self.assertNotIn("Mã pilot (staging)", html)
        self.assertIn("Không hiện mã OTP.", html)
        self.assertIn("Xin mã rồi xác thực.", html)
        self.assertIn("d.pilot_code", html)
        self.assertIn("d.token", html)
        self.assertIn("welora_token", html)
        self.assertIn("/auth/otp/request", html)
        self.assertIn("<title>OTP điện thoại</title>", html)
        self.assertIn("<h1>OTP điện thoại</h1>", html)
        self.assertNotIn("innerHTML", html)
        for nid in (
            "navHome",
            "phone",
            "btnRequest",
            "phoneMasked",
            "pilotWrap",
            "pilotCode",
            "code",
            "btnVerify",
            "status",
            "otpErr",
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
