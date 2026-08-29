"""P2 Ticket BV — Pre-Rule placeholder tất tay ETF."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "prerule.html"


class TestP2PreruleAllinVi(unittest.TestCase):
    def test_placeholder(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('placeholder="Ví dụ: Tôi muốn tất tay ETF ngay"', html)
        self.assertIn("\u1ea5", html)
        self.assertNotIn("all-in", html)
        self.assertIn("<title>Pre-Rule · gỡ lỗi</title>", html)
        self.assertIn("<h1>Pre-Rule</h1>", html)
        self.assertIn("Deny trước LLM. Không hiện user_id.", html)
        self.assertIn("/auth/device", html)
        self.assertIn("/agent/pre-rule", html)
        self.assertIn("guardrail_result", html)
        self.assertIn("rule_hit", html)
        self.assertIn("should_call_llm", html)
        self.assertIn("safety_gate_status", html)
        self.assertIn("textContent", html)
        self.assertNotIn("innerHTML", html)
        for nid in (
            "navHome",
            "q",
            "go",
            "err",
            "guardrail",
            "ruleHit",
            "llmCalled",
            "gateStatus",
            "reply",
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
