"""P2 Ticket AE — /app/safety Vietnamese copy, no hsBars innerHTML."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html"


class TestP2SafetyVi(unittest.TestCase):
    def test_vietnamese_copy_and_ids(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("CHƯA ĐẠT", html)
        self.assertIn("ĐẠT", html)
        self.assertIn("Điểm không bypass Cổng An Toàn", html)
        self.assertIn("Tạo quỹ khẩn cấp 3 tháng", html)
        self.assertNotIn("Tạo Goal quỹ 3 tháng", html)
        self.assertIn("Chi tiêu thiết yếu / tháng", html)
        self.assertIn("Học SAFE-02", html)
        self.assertIn("Chưa có quỹ khẩn cấp", html)
        self.assertNotIn("Chưa có Goal", html)
        self.assertIn('id="navHome"', html)
        self.assertIn("welora_device_id", html)
        self.assertIn('id="masteryState"', html)
        self.assertIn("not_started", html)
        self.assertIn("familiar", html)
        self.assertIn("apply", html)
        self.assertIn("mastered", html)
        self.assertIn("/users/", html)
        self.assertIn("/mastery", html)
        self.assertIn("PATCH", html)
        self.assertNotIn("CHUA DAT", html)
        self.assertNotIn("hsBars\").innerHTML", html)
        self.assertNotIn('hsBars").innerHTML', html)

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
