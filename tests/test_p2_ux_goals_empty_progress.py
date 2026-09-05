"""P2 UX — goals empty state disables progress."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "goals.html"


class TestP2UxGoalsEmptyProgress(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.html = HTML.read_text(encoding="utf-8")

    def test_empty_hint_and_disable(self):
        self.assertIn("function setProgressEnabled", self.html)
        self.assertIn("function emptyProgressHint", self.html)
        self.assertIn("Tạo quỹ khẩn cấp hoặc mục tiêu trả nợ trước khi cộng tiến độ.", self.html)
        self.assertIn("Bấm Tạo trả nợ phía trên trước.", self.html)
        self.assertIn("setProgressEnabled(false)", self.html)
        self.assertIn("#addChips button", self.html)

    def test_page_and_health(self):
        r = self.client.get("/app/goals")
        self.assertEqual(r.status_code, 200)
        self.assertIn("addHint", r.text)
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
