"""P2 Ticket AX — safety Checklist/Health Score section titles Vietnamese."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html"


class TestP2SafetyHsVi(unittest.TestCase):
    def test_section_titles(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn(">Danh sách<", html)
        self.assertIn(">Điểm sức khỏe<", html)
        self.assertIn("\u00e1ch", html)
        self.assertIn("\u1ec3", html)
        self.assertIn("s\u1ee9c", html)
        self.assertIn("kh\u1ecfe", html)
        self.assertNotIn("kh\u1edfe", html)
        self.assertNotIn("Checklist", html)
        self.assertNotIn("Health Score", html)
        self.assertIn("<h1>An Toàn</h1>", html)
        self.assertIn("Goal quỹ", html)
        self.assertIn("Điểm không bypass Cổng An Toàn", html)
        self.assertIn("CHƯA ĐẠT", html)
        self.assertIn("ĐẠT", html)
        self.assertIn("Làm chủ · —", html)
        self.assertIn("Đạt cổng: chưa", html)
        self.assertNotIn("meets_gate: false", html)
        self.assertIn('value="not_started"', html)
        self.assertIn('value="apply"', html)
        self.assertIn("/mastery", html)
        self.assertNotIn("innerHTML", html)
        for nid in (
            "navHome", "gateCard", "gateStatus", "masteryBadge", "masteryStatus",
            "masteryState", "hsCard", "hsScore", "hsBars", "essential",
            "btnCreate", "amount", "btnSave",
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
