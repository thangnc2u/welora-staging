"""P2 OS Dual-control MVP (L-DUAL-CONTROL) — Founder 15/09 B.

DENY when missing companion + in-app dual confirm for two users.
Acts: envelope ceiling change / lock + estate checklist.
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
from welora.mode_c_act import (
    ACT_CHANGE_CEILING,
    ACT_CREATE_ENVELOPE,
    ACT_ESTATE_CHECKLIST,
    ACT_LOCK_ENVELOPE,
    DUAL_CONTROL_ACTS,
    MODE_C,
    POLICY_DUAL_CONTROL,
    POLICY_VERSION,
    cancel_pending_dual,
    companion_confirm_act,
    confirm_act,
    get_estate_checklist,
    list_envelopes,
    propose_act,
    reset_mode_c_store,
    set_companion,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
DUAL_HTML = ROOT / "welora" / "api" / "static" / "dual-control.html"
CHAT = ROOT / "welora" / "api" / "static" / "chat.html"


class TestP2OsDualControlMvp(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_all_stores()
        reset_mode_c_store()
        cls.pair = load_pair()

    def setUp(self) -> None:
        reset_mode_c_store()
        self.client = TestClient(create_app())
        self.primary = self.pair["passed"]["user_id"]
        self.companion = "user_companion_dual_01"
        # Ensure companion also exists as a distinct id (no fixture required).
        self.assertNotEqual(self.primary, self.companion)

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
        self.assertEqual(POLICY_DUAL_CONTROL, "L-DUAL-CONTROL")
        self.assertEqual(MODE_C, "C")
        self.assertIn(ACT_LOCK_ENVELOPE, DUAL_CONTROL_ACTS)
        self.assertIn(ACT_CHANGE_CEILING, DUAL_CONTROL_ACTS)
        self.assertIn(ACT_ESTATE_CHECKLIST, DUAL_CONTROL_ACTS)
        self.assertNotIn(ACT_CREATE_ENVELOPE, DUAL_CONTROL_ACTS)

    def test_ui_vi_dual_control_page(self):
        html = DUAL_HTML.read_text(encoding="utf-8")
        self.assertIn("Đồng kiểm", html)
        self.assertIn("/os/companion", html)
        self.assertIn("companion-confirm", html)
        self.assertIn("Người đồng hành", html)
        chat = CHAT.read_text(encoding="utf-8")
        self.assertIn("dual-control", chat)

    def test_companion_create_list_api(self):
        r = self.client.post(
            "/os/companion",
            json={"user_id": self.primary, "companion_user_id": self.companion},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json().get("ok"))
        self.assertEqual(r.json()["link"]["companion_user_id"], self.companion)

        listed = self.client.get("/os/companion", params={"user_id": self.primary})
        self.assertEqual(listed.status_code, 200)
        body = listed.json()
        self.assertEqual(body["companion_user_id"], self.companion)
        self.assertEqual(len(body["items"]), 1)

        bad = self.client.post(
            "/os/companion",
            json={"user_id": self.primary, "companion_user_id": self.primary},
        )
        self.assertEqual(bad.status_code, 400)

    def test_missing_companion_lock_deny_no_os_write(self):
        code, out = propose_act(
            user_id=self.primary,
            message="Khóa phong bì lấy chéo",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("guardrail_result"), "deny")
        self.assertEqual(out.get("rule"), POLICY_DUAL_CONTROL)
        self.assertEqual(out.get("policy_version"), POLICY_DUAL_CONTROL)
        self.assertIsNone(out.get("act_proposal"))
        self.assertTrue(out.get("companion_missing"))
        reply = out.get("reply") or ""
        self.assertIn("đồng hành", reply.lower())
        self.assertIn("L-DUAL-CONTROL", reply)
        _, listed = list_envelopes(self.primary)
        self.assertEqual(listed["items"], [])

    def test_missing_companion_estate_deny(self):
        code, out = propose_act(
            user_id=self.primary,
            message="Mở checklist di sản",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("rule"), POLICY_DUAL_CONTROL)
        self.assertIsNone(out.get("act_proposal"))
        _, est = get_estate_checklist(self.primary)
        self.assertIsNone(est.get("checklist"))

    def test_missing_companion_ceiling_deny(self):
        code, out = propose_act(
            user_id=self.primary,
            message="Đổi trần phong bì 20000000",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("rule"), POLICY_DUAL_CONTROL)
        self.assertEqual(out.get("act_kind"), ACT_CHANGE_CEILING)

    def test_create_envelope_still_single_confirm(self):
        """Create envelope is NOT dual-control in MVP — existing Mode C path."""
        code, prop = propose_act(
            user_id=self.primary,
            message="Tạo phong bì học phí",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertTrue(prop["ok"])
        self.assertTrue(prop["needs_confirm"])
        self.assertEqual(prop["act_proposal"]["status"], "proposed")
        self.assertEqual(prop["policy_version"], POLICY_VERSION)

        code2, done = confirm_act(
            user_id=self.primary,
            proposal_id=prop["act_proposal"]["proposal_id"],
            confirm=True,
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code2, 200)
        self.assertTrue(done["ok"])
        _, listed = list_envelopes(self.primary)
        self.assertEqual(len(listed["items"]), 1)

    def test_has_companion_pending_then_companion_confirm_pass(self):
        set_companion(user_id=self.primary, companion_user_id=self.companion)

        code, prop = propose_act(
            user_id=self.primary,
            message="Khóa phong bì — cấm lấy chéo",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertTrue(prop["ok"])
        self.assertEqual(prop["status"], "pending_dual")
        self.assertTrue(prop["needs_companion_confirm"])
        self.assertFalse(prop["needs_confirm"])
        self.assertEqual(prop["policy_version"], POLICY_DUAL_CONTROL)
        self.assertEqual(prop["companion_user_id"], self.companion)
        proposal = prop["act_proposal"]
        self.assertEqual(proposal["status"], "pending_dual")
        self.assertEqual(proposal["act_kind"], ACT_LOCK_ENVELOPE)

        # No OS write yet
        _, listed = list_envelopes(self.primary)
        self.assertEqual(listed["items"], [])

        # Primary alone cannot write via confirm
        blocked = confirm_act(
            user_id=self.primary,
            proposal_id=proposal["proposal_id"],
            confirm=True,
            gate_status="passed",
            answer_confidence=0.99,
        )
        self.assertEqual(blocked[0], 403)
        self.assertEqual(blocked[1].get("rule"), POLICY_DUAL_CONTROL)
        _, listed = list_envelopes(self.primary)
        self.assertEqual(listed["items"], [])

        # Companion confirm → write
        code2, done = companion_confirm_act(
            companion_user_id=self.companion,
            proposal_id=proposal["proposal_id"],
            confirm=True,
        )
        self.assertEqual(code2, 200)
        self.assertTrue(done["ok"])
        self.assertEqual(done["policy_version"], POLICY_DUAL_CONTROL)
        self.assertEqual(done["user_id"], self.primary)
        self.assertEqual(done["companion_user_id"], self.companion)
        self.assertEqual(done["log"]["user_id"], self.primary)
        self.assertEqual(done["log"]["companion_user_id"], self.companion)
        self.assertEqual(done["log"]["policy_version"], POLICY_DUAL_CONTROL)
        self.assertEqual(done["log"]["mode"], MODE_C)
        _, listed = list_envelopes(self.primary)
        self.assertEqual(len(listed["items"]), 1)
        self.assertTrue(listed["items"][0].get("locked"))

    def test_estate_pending_companion_confirm(self):
        set_companion(user_id=self.primary, companion_user_id=self.companion)
        code, prop = propose_act(
            user_id=self.primary,
            message="Mở checklist di sản",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code, 200)
        self.assertEqual(prop["status"], "pending_dual")
        pid = prop["act_proposal"]["proposal_id"]
        _, est0 = get_estate_checklist(self.primary)
        self.assertIsNone(est0.get("checklist"))

        code2, done = companion_confirm_act(
            companion_user_id=self.companion,
            proposal_id=pid,
            confirm=True,
        )
        self.assertEqual(code2, 200)
        self.assertTrue(done["ok"])
        _, est = get_estate_checklist(self.primary)
        self.assertIsNotNone(est.get("checklist"))
        self.assertEqual(est["checklist"]["kind"], "estate_checklist")

    def test_ceiling_pending_companion_confirm(self):
        set_companion(user_id=self.primary, companion_user_id=self.companion)
        # Seed an envelope via non-dual create
        code, prop = propose_act(
            user_id=self.primary,
            message="Tạo phong bì quỹ cưới",
            gate_status="passed",
            answer_confidence=0.90,
        )
        confirm_act(
            user_id=self.primary,
            proposal_id=prop["act_proposal"]["proposal_id"],
            confirm=True,
            gate_status="passed",
            answer_confidence=0.90,
        )

        code2, dual = propose_act(
            user_id=self.primary,
            message="Đổi trần phong bì 25000000",
            gate_status="passed",
            answer_confidence=0.90,
        )
        self.assertEqual(code2, 200)
        self.assertEqual(dual["status"], "pending_dual")
        self.assertEqual(dual["act_proposal"]["act_kind"], ACT_CHANGE_CEILING)

        code3, done = companion_confirm_act(
            companion_user_id=self.companion,
            proposal_id=dual["act_proposal"]["proposal_id"],
            confirm=True,
        )
        self.assertEqual(code3, 200)
        self.assertTrue(done["ok"])
        _, listed = list_envelopes(self.primary)
        self.assertEqual(float(listed["items"][0]["target_amount"]), 25000000.0)

    def test_primary_can_cancel_pending(self):
        set_companion(user_id=self.primary, companion_user_id=self.companion)
        _, prop = propose_act(
            user_id=self.primary,
            message="Khóa phong bì",
            gate_status="passed",
            answer_confidence=0.90,
        )
        pid = prop["act_proposal"]["proposal_id"]
        code, out = cancel_pending_dual(user_id=self.primary, proposal_id=pid)
        self.assertEqual(code, 200)
        self.assertTrue(out.get("cancelled"))
        # Companion confirm after cancel fails
        code2, denied = companion_confirm_act(
            companion_user_id=self.companion,
            proposal_id=pid,
            confirm=True,
        )
        self.assertEqual(code2, 409)
        _, listed = list_envelopes(self.primary)
        self.assertEqual(listed["items"], [])

    def test_spoof_cannot_bypass_companion_confirm(self):
        """Align #184: do not trust client flags / wrong companion_user_id."""
        set_companion(user_id=self.primary, companion_user_id=self.companion)
        _, prop = propose_act(
            user_id=self.primary,
            message="Khóa phong bì",
            gate_status="passed",
            answer_confidence=0.90,
        )
        pid = prop["act_proposal"]["proposal_id"]

        # Wrong user claims to be companion
        r = self.client.post(
            "/agent/mode-c/companion-confirm",
            json={
                "companion_user_id": "attacker_spoof",
                "proposal_id": pid,
                "confirm": True,
                "dual_ok": True,
                "skip_dual": True,
                "is_companion": True,
                "gate_status": "passed",
                "answer_confidence": 0.99,
            },
        )
        self.assertEqual(r.status_code, 403)
        detail = r.json().get("detail")
        blob = detail if isinstance(detail, dict) else {"error": detail}
        self.assertIn("companion", str(blob.get("error") or blob).lower())

        # Primary tries companion-confirm endpoint as themselves
        r2 = self.client.post(
            "/agent/mode-c/companion-confirm",
            json={
                "companion_user_id": self.primary,
                "proposal_id": pid,
                "confirm": True,
                "dual_ok": True,
            },
        )
        self.assertEqual(r2.status_code, 403)

        # Primary confirm HTTP still blocked
        r3 = self.client.post(
            "/agent/mode-c/confirm",
            json={
                "user_id": self.primary,
                "proposal_id": pid,
                "confirm": True,
                "gate_status": "passed",
                "answer_confidence": 0.99,
            },
        )
        self.assertEqual(r3.status_code, 403)

        listed = self.client.get("/os/envelopes", params={"user_id": self.primary})
        self.assertEqual(listed.json()["items"], [])

    def test_http_happy_path_pending_confirm(self):
        link = self.client.post(
            "/os/companion",
            json={"user_id": self.primary, "companion_user_id": self.companion},
        )
        self.assertEqual(link.status_code, 200)

        prop = self.client.post(
            "/agent/mode-c/propose",
            json={
                "user_id": self.primary,
                "message": "Mở checklist di sản",
                "gate_status": "passed",
                "answer_confidence": 0.99,
            },
        )
        self.assertEqual(prop.status_code, 200)
        body = prop.json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("status"), "pending_dual")
        pid = body["act_proposal"]["proposal_id"]

        pending = self.client.get(
            "/os/dual-control/pending", params={"user_id": self.primary}
        )
        self.assertEqual(pending.status_code, 200)
        self.assertEqual(len(pending.json()["items"]), 1)

        conf = self.client.post(
            "/agent/mode-c/companion-confirm",
            json={
                "companion_user_id": self.companion,
                "proposal_id": pid,
                "confirm": True,
            },
        )
        self.assertEqual(conf.status_code, 200)
        done = conf.json()
        self.assertTrue(done.get("ok"))
        self.assertEqual(done.get("policy_version"), POLICY_DUAL_CONTROL)
        self.assertEqual(done["log"]["companion_user_id"], self.companion)

        est = self.client.get(
            "/os/estate-checklist", params={"user_id": self.primary}
        )
        self.assertIsNotNone(est.json().get("checklist"))

    def test_http_missing_companion_deny(self):
        r = self.client.post(
            "/agent/mode-c/propose",
            json={
                "user_id": self.primary,
                "message": "Khóa phong bì",
                "gate_status": "passed",
                "answer_confidence": 0.99,
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body.get("ok"))
        self.assertEqual(body.get("rule"), POLICY_DUAL_CONTROL)
        self.assertIsNone(body.get("act_proposal"))


if __name__ == "__main__":
    unittest.main()
