"""P2 Ticket BB — home muted giao diện gốc."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "home.html"


class TestP2HomeMutedVi(unittest.TestCase):
    def test_muted(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("An Toàn trước · giao diện gốc", html)
        self.assertIn("An Toàn trước", html)
        self.assertIn("\u1ec7n", html)
        self.assertIn("g\u1ed1c", html)
        self.assertNotIn("Native UI", html)
        self.assertIn("<h1>Welora</h1>", html)
        self.assertIn("<title>Welora</title>", html)
        self.assertNotIn("innerHTML", html)
        for nid in (
            "navOnboarding", "navSafety", "navChat", "navContent", "navDemo",
            "navParser", "navMetrics", "navLogs", "navConstitution", "navDna",
            "navGoals", "navOtp", "navPreRule", "navHealth",
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
