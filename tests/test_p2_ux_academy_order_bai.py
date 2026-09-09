"""P2 UX — Welorademy sort by order + Bài from order."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "academy.html"


class TestP2UxAcademyOrderBai(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.html = HTML.read_text(encoding="utf-8")

    def test_sort_by_order_and_bai_from_order(self):
        self.assertIn("slice().sort", self.html)
        self.assertIn("a.order", self.html)
        self.assertIn("b.order", self.html)
        self.assertIn("nOrId.order", self.html)
        self.assertIn("Bài ", self.html)
        self.assertIn("baiLabel(n)", self.html)
        # Prefer order over parsing N02-xx tail when order present
        self.assertIn("Number(nOrId.order)", self.html)

    def test_page_and_health(self):
        r = self.client.get("/app/academy")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
