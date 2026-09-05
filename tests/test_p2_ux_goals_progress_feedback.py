"""P2 UX — goals progress + debt create feedback."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "goals.html"


class TestP2UxGoalsProgressFeedback(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.html = HTML.read_text(encoding="utf-8")

    def test_error_shows_detail_or_error(self):
        self.assertIn("function readErr", self.html)
        self.assertIn("b.detail||b.error", self.html)
        self.assertIn("await readErr(r,", self.html)

    def test_last_id_after_debt_create(self):
        self.assertIn("lastId=body.goal_id", self.html)
        self.assertIn("sel.value=lastId", self.html)

    def test_type_based_add_label(self):
        self.assertIn("Ghi trả nợ", self.html)
        self.assertIn("Cộng vào quỹ", self.html)
        self.assertIn("Đang cập nhật: ", self.html)
        self.assertIn("function syncAddUi", self.html)
        self.assertIn("id=\"addHint\"", self.html.replace("'", '"') or self.html)

    def test_buttons_disable_and_catch(self):
        self.assertIn("btn.disabled=true", self.html)
        self.assertIn("btn.disabled=false", self.html)
        self.assertIn("catch(_e)", self.html)

    def test_page_and_health(self):
        r = self.client.get("/app/goals")
        self.assertEqual(r.status_code, 200)
        self.assertIn("addBtn", r.text)
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
