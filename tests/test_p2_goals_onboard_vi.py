"""P2 Ticket BE — goals empty CTA Bắt đầu."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "goals.html"


class TestP2GoalsOnboardVi(unittest.TestCase):
    def test_copy(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Đi Bắt đầu để tạo quỹ 3 tháng", html)
        self.assertIn("\u1eaf", html)
        self.assertIn("\u1ea7", html)
        self.assertNotIn("Đi Onboarding", html)
        self.assertNotIn("Onboarding để", html)
        self.assertIn("ctaOnboarding", html)
        self.assertIn("/app/onboarding", html)
        self.assertIn("<h1>Quỹ khẩn cấp</h1>", html)
        self.assertIn("<title>Quỹ khẩn cấp</title>", html)
        self.assertIn("Mục tiêu 3 tháng chi thiết yếu", html)
        self.assertIn("/goals", html)
        self.assertIn("/progress", html)
        self.assertIn("welora_device_id", html)
        self.assertIn("textContent", html)
        self.assertIn("createElement", html)
        self.assertNotIn("innerHTML", html)
        for nid in ("navHome", "goalList", "addBox", "addAmount", "addBtn", "addErr"):
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
