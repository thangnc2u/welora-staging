"""P2 UX — Welorapedia list/reader titles VI (tag, no key · title)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "content.html"


class TestP2UxPediaTitlesVi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.html = HTML.read_text(encoding="utf-8")

    def test_no_key_dot_title_list_concat(self):
        # Must not build list link text as principle_key · title
        self.assertNotIn("principle_key||'')+' · '", self.html)
        self.assertNotIn("(i.principle_key||'')+' · '+(i.title||'')", self.html)
        self.assertIn("a.textContent=i.title||''", self.html)

    def test_vi_tag_map(self):
        self.assertIn("An toàn", self.html)
        self.assertIn("Nợ", self.html)
        self.assertIn("Cốt lõi", self.html)
        self.assertIn("function viTag", self.html)
        self.assertIn("SAFE-", self.html)
        self.assertIn("DEBT-", self.html)
        self.assertIn("CORE-", self.html)
        self.assertIn("className='tag'", self.html)

    def test_page_and_health(self):
        r = self.client.get("/app/content")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
