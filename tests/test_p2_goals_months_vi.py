"""P2 Ticket CC — goals label Tháng chi mục tiêu."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "goals.html"


class TestP2GoalsMonthsVi(unittest.TestCase):
    def test_label(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("line('Tháng chi mục tiêu', tgt.months_of_expense)", html)
        self.assertIn("\u00e1", html)
        self.assertIn("\u1ee5", html)
        self.assertIn("\u00ea", html)
        self.assertNotIn("line('target.months_of_expense'", html)
        self.assertIn("tgt.months_of_expense", html)
        self.assertIn("line('Tên quỹ', g.title||'Quỹ khẩn cấp')", html)
        self.assertIn("line('Loại quỹ', g.type||'')", html)
        self.assertIn("line('current.amount'", html)
        self.assertIn("<title>Quỹ khẩn cấp</title>", html)
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
