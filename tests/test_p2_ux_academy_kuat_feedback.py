"""P2 UX — Welorademy KUAT submit feedback."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "welora" / "api" / "static" / "academy.html"


class TestP2UxAcademyKuatFeedback(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.html = HTML.read_text(encoding="utf-8")

    def test_xp_updates_after_kuat(self):
        self.assertIn("setXp", self.html)
        self.assertIn("d.xp", self.html)
        self.assertIn("'XP '", self.html)
        self.assertIn("id=\"xpLine\"", self.html)

    def test_kuat_out_not_muted_and_scrolls(self):
        self.assertIn('id="kuatOut"', self.html)
        self.assertNotIn('id="kuatOut" class="muted"', self.html)
        self.assertIn("#kuatOut.pass", self.html)
        self.assertIn("#kuatOut.fail", self.html)
        self.assertIn("scrollIntoView", self.html)
        self.assertIn("'\u0110\u1ea0T'", self.html)
        self.assertIn("'CH\u01afA \u0110\u1ea0T'", self.html)

    def test_btn_disabled_and_error_text(self):
        self.assertIn("btn.disabled=true", self.html)
        self.assertIn("btn.disabled=false", self.html)
        self.assertIn("Không nộp được KUAT", self.html)

    def test_nudge_not_hidden_when_passed(self):
        self.assertIn("osNudge", self.html)
        self.assertIn("mastered", self.html)
        self.assertIn("else if(!mastered)", self.html)

    def test_page_and_health(self):
        r = self.client.get("/app/academy")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/academy/kuat", r.text)
        self.assertNotIn("Welora Academy", r.text)
        self.assertIn("Welorademy", r.text)
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
