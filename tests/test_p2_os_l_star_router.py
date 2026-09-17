"""P2 OS: Full L-* policy router — unit per rule + Mode C choke-point."""

from __future__ import annotations

import unittest

from welora.agent import (
    CONFIDENCE_THRESHOLD,
    HARD,
    PRIORITY,
    TARGET_MONTHS as AGENT_TARGET,
    run_hard_deny_suite,
)
from welora.core_constitution import CORE_CODES, get_core_constitution
from welora.fixtures import load_pair, reset_all_stores
from welora.mode_c_act import (
    ACT_CREATE_ENVELOPE,
    ACT_LOCK_ENVELOPE,
    ACT_WITHDRAW_EFUND,
    MODE_C,
    POLICY_COOL_OFF,
    POLICY_DUAL_CONTROL,
    POLICY_VERSION,
    companion_confirm_act,
    confirm_act,
    list_envelopes,
    propose_act,
    reset_mode_c_store,
    set_companion,
    set_persona,
)
from welora.policy_engine import (
    MSG,
    POLICY_VERSION as ROUTER_VERSION,
    RULE_ORDER,
    evaluate,
    registered_rule_ids,
)
from welora.safety_gate import TARGET_MONTHS


class TestP2OsLStarRouter(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_all_stores()
        reset_mode_c_store()
        cls.pair = load_pair()

    def setUp(self) -> None:
        reset_mode_c_store()
        reset_all_stores()
        self.pair = load_pair()
        self.uid = self.pair["passed"]["user_id"]
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
        self.assertTrue(len(CORE_CODES) >= 10)
        for i in range(1, 11):
            self.assertIn(f"CORE-{i:02d}", CORE_CODES)
        self.assertTrue(get_core_constitution())
        self.assertEqual(POLICY_VERSION, ROUTER_VERSION)
        self.assertTrue(POLICY_VERSION.startswith("L-"))
        self.assertEqual(MODE_C, "C")

    def test_registry_fixed_order(self):
        self.assertEqual(registered_rule_ids(), RULE_ORDER)
        self.assertEqual(
            list(RULE_ORDER),
            [
                "L-EMERGENCY",
                "L-PILLAR-ORDER",
                "L-PROTECT-CAP",
                "L-PROTECT-COVER",
                "L-RETIRE-FLOOR",
                "L-ENVELOPE-P3",
                "L-ENVELOPE-P4",
                "L-NO-ILP-NEW",
                "L-ILP-AUDIT",
                "L-BHXH-TOPUP",
                "L-ESTATE",
                "L-NO-TICKER",
                "L-NO-SPEC",
                "L-COOL-OFF",
                "L-DUAL-CONTROL",
                "L-FIDUCIARY",
            ],
        )

    # --- One assert per registered rule ---
    def test_rule_l_emergency(self):
        d = evaluate(
            {"kind": "withdraw_emergency_fund", "invest_from_efund": True},
            "P1",
            {},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-EMERGENCY")
        self.assertIn("L-EMERGENCY", d.message_vi)

    def test_rule_l_pillar_order(self):
        d = evaluate(
            {"kind": "buy_ticker", "growth_act": True},
            "P1",
            {"gate_status": "not_passed"},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-PILLAR-ORDER")

    def test_rule_l_protect_cap(self):
        d = evaluate(
            {"kind": "schedule_bh_reminder", "params": {"protect_premium_pct": 0.40}},
            "P2",
            {},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-PROTECT-CAP")

    def test_rule_l_protect_cover(self):
        d = evaluate({"kind": "cancel_insurance_cover", "cancel_insurance_cover": True}, "P1", {})
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-PROTECT-COVER")

    def test_rule_l_retire_floor(self):
        d = evaluate(
            {
                "kind": "withdraw_retire",
                "params": {"retire_remaining": 10, "retire_floor": 100},
            },
            "P3",
            {},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-RETIRE-FLOOR")

    def test_rule_l_envelope_p3(self):
        d = evaluate(
            {"kind": "create_envelope", "envelope_p3_violation": True},
            "P3",
            {},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-ENVELOPE-P3")

    def test_rule_l_envelope_p4(self):
        d = evaluate(
            {"kind": "cross_take", "cross_take": True, "from_locked": True},
            "P4",
            {},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-ENVELOPE-P4")

    def test_rule_l_no_ilp_new(self):
        d = evaluate({"kind": "ilp_new", "message": "mua ILP mới"}, "P1", {})
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-NO-ILP-NEW")

    def test_rule_l_ilp_audit(self):
        d = evaluate(
            {
                "kind": "ilp_audit",
                "ilp_audit": True,
                "params": {"submit_forms": True},
            },
            "P1",
            {},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-ILP-AUDIT")

    def test_rule_l_bhxh_topup(self):
        d = evaluate(
            {
                "kind": "schedule_bh_reminder",
                "params": {
                    "reminder_kind": "BHXH_topup",
                    "submit_forms": True,
                    "no_submit_forms": False,
                },
            },
            "P1",
            {},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-BHXH-TOPUP")

    def test_rule_l_estate(self):
        d = evaluate(
            {"kind": "open_estate_checklist", "legal_will": True, "message": "soạn di chúc pháp lý"},
            "P1",
            {},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-ESTATE")

    def test_rule_l_no_ticker(self):
        d = evaluate({"message": "Mua mã VNM giúp tôi"}, "P1", {})
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-NO-TICKER")

    def test_rule_l_no_spec(self):
        d = evaluate({"message": "all-in cổ phiếu đòn bẩy"}, "P1", {})
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-NO-SPEC")

    def test_rule_l_cool_off(self):
        d = evaluate(
            {
                "kind": "withdraw_emergency_fund",
                "phase": "propose",
                "cool_off": {"triggered": True},
            },
            "P1",
            {"persona": "P1"},
        )
        self.assertEqual(d.verdict, "ESCALATE")
        self.assertEqual(d.rule_id, "L-COOL-OFF")
        self.assertTrue(d.escalate_flag)
        self.assertEqual(d.side_effect, "pending_cool_off")

    def test_rule_l_dual_control(self):
        d = evaluate(
            {"kind": "lock_envelope", "phase": "propose"},
            "P1",
            {"companion": None},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-DUAL-CONTROL")

    def test_rule_l_fiduciary(self):
        d = evaluate({"message": "Chuyển tiền ngân hàng 10 triệu"}, "P1", {})
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-FIDUCIARY")

    def test_allow_falls_through(self):
        d = evaluate(
            {
                "kind": "create_envelope",
                "params": {"title": "Du lịch", "no_bank_transfer": True},
                "phase": "propose",
            },
            "P1",
            {"gate_status": "passed", "companion": None},
        )
        self.assertEqual(d.verdict, "ALLOW")
        self.assertIsNone(d.rule_id)
        self.assertEqual(d.policy_version, ROUTER_VERSION)
        self.assertIn("mode", d.to_log())
        self.assertIn("tools_called", d.to_log())
        self.assertFalse(d.to_log()["escalate_flag"])

    def test_deny_surfaces_vi_rule_code(self):
        for code in RULE_ORDER:
            self.assertIn(code, MSG[code])

    # --- Mode C integration ---
    def test_mode_c_deny_blocks_write(self):
        code, out = propose_act(
            user_id=self.uid,
            message="Mua mã VNM giúp tôi",
            gate_status="passed",
            answer_confidence=0.95,
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("rule"), "L-NO-TICKER")
        self.assertIn("L-NO-TICKER", out.get("reply", "") + out.get("rule", ""))
        items = list_envelopes(self.uid)[1]["items"]
        self.assertEqual(items, [])

    def test_mode_c_escalate_cool_off_no_write(self):
        code, out = propose_act(
            user_id=self.uid,
            message="Rút quỹ khẩn cấp 5000000",
            gate_status="passed",
            answer_confidence=0.95,
            params={
                "amount": 5_000_000,
                "current_amount": 10_000_000,
                "essential_expense_monthly": 5_000_000,
            },
            reason="khẩn cấp y tế",
        )
        self.assertEqual(code, 200)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("status"), "pending_cool_off")
        self.assertEqual(out.get("rule"), POLICY_COOL_OFF)
        self.assertTrue(out.get("escalate_flag"))
        prop = out["act_proposal"]
        # Early confirm must not write
        ccode, cout = confirm_act(
            user_id=self.uid,
            proposal_id=prop["proposal_id"],
            confirm=True,
            gate_status="passed",
            answer_confidence=0.95,
            cool_off_advance=False,
        )
        self.assertEqual(ccode, 200)
        self.assertFalse(cout.get("ok"))
        self.assertEqual(cout.get("status"), "pending_cool_off")
        self.assertNotIn("act_id", cout)

    def test_mode_c_dual_still_behaves(self):
        # Missing companion → DENY, no write
        code, out = propose_act(
            user_id=self.uid,
            message="Khóa phong bì cấm lấy chéo",
            gate_status="passed",
            answer_confidence=0.95,
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("rule"), POLICY_DUAL_CONTROL)
        self.assertTrue(out.get("companion_missing"))

        companion = "user_companion_router_01"
        set_companion(user_id=self.uid, companion_user_id=companion)
        code, out = propose_act(
            user_id=self.uid,
            message="Khóa phong bì cấm lấy chéo",
            gate_status="passed",
            answer_confidence=0.95,
        )
        self.assertEqual(code, 200)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("status"), "pending_dual")
        prop = out["act_proposal"]
        # Primary confirm blocked
        ccode, cout = confirm_act(
            user_id=self.uid,
            proposal_id=prop["proposal_id"],
            confirm=True,
        )
        self.assertEqual(ccode, 403)
        self.assertEqual(cout.get("rule"), POLICY_DUAL_CONTROL)
        # Companion confirm writes
        dcode, done = companion_confirm_act(
            companion_user_id=companion,
            proposal_id=prop["proposal_id"],
            confirm=True,
        )
        self.assertEqual(dcode, 200)
        self.assertTrue(done.get("ok"))
        self.assertEqual(done.get("rule"), POLICY_DUAL_CONTROL)
        self.assertIn("act_id", done)
        self.assertIn("persona", done.get("log") or done)
        log = done.get("log") or {}
        self.assertIn("tools_called", log)
        self.assertIn("escalate_flag", log)
        self.assertEqual(log.get("mode"), MODE_C)

    def test_mode_c_allow_create_envelope_still_works(self):
        code, out = propose_act(
            user_id=self.uid,
            message="Tạo phong bì Du lịch",
            gate_status="passed",
            answer_confidence=0.95,
        )
        self.assertEqual(code, 200)
        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("needs_confirm"))
        prop = out["act_proposal"]
        self.assertEqual(prop["act_kind"], ACT_CREATE_ENVELOPE)
        ccode, done = confirm_act(
            user_id=self.uid,
            proposal_id=prop["proposal_id"],
            confirm=True,
            gate_status="passed",
            answer_confidence=0.95,
        )
        self.assertEqual(ccode, 200)
        self.assertTrue(done.get("ok"))
        self.assertIn("act_id", done)
        self.assertEqual(done.get("policy_version"), POLICY_VERSION)
        log = done.get("log") or {}
        self.assertEqual(log.get("mode"), MODE_C)
        self.assertIn("persona", log)
        self.assertIn("tools_called", log)
        self.assertFalse(log.get("escalate_flag"))


if __name__ == "__main__":
    unittest.main()
