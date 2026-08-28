"""P2 Ticket AN — logs page Vietnamese labels, API fields + redact unchanged."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "logs.html"


class TestP2LogsVi(unittest.TestCase):
    def test_labels_ids_redact(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('id="navHome"', html)
        self.assertIn('id="logList"', html)
        self.assertIn('id="logErr"', html)
        self.assertIn("welora_device_id", html)
        self.assertIn("<h1>Nhật ký quyết định</h1>", html)
        self.assertIn("Deny · luật · gọi LLM · không lộ id", html)
        self.assertIn("'Kết quả'", html)
        self.assertIn("'Luật'", html)
        self.assertIn("'Gọi LLM'", html)
        self.assertIn("'Cổng'", html)
        self.assertIn("'Câu hỏi'", html)
        self.assertIn("row.guardrail_result", html)
        self.assertIn("row.rule_hit", html)
        self.assertIn("row.llm_called", html)
        self.assertIn("row.safety_gate_status", html)
        self.assertIn("row.user_query_summary", html)
        self.assertIn("/agent/decision-logs?user_id=", html)
        self.assertIn("data.items", html)
        self.assertIn("Bearer", html)
        self.assertIn("sk-", html)
        self.assertIn("xai-", html)
        self.assertIn("[REDACTED]", html)
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("<h1>Decision logs</h1>", html)
        self.assertNotIn("textContent=...user_id", html)

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
