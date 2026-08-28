"""P2 Ticket BI — parser existing-goal note middle-dot."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "parser.html"


class TestP2ParserNoteVi(unittest.TestCase):
    def test_note(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Goal đã có · không ghi đè. Hiện tại ", html)
        self.assertIn("\u00e3", html)
        self.assertIn("\u00e8", html)
        self.assertIn("Hi\u1ec7n", html)
        self.assertNotIn("Goal đã có —", html)
        self.assertIn("thiết yếu · <strong>không</strong>", html)
        self.assertIn("<h1>Parser CSV ngân hàng</h1>", html)
        self.assertIn("/parser/csv", html)
        self.assertIn("goal_draft", html)
        self.assertIn("createGoalBtn", html)
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
