"""P2-OS-18 Chat xóa ruleHit dead code."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "chat.html"


class TestP2OsChatRulehitDeadVi(unittest.TestCase):
    def test_no_rulehit(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertNotIn("const ruleHit=d.rule_hit;", html)
        self.assertNotIn("d.rule_hit", html)
        self.assertNotIn("ruleHit", html)
        self.assertNotIn("rule_hit", html)
        self.assertIn("d.guardrail_result==='deny'", html)
        self.assertIn("\\nTừ chối cứng", html)
        self.assertIn("'deny':'pass'", html)
        self.assertIn('id="denyCta"', html)
        self.assertIn("/agent/chat", html)
        self.assertIn("safety_gate_status", html)
        self.assertNotIn("innerHTML", html)
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
