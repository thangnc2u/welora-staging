"""P2 Ticket BH — parser muted separator middle-dot."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "parser.html"


class TestP2ParserMutedVi(unittest.TestCase):
    def test_muted(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Gợi ý chi tiêu thiết yếu · <strong>không</strong>", html)
        self.assertIn("thi\u1ebft y\u1ebfu", html)
        self.assertNotIn("thiết yếu — <strong>", html)
        self.assertIn("ghi đè quỹ/DNA", html)
        self.assertIn("Quỹ đã có · không ghi đè", html)
        self.assertNotIn("Goal/DNA", html)
        self.assertIn("<h1>Parser CSV ngân hàng</h1>", html)
        self.assertIn("/parser/csv", html)
        self.assertIn("goal_draft", html)
        self.assertIn("createGoalBtn", html)
        self.assertIn("textContent", html)
        self.assertIn("createElement", html)
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
