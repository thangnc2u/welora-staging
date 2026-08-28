"""P2 Ticket AB — decision logs redact phone/token; UI no user_id."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.chat_service import reset_logs, sanitize_query
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "logs.html"


class TestP2LogsRedact(unittest.TestCase):
    def setUp(self) -> None:
        reset_logs()
        self.client = TestClient(create_app())

    def test_sanitize_phone_bearer_prefixes(self):
        raw = "Gọi +84912345678 hoặc 0912345678 Bearer abcdefghijk xai-ABCDEFG123 sk-SUPERSECRET99"
        clean = sanitize_query(raw)
        self.assertNotIn("0912345678", clean)
        self.assertNotIn("+84912345678", clean)
        self.assertNotIn("84912345678", clean)
        self.assertNotIn("abcdef", clean)
        self.assertNotIn("xai-ABCDEFG123", clean)
        self.assertNotIn("sk-SUPERSECRET99", clean)
        self.assertIn("[REDACTED]", clean)

    def test_decision_logs_api_redacts(self):
        auth = self.client.post("/auth/device", json={"device_id": "dev-ab-redact"})
        uid = auth.json()["user_id"]
        self.client.post(
            "/agent/chat",
            json={
                "user_id": uid,
                "message": "All-in ETF phone 0987654321 Bearer tok_LIVE_abc xai-HELLOKEY99",
            },
        )
        logs = self.client.get("/agent/decision-logs", params={"user_id": uid}).json()
        blob = str(logs)
        self.assertNotIn("0987654321", blob)
        self.assertNotIn("tok_LIVE_abc", blob)
        self.assertNotIn("xai-HELLOKEY99", blob)
        item = logs["items"][0]
        summary = item.get("user_query_summary") or ""
        preview = item.get("raw_response_preview") or ""
        self.assertNotIn("0987654321", summary)
        self.assertNotIn("xai-HELLOKEY99", preview)

    def test_logs_html_no_user_id_innerhtml(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn('id="logList"', html)
        self.assertIn("welora_device_id", html)
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("textContent=user_id", html)
        self.assertNotIn("user_id)+", html)
        self.assertIn("textContent", html)

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
