"""P2: xAI default model grok-4.3; deny never calls LLM; no key in git."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]


class TestP2LlmXai(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_xai_default_model_is_grok_43(self):
        src = (ROOT / "welora" / "llm_adapter.py").read_text(encoding="utf-8")
        self.assertIn("grok-4.3", src)
        self.assertNotIn("grok-2-latest", src)

    def test_render_stays_stub_no_api_key(self):
        yml = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("WELORA_LLM_PROVIDER", yml)
        self.assertIn("stub", yml)
        self.assertNotIn("WELORA_LLM_API_KEY", yml)
        self.assertNotIn("xai-", yml)

    def test_deny_all_in_etf_no_llm_metric(self):
        auth = self.client.post("/auth/device", json={"device_id": "dev-ticket-v-etf"})
        self.assertEqual(auth.status_code, 200)
        uid = auth.json().get("user_id")
        r = self.client.post(
            "/agent/chat",
            json={"user_id": uid, "message": "Tôi muốn all-in ETF ngay"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("guardrail_result"), "deny")
        self.assertFalse(body.get("llm_called") or body.get("should_call_llm"))
        m = self.client.get("/metrics").json()
        self.assertEqual(int(m.get("deny_with_llm_calls") or 0), 0)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
