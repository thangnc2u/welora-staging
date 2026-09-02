"""P2 Native UI /app/parser — suggestion + categories, no JSON dump."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

PARSER_HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "parser.html"


class TestP2ParserUi(unittest.TestCase):
    def test_parser_html_ids_no_category_json_dump(self):
        html = PARSER_HTML.read_text(encoding="utf-8")
        self.assertIn('id="csv"', html)
        self.assertIn('id="go"', html)
        self.assertIn('id="out"', html)
        self.assertIn('id="suggestionEssential"', html)
        self.assertIn('id="categories"', html)
        self.assertIn('id="goalDraft"', html)
        self.assertIn('id="createGoalBtn"', html)
        self.assertNotIn("JSON.stringify(j.category_counts)", html)
        self.assertIn("/app/safety", html)
        self.assertIn("không", html)
        self.assertIn("bỏ qua Cổng", html)
        self.assertNotIn("bypass Cổng", html)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        client = TestClient(create_app())
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
