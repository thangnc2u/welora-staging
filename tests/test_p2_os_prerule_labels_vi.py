"""P2-OS-17 Pre-Rule nhãn + value VI."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "prerule.html"


class TestP2OsPreruleLabelsVi(unittest.TestCase):
    def test_labels_and_maps(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn(">Kết quả</div>", html)
        self.assertIn(">Luật</div>", html)
        self.assertIn(">Gọi LLM</div>", html)
        self.assertIn(">Cổng</div>", html)
        self.assertIn(">Phản hồi</div>", html)
        self.assertNotIn(">guardrail_result</div>", html)
        self.assertNotIn(">rule_hit</div>", html)
        self.assertNotIn(">should_call_llm</div>", html)
        self.assertNotIn(">safety_gate_status</div>", html)
        self.assertNotIn(">reply</div>", html)
        self.assertIn("d.guardrail_result", html)
        self.assertIn("d.rule_hit", html)
        self.assertIn("d.should_call_llm", html)
        self.assertIn("d.safety_gate_status", html)
        self.assertIn("d.reply", html)
        self.assertIn("'Từ chối cứng'", html)
        self.assertIn("'Cho qua'", html)
        self.assertIn("'Cảnh báo nhẹ'", html)
        self.assertIn("'\u0110\u1ea0T'", html)
        self.assertIn("'CH\u01afA \u0110\u1ea0T'", html)
        self.assertIn("'Có'", html)
        self.assertIn("'Không'", html)
        self.assertIn('id="guardrail"', html)
        self.assertIn('id="ruleHit"', html)
        self.assertIn('id="llmCalled"', html)
        self.assertIn('id="gateStatus"', html)
        self.assertIn('id="reply"', html)
        self.assertIn("<title>Pre-Rule · gỡ lỗi</title>", html)
        self.assertIn("<h1>Pre-Rule</h1>", html)
        self.assertIn("Chạy Pre-Rule", html)
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
