"""P2 polish — Goals a11y (label/aria) + EF title matches API (no client invent)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
HTML = STATIC / "goals.html"


class TestP2PolishGoalsA11yEfTitle(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.html = HTML.read_text(encoding="utf-8")

    def test_health_gate_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])

    def test_goals_page_a11y_create_edit_progress(self):
        r = self.client.get("/app/goals")
        self.assertEqual(r.status_code, 200)
        body = r.text
        # debt create form labels
        self.assertIn('for="debtTitle"', body)
        self.assertIn('for="debtSubtype"', body)
        self.assertIn('for="debtTarget"', body)
        self.assertIn('id="debtCreateBtn"', body)
        self.assertIn('aria-labelledby="debtBoxLabel"', body)
        self.assertIn('aria-describedby="debtErr"', body)
        self.assertIn('role="alert"', body)
        # progress form labels
        self.assertIn('for="goalPick"', body)
        self.assertIn('for="addAmount"', body)
        self.assertIn('aria-labelledby="addBoxLabel"', body)
        self.assertIn('aria-describedby="addHint addErr"', body)
        # chips accessible names + keyboard focus styles present
        self.assertIn('aria-label="Gợi ý số tiền trả nợ"', body)
        self.assertIn('aria-label="Gợi ý số tiền cộng tiến độ"', body)
        self.assertIn("focus-visible", body)
        self.assertIn("setAttribute('role','button')", body)
        self.assertIn("setAttribute('tabindex','0')", body)
        self.assertIn("keydown", body)

    def test_ef_title_uses_api_no_client_invent(self):
        html = self.html
        # no invent alternate EF title string on display
        self.assertNotIn("g.title||(isDebt?'Trả nợ nguy hiểm':'Quỹ khẩn cấp')", html)
        self.assertNotIn("g.title||'Quỹ khẩn cấp'", html)
        self.assertIn("line(isDebt?'Tên mục tiêu':'Tên quỹ', g.title)", html)
        # pick/hint may fall back to typeLabel, not invent months-stripped EF title
        self.assertIn("g.title||typeLabel(g.type)", html)

        # API title for EF must be months-aware; UI must show that field
        auth = self.client.post("/auth/device", json={"device_id": "a11y-ef-title-dev-1"})
        self.assertEqual(auth.status_code, 200)
        uid = auth.json()["user_id"]
        created = self.client.post(
            "/goals",
            json={
                "user_id": uid,
                "type": "emergency_fund",
                "essential_expense_monthly": 10_000_000,
            },
        )
        self.assertEqual(created.status_code, 201)
        api_title = created.json()["title"]
        self.assertEqual(api_title, "Quỹ khẩn cấp 3 tháng")

        listed = self.client.get("/goals", params={"user_id": uid})
        self.assertEqual(listed.status_code, 200)
        items = listed.json()["items"]
        ef = next(g for g in items if g["type"] == "emergency_fund")
        self.assertEqual(ef["title"], api_title)
        # DOM render path binds g.title (asserted above) — displayed == API
        self.assertIn("g.title", html)

    def test_money_css_linked_and_js_200(self):
        page = self.client.get("/app/goals")
        self.assertEqual(page.status_code, 200)
        self.assertIn("/static/money.css", page.text)
        self.assertIn("/static/money.js", page.text)
        css = self.client.get("/static/money.css")
        self.assertEqual(css.status_code, 200)
        js = self.client.get("/static/money.js")
        self.assertEqual(js.status_code, 200)
        self.assertIn("formatVnd", js.text)

    def test_constraints_files_untouched_markers(self):
        # smoke: hard deny / gate / family_context ALLOWED still present as before
        from welora import safety_gate
        from pathlib import Path as P

        self.assertEqual(safety_gate.TARGET_MONTHS, 3)
        fc = (STATIC / "family_context.js").read_text(encoding="utf-8")
        self.assertIn("ALLOWED", fc)
        self.assertIn("solo", fc)


if __name__ == "__main__":
    unittest.main()
