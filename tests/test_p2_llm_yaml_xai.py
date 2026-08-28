"""P2 Ticket AA — render.yaml pins WELORA_LLM_PROVIDER=xai, no secrets."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]


class TestP2LlmYamlXai(unittest.TestCase):
    def test_render_yaml_xai_no_secrets(self):
        yml = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("WELORA_LLM_PROVIDER", yml)
        self.assertIn("value: xai", yml)
        self.assertNotIn("WELORA_LLM_API_KEY", yml)
        self.assertNotIn("XAI_API_KEY", yml)
        self.assertNotIn("xai-", yml)
        self.assertNotRegex(yml, r"(?i)api[_-]?key\s*[:=]")

    def test_deny_still_no_llm(self):
        client = TestClient(create_app())
        auth = client.post("/auth/device", json={"device_id": "dev-ticket-aa-deny"})
        uid = auth.json().get("user_id")
        r = client.post("/agent/chat", json={"user_id": uid, "message": "Tôi muốn all-in ETF ngay"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json().get("guardrail_result"), "deny")
        self.assertFalse(r.json().get("llm_called"))

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
