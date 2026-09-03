"""P2 security — strip HTML from CSV text fields."""

from __future__ import annotations

import json
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.csv_parser import sanitize_csv_text
from welora.safety_gate import TARGET_MONTHS

CSV_SAFE = "date,description,amount\n2026-01-01,Winmart,-150000\n2026-01-02,Lương,8000000\n"
CSV_XSS = (
    "date,description,amount\n"
    '2026-01-01,"<script>alert(1)</script>Winmart",-150000\n'
    '2026-01-02,"<b>Lương</b>",8000000\n'
)


class TestP2SecCsvSanitize(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_sanitize_helper_strips_script(self):
        raw = "<script>alert(1)</script>Winmart"
        out = sanitize_csv_text(raw)
        self.assertNotIn("<script>", out)
        self.assertNotIn("</script>", out)
        self.assertIn("Winmart", out)

    def test_parser_csv_does_not_echo_script(self):
        r = self.client.post(
            "/parser/csv",
            json={"text": CSV_XSS, "filename": "stmt.html"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        blob = json.dumps(body, ensure_ascii=False)
        self.assertNotIn("<script>", blob)
        self.assertNotIn("</script>", blob)
        self.assertNotIn("<b>", blob)
        txs = body.get("transactions") or []
        self.assertTrue(txs)
        for t in txs:
            desc = str(t.get("description") or "")
            raw = str(t.get("raw") or "")
            self.assertNotIn("<", desc)
            self.assertNotIn(">", desc)
            self.assertIsInstance(t.get("amount"), (int, float))
        amounts = sorted(t["amount"] for t in txs)
        self.assertEqual(amounts, [-150000.0, 8000000.0])
        sug = (body.get("suggestion") or {}).get("essential_expense_monthly")
        self.assertIsNotNone(sug)
        draft = body.get("goal_draft") or {}
        self.assertEqual(draft.get("target_months"), 3)
        self.assertEqual(draft.get("auto_overwrite"), False)
        self.assertFalse(body.get("auto_overwrite"))

    def test_normal_csv_still_parses(self):
        r = self.client.post("/parser/csv", json={"text": CSV_SAFE, "filename": "ok.csv"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertGreaterEqual(body.get("transaction_count") or 0, 2)
        self.assertIn("Winmart", json.dumps(body, ensure_ascii=False))

    def test_parser_ui_and_health(self):
        self.assertEqual(TARGET_MONTHS, 3)
        ui = self.client.get("/app/parser")
        self.assertEqual(ui.status_code, 200)
        self.assertIn("/parser/csv", ui.text)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
