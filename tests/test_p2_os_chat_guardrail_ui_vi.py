"""P2-OS-10 Chat ẩn guardrail raw trong bubble."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "chat.html"


class TestP2OsChatGuardrailUiVi(unittest.TestCase):
    def test_bubble_no_raw_guardrail(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertNotIn("'\\n['+", html)
        self.assertNotIn('"\\n["+', html)
        self.assertNotIn("+' · '+", html)
        self.assertNotIn("+" · "+", html)
        self.assertNotIn("' · '+", html)
        self.assertIn("Từ chối cứng", html)
        self.assertIn("d.guardrail_result==='deny'", html)
        self.assertIn("d.rule_hit", html)
        self.assertIn('id="denyCta"', html)
        self.assertIn("/app/content?key=SAFE-02", html)
        self.assertIn("'deny':'pass'", html)
        self.assertIn("welora_device_id", html)
        self.assertNotIn("innerHTML", html)

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
