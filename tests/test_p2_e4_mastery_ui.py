"""P2-E4 — Mastery gate + API. Fund đủ + mastery < apply → not_passed."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.fixtures import reset_all_stores
from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.goals_api import use_store
from welora.mastery import reset_mastery_store, set_state
from welora.safety_gate import TARGET_MONTHS


class TestP2E4MasteryGate(unittest.TestCase):
    def setUp(self) -> None:
        use_store(InMemoryEmergencyFundStore())
        reset_all_stores()
        reset_mastery_store()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        use_store(InMemoryEmergencyFundStore())
        reset_all_stores()
        reset_mastery_store()

    def test_health_untouched(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["gate_months"], 3)
        self.assertTrue(body["hard_deny"])
        self.assertIn("dialect", body)
        self.assertEqual(TARGET_MONTHS, 3)

    def test_safety_html_has_mastery_badge(self):
        html = Path("welora/api/static/safety.html").read_text(encoding="utf-8")
        self.assertIn("masteryBadge", html)
        self.assertIn("meets_gate", html)
        self.assertIn("SAFE-02", html)
        self.assertIn("hs-card", html)
        self.assertIn("Điểm sức khởe", html)
        self.assertIn("btnSave", html)
        self.assertIn("set_amount", html)

    def test_fund_enough_familiar_not_passed(self):
        uid = "e4_familiar"
        self.client.post(
            "/goals",
            json={"user_id": uid, "essential_expense_monthly": 10_000_000, "current_amount": 30_000_000},
        )
        r = self.client.patch(f"/users/{uid}/mastery", json={"state": "familiar"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["state"], "familiar")
        self.assertFalse(r.json()["meets_gate"])
        gate = self.client.get(f"/users/{uid}/safety-gate").json()
        self.assertEqual(gate["status"], "not_passed")
        self.assertIn("mastery_missing", gate["reasons"])
        self.assertGreaterEqual(gate["months_covered"], 3)

    def test_fund_enough_apply_passed(self):
        uid = "e4_apply"
        self.client.post(
            "/goals",
            json={"user_id": uid, "essential_expense_monthly": 10_000_000, "current_amount": 30_000_000},
        )
        r = self.client.patch(f"/users/{uid}/mastery", json={"state": "apply"})
        self.assertTrue(r.json()["meets_gate"])
        gate = self.client.get(f"/users/{uid}/safety-gate").json()
        self.assertEqual(gate["status"], "passed")
        self.assertNotIn("mastery_missing", gate.get("reasons") or [])

    def test_score_does_not_pass_gate(self):
        uid = "e4_score"
        self.client.post(
            "/goals",
            json={"user_id": uid, "essential_expense_monthly": 10_000_000, "current_amount": 30_000_000},
        )
        set_state(uid, "learning")
        hs = self.client.get(f"/users/{uid}/health-score").json()
        self.assertIn("score", hs)
        gate = self.client.get(f"/users/{uid}/safety-gate").json()
        self.assertEqual(gate["status"], "not_passed")
        self.assertFalse(bool(hs.get("can_bypass") or hs.get("can_bypass_gate_with_score")))


class TestP2E4MasterySqlite(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_store = os.environ.get("WELORA_STORE")
        self._prev_url = os.environ.get("WELORA_DB_URL")
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        os.environ["WELORA_STORE"] = "sqlite"
        os.environ["WELORA_DB_URL"] = self._tmp.name
        from welora.db.repos import SqliteEmergencyFundStore
        use_store(SqliteEmergencyFundStore(self._tmp.name))
        reset_all_stores()
        reset_mastery_store()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        use_store(InMemoryEmergencyFundStore())
        reset_all_stores()
        reset_mastery_store()
        if self._prev_store is None:
            os.environ.pop("WELORA_STORE", None)
        else:
            os.environ["WELORA_STORE"] = self._prev_store
        if self._prev_url is None:
            os.environ.pop("WELORA_DB_URL", None)
        else:
            os.environ["WELORA_DB_URL"] = self._prev_url
        try:
            Path(self._tmp.name).unlink(missing_ok=True)
        except Exception:
            pass

    def test_sqlite_familiar_not_passed(self):
        uid = "e4_sql_fam"
        self.client.post(
            "/goals",
            json={"user_id": uid, "essential_expense_monthly": 10_000_000, "current_amount": 30_000_000},
        )
        self.client.patch(f"/users/{uid}/mastery", json={"state": "familiar"})
        gate = self.client.get(f"/users/{uid}/safety-gate").json()
        self.assertEqual(gate["status"], "not_passed")
        self.assertIn("mastery_missing", gate["reasons"])

    def test_sqlite_apply_passed(self):
        uid = "e4_sql_apply"
        self.client.post(
            "/goals",
            json={"user_id": uid, "essential_expense_monthly": 10_000_000, "current_amount": 30_000_000},
        )
        self.client.patch(f"/users/{uid}/mastery", json={"state": "apply"})
        gate = self.client.get(f"/users/{uid}/safety-gate").json()
        self.assertEqual(gate["status"], "passed")


if __name__ == "__main__":
    unittest.main()
