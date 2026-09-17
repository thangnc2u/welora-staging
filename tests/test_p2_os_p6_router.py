"""P2 OS — P6 persona router specialization.

DoD:
1. L-EMERGENCY floors 6–12 months + 24 months medical → DENY when short
2. Money/estate Acts → L-DUAL-CONTROL (≥1 child); no self cool-off; create_envelope = dual
3. L-ESTATE: checklist ALLOW; legal will ESCALATE; large missing checklist DENY
4. L-NO-ILP-NEW absolute DENY + VI
5. Fixture P6 + child companion; 10/10 large Acts without child = DENY
6. Hard Deny / TARGET_MONTHS=3 / CORE / #186–#189 preserved
"""

from __future__ import annotations

import unittest

from welora.fixtures import build_p6_fixture, load_pair, reset_all_stores
from welora import goals_api
from welora.mode_c_act import (
    ACT_CHANGE_CEILING,
    ACT_CREATE_ENVELOPE,
    ACT_ESTATE_CHECKLIST,
    ACT_LOCK_ENVELOPE,
    ACT_WITHDRAW_EFUND,
    POLICY_DUAL_CONTROL,
    confirm_act,
    companion_confirm_act,
    propose_act,
    reset_mode_c_store,
    set_companion,
    set_persona,
)
from welora.policy_engine import (
    P6_EMERGENCY_FLOOR_MONTHS_MIN,
    P6_MEDICAL_FLOOR_MONTHS,
    evaluate,
)
from welora.safety_gate import TARGET_MONTHS

def _set_efund_months(user_id: str, months: float) -> None:
    g = goals_api.STORE.get_active_for_user(user_id)
    if g is None:
        # fallback: any goal for user
        for gid, goal in list(getattr(goals_api.STORE, "_by_id", {}).items()):
            if goal.user_id == user_id:
                g = goal
                break
    assert g is not None
    target = g.essential_expense_monthly * months
    try:
        goals_api.STORE.record_progress(g.goal_id, set_amount=target)
    except ValueError:
        g.current_amount = target
        g.status = "active"
        goals_api.STORE.save(g)



class TestP6RouterUnit(unittest.TestCase):
    def test_emergency_floor_constants(self):
        self.assertEqual(P6_EMERGENCY_FLOOR_MONTHS_MIN, 6)
        self.assertEqual(P6_MEDICAL_FLOOR_MONTHS, 24)
        self.assertEqual(TARGET_MONTHS, 3)

    def test_l_emergency_p6_below_floor_deny(self):
        d = evaluate(
            {
                "kind": "withdraw_emergency_fund",
                "params": {
                    "amount": 1_000_000,
                    "months_covered_after": 4.0,
                    "essential_expense_monthly": 10_000_000,
                    "touch_efund": True,
                },
            },
            "P6",
            {"efund_months_covered": 5.0},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-EMERGENCY")
        self.assertTrue(d.meta.get("fail_closed"))

    def test_l_emergency_p6_medical_24m_deny(self):
        d = evaluate(
            {
                "kind": "withdraw_emergency_fund",
                "message": "Rút quỹ KH trả viện phí",
                "params": {
                    "amount": 5_000_000,
                    "months_covered_after": 18.0,
                    "medical": True,
                    "purpose": "medical",
                    "touch_efund": True,
                },
            },
            "P6",
            {},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-EMERGENCY")
        self.assertEqual(d.meta.get("p6_floor_months"), 24)
        self.assertIn("24", d.message_vi)

    def test_l_emergency_p6_sufficient_allows_fallthrough(self):
        d = evaluate(
            {
                "kind": "withdraw_emergency_fund",
                "params": {
                    "amount": 1_000_000,
                    "months_covered_after": 10.0,
                    "touch_efund": True,
                },
            },
            "P6",
            {"companion": None},
        )
        # Floor OK → dual DENY (no child companion)
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-DUAL-CONTROL")

    def test_l_estate_checklist_allow_fallthrough_to_dual(self):
        d = evaluate(
            {
                "kind": "open_estate_checklist",
                "params": {"checklist_only": True, "no_legal_will": True},
            },
            "P6",
            {"companion": {"companion_user_id": "c1", "role": "child"}},
        )
        self.assertEqual(d.verdict, "ESCALATE")
        self.assertEqual(d.rule_id, "L-DUAL-CONTROL")
        self.assertEqual(d.side_effect, "pending_dual")

    def test_l_estate_legal_will_escalate_p6(self):
        d = evaluate(
            {
                "kind": "open_estate_checklist",
                "legal_will": True,
                "message": "soạn di chúc pháp lý",
            },
            "P6",
            {},
        )
        self.assertEqual(d.verdict, "ESCALATE")
        self.assertEqual(d.rule_id, "L-ESTATE")
        self.assertTrue(d.escalate_flag)

    def test_l_estate_large_missing_checklist_deny(self):
        d = evaluate(
            {"kind": "lock_envelope", "large_act": True, "params": {}},
            "P6",
            {"companion": {"companion_user_id": "c1", "role": "child"}},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-ESTATE")
        self.assertTrue(d.meta.get("missing_estate_checklist"))

    def test_l_no_ilp_new_absolute_p6(self):
        d = evaluate({"kind": "ilp_new", "message": "mua ILP mới"}, "P6", {})
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-NO-ILP-NEW")
        self.assertIn("P6", d.message_vi)
        self.assertIn("ILP", d.message_vi)

    def test_p6_create_envelope_escalates_dual_with_child(self):
        d = evaluate(
            {"kind": "create_envelope", "params": {"title": "Học phí"}},
            "P6",
            {"companion": {"companion_user_id": "child1", "role": "child"}},
        )
        self.assertEqual(d.verdict, "ESCALATE")
        self.assertEqual(d.rule_id, "L-DUAL-CONTROL")
        self.assertEqual(d.side_effect, "pending_dual")

    def test_p6_non_child_companion_deny(self):
        d = evaluate(
            {"kind": "create_envelope", "params": {}},
            "P6",
            {"companion": {"companion_user_id": "spouse1", "role": "spouse"}},
        )
        self.assertEqual(d.verdict, "DENY")
        self.assertEqual(d.rule_id, "L-DUAL-CONTROL")
        self.assertTrue(d.meta.get("companion_not_child") or d.meta.get("child_companion_required"))


class TestP6RouterModeC(unittest.TestCase):
    def setUp(self):
        reset_all_stores()
        reset_mode_c_store()
        self.fx = build_p6_fixture(user_id="user_p6_router", companion_user_id="user_p6_child")
        self.uid = self.fx["user_id"]
        self.child = self.fx["companion_user_id"]

    def tearDown(self):
        reset_mode_c_store()
        reset_all_stores()

    def test_fixture_persona_and_child(self):
        self.assertEqual(self.fx["persona"], "P6")
        self.assertEqual(self.fx["companion_role"], "child")
        g = goals_api.STORE.get_active_for_user(self.uid)
        self.assertGreaterEqual(g.current_amount / g.essential_expense_monthly, 6.0)

    def test_create_envelope_p6_pending_dual(self):
        code, out = propose_act(
            user_id=self.uid,
            message="Tạo phong bì học phí",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("status"), "pending_dual")
        self.assertEqual(out.get("rule"), POLICY_DUAL_CONTROL)
        self.assertTrue(out.get("needs_companion_confirm"))

    def test_create_envelope_p6_no_child_deny(self):
        reset_mode_c_store()
        reset_all_stores()
        pair = load_pair()
        uid = pair["passed"]["user_id"]
        set_persona(user_id=uid, persona="P6")
        # top up EF not required for create_envelope
        code, out = propose_act(
            user_id=uid,
            message="Tạo phong bì du lịch",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("rule"), POLICY_DUAL_CONTROL)
        self.assertTrue(out.get("companion_missing"))

    def test_p6_emergency_short_balance_deny(self):
        g = goals_api.STORE.get_active_for_user(self.uid)
        # Drain to ~4 months — below P6 floor 6
        _set_efund_months(self.uid, 4)
        amount = g.essential_expense_monthly * 0.5
        code, out = propose_act(
            user_id=self.uid,
            message=f"Rút quỹ khẩn cấp {int(amount)}",
            gate_status="passed",
            answer_confidence=0.90,
            params={"amount": amount},
            reason="test floor",
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("rule"), "L-EMERGENCY")
        self.assertNotEqual(out.get("status"), "pending_cool_off")

    def test_p6_medical_24m_deny(self):
        g = goals_api.STORE.get_active_for_user(self.uid)
        # 12 months OK for general, short for medical 24
        amount = g.essential_expense_monthly * 1.0
        code, out = propose_act(
            user_id=self.uid,
            message=f"Rút quỹ khẩn cấp {int(amount)} trả viện phí y tế",
            gate_status="passed",
            answer_confidence=0.90,
            params={"amount": amount, "medical": True},
            reason="medical",
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("rule"), "L-EMERGENCY")

    def test_p6_no_ilp_new_mode_c(self):
        code, out = propose_act(
            user_id=self.uid,
            message="Tôi muốn mua ILP mới",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("rule"), "L-NO-ILP-NEW")

    def test_p6_legal_will_escalate(self):
        code, out = propose_act(
            user_id=self.uid,
            message="Giúp soạn di chúc pháp lý giúp tôi",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("rule"), "L-ESTATE")
        self.assertTrue(out.get("escalate_flag"))

    def test_p6_estate_checklist_dual_then_companion(self):
        code, out = propose_act(
            user_id=self.uid,
            message="Mở checklist di sản",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertTrue(out.get("ok"))
        self.assertEqual(out.get("status"), "pending_dual")
        pid = out["act_proposal"]["proposal_id"]
        # primary cannot confirm
        blocked = confirm_act(
            user_id=self.uid,
            proposal_id=pid,
            confirm=True,
            gate_status="passed",
            answer_confidence=0.99,
        )
        self.assertEqual(blocked[0], 403)
        c2, done = companion_confirm_act(
            companion_user_id=self.child,
            proposal_id=pid,
            confirm=True,
        )
        self.assertEqual(c2, 200)
        self.assertTrue(done.get("ok"))

    def test_10_of_10_large_acts_without_child_deny(self):
        """DoD #5: 10/10 large Acts without child companion = DENY."""
        reset_mode_c_store()
        reset_all_stores()
        pair = load_pair()
        uid = pair["passed"]["user_id"]
        set_persona(user_id=uid, persona="P6")
        g = goals_api.STORE.get_active_for_user(uid)
        _set_efund_months(uid, 12)
        # Seed one envelope so lock/ceiling resolve
        code0, env = propose_act(
            user_id=pair["passed"]["user_id"],
            message="Tạo phong bì tạm",
            gate_status="passed",
            answer_confidence=0.90,
        )
        # Without companion create is DENY for P6 — seed via temporary P1
        set_persona(user_id=uid, persona="P1")
        code0, env = propose_act(
            user_id=uid,
            message="Tạo phong bì tạm P1",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertTrue(env.get("ok"))
        pid0 = env["act_proposal"]["proposal_id"]
        confirm_act(
            user_id=uid,
            proposal_id=pid0,
            confirm=True,
            gate_status="passed",
            answer_confidence=0.90,
        )
        set_persona(user_id=uid, persona="P6")
        # Ensure estate checklist present so lock/ceiling hit dual not L-ESTATE
        from welora import mode_c_act as mca

        mca._ESTATE[uid] = {
            "kind": "estate_checklist",
            "no_legal_will": True,
            "items": ["stub"],
        }

        scenarios = [
            ("Tạo phong bì học phí A", {}),
            ("Tạo phong bì học phí B", {}),
            ("Khóa phong bì lấy chéo", {}),
            ("Đổi trần phong bì lên 50000000", {"target_amount": 50_000_000}),
            ("Mở checklist di sản", {}),
            (
                "Rút quỹ khẩn cấp 5000000",
                {"amount": 5_000_000},
            ),
            (
                "Rút quỹ khẩn cấp 8000000",
                {"amount": 8_000_000},
            ),
            ("Tạo phong bì nghỉ hưu", {}),
            ("Khóa phong bì không lấy chéo", {}),
            ("Đổi trần phong bì 20000000", {"target_amount": 20_000_000}),
        ]
        self.assertEqual(len(scenarios), 10)
        denies = 0
        for msg, params in scenarios:
            code, out = propose_act(
                user_id=uid,
                message=msg,
                gate_status="passed",
                answer_confidence=0.90,
                params=params or None,
                reason="large act no child",
            )
            self.assertEqual(code, 200, msg)
            self.assertFalse(out.get("ok"), msg)
            # DENY (dual missing child, or emergency, or estate) — never ALLOW write
            self.assertIsNone(out.get("act_proposal"), msg)
            self.assertNotEqual(out.get("status"), "proposed", msg)
            self.assertNotEqual(out.get("status"), "pending_cool_off", msg)
            denies += 1
        self.assertEqual(denies, 10)

    def test_p6_no_self_cool_off_on_large_withdraw(self):
        g = goals_api.STORE.get_active_for_user(self.uid)
        amount = g.current_amount * 0.25
        # Strip companion to force DENY dual (not cool-off)
        from welora import mode_c_act as mca

        mca._COMPANIONS.pop(self.uid, None)
        code, out = propose_act(
            user_id=self.uid,
            message=f"Rút quỹ khẩn cấp {int(amount)}",
            gate_status="passed",
            answer_confidence=0.90,
            params={"amount": amount},
            reason="should be dual not cool-off",
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertNotEqual(out.get("status"), "pending_cool_off")
        self.assertIn(out.get("rule"), (POLICY_DUAL_CONTROL, "L-DUAL-CONTROL"))


if __name__ == "__main__":
    unittest.main()
