"""P2 Ticket AO — health-score page Vietnamese copy + level map."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "healthscore.html"


class TestP2HealthscoreVi(unittest.TestCase):
    def test_copy_and_level_map(self):
        html = HTML.read_text(encoding="utf-8")
        for nid in ("navHome", "hsScore", "hsLevel", "hsBypassNote", "hsComponents", "hsErr"):
            self.assertIn(f'id="{nid}"', html)
        self.assertIn("welora_device_id", html)
        self.assertIn("Welora · Điểm sức khỏe", html)
        self.assertIn("<h1>Điểm sức khỏe</h1>", html)
        self.assertIn("Điểm không bypass Cổng An Toàn", html)
        self.assertIn("Không đọc được điểm sức khỏe", html)
        self.assertIn("critical:'Nguy cấp'", html)
        self.assertIn("low:'Thấp'", html)
        self.assertIn("moderate:'Trung bình'", html)
        self.assertIn("good:'Tốt'", html)
        self.assertIn("strong:'Vững'", html)
        self.assertIn("LEVELS[raw]||raw", html)
        self.assertIn("/ 1000", html)
        self.assertIn("/auth/device", html)
        self.assertIn("/health-score", html)
        self.assertIn("j.score", html)
        self.assertIn("j.level", html)
        self.assertIn("can_bypass_gate_with_score", html)
        self.assertIn("cashflow", html)
        self.assertIn("emergency_fund", html)
        self.assertIn("savings_invest_rate", html)
        self.assertIn("behavior_consistency", html)
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("<h1>Health Score</h1>", html)
        self.assertNotIn("Không đọc được Health Score", html)
        self.assertNotIn("\u1edf", html)
        self.assertIn("\u1ecf", html)

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
