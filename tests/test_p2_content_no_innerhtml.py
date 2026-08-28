"""P2 Ticket AG — content index without innerHTML."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "content.html"


class TestP2ContentNoInnerHtml(unittest.TestCase):
    def test_content_html_no_innerhtml(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('id="contentKey"', html)
        self.assertIn('id="contentTitle"', html)
        self.assertIn('id="contentBody"', html)
        self.assertIn('id="navHome"', html)
        self.assertIn("createElement", html)
        self.assertIn("encodeURIComponent", html)
        self.assertIn("textContent", html)
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("JSON.stringify", html)

    def test_app_content_200(self):
        r = TestClient(create_app()).get("/app/content")
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="contentBody"', r.text)
        self.assertNotIn("innerHTML", r.text)

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
