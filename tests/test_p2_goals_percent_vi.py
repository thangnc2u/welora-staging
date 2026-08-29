"""P2 Ticket CE — goals label Phần trăm."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "goals.html"


class TestP2GoalsPercentVi(unittest.TestCase):
    def test_label(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("line('Phần trăm', cur.percent)", html)
        self.assertIn("\u1ea7", html)
        self.assertIn("\u0103", html)
        self.assertNotIn("line('current.percent'", html)
        self.assertIn("cur.percent", html)
        self.assertIn("line('Tên quỹ', g.title||'Quỹ khẩn cấp')", html)
        self.assertIn("line('Loại quỹ', g.type||'')", html)
        self.assertIn("line('Tháng chi mục tiêu', tgt.months_of_expense)", html)
        self.assertIn("line('Số dư hiện tại', cur.amount)", html)
        self.assertIn("line('current.months_covered'", html)
        self.assertNotIn("innerHTML", html)
        for nid in ("navHome", "goalList", "addBox", "addAmount", "addBtn", "addErr"):
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
