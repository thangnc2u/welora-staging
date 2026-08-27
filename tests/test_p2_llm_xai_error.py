"""P2: grok-4.3 payload + HTTP error visible; deny never calls LLM."""

from __future__ import annotations

import io
import urllib.error
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.chat_service import reset_logs, service_chat
from welora.llm_adapter import build_openai_compatible_payload, safe_call_llm
from welora.safety_gate import TARGET_MONTHS


class TestP2LlmXaiError(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_payload_grok43_no_temperature_has_reasoning_none(self):
        p = build_openai_compatible_payload("grok-4.3", "sys", "hi")
        self.assertEqual(p["model"], "grok-4.3")
        self.assertNotIn("temperature", p)
        self.assertEqual(p.get("reasoning_effort"), "none")
        p2 = build_openai_compatible_payload("gpt-4o-mini", "sys", "hi")
        self.assertNotIn("temperature", p2)
        self.assertNotIn("reasoning_effort", p2)

    def test_http_error_keeps_llm_error(self):
        def boom(system: str, message: str) -> str:
            raise urllib.error.HTTPError(
                "https://api.x.ai/v1/chat/completions",
                400,
                "Bad Request",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(b""),
            )

        reply, tag, invoked = safe_call_llm(boom, "sys", "hi")
        self.assertFalse(invoked)
        self.assertEqual(tag, "llm_error")
        self.assertIn("HTTPError", reply)
        self.assertIn("400", reply)
        self.assertNotIn("xai-", reply)

        code, out = service_chat(
            user_id="u-pass-budget",
            message="Gợi ý ngân sách chi tiêu hàng tháng",
            context_seed={
                "user_id": "u-pass-budget",
                "safety_gate": {"status": "passed", "months_covered": 3},
            },
            call_llm=boom,
        )
        self.assertEqual(code, 200)
        if out.get("guardrail_result") != "deny":
            self.assertEqual(out.get("model_used"), "llm_error")
            self.assertFalse(out.get("llm_called"))
            self.assertIn("HTTPError", out.get("reply") or "")

    def test_deny_all_in_etf_no_llm(self):
        reset_logs()
        auth = self.client.post("/auth/device", json={"device_id": "dev-ticket-w-etf"})
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
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
