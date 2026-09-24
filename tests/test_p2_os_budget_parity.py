"""P0 OS — Budget parity CP (ticket 4/4): avg 3–6 months / rollover / goal contrib.

Extends Budget-from-CSV #135. Does NOT break CSV path.
Hard bans: Hard Deny · TARGET_MONTHS/gate_months=3 · silent overwrite · OB · Investments · Pillar 4.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("WELORA_STORE", "memory")

from fastapi.testclient import TestClient

from welora.agent import (
    CONFIDENCE_THRESHOLD,
    HARD,
    PRIORITY,
    TARGET_MONTHS as AGENT_TARGET,
)
from welora.api.app import create_app
from welora.budget import reset_budget_store
from welora.fixtures import reset_all_stores
from welora.os_accounts import InMemoryAccountStore, reset_account_store, use_store as use_account_store
from welora.os_transactions import (
    InMemoryTransactionStore,
    reset_transaction_store,
    use_store as use_tx_store,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
BUDGET_HTML = ROOT / "welora" / "api" / "static" / "budget.html"
PARSER_HTML = ROOT / "welora" / "api" / "static" / "parser.html"
SAFETY_PY = ROOT / "welora" / "safety_gate.py"


class TestP2OsBudgetParity(unittest.TestCase):
    def setUp(self) -> None:
        reset_all_stores()
        reset_budget_store()
        use_account_store(InMemoryAccountStore())
        reset_account_store()
        use_tx_store(InMemoryTransactionStore())
        reset_transaction_store()
        self.client = TestClient(create_app())
        self.uid = "user_budget_parity_01"
        self.aid = self._create_account()

    def _create_account(self, name: str = "Chi tiêu") -> str:
        r = self.client.post(
            "/os/accounts",
            json={
                "user_id": self.uid,
                "name": name,
                "type": "chi_tieu_hang_ngay",
                "opening_balance": 50_000_000,
                "consent_ack": True,
                "source": "manual",
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["account_id"]

    def _tx(self, *, date: str, amount: float, category: str, note: str = "") -> dict:
        r = self.client.post(
            "/os/transactions",
            json={
                "user_id": self.uid,
                "account_id": self.aid,
                "amount": amount,
                "category": category,
                "date": date,
                "note": note or category,
                "consent_ack": True,
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()

    def _seed_three_months(self) -> None:
        # Jul / Aug / Sep 2026 — real outflows (negative amounts)
        for mo, rent, food in (
            ("2026-07", -3_000_000, -1_200_000),
            ("2026-08", -3_600_000, -1_800_000),
            ("2026-09", -3_300_000, -1_500_000),
        ):
            self._tx(date=f"{mo}-01", amount=rent, category="Nhà ở")
            self._tx(date=f"{mo}-10", amount=food, category="Ăn uống")
            # income — must not inflate avg
            self._tx(date=f"{mo}-05", amount=25_000_000, category="Lương")

    def test_draft_from_avg_three_months_real_averages(self):
        self._seed_three_months()
        r = self.client.post(
            "/budget/draft-from-avg",
            json={"user_id": self.uid, "months": 3},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertIs(body.get("auto_overwrite"), False)
        draft = body["draft"]
        self.assertEqual(draft["kind"], "budget_draft")
        self.assertEqual(draft["source"], "avg_spend")
        self.assertIs(draft["auto_overwrite"], False)
        self.assertIs(draft.get("fictional_estimate"), False)
        self.assertEqual(draft["months_requested"], 3)
        self.assertEqual(draft["months_used"], 3)
        self.assertEqual(draft["window_months"], ["2026-07", "2026-08", "2026-09"])

        by_cat = {x["category"]: x for x in draft["lines"]}
        self.assertIn("Nhà ở", by_cat)
        self.assertIn("Ăn uống", by_cat)
        # (3.0+3.6+3.3)e6 / 3 = 3.3e6
        self.assertAlmostEqual(by_cat["Nhà ở"]["avg_monthly"], 3_300_000.0, places=1)
        # (1.2+1.8+1.5)e6 / 3 = 1.5e6
        self.assertAlmostEqual(by_cat["Ăn uống"]["avg_monthly"], 1_500_000.0, places=1)
        self.assertEqual(by_cat["Nhà ở"]["months_used"], 3)
        self.assertEqual(by_cat["Nhà ở"]["count"], 3)
        # Must not be a flat fictional estimate (e.g. equal arbitrary 1.0)
        self.assertNotEqual(by_cat["Nhà ở"]["avg_monthly"], by_cat["Ăn uống"]["avg_monthly"])
        self.assertNotIn("Lương", by_cat)

    def test_months_window_clamp_3_to_6(self):
        self._seed_three_months()
        bad_low = self.client.post(
            "/budget/draft-from-avg",
            json={"user_id": self.uid, "months": 2},
        )
        self.assertEqual(bad_low.status_code, 400)
        bad_high = self.client.post(
            "/budget/draft-from-avg",
            json={"user_id": self.uid, "months": 7},
        )
        self.assertEqual(bad_high.status_code, 400)
        # Request 6 but only 3 months history → clamp months_used to 3
        ok = self.client.post(
            "/budget/draft-from-avg",
            json={"user_id": self.uid, "months": 6},
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        d = ok.json()["draft"]
        self.assertEqual(d["months_requested"], 6)
        self.assertEqual(d["months_used"], 3)
        empty = self.client.post(
            "/budget/draft-from-avg",
            json={"user_id": "user_no_txs", "months": 3},
        )
        self.assertEqual(empty.status_code, 400)
        self.assertIn("no_outflow", str(empty.json()).lower() + str(empty.json()))

    def test_goal_contrib_lines_and_apply_does_not_mutate_goals(self):
        self._seed_three_months()
        ef = self.client.post(
            "/goals",
            json={
                "user_id": self.uid,
                "type": "emergency_fund",
                "essential_expense_monthly": 10_000_000,
                "current_amount": 2_000_000,
                "monthly_contribution": 500_000,
            },
        )
        self.assertIn(ef.status_code, (200, 201), ef.text)
        ef_body = ef.json()
        ef_id = ef_body["goal_id"]
        ef_before = float(ef_body["current"]["amount"])

        debt = self.client.post(
            "/goals",
            json={
                "user_id": self.uid,
                "type": "debt_payoff",
                "target_amount": 20_000_000,
                "current_amount": 5_000_000,
                "monthly_contribution": 1_000_000,
                "title": "Thẻ tín dụng",
            },
        )
        self.assertIn(debt.status_code, (200, 201), debt.text)
        debt_body = debt.json()
        debt_id = debt_body["goal_id"]
        debt_before = float(debt_body["current"]["amount"])

        draft_r = self.client.post(
            "/budget/draft-from-avg",
            json={"user_id": self.uid, "months": 3},
        )
        self.assertEqual(draft_r.status_code, 200, draft_r.text)
        draft = draft_r.json()["draft"]
        g_lines = draft.get("goal_contrib_lines") or []
        types = {x["goal_type"] for x in g_lines}
        self.assertIn("emergency_fund", types)
        self.assertIn("debt_payoff", types)
        for x in g_lines:
            self.assertEqual(x.get("kind"), "goal_contrib")
            self.assertGreater(float(x["amount"]), 0)

        applied = self.client.post(
            "/budget",
            json={"user_id": self.uid, "draft": draft, "confirm": True},
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        saved = applied.json()["budget"]
        self.assertIs(saved["auto_overwrite"], False)
        self.assertFalse(saved.get("goals_touched"))
        self.assertGreaterEqual(len(saved.get("goal_contrib_lines") or []), 2)

        # Goal balances unchanged
        ef_after = self.client.get(f"/goals/{ef_id}").json()
        debt_after = self.client.get(f"/goals/{debt_id}").json()
        self.assertAlmostEqual(float(ef_after["current"]["amount"]), ef_before)
        self.assertAlmostEqual(float(debt_after["current"]["amount"]), debt_before)
        # ids still present
        self.assertEqual(ef_after["goal_id"], ef_id)
        self.assertEqual(debt_after["goal_id"], debt_id)

    def test_rollover_close_period_carries_remaining(self):
        self._seed_three_months()
        draft = self.client.post(
            "/budget/draft-from-avg",
            json={"user_id": self.uid, "months": 3},
        ).json()["draft"]
        draft["period"] = "2026-09"
        applied = self.client.post(
            "/budget",
            json={"user_id": self.uid, "draft": draft, "confirm": True, "period": "2026-09"},
        )
        self.assertEqual(applied.status_code, 200, applied.text)
        budget = applied.json()["budget"]
        self.assertEqual(budget["period"], "2026-09")

        # Spend less than allocated on Nhà ở so remaining > 0
        nha = next(x for x in budget["lines"] if x["category"] == "Nhà ở")
        alloc = float(nha["allocated"])
        spent_nha = alloc * 0.4  # 60% remaining

        denied = self.client.post(
            "/budget/close-period",
            json={
                "user_id": self.uid,
                "period": "2026-09",
                "confirm": False,
                "spent_by_category": {"Nhà ở": spent_nha, "Ăn uống": 0},
            },
        )
        self.assertEqual(denied.status_code, 400)

        closed = self.client.post(
            "/budget/close-period",
            json={
                "user_id": self.uid,
                "period": "2026-09",
                "confirm": True,
                "spent_by_category": {"Nhà ở": spent_nha, "Ăn uống": 0},
            },
        )
        self.assertEqual(closed.status_code, 200, closed.text)
        body = closed.json()
        self.assertIs(body.get("auto_overwrite"), False)
        closed_nha = next(x for x in body["closed"]["lines"] if x["category"] == "Nhà ở")
        expected_rem = alloc - spent_nha
        self.assertAlmostEqual(float(closed_nha["remaining"]), expected_rem, places=1)
        self.assertAlmostEqual(float(closed_nha["rollover_out"]), expected_rem, places=1)

        nxt = body["next"]
        self.assertEqual(nxt["period"], "2026-10")
        next_nha = next(x for x in nxt["lines"] if x["category"] == "Nhà ở")
        self.assertAlmostEqual(float(next_nha["rollover_in"]), expected_rem, places=1)
        self.assertGreater(float(next_nha["remaining"]), float(next_nha["allocated"]) - 1)

        # Active budget is next period
        got = self.client.get("/budget", params={"user_id": self.uid}).json()
        self.assertEqual(got["budget"]["period"], "2026-10")
        # Alias route
        again = self.client.post(
            "/budget/rollover",
            json={
                "user_id": self.uid,
                "period": "2026-10",
                "confirm": True,
                "spent_by_category": {"Nhà ở": 0, "Ăn uống": 0},
            },
        )
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json()["next"]["period"], "2026-11")

    def test_confirm_replace_and_auto_overwrite_false(self):
        self._seed_three_months()
        draft = self.client.post(
            "/budget/draft-from-avg",
            json={"user_id": self.uid, "months": 3},
        ).json()["draft"]

        denied = self.client.post(
            "/budget",
            json={"user_id": self.uid, "draft": draft, "confirm": False},
        )
        self.assertEqual(denied.status_code, 400)

        first = self.client.post(
            "/budget",
            json={"user_id": self.uid, "draft": draft, "confirm": True},
        )
        self.assertEqual(first.status_code, 200)
        self.assertIs(first.json()["budget"]["auto_overwrite"], False)
        self.assertIs(first.json().get("auto_overwrite"), False)

        clash = self.client.post(
            "/budget",
            json={
                "user_id": self.uid,
                "draft": draft,
                "confirm": True,
                "replace_existing": False,
            },
        )
        self.assertEqual(clash.status_code, 409)
        self.assertIn("budget_exists", str(clash.json()))

        ok = self.client.post(
            "/budget",
            json={
                "user_id": self.uid,
                "draft": draft,
                "confirm": True,
                "replace_existing": True,
            },
        )
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json().get("replaced"))
        self.assertIs(ok.json()["auto_overwrite"], False)
        self.assertIs(ok.json()["budget"]["auto_overwrite"], False)

    def test_health_gate_hard_and_ui(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(AGENT_TARGET, 3)
        self.assertEqual(CONFIDENCE_THRESHOLD, 0.80)
        self.assertEqual(HARD, {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"})
        self.assertEqual(
            PRIORITY,
            ["R01", "R03", "R02", "R08", "R09", "R06", "R07", "R04", "R05"],
        )
        r = self.client.get("/health").json()
        self.assertEqual(r["status"], "ok")
        self.assertEqual(r["gate_months"], 3)
        self.assertTrue(r["hard_deny"])

        page = self.client.get("/app/budget")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Trung bình chi tiêu", page.text)
        self.assertIn("rollover", page.text.lower() + page.text)
        self.assertIn("confirmSave", page.text)
        self.assertIn("/budget/draft-from-avg", page.text)
        self.assertIn("/budget/close-period", page.text)
        self.assertNotIn("innerHTML", page.text)

        html = BUDGET_HTML.read_text(encoding="utf-8")
        self.assertIn("Đóng góp Mục tiêu", html)
        self.assertNotIn("auto_overwrite", html)

        # CSV parser path still exposes budget block
        parser = PARSER_HTML.read_text(encoding="utf-8")
        self.assertIn('id="budgetDraft"', parser)
        self.assertIn("Tạo / cập nhật ngân sách", parser)
        self.assertIn("budgetConfirm", parser)

        # safety_gate TARGET_MONTHS literal still 3
        safety = SAFETY_PY.read_text(encoding="utf-8")
        self.assertIn("TARGET_MONTHS = 3", safety)


if __name__ == "__main__":
    unittest.main()
