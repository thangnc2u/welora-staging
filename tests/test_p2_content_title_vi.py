"""P2 Ticket BF — content title Welora · Nội dung."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "content.html"


class TestP2ContentTitleVi(unittest.TestCase):
    def test_title(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("<title>Welora · Nội dung</title>", html)
        self.assertIn("\u00b7", html)
        self.assertIn("N\u1ed9i dung", html)
        self.assertNotIn("<title>Welora — Nội dung</title>", html)
        self.assertNotIn("<title>Welora - Nội dung</title>", html)
        self.assertIn("Welorapedia · principle_key", html)
        self.assertIn("/content", html)
        self.assertIn("principle_key", html)
        self.assertIn("textContent", html)
        self.assertIn("createElement", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn("/app/chat", html)
        self.assertIn("/app/safety", html)
        for nid in ("navHome", "contentKey", "contentTitle", "contentBody"):
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
