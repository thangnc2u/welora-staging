"""P2 Ticket BZ — Pre-Rule muted mã tài khoản."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "prerule.html"


class TestP2PreruleUseridVi(unittest.TestCase):
    def test_muted(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Từ chối trước LLM. Không hiện mã tài khoản.", html)
        self.assertNotIn("Deny trước LLM", html)
        self.assertIn("\u00e3", html)
        self.assertIn("\u00e0", html)
        self.assertIn("\u1ea3", html)
        self.assertNotIn("Không hiện user_id.", html)
        self.assertIn("user_id", html)
        self.assertIn('placeholder="Ví dụ: Tôi muốn tất tay ETF ngay"', html)
        self.assertIn("<title>Pre-Rule · gỡ lỗi</title>", html)
        self.assertIn("<h1>Pre-Rule</h1>", html)
        self.assertIn("Chạy Pre-Rule", html)
        self.assertIn("/agent/pre-rule", html)
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
