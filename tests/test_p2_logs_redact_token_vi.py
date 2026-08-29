"""P2 Ticket CU — logs UI redact token [ĐÃ ẨN]."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "logs.html"


class TestP2LogsRedactTokenVi(unittest.TestCase):
    def test_token(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("'[ĐÃ ẨN]'", html)
        self.assertIn("\\[REDACTED\\]/g,'[ĐÃ ẨN]'", html)
        self.assertIn("\u0110", html)
        self.assertIn("\u00c3", html)
        self.assertIn("\u1ea8", html)
        self.assertNotIn("'[REDACTED]'", html)
        self.assertNotIn("[REDACTED]", html)
        self.assertIn("function redact", html)
        self.assertIn("(?:\\+84|0)", html)
        self.assertIn("Bearer", html)
        self.assertIn("sk-|xai-|ghp_|github_pat_", html)
        self.assertIn("<title>Welora · Nhật ký quyết định</title>", html)
        self.assertIn("<h1>Nhật ký quyết định</h1>", html)
        self.assertIn("Deny · luật · gọi LLM · không lộ id", html)
        self.assertIn("'Kết quả'", html)
        self.assertIn("'Luật'", html)
        self.assertIn("'Gọi LLM'", html)
        self.assertIn("'Cổng'", html)
        self.assertIn("'Câu hỏi'", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn('id="navHome"', html)
        self.assertIn('id="logList"', html)
        self.assertIn('id="logErr"', html)

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
