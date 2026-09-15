"""P2 OS Cooling-off product (L-COOL-OFF) — Founder 15/09.

Override sàn quỹ KH or transfer ≥20% → pending_cool_off + reason + 24h.
P6 → dual-control escalate (not self cool-off). Gate/confidence server-side.
"""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.agent import (
    CONFIDENCE_THRESHOLD,
    HARD,
    PRIORITY,
    TARGET_MONTHS as AGENT_TARGET,
    run_hard_deny_suite,
)
from welora.api.app import create_app
from welora.fixtures import load_pair, reset_all_stores
from welora import goals_api
from welora.mode_c_act import (
    ACT_CREATE_ENVELOPE,
    ACT_WITHDRAW_EFUND,
    COOL_OFF_HOURS,
    MODE_C,
    POLICY_COOL_OFF,
    POLICY_DUAL_CONTROL,
    POLICY_VERSION,
    TRANSFER_PCT_THRESHOLD,
    UNDO_HOURS,
    companion_confirm_act,
    confirm_act,
    evaluate_cool_off_trigger,
    inject_clock_advance,
    propose_act,
    reset_mode_c_store,
    set_companion,
    set_persona,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "welora" / "api" / "static" / "chat.html"


class TestP2OsCoolingOff(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_all_stores()
        reset_mode_c_store()
        cls.pair = load_pair()

    def setUp(self) -> None:
        reset_mode_c_store()
        # Keep fixtures' EF goals — only reset Mode C store + re-load pair EF
        reset_all_stores()
        self.pair = load_pair()
        self.client = TestClient(create_app())
        self.uid = self.pair["passed"]["user_id"]
        self.companion = "user_companion_cool_01"
        set_persona(user_id=self.uid, persona="P1")

    def test_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(AGENT_TARGET, 3)
        self.assertEqual(CONFIDENCE_THRESHOLD, 0.80)
        self.assertEqual(HARD, {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"})
        self.assertEqual(
            PRIORITY,
            ["R01", "R03", "R02", "R08", "R09", "R06", "R07", "R04", "R05"],
        )
        passed_n, failed = run_hard_deny_suite()
        self.assertEqual(failed, [])
        self.assertEqual(passed_n, 8)
        self.assertTrue(POLICY_VERSION.startswith("L-"))
        self.assertEqual(POLICY_COOL_OFF, "L-COOL-OFF")
        self.assertEqual(COOL_OFF_HOURS, 24)
        self.assertEqual(UNDO_HOURS, 24)
        self.assertEqual(TRANSFER_PCT_THRESHOLD, 0.20)
        self.assertEqual(MODE_C, "C")
        from welora.core_constitution import CORE_CODES, get_core_constitution

        self.assertTrue(len(CORE_CODES) >= 10)
        for i in range(1, 11):
            self.assertIn(f"CORE-{i:02d}", CORE_CODES)
        core = get_core_constitution()
        self.assertTrue(core)

    def test_ui_vi_red_cool_off_chip(self):
        html = CHAT.read_text(encoding="utf-8")
        self.assertIn("L-COOL-OFF", html)
        self.assertIn("CẢNH BÁO ĐỎ", html)
        self.assertIn("mcCoolReason", html)
        self.assertIn("coolOffChip", html)
        self.assertIn("#ef4444", html)

    def test_evaluate_below_floor_and_pct(self):
        goal = goals_api.STORE.get_active_for_user(self.uid)
        self.assertIsNotNone(goal)
        # passed fixture: ~3.2 months — withdraw enough to go below 3mo floor
        amount_floor = goal.current_amount - (goal.essential_expense_monthly * 2.5)
        meta = evaluate_cool_off_trigger(user_id=self.uid, amount=amount_floor)
        self.assertTrue(meta["triggered"])
        self.assertTrue(meta["below_floor"])

        # ≥20% even if still above floor
        amt20 = goal.current_amount * 0.25
        meta2 = evaluate_cool_off_trigger(user_id=self.uid, amount=amt20)
        self.assertTrue(meta2["triggered"])
        self.assertTrue(meta2["large_transfer"])

        # tiny amount — no cool-off
        meta3 = evaluate_cool_off_trigger(user_id=self.uid, amount=1000)
        self.assertFalse(meta3["triggered"])

    def test_propose_cool_off_needs_reason(self):
        goal = goals_api.STORE.get_active_for_user(self.uid)
        amount = goal.current_amount * 0.30
        code, out = propose_act(
            user_id=self.uid,
            message=f"Rút quỹ khẩn cấp {int(amount)}",
            gate_status="passed",
            answer_confidence=0.90,
            params={"amount": amount},
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("status"), "pending_cool_off")
        self.assertEqual(out.get("rule"), POLICY_COOL_OFF)
        self.assertTrue(out.get("needs_reason"))
        self.assertEqual(out.get("warning_level"), "red")
        self.assertIn("L-COOL-OFF", out.get("reply") or "")
        self.assertIsNone(out.get("act_proposal"))
        # no EF mutation
        g2 = goals_api.STORE.get_active_for_user(self.uid)
        self.assertEqual(g2.current_amount, goal.current_amount)

    def test_cool_off_path_early_confirm_stays_pending(self):
        goal = goals_api.STORE.get_active_for_user(self.uid)
        amount = goal.current_amount * 0.30
        code, out = propose_act(
            user_id=self.uid,
            message=f"Rút quỹ khẩn cấp {int(amount)}",
            gate_status="passed",
            answer_confidence=0.90,
            params={"amount": amount},
            reason="Cần tiền sửa nhà gấp",
        )
        self.assertEqual(code, 200)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("status"), "pending_cool_off")
        self.assertEqual(out.get("rule"), POLICY_COOL_OFF)
        self.assertTrue(out.get("needs_cool_off_wait"))
        pid = out["act_proposal"]["proposal_id"]
        self.assertEqual(out["act_proposal"]["act_kind"], ACT_WITHDRAW_EFUND)
        self.assertTrue(str(out["act_proposal"].get("reason") or ""))

        # Early confirm → still pending, no write
        code2, early = confirm_act(
            user_id=self.uid,
            proposal_id=pid,
            confirm=True,
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code2, 200)
        self.assertFalse(early.get("ok"))
        self.assertEqual(early.get("status"), "pending_cool_off")
        self.assertTrue(early.get("still_pending") or early.get("needs_cool_off_wait"))
        g2 = goals_api.STORE.get_active_for_user(self.uid)
        self.assertEqual(g2.current_amount, goal.current_amount)

    def test_advance_hook_allows_execute(self):
        goal = goals_api.STORE.get_active_for_user(self.uid)
        before = goal.current_amount
        amount = before * 0.30
        _, out = propose_act(
            user_id=self.uid,
            message=f"Rút quỹ khẩn cấp {int(amount)}",
            gate_status="passed",
            answer_confidence=0.90,
            params={"amount": amount},
            reason="Lý do UAT advance",
        )
        pid = out["act_proposal"]["proposal_id"]

        # HTTP with advance header
        r = self.client.post(
            "/agent/mode-c/confirm",
            json={"user_id": self.uid, "proposal_id": pid, "confirm": True},
            headers={"X-Test-Cool-Off-Advance": "1"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("policy_version"), POLICY_COOL_OFF)
        self.assertEqual(body.get("act_kind"), ACT_WITHDRAW_EFUND)
        g2 = goals_api.STORE.get_active_for_user(self.uid)
        self.assertAlmostEqual(g2.current_amount, before - amount, places=2)
        self.assertIn("undo", body)
        self.assertEqual(body["undo"]["hours"], UNDO_HOURS)

    def test_clock_inject_allows_execute(self):
        goal = goals_api.STORE.get_active_for_user(self.uid)
        before = goal.current_amount
        amount = before * 0.22
        _, out = propose_act(
            user_id=self.uid,
            message=f"Chuyển từ quỹ khẩn cấp {int(amount)}",
            gate_status="passed",
            answer_confidence=0.90,
            params={"amount": amount},
            reason="Clock inject test",
        )
        pid = out["act_proposal"]["proposal_id"]
        inject_clock_advance(hours=COOL_OFF_HOURS + 0.1)
        code, done = confirm_act(
            user_id=self.uid,
            proposal_id=pid,
            confirm=True,
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertTrue(done.get("ok"))
        g2 = goals_api.STORE.get_active_for_user(self.uid)
        self.assertAlmostEqual(g2.current_amount, before - amount, places=2)

    def test_p6_escalates_to_dual_not_self_cool_off(self):
        set_persona(user_id=self.uid, persona="P6")
        goal = goals_api.STORE.get_active_for_user(self.uid)
        amount = goal.current_amount * 0.30

        # Missing companion → DENY dual (not pending_cool_off alone)
        code, out = propose_act(
            user_id=self.uid,
            message=f"Rút quỹ khẩn cấp {int(amount)}",
            gate_status="passed",
            answer_confidence=0.90,
            params={"amount": amount},
            reason="P6 should not self cool-off",
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("rule"), POLICY_DUAL_CONTROL)
        self.assertTrue(out.get("cool_off_escalated_to_dual") or out.get("companion_missing"))
        self.assertNotEqual(out.get("status"), "pending_cool_off")
        self.assertIsNone(out.get("act_proposal"))

        # With companion → pending_dual
        set_companion(user_id=self.uid, companion_user_id=self.companion)
        code2, out2 = propose_act(
            user_id=self.uid,
            message=f"Rút quỹ khẩn cấp {int(amount)}",
            gate_status="passed",
            answer_confidence=0.90,
            params={"amount": amount},
            reason="P6 dual path",
        )
        self.assertEqual(code2, 200)
        self.assertTrue(out2.get("ok"))
        self.assertEqual(out2.get("status"), "pending_dual")
        self.assertEqual(out2.get("rule"), POLICY_DUAL_CONTROL)
        self.assertTrue(out2.get("cool_off_escalated_to_dual"))
        self.assertTrue(out2.get("needs_companion_confirm"))
        pid = out2["act_proposal"]["proposal_id"]

        # Primary confirm blocked
        blocked = confirm_act(
            user_id=self.uid,
            proposal_id=pid,
            confirm=True,
            gate_status="passed",
            answer_confidence=0.99,
            cool_off_advance=True,
        )
        self.assertEqual(blocked[0], 403)

        before = goals_api.STORE.get_active_for_user(self.uid).current_amount
        code3, done = companion_confirm_act(
            companion_user_id=self.companion,
            proposal_id=pid,
            confirm=True,
        )
        self.assertEqual(code3, 200)
        self.assertTrue(done.get("ok"))
        after = goals_api.STORE.get_active_for_user(self.uid).current_amount
        self.assertAlmostEqual(after, before - amount, places=2)

    def test_small_withdraw_no_cool_off_normal_confirm(self):
        goal = goals_api.STORE.get_active_for_user(self.uid)
        amount = 5000.0  # tiny vs ~32M
        code, out = propose_act(
            user_id=self.uid,
            message=f"Rút quỹ khẩn cấp {int(amount)}",
            gate_status="passed",
            answer_confidence=0.90,
            params={"amount": amount},
        )
        self.assertEqual(code, 200)
        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("needs_confirm"))
        self.assertEqual(out["act_proposal"]["status"], "proposed")
        self.assertEqual(out.get("policy_version"), POLICY_VERSION)
        pid = out["act_proposal"]["proposal_id"]
        before = goal.current_amount
        code2, done = confirm_act(
            user_id=self.uid,
            proposal_id=pid,
            confirm=True,
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code2, 200)
        self.assertTrue(done.get("ok"))
        after = goals_api.STORE.get_active_for_user(self.uid).current_amount
        self.assertAlmostEqual(after, before - amount, places=2)

    def test_create_envelope_unaffected(self):
        code, out = propose_act(
            user_id=self.uid,
            message="Tạo phong bì học phí",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertTrue(out["ok"])
        self.assertEqual(out["act_proposal"]["act_kind"], ACT_CREATE_ENVELOPE)
        self.assertEqual(out["act_proposal"]["status"], "proposed")

    def test_http_propose_confirm_spoof_gate_ignored(self):
        """Align #184: client gate/confidence ignored on cool-off confirm."""
        # not_passed user cannot propose cool-off write path
        np = self.pair["not_passed"]["user_id"]
        set_persona(user_id=np, persona="P1")
        r = self.client.post(
            "/agent/mode-c/propose",
            json={
                "user_id": np,
                "message": "Rút quỹ khẩn cấp 5000000",
                "reason": "spoof",
                "gate_status": "passed",
                "answer_confidence": 0.99,
                "params": {"amount": 5_000_000},
            },
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("gate_blocked") or not r.json().get("ok"))

    def test_http_cool_off_happy_with_advance(self):
        goal = goals_api.STORE.get_active_for_user(self.uid)
        amount = goal.current_amount * 0.35
        prop = self.client.post(
            "/agent/mode-c/propose",
            json={
                "user_id": self.uid,
                "message": f"Rút quỹ khẩn cấp {int(amount)}",
                "reason": "HTTP UAT",
                "persona": "P1",
                "params": {"amount": amount},
                "gate_status": "not_passed",
                "answer_confidence": 0.1,
            },
        )
        self.assertEqual(prop.status_code, 200)
        body = prop.json()
        self.assertEqual(body.get("status"), "pending_cool_off")
        pid = body["act_proposal"]["proposal_id"]

        early = self.client.post(
            "/agent/mode-c/confirm",
            json={"user_id": self.uid, "proposal_id": pid, "confirm": True},
        )
        self.assertEqual(early.status_code, 200)
        self.assertEqual(early.json().get("status"), "pending_cool_off")
        self.assertFalse(early.json().get("ok"))

        done = self.client.post(
            "/agent/mode-c/confirm",
            json={"user_id": self.uid, "proposal_id": pid, "confirm": True},
            headers={"X-Test-Cool-Off-Advance": "true"},
        )
        self.assertEqual(done.status_code, 200)
        self.assertTrue(done.json().get("ok"))


if __name__ == "__main__":
    unittest.main()
