"""P2 Native UI /app/chat — gateBadge + denyCta. Deny never calls LLM."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.chat_service import reset_logs
from welora.fixtures import load_pair, reset_all_stores
from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.goals_api import use_store
from welora.metrics import reset_metrics
from welora.safety_gate import TARGET_MONTHS

CHAT_HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "chat.html"


class TestP2NativeChatUi(unittest.TestCase):
    def setUp(self) -> None:
        use_store(InMemoryEmergencyFundStore())
        reset_all_stores()
        reset_logs()
        reset_metrics()
        self.pair = load_pair()
        self.client = TestClient(create_app())

    def test_chat_html_has_gate_badge_and_deny_cta(self):
        html = CHAT_HTML.read_text(encoding="utf-8")
        self.assertIn('id="gateBadge"', html)
        self.assertIn('id="denyCta"', html)
        self.assertIn("/app/content?key=SAFE-02", html)
        self.assertIn("<a", html)
        self.assertNotIn("TARGET_MONTHS", html)

    def test_hard_deny_chat_no_llm_metrics_zero(self):
        self.assertEqual(TARGET_MONTHS, 3)
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

    def test_health_untouched(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["gate_months"], 3)
        self.assertTrue(body["hard_deny"])
        self.assertIn("dialect", body)


if __name__ == "__main__":
    unittest.main()
