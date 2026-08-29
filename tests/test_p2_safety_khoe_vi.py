"""P2 Ticket CT — safety section-title Điểm sức khỏe (ỏ U+1ECF)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html"


class TestP2SafetyKhoeVi(unittest.TestCase):
    def test_section_title(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('<div class="section-title">Điểm sức khỏe</div>', html)
        self.assertIn("\u1ecf", html)
        self.assertIn("\u1ec3", html)
        self.assertIn("\u1ee9", html)
        self.assertNotIn("Điểm sức khởe", html)
        self.assertNotIn("khởe", html)
        self.assertNotIn("\u1edf", html)
        self.assertIn('<div class="section-title">Danh sách</div>', html)
        self.assertIn('<div class="section-title">Goal quỹ</div>', html)
        self.assertIn("<title>Welora · An Toàn</title>", html)
        self.assertIn("<h1>An Toàn</h1>", html)
        self.assertIn("Điểm không bypass Cổng An Toàn", html)
        self.assertIn('value="not_started"', html)
        self.assertIn('value="apply"', html)
        self.assertNotIn("innerHTML", html)
        for nid in (
            "navHome", "gateCard", "gateStatus", "gateMeta", "masteryBadge",
            "masteryStatus", "masteryMeta", "masteryState", "hsCard", "hsScore",
            "hsBars", "barFill", "goalMeta", "essential", "btnCreate", "amount", "btnSave",
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
