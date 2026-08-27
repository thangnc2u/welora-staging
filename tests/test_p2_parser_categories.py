"""P2 parser category_counts — heuristic VN labels, no LLM."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

SAMPLE = """date,amount,description
01/07/2026,-3500000,Thuê nhà tháng 7
05/07/2026,-450000,Điện EVN
10/07/2026,25000000,Lương
12/07/2026,-1200000,WinMart
15/07/2026,-2000000,Học phí
01/08/2026,-3500000,Thuê nhà tháng 8
10/08/2026,25000000,Lương
"""

NEED = ("Nhà ở", "Điện nước", "Lương", "Siêu thị", "Học phí")
STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"


class TestP2ParserCategories(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_sample_seven_rows_category_counts(self):
        r = self.client.post("/parser/csv", json={"text": SAMPLE, "filename": "sample.csv"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertIs(body.get("auto_overwrite"), False)
        counts = body.get("category_counts") or {}
        for k in NEED:
            self.assertIn(k, counts, counts)
            self.assertGreaterEqual(int(counts[k]), 1)
        sug = body.get("suggestion") or {}
        self.assertIn("essential_expense_monthly", sug)

    def test_parser_ui_still_has_categories(self):
        r = self.client.get("/app/parser")
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="categories"', r.text)
        self.assertNotIn("JSON.stringify(j.category_counts)", r.text)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
