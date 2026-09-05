"""P2 UX — Welorapedia markdown reader."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "content.html"


class TestP2UxPediaReader(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.html = HTML.read_text(encoding="utf-8")

    def test_no_raw_textcontent_body(self):
        self.assertNotIn("elBody.textContent=d.body_markdown", self.html)
        self.assertNotIn("white-space:pre-wrap", self.html)
        self.assertIn("function stripFrontmatter", self.html)
        self.assertIn("function renderMarkdown", self.html)
        self.assertIn("renderMarkdown(elBody, stripFrontmatter", self.html)

    def test_strips_editorial_and_renders_subset(self):
        self.assertIn("principle_key", self.html)
        self.assertIn("createElement('h2')", self.html)
        self.assertIn("createElement('h3')", self.html)
        self.assertIn("createElement('p')", self.html)
        self.assertIn("createElement('strong')", self.html)
        self.assertIn("createElement('em')", self.html)
        self.assertIn("createElement('ul')", self.html)
        self.assertIn("createElement('ol')", self.html)
        self.assertIn("createElement('hr')", self.html)
        self.assertIn("function isSafeHref", self.html)

    def test_keeps_chrome(self):
        self.assertIn("contentTitle", self.html)
        self.assertIn("govMeta", self.html)
        self.assertIn("ctaAcademy", self.html)
        self.assertIn("Welorademy", self.html)
        self.assertNotIn("Welora Academy", self.html)

    def test_page_and_health(self):
        r = self.client.get("/app/content")
        self.assertEqual(r.status_code, 200)
        self.assertIn("renderMarkdown", r.text)
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
