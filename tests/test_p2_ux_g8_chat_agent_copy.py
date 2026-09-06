"""P2 UX G8 — user-facing Chat với Agent."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"


class TestP2UxG8ChatAgentCopy(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_static_no_tro_ly_ai(self):
        for name in ("shell.js", "chat.html"):
            text = (STATIC / name).read_text(encoding="utf-8")
            self.assertNotIn("Trợ lý AI", text, name)
            self.assertIn("Chat với Agent", text, name)

    def test_chat_page(self):
        r = self.client.get("/app/chat")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Chat với Agent", r.text)
        self.assertNotIn("Trợ lý AI", r.text)
        self.assertNotIn('id="gateBadge"', r.text)
        self.assertIn("/agent/chat", r.text)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        b = self.client.get("/health").json()
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
