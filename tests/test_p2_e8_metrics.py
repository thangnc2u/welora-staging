"""P2-E8 — metrics + decision log no PII. Hard Deny never increments deny_with_llm_calls."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.chat_service import reset_logs, sanitize_query
from welora.fixtures import load_pair, reset_all_stores
from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.goals_api import use_store
from welora.metrics import reset_metrics, snapshot
from welora.safety_gate import TARGET_MONTHS


class TestP2E8Metrics(unittest.TestCase):
    def setUp(self) -> None:
        use_store(InMemoryEmergencyFundStore())
        reset_all_stores()
        reset_logs()
        reset_metrics()
        self.pair = load_pair()
        self.client = TestClient(create_app())

    def test_health_untouched(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["gate_months"], 3)
        self.assertTrue(body["hard_deny"])
        self.assertIn("dialect", body)
        self.assertEqual(TARGET_MONTHS, 3)

    def test_hard_deny_chat_metrics_zero_llm(self):
        seed = self.pair["not_passed"]["agent_context_seed"]
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
        self.assertEqual(body["guardrail_result"], "deny")
        self.assertEqual(body["model_used"], "rule_only")
        self.assertFalse(body.get("llm_called"))
        m = self.client.get("/metrics").json()
        self.assertEqual(m["deny_with_llm_calls"], 0)
        self.assertGreaterEqual(m["deny_total"], 1)
        self.assertEqual(snapshot()["deny_with_llm_calls"], 0)

    def test_sanitize_strips_secrets_and_phone(self):
        raw = "Gọi 0912345678 token=sk-SUPERSECRETKEY99 api_key=xai-ABCDEFG123"
        clean = sanitize_query(raw)
        self.assertNotIn("0912345678", clean)
        self.assertNotIn("sk-SUPERSECRETKEY99", clean)
        self.assertNotIn("xai-ABCDEFG123", clean)
        self.assertIn("[REDACTED]", clean)
        self.assertLessEqual(len(clean), 121)

    def test_decision_log_has_no_pii(self):
        seed = self.pair["not_passed"]["agent_context_seed"]
        uid = seed["user_id"]
        self.client.post(
            "/agent/chat",
            json={
                "user_id": uid,
                "message": "Rút quỹ all-in, phone 0987654321 token=ghp_abcDEF123456",
                "context": seed,
            },
        )
        logs = self.client.get("/agent/decision-logs", params={"user_id": uid}).json()
        blob = str(logs)
        self.assertNotIn("0987654321", blob)
        self.assertNotIn("ghp_abcDEF123456", blob)
        item = logs["items"][0]
        self.assertNotIn("token", item)
        self.assertNotIn("api_key", item)
        self.assertNotIn("phone", item)
        self.assertLessEqual(len(item.get("user_query_summary") or ""), 121)


if __name__ == "__main__":
    unittest.main()
