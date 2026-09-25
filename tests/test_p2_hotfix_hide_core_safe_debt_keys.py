"""P2 hotfix — hide CORE/SAFE/DEBT keys from /app/goals user-facing copy."""

from __future__ import annotations

import re
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.pedia_inline import (
    excerpt_body,
    pedia_card,
    pedia_cards_for_goal,
    scrub_internal_codes,
    strip_frontmatter,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
GOALS_HTML = ROOT / "welora" / "api" / "static" / "goals.html"
KEY_RE = re.compile(r"\b(?:CORE|SAFE|DEBT)-\d+\b")


class TestP2HotfixHideCoreSafeDebtKeys(unittest.TestCase):
    def test_strip_frontmatter_drops_principle_meta(self):
        raw = (
            "# WP-02-01: Quỹ khẩn cấp là gì?\n"
            "**Module:** 02 – An Toàn Tài Chính\n"
            "**principle_key:** SAFE-01\n"
            "**secondary_keys:** CORE-07\n"
            "---\n\n"
            "## 1. Câu hỏi thực tế\n"
            "Quỹ khẩn cấp là gì?\n"
        )
        cleaned = strip_frontmatter(raw)
        self.assertNotIn("principle_key", cleaned)
        self.assertNotIn("SAFE-01", cleaned)
        self.assertNotIn("CORE-07", cleaned)
        self.assertNotIn("Module:", cleaned)
        self.assertIn("Câu hỏi thực tế", cleaned)

    def test_excerpt_body_no_internal_keys(self):
        for goal_type in ("emergency_fund", "debt_payoff"):
            for card in pedia_cards_for_goal(goal_type):
                with self.subTest(goal_type=goal_type, key=card["principle_key"]):
                    self.assertTrue(card["excerpt"])
                    self.assertIsNone(KEY_RE.search(card["excerpt"]))
                    self.assertNotIn("principle_key", card["excerpt"].lower())
                    self.assertNotIn("secondary_keys", card["excerpt"].lower())
                    self.assertNotIn("Module:", card["excerpt"])
                    self.assertNotIn("Status:", card["excerpt"])

    def test_scrub_removes_bare_codes(self):
        self.assertEqual(scrub_internal_codes("Xem CORE-07 và SAFE-01 nhé"), "Xem và nhé")
        leak = excerpt_body("**principle_key:** DEBT-01\n**secondary_keys:** CORE-07\n---\nHọ học trả nợ.")
        self.assertIsNone(KEY_RE.search(leak))
        self.assertIn("trả nợ", leak.lower())

    def test_goals_html_has_strip_and_uses_it(self):
        html = GOALS_HTML.read_text(encoding="utf-8")
        self.assertIn("function stripFrontmatter", html)
        self.assertIn("function scrubInternalCodes", html)
        self.assertIn("stripFrontmatter(md", html)
        self.assertIn("scrubInternalCodes", html)
        self.assertIn("ex.textContent=excerpt(d.body_markdown||'')", html)
        self.assertIn("Học thêm", html)
        # Internal fetch keys stay in JS (not rendered as textContent of excerpts)
        self.assertIn("SAFE-01", html)
        self.assertIn("DEBT-01", html)
        self.assertNotIn("innerHTML", html)

    def test_content_api_body_still_has_keys_internally(self):
        """Codes remain in stored markdown / API for deep-link; UI strips on display."""
        client = TestClient(create_app())
        r = client.get("/content/SAFE-01")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("principle_key"), "SAFE-01")
        # Raw body may still contain meta — display layer owns scrubbing
        card = pedia_card("SAFE-01")
        assert card is not None
        self.assertIsNone(KEY_RE.search(card["excerpt"]))

    def test_goals_page_and_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        client = TestClient(create_app())
        r = client.get("/app/goals")
        self.assertEqual(r.status_code, 200)
        self.assertIn("stripFrontmatter", r.text)
        self.assertIn("Học thêm", r.text)
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
