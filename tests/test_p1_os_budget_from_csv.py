"""P1 G1 — OS ngân sách từ CSV. Budget ≠ Goal quỹ. Không silent overwrite."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.budget import reset_budget_store
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

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "parser.html"


class TestP1OsBudgetFromCsv(unittest.TestCase):
    def setUp(self) -> None:
        reset_budget_store()
        self.client = TestClient(create_app())

    def test_parse_returns_budget_draft_not_goal(self):
        r = self.client.post("/parser/csv", json={"text": SAMPLE, "filename": "s.csv"})
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertIs(body.get("auto_overwrite"), False)
        draft = body.get("budget_draft") or {}
        self.assertEqual(draft.get("kind"), "budget_draft")
        self.assertIs(draft.get("auto_overwrite"), False)
        lines = draft.get("lines") or []
        cats = {x["category"] for x in lines}
        self.assertIn("Nhà ở", cats)
        self.assertIn("Siêu thị", cats)
        nha = next(x for x in lines if x["category"] == "Nhà ở")
        self.assertGreater(float(nha["outflow"]), 0)
        goal = body.get("goal_draft") or {}
        self.assertEqual(goal.get("type"), "emergency_fund")
        self.assertNotEqual(draft.get("kind"), goal.get("type"))

    def test_apply_persists_and_get(self):
        auth = self.client.post("/auth/device", json={"device_id": "dev-budget-a"})
        uid = auth.json()["user_id"]
        parsed = self.client.post("/parser/csv", json={"text": SAMPLE}).json()
        draft = parsed["budget_draft"]
        denied = self.client.post("/budget", json={"user_id": uid, "draft": draft, "confirm": False})
        self.assertEqual(denied.status_code, 400)
        applied = self.client.post(
            "/budget",
            json={"user_id": uid, "draft": draft, "confirm": True},
        )
        self.assertEqual(applied.status_code, 200)
        saved = applied.json()["budget"]
        self.assertEqual(saved["kind"], "budget")
        self.assertEqual(saved["status"], "applied")
        self.assertIs(saved["auto_overwrite"], False)
        got = self.client.get("/budget", params={"user_id": uid}).json()
        self.assertEqual(got["status"], "applied")
        self.assertEqual(len(got["budget"]["lines"]), len(draft["lines"]))

    def test_second_apply_does_not_clobber_silently(self):
        auth = self.client.post("/auth/device", json={"device_id": "dev-budget-b"})
        uid = auth.json()["user_id"]
        parsed = self.client.post("/parser/csv", json={"text": SAMPLE}).json()
        draft = parsed["budget_draft"]
        first = self.client.post("/budget", json={"user_id": uid, "draft": draft, "confirm": True})
        self.assertEqual(first.status_code, 200)
        first_total = first.json()["budget"]["total_outflow"]
        other = dict(draft)
        other["lines"] = [{"category": "Khác", "count": 1, "outflow": 1}]
        other["total_outflow"] = 1
        clash = self.client.post(
            "/budget",
            json={"user_id": uid, "draft": other, "confirm": True, "replace_existing": False},
        )
        self.assertEqual(clash.status_code, 409)
        self.assertIn("budget_exists", str(clash.json()))
        still = self.client.get("/budget", params={"user_id": uid}).json()
        self.assertEqual(still["budget"]["total_outflow"], first_total)
        ok = self.client.post(
            "/budget",
            json={"user_id": uid, "draft": other, "confirm": True, "replace_existing": True},
        )
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json().get("replaced"))
        self.assertEqual(ok.json()["budget"]["total_outflow"], 1)

    def test_parser_ui_budget_block(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('id="budgetDraft"', html)
        self.assertIn('id="budgetApplyBtn"', html)
        self.assertIn("Tạo / cập nhật ngân sách", html)
        self.assertIn("/budget", html)
        self.assertIn("Ngân sách đã có", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn('id="goalDraft"', html)
        self.assertIn("Tạo quỹ khẩn cấp", html)

    def test_health_gate_hard(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health").json()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["gate_months"], 3)
        self.assertTrue(r["hard_deny"])
        page = self.client.get("/app/parser")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Tạo / cập nhật ngân sách", page.text)
        alt = self.client.get("/app/budget")
        self.assertEqual(alt.status_code, 200)


if __name__ == "__main__":
    unittest.main()
