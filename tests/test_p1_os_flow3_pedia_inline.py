"""P1 G1 — OS Flow 3: Pedia inline trên Goal quỹ / nợ."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.content_map import get_article
from welora.pedia_inline import (
    GOAL_PEDIA_KEYS,
    keys_for_goal_type,
    pedia_card,
    pedia_cards_for_goal,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "welora" / "api" / "static" / "goals.html"


class TestP1OsFlow3PediaInline(unittest.TestCase):
    def test_map_two_goal_types(self):
        self.assertEqual(GOAL_PEDIA_KEYS["emergency_fund"], ["SAFE-01"])
        self.assertEqual(keys_for_goal_type("emergency_fund"), ["SAFE-01"])
        self.assertEqual(keys_for_goal_type("debt_payoff"), ["DEBT-01", "DEBT-02", "DEBT-03"])
        self.assertEqual(keys_for_goal_type("unknown"), [])

        fund = pedia_cards_for_goal("emergency_fund")
        self.assertEqual(len(fund), 1)
        self.assertEqual(fund[0]["principle_key"], "SAFE-01")
        self.assertTrue(fund[0]["excerpt"])
        self.assertEqual(fund[0]["href"], "/app/content?key=SAFE-01")
        self.assertIn("Welorademy", fund[0]["academy_label"])
        self.assertEqual(fund[0]["linked_module_id"], "M02")
        self.assertEqual(fund[0]["linked_article_id"], "WP-02-01")

        debt = pedia_cards_for_goal("debt_payoff")
        keys = [c["principle_key"] for c in debt]
        self.assertEqual(keys, ["DEBT-01", "DEBT-02", "DEBT-03"])
        self.assertEqual(debt[2]["principle_key"], "DEBT-03")
        self.assertIn("An Toàn trước đầu tư", debt[2]["title"])

    def test_unknown_key_no_crash(self):
        self.assertIsNone(pedia_card("NOT-A-KEY"))
        miss = get_article("NOT-A-KEY")
        self.assertFalse(miss.get("ok"))
        self.assertEqual(pedia_cards_for_goal(""), [])
        self.assertEqual(pedia_cards_for_goal("savings"), [])

    def test_goals_html_inline_block(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Học thêm", html)
        self.assertIn("/content/", html)
        self.assertIn("/app/content?key=", html)
        self.assertIn("Welorademy", html)
        self.assertIn("Xem đầy đủ", html)
        self.assertIn("pedia", html)
        self.assertIn("SAFE-01", html)
        self.assertIn("DEBT-01", html)
        self.assertIn("DEBT-02", html)
        self.assertIn("DEBT-03", html)
        self.assertNotIn("Welora Academy", html)
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("type:'emergency_fund'", html)

    def test_health_gate_hard(self):
        self.assertEqual(TARGET_MONTHS, 3)
        client = TestClient(create_app())
        r = client.get("/app/goals")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Học thêm", r.text)
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        ok = client.get("/content/SAFE-01")
        self.assertEqual(ok.status_code, 200)
        miss = client.get("/content/NOT-A-KEY")
        self.assertEqual(miss.status_code, 404)


if __name__ == "__main__":
    unittest.main()
