"""P2 Ticket AU — chat muted Vietnamese."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "chat.html"


class TestP2ChatMutedVi(unittest.TestCase):
    def test_muted(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Từ chối cứng trước LLM · An Toàn ≥ 3 tháng", html)
        self.assertIn("\u1eeb", html)
        self.assertIn("c\u1ee9ng", html)
        self.assertNotIn("Hard Deny trước LLM · An Toàn ≥ 3 tháng", html)
        self.assertIn("<h1>Chat với Agent</h1>", html)
        self.assertIn("Cổng: ĐẠT", html)
        self.assertIn("Cổng: CHƯA ĐẠT", html)
        for nid in ("navHome", "gateBadge", "denyCta", "log", "f", "q"):
            self.assertIn(f'id="{nid}"', html)
        self.assertIn("welora_device_id", html)
        self.assertIn("/agent/chat", html)
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
