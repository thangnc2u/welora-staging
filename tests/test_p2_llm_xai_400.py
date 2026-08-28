"""P2: no reasoning_effort; HTTPError body snippet 180; deny no LLM."""

from __future__ import annotations

import io
import urllib.error
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.chat_service import reset_logs
from welora.llm_adapter import build_openai_compatible_payload, safe_call_llm
from welora.safety_gate import TARGET_MONTHS


class TestP2LlmXai400(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_payload_has_no_reasoning_or_temperature(self):
        p = build_openai_compatible_payload("grok-4.3", "sys", "hi")
        self.assertNotIn("reasoning_effort", p)
        self.assertNotIn("temperature", p)
        self.assertEqual(p["model"], "grok-4.3")

    def test_http_400_includes_body_snippet(self):
        def boom(system: str, message: str) -> str:
            raise urllib.error.HTTPError(
                "https://api.x.ai/v1/chat/completions",
                400,
                "Bad Request",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(b'{"error":"bad_request_demo"}'),
            )

        reply, tag, invoked = safe_call_llm(boom, "sys", "hi")
        self.assertFalse(invoked)
        self.assertEqual(tag, "llm_error")
        self.assertIn("HTTPError 400", reply)
        self.assertIn("bad_request_demo", reply)
        self.assertLessEqual(len(reply), 280)

    def test_deny_all_in_etf_no_llm(self):
        reset_logs()
        auth = self.client.post("/auth/device", json={"device_id": "dev-ticket-x-etf"})
        uid = auth.json().get("user_id")
        r = self.client.post(
            "/agent/chat",
            json={"user_id": uid, "message": "Tôi muốn all-in ETF ngay"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("guardrail_result"), "deny")
        self.assertFalse(body.get("llm_called"))
        m = self.client.get("/metrics").json()
        self.assertEqual(int(m.get("deny_with_llm_calls") or 0), 0)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
