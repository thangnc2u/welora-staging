"""P2 Ticket CA — goals label Tên quỹ."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "goals.html"


class TestP2GoalsTitleVi(unittest.TestCase):
    def test_label(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("line('Tên quỹ', g.title||'Quỹ khẩn cấp')", html)
        self.assertIn("\u00ea", html)
        self.assertIn("\u1ef9", html)
        self.assertNotIn("line('title'", html)
        self.assertIn("g.title", html)
        self.assertIn("<title>Quỹ khẩn cấp</title>", html)
        self.assertIn("<h1>Quỹ khẩn cấp</h1>", html)
        self.assertIn("Mục tiêu 3 tháng chi thiết yếu", html)
        self.assertIn("Chưa có quỹ khẩn cấp", html)
        self.assertIn("Đi Bắt đầu để tạo quỹ 3 tháng", html)
        self.assertIn("line('type'", html)
        self.assertIn("add_amount", html)
        self.assertIn("goal_id", html)
        self.assertNotIn("innerHTML", html)
        for nid in (
            "navHome",
            "goalList",
            "addBox",
            "addAmount",
            "addBtn",
            "addErr",
        ):
            self.assertIn(f'id="{nid}"', html)
        self.assertIn("ctaOnboarding", html)

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
