"""P2 UX — Bottom Nav Từ điển (Welorapedia)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "welora" / "api" / "static" / "shell.js").read_text(encoding="utf-8")


class TestP2UxNavTudien(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_four_labels_in_shell_js(self):
        for label in ("Trang chủ", "Từ điển", "Trợ lý AI", "Học viện"):
            self.assertIn(label, JS)
        self.assertIn('href: "/app/content"', JS)
        self.assertNotIn('label: "Mục tiêu"', JS)
        self.assertNotIn("Welora Academy", JS)

    def test_content_loads_shell_pedia_tab(self):
        r = self.client.get("/app/content")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/static/shell.js", r.text)
        self.assertIn('data-shell-tab="pedia"', r.text)
        self.assertIn("Welorapedia", r.text)
        self.assertIn("Welorademy", r.text)
        self.assertNotIn("Welora Academy", r.text)

    def test_dashboard_keeps_goals_link(self):
        home = self.client.get("/app").text
        self.assertIn("Mở Mục tiêu", home)
        self.assertIn("/app/goals", home)
        self.assertEqual(self.client.get("/app/goals").status_code, 200)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        b = self.client.get("/health").json()
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
