"""P2 Ticket AM — metrics page Vietnamese labels, JSON keys unchanged."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "metrics.html"


class TestP2MetricsVi(unittest.TestCase):
    def test_labels_and_ids(self):
        html = HTML.read_text(encoding="utf-8")
        for nid in ("mDenyLlm", "mGateMonths", "mHardDeny", "mChatTotal", "mDenyTotal", "mErr", "navHome"):
            self.assertIn(f'id="{nid}"', html)
        self.assertIn("<h1>Chỉ số</h1>", html)
        self.assertIn("Từ chối có gọi LLM", html)
        self.assertIn("Cổng (tháng)", html)
        self.assertIn("Từ chối cứng", html)
        self.assertIn("Tổng chat", html)
        self.assertIn("Tổng từ chối", html)
        self.assertIn("Từ chối cứng không gọi LLM · Từ chối có gọi LLM phải = 0", html)
        self.assertNotIn(">Hard Deny<", html)
        self.assertNotIn("Tổng deny", html)
        self.assertIn("d.deny_with_llm_calls", html)
        self.assertIn("d.gate_months", html)
        self.assertIn("d.hard_deny", html)
        self.assertIn("d.chat_total", html)
        self.assertIn("d.deny_total", html)
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("<h1>Metrics</h1>", html)

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
