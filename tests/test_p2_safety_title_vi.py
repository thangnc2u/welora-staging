"""P2 Ticket BG — safety title Welora · An Toàn."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html"


class TestP2SafetyTitleVi(unittest.TestCase):
    def test_title(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("<title>Welora · An Toàn</title>", html)
        self.assertIn("\u00b7", html)
        self.assertIn("To\u00e0n", html)
        self.assertNotIn("<title>Welora — An Toàn</title>", html)
        self.assertNotIn("<title>Welora - An Toàn</title>", html)
        self.assertIn("<h1>An Toàn</h1>", html)
        self.assertIn("Làm chủ ·", html)
        self.assertIn("meets_gate", html)
        self.assertIn("Danh sách", html)
        self.assertIn("Mục tiêu", html)
        self.assertIn("Điểm không bỏ qua Cổng An Toàn", html)
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
