"""P2 UX — Safety gate checklist + hide mastery select for learners."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html"


class TestP2UxGateChecklist(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.html = HTML.read_text(encoding="utf-8")

    def test_checklist_and_ctas(self):
        self.assertIn('id="gateChecklist"', self.html)
        self.assertIn("renderGateChecklist", self.html)
        self.assertIn("Quỹ khẩn cấp ≥ 3 tháng", self.html)
        self.assertIn("Nợ nguy hiểm đã xử lý", self.html)
        self.assertIn("Làm chủ nguyên tắc", self.html)
        self.assertIn('id="ctaGateChat"', self.html)
        self.assertIn("Chat với Agent", self.html)
        self.assertIn("/app/chat", self.html)
        self.assertIn("/app/academy", self.html)
        self.assertIn("addCheckItem", self.html)
        self.assertIn("emergency_fund_below_3_months", self.html)

    def test_mastery_select_hidden_not_removed(self):
        # Keep id for legacy tests; hide from learner UI
        self.assertIn('id="masteryState"', self.html)
        self.assertIn('id="masteryState" hidden', self.html)
        self.assertIn("ms.hidden=true", self.html)

    def test_page_and_health_untouched(self):
        r = self.client.get("/app/safety")
        self.assertEqual(r.status_code, 200)
        self.assertIn("gateChecklist", r.text)
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
