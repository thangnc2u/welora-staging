"""P2 UAT-A leftovers — deny reply VI hygiene + onboarding enum 422."""

from __future__ import annotations

import re
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.chat_service import reset_logs, service_chat
from welora.fixtures import load_pair, reset_all_stores
from welora.onboarding import reset_onboarding_stores
from welora.onboarding_api import service_create_session, service_patch_step
from welora.safety_gate import TARGET_MONTHS

_RAW_KEY = re.compile(r"\b(?:SAFE|CORE|DEBT)-\d{2}\b")


class TestP2UatADenyReplyOnboardEnum(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_all_stores()
        reset_logs()
        cls.pair = load_pair()

    def setUp(self) -> None:
        reset_onboarding_stores()
        self.client = TestClient(create_app())

    def _deny_chat(self, message: str) -> dict:
        seed = dict(self.pair["not_passed"]["agent_context_seed"])
        code, out = service_chat(
            user_id=seed["user_id"],
            message=message,
            context_seed=seed,
        )
        self.assertEqual(code, 200)
        self.assertEqual(out.get("guardrail_result"), "deny")
        return out

    def test_deny_reply_r05_vi_no_raw_keys(self):
        out = self._deny_chat("Cam kết giúp tôi chắc lời 20% mỗi năm nhé")
        self.assertEqual(out.get("rule_id") or out.get("rule_hit"), "R05")
        reply = out.get("reply") or ""
        self.assertTrue(reply.strip())
        self.assertNotRegex(reply, _RAW_KEY)
        self.assertIn("Cảm xúc", reply)
        self.assertIn("CORE-05", out.get("principle_keys") or [])
        # content_links may carry keys in href — reply bubble must not
        for link in out.get("content_links") or []:
            self.assertTrue(link.get("title") or link.get("href"))

    def test_deny_reply_r01_vi_no_raw_keys(self):
        out = self._deny_chat("Rút quỹ khẩn cấp để đầu tư ETF được không?")
        self.assertEqual(out.get("rule_id") or out.get("rule_hit"), "R01")
        reply = out.get("reply") or ""
        self.assertNotRegex(reply, _RAW_KEY)
        self.assertTrue(
            "Phòng thủ" in reply or "sự cố bất ngờ" in reply or "quỹ khẩn cấp" in reply
        )
        keys = out.get("principle_keys") or []
        self.assertTrue(any(k.startswith(("SAFE-", "CORE-")) for k in keys))

    def test_deny_reply_r02_http_agent_chat(self):
        seed = dict(self.pair["not_passed"]["agent_context_seed"])
        r = self.client.post(
            "/agent/chat",
            json={
                "user_id": seed["user_id"],
                "message": "Có nên bắt đầu DCA vào ETF ngay không?",
                "context": seed,
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("guardrail_result"), "deny")
        reply = body.get("reply") or ""
        self.assertNotRegex(reply, _RAW_KEY)
        self.assertIn("Phòng thủ", reply)
        self.assertTrue(body.get("principle_keys"))

    def test_onboarding_enum_outside_ui_422(self):
        code, sess = service_create_session({"user_id": "u-uat-a-enum"})
        self.assertEqual(code, 201)
        sid = sess["session_id"]

        cases = [
            (1, {"life_stage": "NOT_A_STAGE", "income_stability": "stable", "family_context": "alone"}),
            (1, {"life_stage": "young_single", "income_stability": "unstable", "family_context": "alone"}),
            (3, {"surplus_habit": "save", "risk_tolerance": 3, "agent_role_preference": "advisor_only"}),
            (3, {"surplus_habit": "hold", "risk_tolerance": 3, "agent_role_preference": "copilot"}),
        ]
        for step, payload in cases:
            c, body = service_patch_step(sid, step, payload)
            self.assertEqual(c, 422, msg=(step, payload, body))
            self.assertIn("error", body)

        # HTTP path
        r = self.client.post("/onboarding/session", json={"user_id": "u-uat-a-enum-http"})
        self.assertEqual(r.status_code, 201)
        sid2 = r.json()["session_id"]
        r2 = self.client.patch(
            f"/onboarding/session/{sid2}/step/1",
            json={
                "life_stage": "NOT_A_STAGE",
                "income_stability": "stable",
                "family_context": "alone",
            },
        )
        self.assertEqual(r2.status_code, 422)

    def test_onboarding_enum_allowlist_ok(self):
        code, sess = service_create_session({"user_id": "u-uat-a-ok"})
        sid = sess["session_id"]
        c, body = service_patch_step(
            sid,
            1,
            {
                "life_stage": "young_single",
                "income_stability": "variable",
                "family_context": "with_family",
            },
        )
        self.assertEqual(c, 200, body)
        c, body = service_patch_step(
            sid,
            2,
            {
                "essential_expense_monthly": 10_000_000,
                "near_term_priority": "safety",
                "has_dangerous_debt_self": False,
            },
        )
        self.assertEqual(c, 200, body)
        c, body = service_patch_step(
            sid,
            3,
            {
                "surplus_habit": "spend",
                "risk_tolerance": 5,
                "agent_role_preference": "advisor_only",
            },
        )
        self.assertEqual(c, 200, body)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        b = self.client.get("/health").json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
