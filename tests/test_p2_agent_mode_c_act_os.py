"""P2 Agent Mode C — Act nội bộ OS (MVP). G1 confirm ≠ L2. Hard Deny untouched."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.agent import (
    CONFIDENCE_THRESHOLD,
    HARD,
    PRIORITY,
    TARGET_MONTHS as AGENT_TARGET,
    evaluate_pre_rules,
    run_hard_deny_suite,
)
from welora.api.app import create_app
from welora.chat_service import reset_logs, service_chat
from welora.fixtures import load_pair, reset_all_stores
from welora.mode_c_act import (
    ACT_CREATE_ENVELOPE,
    CROSS_TAKE_SUPPORTED,
    MODE_C,
    MODE_C_CHIP,
    MODE_C_DISCLAIMER,
    POLICY_VERSION,
    UNDO_HOURS,
    companion_confirm_act,
    confirm_act,
    detect_external_deny,
    list_envelopes,
    propose_act,
    reset_mode_c_store,
    set_companion,
    undo_act,
)
from welora.pre_rule_service import context_from_seed
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "welora" / "api" / "static" / "chat.html"


class TestP2AgentModeCActOs(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_all_stores()
        reset_logs()
        reset_mode_c_store()
        cls.pair = load_pair()
        cls.html = CHAT.read_text(encoding="utf-8")

    def setUp(self) -> None:
        reset_mode_c_store()
        reset_logs()
        self.client = TestClient(create_app())
        self.passed = self.pair["passed"]["agent_context_seed"]
        self.not_passed = self.pair["not_passed"]["agent_context_seed"]

    # --- Hard constraints untouched ---
    def test_hard_constraints_untouched(self):
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
        # L-* stub additive only
        self.assertTrue(POLICY_VERSION.startswith("L-"))
        self.assertEqual(MODE_C, "C")
        self.assertIn("Hành động trên OS", MODE_C_DISCLAIMER)
        self.assertIn("24 giờ", MODE_C_DISCLAIMER)

    # --- Gate + confidence gate Mode C ---
    def test_gate_not_passed_blocks_mode_c_propose(self):
        code, out = propose_act(
            user_id="u-np",
            message="Tạo phong bì học phí",
            gate_status="not_passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertTrue(out.get("gate_blocked"))
        self.assertIsNone(out.get("act_proposal"))
        self.assertIn("Cổng An Toàn", out.get("reply") or "")

    def test_low_confidence_blocks_mode_c(self):
        code, out = propose_act(
            user_id="u-lc",
            message="Tạo phong bì quỹ cưới",
            gate_status="passed",
            answer_confidence=0.40,
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertIn("80%", out.get("reply") or "")

    # --- Happy path: propose → confirm → OS change → undo ---
    def test_create_envelope_propose_confirm_undo(self):
        seed = dict(self.passed)
        seed["answer_confidence"] = 0.90
        code, prop = propose_act(
            user_id=seed["user_id"],
            message="Tạo phong bì học phí con",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertTrue(prop["ok"])
        self.assertEqual(prop["mode"], "C")
        self.assertEqual(prop["mode_chip"], MODE_C_CHIP)
        self.assertEqual(prop["disclaimer"], MODE_C_DISCLAIMER)
        self.assertEqual(prop["policy_version"], POLICY_VERSION)
        self.assertTrue(prop["needs_confirm"])
        proposal = prop["act_proposal"]
        self.assertEqual(proposal["act_kind"], ACT_CREATE_ENVELOPE)
        self.assertTrue(proposal["needs_confirm"])

        # no write yet
        _, listed = list_envelopes(seed["user_id"])
        self.assertEqual(listed["items"], [])

        # confirm required
        bad = confirm_act(
            user_id=seed["user_id"],
            proposal_id=proposal["proposal_id"],
            confirm=False,
        )
        self.assertEqual(bad[0], 400)

        code2, done = confirm_act(
            user_id=seed["user_id"],
            proposal_id=proposal["proposal_id"],
            confirm=True,
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code2, 200)
        self.assertTrue(done["ok"])
        self.assertEqual(done["mode"], "C")
        self.assertEqual(done["policy_version"], POLICY_VERSION)
        self.assertIn("undo", done)
        self.assertEqual(done["undo"]["hours"], UNDO_HOURS)
        env = done["result"]
        self.assertEqual(env["kind"], "envelope")
        self.assertIn("học phí", env["title"].lower())

        _, listed2 = list_envelopes(seed["user_id"])
        self.assertEqual(len(listed2["items"]), 1)

        code3, undone = undo_act(
            user_id=seed["user_id"],
            act_id=done["act_id"],
            undo_token=done["undo"]["token"],
        )
        self.assertEqual(code3, 200)
        self.assertTrue(undone["undone"])
        _, listed3 = list_envelopes(seed["user_id"])
        self.assertEqual(listed3["items"], [])

    def test_chat_path_gate_passed_proposes_envelope(self):
        seed = dict(self.passed)
        seed["data_confidence"] = "full"
        seed["answer_confidence"] = 0.90

        def llm(_s: str, _m: str) -> str:
            return "should not run for Mode C propose"

        code, out = service_chat(
            user_id=seed["user_id"],
            message="Tạo phong bì quỹ du lịch",
            context_seed=seed,
            call_llm=llm,
        )
        self.assertEqual(code, 200)
        self.assertEqual(out.get("mode"), "C")
        self.assertTrue(out.get("needs_confirm"))
        self.assertIsNotNone(out.get("act_proposal"))
        self.assertIn("Mode C", out.get("mode_chip") or "")
        self.assertIn("24 giờ", out.get("disclaimer") or "")
        self.assertFalse(out.get("llm_called"))
        self.assertEqual(out.get("policy_version"), POLICY_VERSION)

    def test_http_staging_path_propose_confirm(self):
        seed = dict(self.passed)
        uid = seed["user_id"]
        # propose via API with explicit gate+confidence (fixture seed user may lack live gate)
        r = self.client.post(
            "/agent/mode-c/propose",
            json={
                "user_id": uid,
                "message": "Tạo phong bì quỹ mưa",
                "gate_status": "passed",
                "answer_confidence": 0.90,
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        pid = body["act_proposal"]["proposal_id"]

        denied = self.client.post(
            "/agent/mode-c/confirm",
            json={"user_id": uid, "proposal_id": pid, "confirm": False},
        )
        self.assertEqual(denied.status_code, 400)

        conf = self.client.post(
            "/agent/mode-c/confirm",
            json={
                "user_id": uid,
                "proposal_id": pid,
                "confirm": True,
                "gate_status": "passed",
                "answer_confidence": 0.90,
            },
        )
        self.assertEqual(conf.status_code, 200)
        done = conf.json()
        self.assertTrue(done["ok"])
        self.assertEqual(done["result"]["kind"], "envelope")

        listed = self.client.get("/os/envelopes", params={"user_id": uid})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["items"]), 1)

    # --- Other Mode C acts ---
    def test_bh_reminder_schedule_only(self):
        code, prop = propose_act(
            user_id="u-bh",
            message="Nhắc BHYT tháng sau",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertTrue(prop["ok"])
        self.assertEqual(prop["act_proposal"]["act_kind"], "schedule_bh_reminder")
        params = prop["act_proposal"]["params"]
        self.assertTrue(params["schedule_only"])
        self.assertTrue(params["no_submit_forms"])
        self.assertTrue(params["no_forge_signature"])
        _, done = confirm_act(
            user_id="u-bh",
            proposal_id=prop["act_proposal"]["proposal_id"],
            confirm=True,
        )
        self.assertTrue(done["ok"])
        rem = done["result"]
        self.assertTrue(rem["schedule_only"])
        self.assertEqual(rem["reminder_kind"], "BHYT")
        got = self.client.get("/os/reminders", params={"user_id": "u-bh"})
        self.assertEqual(len(got.json()["items"]), 1)

    def test_estate_checklist_no_legal_will(self):
        # L-DUAL-CONTROL: estate requires companion + companion confirm.
        uid = self.passed["user_id"]
        set_companion(user_id=uid, companion_user_id="u-est-companion")
        code, prop = propose_act(
            user_id=uid,
            message="Mở checklist di sản",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertTrue(prop["ok"])
        self.assertEqual(prop["act_proposal"]["status"], "pending_dual")
        _, done = companion_confirm_act(
            companion_user_id="u-est-companion",
            proposal_id=prop["act_proposal"]["proposal_id"],
            confirm=True,
        )
        self.assertTrue(done["result"]["checklist_only"])
        self.assertTrue(done["result"]["no_legal_will"])
        got = self.client.get("/os/estate-checklist", params={"user_id": uid})
        self.assertTrue(got.json()["no_legal_will"])
        self.assertIsNotNone(got.json()["checklist"])

    def test_lock_envelope_cross_take(self):
        # create then lock (lock is dual-control — companion confirm)
        uid = self.passed["user_id"]
        set_companion(user_id=uid, companion_user_id="u-lock-companion")
        _, p1 = propose_act(
            user_id=uid,
            message="Tạo phong bì sống",
            gate_status="passed",
            answer_confidence=0.95,
        )
        _, c1 = confirm_act(
            user_id=uid,
            proposal_id=p1["act_proposal"]["proposal_id"],
            confirm=True,
            gate_status="passed",
            answer_confidence=0.95,
        )
        eid = c1["result"]["envelope_id"]
        _, p2 = propose_act(
            user_id=uid,
            message="Khóa phong bì cấm lấy chéo",
            gate_status="passed",
            answer_confidence=0.95,
            params={"envelope_id": eid},
        )
        self.assertEqual(p2["act_proposal"]["act_kind"], "lock_envelope")
        self.assertEqual(p2["act_proposal"]["status"], "pending_dual")
        _, c2 = companion_confirm_act(
            companion_user_id="u-lock-companion",
            proposal_id=p2["act_proposal"]["proposal_id"],
            confirm=True,
        )
        self.assertTrue(c2["result"]["locked"])
        self.assertTrue(c2["result"]["cross_take_forbidden"])
        self.assertTrue(CROSS_TAKE_SUPPORTED)

        # second envelope + cross-take deny
        _, p3 = propose_act(
            user_id=uid,
            message="Tạo phong bì con",
            gate_status="passed",
            answer_confidence=0.95,
        )
        _, c3 = confirm_act(
            user_id=uid,
            proposal_id=p3["act_proposal"]["proposal_id"],
            confirm=True,
            gate_status="passed",
            answer_confidence=0.95,
        )
        ct = self.client.post(
            "/os/envelopes/cross-take",
            json={
                "user_id": uid,
                "from_envelope_id": eid,
                "to_envelope_id": c3["result"]["envelope_id"],
                "amount": 1000,
            },
        )
        self.assertEqual(ct.status_code, 200)
        self.assertEqual(ct.json()["guardrail_result"], "deny")

    # --- DENY external / L2 ---
    def test_deny_buy_ticker_ilp_bank_transfer(self):
        cases = [
            ("Mua mã VNM giúp tôi", "L-NO-TICKER"),
            ("Đặt lệnh mua cổ VIC", "L-NO-TICKER"),
            ("Tôi muốn mua ILP mới", "L-NO-ILP-NEW"),
            ("Ký ILP mới giúp", "L-NO-ILP-NEW"),
            ("Chuyển tiền ngân hàng 10 triệu", "L-FIDUCIARY"),
            ("Bank transfer ra ngoài", "L-FIDUCIARY"),
        ]
        for msg, rule in cases:
            ext = detect_external_deny(msg)
            self.assertIsNotNone(ext, msg)
            self.assertEqual(ext["rule"], rule, msg)
            code, out = propose_act(
                user_id="u-ext",
                message=msg,
                gate_status="passed",
                answer_confidence=0.95,
            )
            self.assertEqual(code, 200, msg)
            self.assertEqual(out["guardrail_result"], "deny", msg)
            self.assertEqual(out["rule"], rule, msg)
            self.assertFalse(out.get("needs_confirm"), msg)
            self.assertIsNone(out.get("act_proposal"), msg)

        seed = dict(self.passed)
        seed["answer_confidence"] = 0.95
        for msg, rule in cases:
            code, out = service_chat(
                user_id=seed["user_id"],
                message=msg,
                context_seed=seed,
                call_llm=lambda s, m: "no",
            )
            self.assertEqual(code, 200, msg)
            # Hard Deny may fire first for some ticker phrases when gate context differs;
            # Mode C or Hard Deny must DENY — never ALLOW write.
            self.assertEqual(out["guardrail_result"], "deny", msg)
            self.assertFalse(out.get("needs_confirm"), msg)

    def test_hard_deny_still_wins_before_mode_c(self):
        seed = dict(self.not_passed)
        seed["answer_confidence"] = 0.95
        ctx = context_from_seed(seed)
        pre = evaluate_pre_rules(
            "Tôi muốn rút quỹ khẩn cấp để all-in một mã cổ phiếu đang nóng.",
            ctx,
        )
        self.assertEqual(pre.result, "deny")
        self.assertIn(pre.primary_hit.rule_id, HARD)

        code, out = service_chat(
            user_id=seed["user_id"],
            message="Tôi muốn rút quỹ khẩn cấp để all-in một mã cổ phiếu đang nóng.",
            context_seed=seed,
            call_llm=lambda s, m: "no",
        )
        self.assertEqual(code, 200)
        self.assertEqual(out["guardrail_result"], "deny")
        # Hard Deny path — no Mode C propose
        self.assertNotEqual(out.get("mode"), "C")

    # --- UI ---
    def test_chat_html_mode_c_chip_confirm_undo(self):
        html = self.html
        self.assertIn("Mode C · Hành động", html)
        self.assertIn("Hành động trên OS — có thể hoàn tác trong 24 giờ", html)
        self.assertIn("modeCConfirm", html)
        self.assertIn("/agent/mode-c/confirm", html)
        self.assertIn("/agent/mode-c/undo", html)
        self.assertIn("mcConfirmBtn", html)
        self.assertIn("modeChip", html)
        self.assertIn("needs_confirm", html)


if __name__ == "__main__":
    unittest.main()
