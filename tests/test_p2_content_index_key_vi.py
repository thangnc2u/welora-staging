"""P2 Ticket BM — content index badge danh sách."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "content.html"


class TestP2ContentIndexKeyVi(unittest.TestCase):
    def test_index_key(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("elKey.textContent='danh sách'", html)
        self.assertIn("s\u00e1ch", html)
        self.assertNotIn("elKey.textContent='index'", html)
        self.assertIn("elTitle.textContent='Welorapedia'", html)
        self.assertIn("elKey.textContent=d.principle_key||key", html)
        self.assertIn("i.principle_key", html)
        self.assertIn("+' · '+", html)
        self.assertIn("unknown principle_key", html)
        self.assertIn("← Chat với Agent", html)
        self.assertIn("An Toàn", html)
        self.assertIn("<title>Welora · Nội dung</title>", html)
        self.assertIn("/content", html)
        self.assertNotIn("innerHTML", html)
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
