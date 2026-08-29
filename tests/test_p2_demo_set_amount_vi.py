"""P2 Ticket BW — demo step6 Nạp quỹ display."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "demo.html"


class TestP2DemoSetAmountVi(unittest.TestCase):
    def test_step6(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn(
            "setStep(6,'Nạp quỹ = 3 × 10.000.000 = 30.000.000 · HTTP '+r.status,'ok');",
            html,
        )
        self.assertIn("\u1ea1", html)
        self.assertIn("\u1ef9", html)
        self.assertIn("\u00d7", html)
        self.assertIn("\u00b7", html)
        self.assertNotIn("set_amount = 3 × 10.000.000 = 30.000.000", html)
        self.assertIn("set_amount:30000000", html)
        self.assertIn("<h2>6 · Nạp quỹ 3 tháng</h2>", html)
        self.assertIn("<h2>5 · Deny (tất tay ETF)</h2>", html)
        self.assertIn("Tôi muốn all-in ETF ngay", html)
        self.assertIn("function setStep", html)
        self.assertIn("textContent", html)
        self.assertNotIn("innerHTML", html)
        for nid in ("navHome", "run", "step1", "step2", "step3", "step4", "step5", "step6", "step7", "step8"):
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
