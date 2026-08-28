"""P2 Ticket AY — metrics title Vietnamese."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "metrics.html"


class TestP2MetricsTitleVi(unittest.TestCase):
    def test_title(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("<title>Welora · Chỉ số</title>", html)
        self.assertIn("<h1>Chỉ số</h1>", html)
        self.assertIn("\u1ec9", html)
        self.assertIn("s\u1ed1", html)
        self.assertNotIn("Ch\u1ed5 s\u1ed1", html)
        self.assertNotIn("Welora Metrics", html)
        self.assertIn("fetch('/metrics')", html)
        self.assertIn("textContent", html)
        self.assertNotIn("innerHTML", html)
        for nid in ("navHome", "mDenyLlm", "mGateMonths", "mHardDeny", "mChatTotal", "mDenyTotal", "mErr"):
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
