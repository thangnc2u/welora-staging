"""P2 Ticket AF — parser #categories without innerHTML."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "parser.html"


class TestP2ParserNoInnerHtml(unittest.TestCase):
    def test_parser_html_no_innerhtml(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('id="categories"', html)
        self.assertIn('id="suggestionEssential"', html)
        self.assertIn('id="goalDraft"', html)
        self.assertIn('id="createGoalBtn"', html)
        self.assertIn('id="navHome"', html)
        self.assertIn("welora_device_id", html)
        self.assertIn("createElement", html)
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("JSON.stringify(j.category_counts)", html)
        go_idx = html.find("document.getElementById('go')")
        btn_idx = html.find("document.getElementById('createGoalBtn')")
        self.assertGreater(go_idx, 0)
        self.assertGreater(btn_idx, go_idx)
        go_block = html[go_idx:btn_idx]
        self.assertNotIn('fetch("/goals"', go_block)
        self.assertNotIn("fetch('/goals'", go_block)

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
