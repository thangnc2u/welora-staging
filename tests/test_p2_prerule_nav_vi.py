"""P2 Ticket AT — Pre-Rule nav/title gỡ lỗi."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HOME = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "home.html"
PRE = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "prerule.html"


class TestP2PreruleNavVi(unittest.TestCase):
    def test_labels(self):
        home = HOME.read_text(encoding="utf-8")
        pre = PRE.read_text(encoding="utf-8")
        self.assertIn('id="navPreRule"', home)
        self.assertIn('href="/app/pre-rule"', home)
        self.assertIn("Pre-Rule · gỡ lỗi", home)
        self.assertIn("<title>Pre-Rule · gỡ lỗi</title>", pre)
        self.assertIn("<h1>Pre-Rule</h1>", pre)
        self.assertIn("Chạy Pre-Rule", pre)
        self.assertIn("\u1ee1", home)
        self.assertIn("\u1ed7", home)
        self.assertIn("\u1ee1", pre)
        self.assertIn("\u1ed7", pre)
        self.assertNotIn("Pre-Rule debug", home)
        self.assertNotIn("Pre-Rule debug", pre)
        self.assertNotIn("g\u1ecf", home + pre)
        for nid in ("navHome", "q", "go", "err", "guardrail", "ruleHit", "llmCalled", "gateStatus", "reply"):
            self.assertIn(f'id="{nid}"', pre)
        self.assertIn("guardrail_result", pre)
        self.assertIn("rule_hit", pre)
        self.assertIn("should_call_llm", pre)
        self.assertIn("safety_gate_status", pre)
        self.assertNotIn("innerHTML", home)
        self.assertNotIn("innerHTML", pre)

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
