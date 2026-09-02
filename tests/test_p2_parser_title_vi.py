"""P2 Ticket BA — parser title Vietnamese."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "parser.html"


class TestP2ParserTitleVi(unittest.TestCase):
    def test_title(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("<title>Welora · Sao kê CSV ngân hàng</title>", html)
        self.assertIn("<h1>Sao kê CSV ngân hàng</h1>", html)
        self.assertIn("ng\u00e2n", html)
        self.assertIn("h\u00e0ng", html)
        self.assertNotIn("Welora — Parser CSV", html)
        self.assertNotIn("<h1>Parser CSV ngân hàng</h1>", html)
        self.assertIn("/parser/csv", html)
        self.assertIn("welora_device_id", html)
        self.assertIn("createGoalBtn", html)
        self.assertIn("goal_draft", html)
        self.assertIn("textContent", html)
        self.assertNotIn("innerHTML", html)
        for nid in (
            "navHome", "csv", "go", "out", "suggestionEssential", "categories",
            "goalDraft", "goalDraftText", "goalExistingNote", "createGoalBtn",
        ):
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
