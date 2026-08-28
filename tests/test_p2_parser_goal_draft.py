"""P2 parser goal_draft — no auto POST /goals, no overwrite."""

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
"""
HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "parser.html"


class TestP2ParserGoalDraft(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_parse_adds_goal_draft_does_not_create_goal(self):
        auth = self.client.post("/auth/device", json={"device_id": "dev-parser-z-1"})
        uid = auth.json()["user_id"]
        before = self.client.get("/goals", params={"user_id": uid}).json()
        n0 = len(before.get("items") or before.get("goals") or [])
        r = self.client.post("/parser/csv", json={"text": SAMPLE, "filename": "s.csv"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertIs(body.get("auto_overwrite"), False)
        self.assertTrue(body.get("category_counts"))
        draft = body.get("goal_draft") or {}
        self.assertEqual(draft.get("type"), "emergency_fund")
        ess = float(draft.get("essential_expense_monthly") or 0)
        self.assertGreater(ess, 0)
        self.assertEqual(draft.get("target_amount"), ess * TARGET_MONTHS)
        self.assertIs(draft.get("auto_overwrite"), False)
        sug = (body.get("suggestion") or {}).get("essential_expense_monthly")
        self.assertEqual(float(sug), ess)
        after = self.client.get("/goals", params={"user_id": uid}).json()
        n1 = len(after.get("items") or after.get("goals") or [])
        self.assertEqual(n1, n0)

    def test_parser_html_goal_draft_confirm_only(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('id="goalDraft"', html)
        self.assertIn('id="createGoalBtn"', html)
        self.assertIn("welora_device_id", html)
        self.assertIn("Goal đã có — không ghi đè", html)
        self.assertIn("Tạo Goal", html)
        self.assertNotIn("JSON.stringify(j.category_counts)", html)
        go_idx = html.find("document.getElementById('go')")
        btn_idx = html.find("document.getElementById('createGoalBtn')")
        self.assertGreater(go_idx, 0)
        self.assertGreater(btn_idx, go_idx)
        go_block = html[go_idx:btn_idx]
        self.assertNotIn("fetch('/goals'", go_block.replace('"', "'"))
        self.assertNotIn('fetch("/goals"', go_block)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
