"""P2 Native UI /app/demo — 8 step cards, no JSON pre dump."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

DEMO_HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "demo.html"


class TestP2DemoUi(unittest.TestCase):
    def test_demo_html_has_run_and_steps(self):
        html = DEMO_HTML.read_text(encoding="utf-8")
        self.assertIn('id="run"', html)
        for i in range(1, 9):
            self.assertIn(f'id="step{i}"', html)
        self.assertNotIn('<pre id="log">', html)
        self.assertNotIn('id="log"', html)
        self.assertIn("set_amount", html)
        self.assertIn("30000000", html)
        self.assertIn("all-in ETF", html)
        self.assertIn("Rút quỹ khẩn cấp để đầu tư", html)

    def test_ui_has_no_months_target_below_three(self):
        html = DEMO_HTML.read_text(encoding="utf-8")
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertNotIn('id="months"', html)
        self.assertNotIn("target_months", html)

    def test_health_untouched(self):
        client = TestClient(create_app())
        r = client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
