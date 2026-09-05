"""P2 UX — hide create-debt when debt_payoff exists."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "goals.html"


class TestP2UxGoalsDebtAlready(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.html = HTML.read_text(encoding="utf-8")

    def test_hide_form_when_debt_exists(self):
        self.assertIn('id="debtAlready"', self.html)
        self.assertIn('id="debtForm"', self.html)
        self.assertIn("function syncDebtBox", self.html)
        self.assertIn("Đã có mục tiêu trả nợ — dùng Cộng tiến độ bên dưới.", self.html)

    def test_409_copy(self):
        self.assertIn("r.status===409", self.html)
        self.assertIn("Bạn đã có mục tiêu trả nợ. Chọn mục tiêu ở phần Cộng tiến độ để ghi trả.", self.html)

    def test_clear_fields_after_ok(self):
        self.assertIn("debtTitle').value=''", self.html)
        self.assertIn("debtSubtype').value=''", self.html)
        self.assertIn("debtTarget').value=''", self.html)

    def test_page_and_health(self):
        r = self.client.get("/app/goals")
        self.assertEqual(r.status_code, 200)
        self.assertIn("debtAlready", r.text)
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
