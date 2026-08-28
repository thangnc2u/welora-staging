"""P2 Ticket BD — DNA onboarding copy → Bắt đầu."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "dna.html"


class TestP2DnaOnboardVi(unittest.TestCase):
    def test_copy(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Hồ sơ bạn khai khi Bắt đầu", html)
        self.assertIn("Hãy hoàn tất Bắt đầu rồi quay lại đây.", html)
        self.assertIn("\u1eaf", html)
        self.assertIn("\u1ea7", html)
        self.assertNotIn("onboarding", html)
        self.assertNotIn("Onboarding", html)
        self.assertIn("<h1>DNA tài chính</h1>", html)
        self.assertIn("<title>DNA tài chính</title>", html)
        self.assertIn("/dna", html)
        self.assertIn("/auth/device", html)
        self.assertIn("life_stage", html)
        self.assertIn("income_stability", html)
        self.assertIn("welora_device_id", html)
        self.assertIn("createElement", html)
        self.assertIn("textContent", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn('id="navHome"', html)
        self.assertIn('id="dna"', html)
        self.assertIn("emptyState", html)

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
