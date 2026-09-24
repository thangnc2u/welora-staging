"""P2 hotfix — P2 parser dark-first + content max-width 480.

CSS/chrome only. Does not touch Hard Deny · TARGET_MONTHS / gate_months · APIs · P1 shell.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("WELORA_STORE", "memory")

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.fixtures import reset_all_stores
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
PARSER_HTML = (ROOT / "welora" / "api" / "static" / "parser.html").read_text(
    encoding="utf-8"
)
CONTENT_HTML = (ROOT / "welora" / "api" / "static" / "content.html").read_text(
    encoding="utf-8"
)


class TestP2HotfixP2ParserContentChrome(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def setUp(self) -> None:
        reset_all_stores()

    def test_parser_no_light_theme_fills(self):
        self.assertNotIn("#f6f7f9", PARSER_HTML)
        # Primary body/card fills must use dark tokens, not light #fff card fill
        body = re.search(r"body\s*\{([^}]+)\}", PARSER_HTML, flags=re.S)
        self.assertIsNotNone(body, msg="parser body rule missing")
        body_css = body.group(1)
        self.assertIn("--bg-app", body_css)
        self.assertNotRegex(body_css, r"background:\s*#fff\b")
        self.assertNotRegex(body_css, r"(?i)background:\s*#ffffff\b")

        card = re.search(r"\.card\s*\{([^}]+)\}", PARSER_HTML, flags=re.S)
        self.assertIsNotNone(card, msg="parser .card rule missing")
        card_css = card.group(1)
        self.assertIn("--bg-surface", card_css)
        self.assertNotRegex(card_css, r"background:\s*#fff\b")
        self.assertNotRegex(card_css, r"(?i)background:\s*#ffffff\b")

    def test_parser_tokens_stylesheet_linked(self):
        self.assertIn("/static/welora-tokens.css", PARSER_HTML)
        self.assertIn("/static/shell.css", PARSER_HTML)
        self.assertIn("--cta-primary", PARSER_HTML)

    def test_parser_budget_confirm_present(self):
        self.assertIn('id="budgetConfirm"', PARSER_HTML)
        # Checkbox width override kept safe
        self.assertRegex(
            PARSER_HTML,
            r'input\[type=["\']checkbox["\']\][^\{]*\{[^}]*width:\s*auto',
        )

    def test_content_max_width_480(self):
        body = re.search(r"body\s*\{([^}]+)\}", CONTENT_HTML, flags=re.S)
        self.assertIsNotNone(body, msg="content body rule missing")
        body_css = body.group(1).replace(" ", "")
        self.assertIn("max-width:480px", body_css)
        self.assertNotIn("max-width:640px", body_css)
        self.assertNotIn("max-width:640px", CONTENT_HTML)

    def test_routes_200(self):
        for path in ("/app/parser", "/app/content"):
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200, path)

    def test_parser_route_has_dark_hooks(self):
        r = self.client.get("/app/parser")
        self.assertEqual(r.status_code, 200)
        self.assertIn("--bg-app", r.text)
        self.assertIn("--bg-surface", r.text)
        self.assertIn('id="budgetConfirm"', r.text)
        self.assertNotIn("#f6f7f9", r.text)

    def test_content_route_max_width_480(self):
        r = self.client.get("/app/content")
        self.assertEqual(r.status_code, 200)
        self.assertIn("max-width:480px", r.text)
        self.assertNotIn("max-width:640px", r.text)

    def test_health_gate_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
