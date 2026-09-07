"""P2 UX — Welorademy titles VI (Bài n + tag, no node_id · title)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "academy.html"


class TestP2UxAcademyTitlesVi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.html = HTML.read_text(encoding="utf-8")

    def test_no_node_id_dot_title(self):
        self.assertNotIn("node_id+' · '+n.title", self.html)
        self.assertNotIn("n.node_id+' · '+n.title", self.html)
        self.assertIn("baiLabel", self.html)
        self.assertIn("n.title||''", self.html)

    def test_bai_and_vi_tags(self):
        self.assertIn("Bài ", self.html)
        self.assertIn("An toàn", self.html)
        self.assertIn("Nợ", self.html)
        self.assertIn("Cốt lõi", self.html)
        self.assertIn("function viTag", self.html)
        self.assertIn("className='tag'", self.html)
        self.assertIn("Từ Welorapedia", self.html)

    def test_page_and_health(self):
        r = self.client.get("/app/academy")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
