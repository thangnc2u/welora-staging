"""P2 Ticket CV — safety masteryMeta Đạt cổng: chưa."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html"


class TestP2SafetyMeetsGateVi(unittest.TestCase):
    def test_chrome(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('id="masteryMeta">Đạt cổng: chưa</div>', html)
        self.assertIn('textContent="Đạt cổng: "+(ok?"đạt":"chưa")', html)
        self.assertIn("\u0110", html)
        self.assertIn("\u1ea1", html)
        self.assertIn("\u1ed5", html)
        self.assertIn("\u01b0", html)
        self.assertIn("\u0111", html)
        self.assertNotIn("meets_gate: false", html)
        self.assertNotIn('textContent="meets_gate:', html)
        self.assertIn("meets_gate:false", html)
        self.assertIn("state.mastery.meets_gate", html)
        self.assertIn("Làm chủ · —", html)
        self.assertIn('"Làm chủ · "+(st==="not_started"?"Chưa bắt đầu":st)', html)
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
