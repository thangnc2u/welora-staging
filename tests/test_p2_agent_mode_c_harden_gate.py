"""P2 Agent Mode C — server-side gate+confidence harden (anti-spoof).

Client-supplied gate_status / answer_confidence on propose/confirm MUST be
ignored; resolve from live user/session/mastery state via context_from_user.
"""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from welora.agent import CONFIDENCE_THRESHOLD
from welora.api.app import create_app
from welora.fixtures import load_pair, reset_all_stores
from welora.mode_c_act import (
    POLICY_VERSION,
    confirm_act,
    propose_act,
    reset_mode_c_store,
    resolve_server_gate_confidence,
)
from welora.safety_gate import TARGET_MONTHS


class TestP2AgentModeCHardenGate(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_all_stores()
        reset_mode_c_store()
        cls.pair = load_pair()

    def setUp(self) -> None:
        reset_mode_c_store()
        self.client = TestClient(create_app())
        self.passed = self.pair["passed"]
        self.not_passed = self.pair["not_passed"]

    def test_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(CONFIDENCE_THRESHOLD, 0.80)
        self.assertTrue(POLICY_VERSION.startswith("L-"))

    def test_resolve_server_gate_matches_fixture(self):
        g_ok, c_ok = resolve_server_gate_confidence(self.passed["user_id"])
        g_np, c_np = resolve_server_gate_confidence(self.not_passed["user_id"])
        self.assertEqual(g_ok, "passed")
        self.assertGreaterEqual(c_ok, CONFIDENCE_THRESHOLD)
        self.assertEqual(g_np, "not_passed")
        # fail-closed for unknown user
        g_u, c_u = resolve_server_gate_confidence("user_does_not_exist_xyz")
        self.assertEqual(g_u, "not_passed")
        self.assertLess(c_u, CONFIDENCE_THRESHOLD)

    def test_http_spoof_propose_denied_when_user_not_passed(self):
        """Client claims passed / high conf while user NOT Đạt cổng → DENY."""
        uid = self.not_passed["user_id"]
        r = self.client.post(
            "/agent/mode-c/propose",
            json={
                "user_id": uid,
                "message": "Tạo phong bì quỹ học phí",
                "gate_status": "passed",
                "answer_confidence": 0.99,
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body.get("ok"))
        self.assertTrue(body.get("gate_blocked"))
        self.assertIsNone(body.get("act_proposal"))
        self.assertEqual(body.get("guardrail_result"), "deny")
        reply = body.get("reply") or ""
        self.assertIn("Cổng An Toàn", reply)
        # no OS write
        listed = self.client.get("/os/envelopes", params={"user_id": uid})
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["items"], [])

    def test_http_spoof_confirm_denied_when_user_not_passed(self):
        """Proposal created offline with spoofed gate; confirm HTTP still DENY."""
        uid = self.not_passed["user_id"]
        # Bypass HTTP propose to plant a proposal (simulates prior spoof path).
        code, prop = propose_act(
            user_id=uid,
            message="Tạo phong bì quỹ cưới",
            gate_status="passed",
            answer_confidence=0.99,
        )
        self.assertEqual(code, 200)
        self.assertTrue(prop["ok"])
        pid = prop["act_proposal"]["proposal_id"]

        conf = self.client.post(
            "/agent/mode-c/confirm",
            json={
                "user_id": uid,
                "proposal_id": pid,
                "confirm": True,
                "gate_status": "passed",
                "answer_confidence": 0.99,
            },
        )
        self.assertEqual(conf.status_code, 403)
        detail = conf.json().get("detail")
        # FastAPI may wrap as detail string or dict
        err = detail if isinstance(detail, str) else (detail or {})
        if isinstance(err, dict):
            err = err.get("error") or err.get("message") or str(err)
        self.assertIn("Cổng An Toàn", str(err))
        listed = self.client.get("/os/envelopes", params={"user_id": uid})
        self.assertEqual(listed.json()["items"], [])

    def test_http_passed_user_act_ok_even_if_client_lies_low(self):
        """User Đạt cổng + conf OK → Act OK; client low-conf spoof ignored."""
        uid = self.passed["user_id"]
        r = self.client.post(
            "/agent/mode-c/propose",
            json={
                "user_id": uid,
                "message": "Tạo phong bì quỹ mưa",
                "gate_status": "not_passed",
                "answer_confidence": 0.10,
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"], msg=body)
        self.assertTrue(body["needs_confirm"])
        pid = body["act_proposal"]["proposal_id"]

        conf = self.client.post(
            "/agent/mode-c/confirm",
            json={
                "user_id": uid,
                "proposal_id": pid,
                "confirm": True,
                "gate_status": "not_passed",
                "answer_confidence": 0.10,
            },
        )
        self.assertEqual(conf.status_code, 200, msg=conf.text)
        done = conf.json()
        self.assertTrue(done["ok"])
        self.assertEqual(done["result"]["kind"], "envelope")
        self.assertIn("undo", done)

        listed = self.client.get("/os/envelopes", params={"user_id": uid})
        self.assertEqual(len(listed.json()["items"]), 1)

        # undo still works (no gate fields on undo)
        undo = self.client.post(
            "/agent/mode-c/undo",
            json={
                "user_id": uid,
                "act_id": done["act_id"],
                "undo_token": done["undo"]["token"],
            },
        )
        self.assertEqual(undo.status_code, 200)
        self.assertTrue(undo.json()["undone"])
        listed2 = self.client.get("/os/envelopes", params={"user_id": uid})
        self.assertEqual(listed2.json()["items"], [])


if __name__ == "__main__":
    unittest.main()
