"""P2 UAT — goals/nợ completed UX + months=0 + focus banner."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.db.repos import SqliteEmergencyFundStore
from welora.goal_emergency_fund import InMemoryEmergencyFundStore, apply_progress
from welora.goals_api import (
    USER_FLAGS,
    service_create_goal,
    service_get_goal,
    service_list_goals,
    service_progress,
    use_store,
)
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "goals.html"
REPOS = Path(__file__).resolve().parents[1] / "welora" / "db" / "repos.py"


def _reset_memory() -> None:
    use_store(InMemoryEmergencyFundStore())
    USER_FLAGS.clear()


class TestMonthsZeroRoundTrip(unittest.TestCase):
    """debt months_of_expense=0 must survive GET/list/progress (not swallowed to 3)."""

    def setUp(self) -> None:
        USER_FLAGS.clear()

    def test_sqlite_months_zero_survives_get_list_progress(self):
        import tempfile

        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        url = f"sqlite:///{path}"
        try:
            store = SqliteEmergencyFundStore(url)
            use_store(store)
            code, created = service_create_goal(
                {
                    "user_id": "m0",
                    "type": "debt_payoff",
                    "target_amount": 10_000_000,
                    "current_amount": 1_000_000,
                }
            )
            self.assertEqual(code, 201)
            self.assertEqual(created["target"]["months_of_expense"], 0)
            gid = created["goal_id"]

            # Force re-read via _row_to_goal (fresh store on same DB)
            store2 = SqliteEmergencyFundStore(url)
            use_store(store2)
            c2, got = service_get_goal(gid)
            self.assertEqual(c2, 200)
            self.assertEqual(got["target"]["months_of_expense"], 0)
            self.assertNotEqual(got["target"]["months_of_expense"], 3)

            c3, listed = service_list_goals("m0", type="debt_payoff")
            self.assertEqual(c3, 200)
            self.assertEqual(listed["items"][0]["target"]["months_of_expense"], 0)

            c4, prog = service_progress(gid, {"add_amount": 500_000})
            self.assertEqual(c4, 200)
            self.assertEqual(prog["target"]["months_of_expense"], 0)
            self.assertEqual(prog["current"]["amount"], 1_500_000)
        finally:
            use_store(InMemoryEmergencyFundStore())
            try:
                os.unlink(path)
            except OSError:
                pass

    def test_row_to_goal_does_not_or_three(self):
        src = REPOS.read_text(encoding="utf-8")
        self.assertNotIn('months_of_expense"] or 3', src)
        self.assertNotIn("months_of_expense'] or 3", src)
        self.assertIn('row["months_of_expense"] is None', src)


class TestCompletedBadgeNoOvershoot(unittest.TestCase):
    def setUp(self) -> None:
        _reset_memory()
        self.html = HTML.read_text(encoding="utf-8")
        self.client = TestClient(create_app())

    def test_html_hoan_thanh_badge_and_disable(self):
        self.assertIn("Hoàn thành", self.html)
        self.assertIn("badge-done", self.html)
        self.assertIn("g.status==='completed'", self.html)
        self.assertIn("Mục tiêu đã hoàn thành — không cộng thêm.", self.html)
        self.assertIn("Đã hoàn thành", self.html)

    def test_api_rejects_progress_after_completed(self):
        code, created = service_create_goal(
            {
                "user_id": "done1",
                "type": "debt_payoff",
                "target_amount": 5_000_000,
                "current_amount": 5_000_000,
            }
        )
        self.assertEqual(code, 201)
        self.assertEqual(created["status"], "completed")
        gid = created["goal_id"]
        c2, err = service_progress(gid, {"add_amount": 100_000})
        self.assertEqual(c2, 400)
        self.assertIn("completed", str(err.get("error", "")).lower())

    def test_apply_progress_raises_when_completed(self):
        _, created = service_create_goal(
            {
                "user_id": "done2",
                "type": "debt_payoff",
                "target_amount": 2_000_000,
                "current_amount": 2_000_000,
            }
        )
        from welora.goals_api import STORE

        goal = STORE.get(created["goal_id"])
        self.assertEqual(goal.status, "completed")
        with self.assertRaises(ValueError) as ctx:
            apply_progress(goal, add_amount=1)
        self.assertIn("completed", str(ctx.exception).lower())

    def test_page_serves_badge(self):
        r = self.client.get("/app/goals")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Hoàn thành", r.text)


class TestFocusDebtExistingShowsProgress(unittest.TestCase):
    def setUp(self) -> None:
        self.html = HTML.read_text(encoding="utf-8")
        self.client = TestClient(create_app())

    def test_focus_debt_progress_not_create_when_exists(self):
        self.assertIn("function applyDebtFocus", self.html)
        self.assertIn("hasDebt", self.html)
        self.assertIn("hasDebtGoal()", self.html)
        # create banner copy still present for no-debt path
        self.assertIn("Bạn đã khai nợ nguy hiểm — tạo mục tiêu trả nợ", self.html)
        # progress CTA when debt already exists
        self.assertIn(
            "Đã có mục tiêu trả nợ — dùng Cộng tiến độ bên dưới.",
            self.html,
        )
        # when hasDebt, scroll/focus progress (addBox), not create form
        self.assertIn("addBox.classList.add('focus-debt')", self.html)
        self.assertIn("box.classList.remove('focus-debt')", self.html)

    def test_debt_progress_placeholder_paid_toward_target(self):
        self.assertIn("Số đã trả hướng mục tiêu", self.html)
        # not create/new-debt wording on progress placeholder path
        self.assertIn(
            "amt.placeholder=(g.type==='debt_payoff')?'Số đã trả hướng mục tiêu'",
            self.html,
        )

    def test_page_and_hard_constraints(self):
        r = self.client.get("/app/goals")
        self.assertEqual(r.status_code, 200)
        self.assertIn("debtFocusBanner", r.text)
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
