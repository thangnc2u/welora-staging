"""P0 follow-up 2 — item 6 (/os/companion consent: pending invite → companion accepts as
themselves; decline / revoke; dual-control only with an ACTIVE link; seeds pre-accepted) and
item 7 (/api/core/v1/entitlements/events requires a user session).

Auth tokens live in the DB (SQLite, or PG via WELORA_TEST_POSTGRES_URL); the Mode C store is the
in-process store (+ its own SQLite write-through when enabled), exercised here in-process.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests._authz import token_for
from tests._db_target import db_env
from welora import entitlements as ent
from welora import mode_c_act as mc
from welora.api.app import create_app
from welora.fixtures import load_pair, reset_all_stores
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
ENV_KEYS = ("WELORA_STORE", "WELORA_DB_URL", "WELORA_ENV")


class _DbBase(unittest.TestCase):
    def setUp(self):
        self.prev = {k: os.environ.get(k) for k in ENV_KEYS}
        self.tmp = tempfile.mkdtemp(prefix="welora-fu2c-")
        env = db_env(self.tmp)
        os.environ["WELORA_DB_URL"] = env["WELORA_DB_URL"]  # auth tokens only; goals stay in memory
        os.environ.pop("WELORA_STORE", None)
        os.environ["WELORA_ENV"] = "staging"
        self.client = TestClient(create_app())

    def tearDown(self):
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def h(self, uid):
        return {"Authorization": "Bearer " + token_for(uid)}


class TestCompanionConsent(_DbBase):
    def setUp(self):
        super().setUp()
        reset_all_stores()
        mc.reset_mode_c_store()
        self.primary = load_pair()["passed"]["user_id"]  # gate passed → dual-control acts reachable
        self.comp = "companion-fu2"
        self.other = "intruder-fu2"

    def invite(self):
        r = self.client.post("/os/companion", json={"user_id": self.primary, "companion_user_id": self.comp},
                             headers=self.h(self.primary))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def propose_estate(self):
        return self.client.post("/agent/mode-c/propose", json={
            "user_id": self.primary, "message": "Mở checklist di sản", "gate_status": "passed",
            "answer_confidence": 0.99}, headers=self.h(self.primary)).json()

    def accept(self, who, primary=None):
        return self.client.post("/os/companion/accept", json={"primary_user_id": primary or self.primary},
                                headers=self.h(who))

    def test_invite_is_pending_and_dual_control_stays_off(self):
        out = self.invite()
        self.assertEqual(out["status"], "pending")
        self.assertIsNone(mc.get_companion(self.primary))
        listed = self.client.get("/os/companion", params={"user_id": self.primary}, headers=self.h(self.primary)).json()
        self.assertEqual((listed["companion_user_id"], listed["pending_companion_user_id"], listed["status"]),
                         (None, self.comp, "pending"))
        prop = self.propose_estate()
        self.assertNotEqual(prop.get("status"), "pending_dual")  # denied: no ACTIVE companion
        self.assertEqual(prop.get("guardrail_result"), "deny")

    def test_only_the_invited_companion_can_accept(self):
        self.invite()
        self.assertEqual(self.accept(self.other).status_code, 404)
        self.assertEqual(self.accept(self.primary).status_code, 404)  # primary cannot self-accept
        spoof = self.client.post("/os/companion/accept",
                                 json={"primary_user_id": self.primary, "companion_user_id": self.comp},
                                 headers=self.h(self.other))
        self.assertEqual(spoof.status_code, 403)
        self.assertEqual(self.client.post("/os/companion/accept", json={"primary_user_id": self.primary}).status_code, 401)
        self.assertIsNone(mc.get_companion(self.primary))

    def test_accept_then_dual_control_works(self):
        self.invite()
        inv = self.client.get("/os/companion/invites", headers=self.h(self.comp)).json()["items"]
        self.assertEqual([(i["primary_user_id"], i["status"]) for i in inv], [(self.primary, "pending")])
        r = self.accept(self.comp)
        self.assertEqual((r.status_code, r.json()["status"]), (200, "active"))
        self.assertEqual(self.accept(self.comp).json().get("already"), True)  # idempotent
        self.assertEqual(mc.get_companion(self.primary)["companion_user_id"], self.comp)
        prop = self.propose_estate()
        self.assertEqual(prop.get("status"), "pending_dual")
        conf = self.client.post("/agent/mode-c/companion-confirm", json={
            "companion_user_id": self.comp, "proposal_id": prop["act_proposal"]["proposal_id"], "confirm": True},
            headers=self.h(self.comp))
        self.assertEqual(conf.status_code, 200)
        self.assertTrue(conf.json().get("ok"))

    def test_decline_and_leave(self):
        self.invite()
        d = self.client.post("/os/companion/decline", json={"primary_user_id": self.primary}, headers=self.h(self.comp))
        self.assertEqual(d.json()["status"], "declined")
        self.assertEqual(self.accept(self.comp).status_code, 409)  # a declined invite cannot be revived
        self.assertIsNone(mc.get_companion(self.primary))
        # re-invite → accept → companion leaves an active link
        self.invite()
        self.accept(self.comp)
        self.client.post("/os/companion/decline", json={"primary_user_id": self.primary}, headers=self.h(self.comp))
        self.assertIsNone(mc.get_companion(self.primary))

    def test_revoke_blocks_pending_confirmation(self):
        self.invite()
        self.accept(self.comp)
        prop = self.propose_estate()
        pid = prop["act_proposal"]["proposal_id"]
        rv = self.client.post("/os/companion/revoke", json={"user_id": self.primary}, headers=self.h(self.primary))
        self.assertEqual(rv.json()["status"], "revoked")
        conf = self.client.post("/agent/mode-c/companion-confirm",
                                json={"companion_user_id": self.comp, "proposal_id": pid, "confirm": True},
                                headers=self.h(self.comp))
        self.assertEqual(conf.status_code, 403)
        self.assertEqual(self.client.get("/os/companion", params={"user_id": self.primary},
                                         headers=self.h(self.primary)).json()["items"], [])
        other = self.client.post("/os/companion/revoke", json={"user_id": self.primary}, headers=self.h(self.other))
        self.assertEqual(other.status_code, 403)

    def test_reinvite_same_companion_does_not_downgrade_active(self):
        self.invite()
        self.accept(self.comp)
        again = self.invite()
        self.assertEqual(again["status"], "active")
        self.assertIsNotNone(mc.get_companion(self.primary))

    def test_legacy_link_without_status_is_pending(self):
        mc._COMPANIONS[self.primary] = {"user_id": self.primary, "companion_user_id": self.comp, "linked_at": "x"}
        self.assertIsNone(mc.get_companion(self.primary))
        self.assertEqual(self.accept(self.comp).json()["status"], "active")
        self.assertIsNotNone(mc.get_companion(self.primary))

    def test_internal_seed_path_is_pre_accepted(self):
        code, out = mc.set_companion(user_id="p6-primary", companion_user_id="p6-child", role="child")
        self.assertEqual((code, out["link"]["status"]), (200, "active"))
        self.assertEqual(mc.get_companion("p6-primary")["companion_user_id"], "p6-child")
        from welora.fixtures import build_p6_fixture

        fx = build_p6_fixture()
        self.assertEqual(mc.get_companion(fx["user_id"])["companion_user_id"], fx["companion_user_id"])

    def test_dual_control_page_has_consent_ui(self):
        html = (STATIC / "dual-control.html").read_text(encoding="utf-8")
        for s in ("/os/companion/invites", "/os/companion/accept", "/os/companion/decline", "/os/companion/revoke",
                  "Chấp nhận", "Từ chối", "pending_companion_user_id"):
            self.assertIn(s, html)


class TestEntitlementEvents(_DbBase):
    def setUp(self):
        super().setUp()
        ent.reset_state_for_tests()

    def post(self, event="pricing.view", payload=None, headers=None):
        return self.client.post("/api/core/v1/entitlements/events",
                                json={"event": event, "payload": payload or {"path": "/pricing"}}, headers=headers or {})

    def test_anonymous_refused(self):
        r = self.post()
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"]["error_code"], "AUTH_REQUIRED")
        self.assertEqual(self.post(headers={"Authorization": "Bearer nope"}).status_code, 401)

    def test_user_event_stamped_with_token_user(self):
        r = self.post(payload={"path": "/pricing", "user_id": "someone-else"}, headers=self.h("ev-user"))
        self.assertEqual(r.status_code, 200)
        p = r.json()["event"]["payload"]
        self.assertEqual((p["user_id"], p["source"]), ("ev-user", "client"))
        mine = [e for e in ent.list_events(50) if e["payload"].get("user_id") == "ev-user"]
        self.assertEqual(len(mine), 1)

    def test_server_event_names_cannot_be_forged(self):
        for name in ("subscription_granted", "refund_completed", "PRICING.VIEW", "pricing", "a." + "x" * 70):
            self.assertEqual(self.post(event=name, headers=self.h("ev-user")).status_code, 422, name)

    def test_pricing_page_sends_token_or_skips(self):
        html = (STATIC / "pricing.html").read_text(encoding="utf-8")
        i = html.index("function emitView()")
        body = html[i:html.index("}\n", html.index("catch (_e)", i)) + 2]
        self.assertIn('if (!tk) return;', body)
        self.assertIn('Authorization: "Bearer " + tk', body)

    def test_constraints(self):
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
