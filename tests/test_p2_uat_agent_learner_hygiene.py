"""P2 UAT — agent learner hygiene: MD strip, deny href, LLM error VI."""

from __future__ import annotations

import io
import re
import urllib.error
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.chat_service import reset_logs, service_chat
from welora.llm_adapter import safe_call_llm
from welora.safety_gate import TARGET_MONTHS

CHAT = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "chat.html"
_LEAKY = re.compile(r"(?:CORE|SAFE|DEBT|PC)-")
_FIXED_VI = "Không gọi được mô hình tư vấn lúc này. Bạn thử lại sau nhé."


class TestP2UatAgentLearnerHygiene(unittest.TestCase):
    def setUp(self) -> None:
        self.html = CHAT.read_text(encoding="utf-8")
        self.client = TestClient(create_app())

    # --- (1) chat bubble MD strip ---
    def test_chat_bubble_strips_md_markers(self):
        self.assertIn("function stripMdMarkers", self.html)
        self.assertIn("stripMdMarkers(t)", self.html)
        self.assertIn(r"/^#{1,6}\s+/gm", self.html)
        self.assertIn(r"/\*\*([^*]+)\*\*/g", self.html)
        self.assertIn(r"/__([^_]+)__/g", self.html)
        # Keep textContent (no innerHTML XSS surface)
        self.assertNotIn("innerHTML", self.html)
        # Post-pass advisory path still uses add() → stripMdMarkers
        self.assertIn("showPostPassChips", self.html)
        self.assertIn("POST_PASS_CHIPS", self.html)
        self.assertIn("add(bubble, cls)", self.html)

    def test_strip_md_markers_js_behavior(self):
        """Mirror JS strip rules in Python for regression contract."""
        def strip_md(t: str) -> str:
            t = re.sub(r"^#{1,6}\s+", "", t, flags=re.M)
            t = re.sub(r"\*\*([^*]+)\*\*", r"\1", t)
            t = re.sub(r"__([^_]+)__", r"\1", t)
            return t

        raw = "## Quỹ khẩn cấp\nGiữ **3 tháng** chi tiêu và __không__ phá quỹ."
        out = strip_md(raw)
        self.assertNotIn("**", out)
        self.assertNotIn("__", out)
        self.assertNotIn("#", out.split("\n")[0])
        self.assertIn("3 tháng", out)
        self.assertIn("không", out)
        self.assertIn("Quỹ khẩn cấp", out)

    # --- (2) denyCta / pickHref hygiene ---
    def test_deny_cta_href_no_principle_keys(self):
        self.assertIn('id="denyCta"', self.html)
        self.assertIn('href="/app/safety"', self.html)
        self.assertIn("Đọc nguyên tắc An Toàn", self.html)
        self.assertIn("function isLeakyHref", self.html)
        self.assertIn("function pickHref", self.html)
        self.assertIn("/app/safety", self.html)
        self.assertIn("academy_href", self.html)
        # Learner-visible defaults / fallbacks must not embed keys in hrefs
        self.assertNotIn("/app/content?key=", self.html)
        self.assertNotIn("encodeURIComponent(keys[0])", self.html)
        self.assertNotIn('href="/app/content', self.html)
        self.assertNotIn("?key=SAFE-", self.html)
        self.assertNotIn("?key=CORE-", self.html)
        self.assertNotIn("?key=DEBT-", self.html)
        self.assertNotIn("?key=PC-", self.html)
        # isLeakyHref source may mention prefixes; denyCta static label stays VI
        label_line = [ln for ln in self.html.splitlines() if 'id="denyCta"' in ln][0]
        self.assertNotRegex(label_line, r"(?:CORE|SAFE|DEBT|PC)-")

    def test_pick_href_contract_prefers_safe_routes(self):
        """Document JS pickHref contract: skip leaky hrefs, prefer academy/safety."""
        self.assertIn("isLeakyHref(L.academy_href)", self.html)
        self.assertIn("!isLeakyHref(h)", self.html)
        self.assertRegex(self.html, r"return '/app/safety';")

    # --- (3) safe_call_llm learner errors ---
    def test_safe_call_llm_http_error_fixed_vi_only(self):
        def boom(system: str, message: str) -> str:
            raise urllib.error.HTTPError(
                "https://api.x.ai/v1/chat/completions",
                400,
                "Bad Request",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(b'{"error":{"message":"secret provider snippet"}}'),
            )

        reply, tag, invoked = safe_call_llm(boom, "sys", "hi")
        self.assertFalse(invoked)
        self.assertEqual(tag, "llm_error")
        self.assertEqual(reply, _FIXED_VI)
        self.assertNotIn("HTTPError", reply)
        self.assertNotIn("HTTP", reply)
        self.assertNotIn("400", reply)
        self.assertNotIn("secret provider", reply)
        self.assertNotIn("snippet", reply)

    def test_post_pass_advisory_llm_error_vi(self):
        reset_logs()

        def boom(system: str, message: str) -> str:
            raise urllib.error.HTTPError(
                "https://api.x.ai/v1/chat/completions",
                503,
                "Unavailable",
                hdrs=None,  # type: ignore[arg-type]
                fp=io.BytesIO(b'{"error":"upstream_down"}'),
            )

        code, out = service_chat(
            user_id="u-pass-hygiene",
            message="Quỹ khẩn cấp nên giữ thế nào?",
            context_seed={
                "user_id": "u-pass-hygiene",
                "safety_gate": {"status": "passed", "months_covered": 3},
            },
            call_llm=boom,
        )
        self.assertEqual(code, 200)
        if out.get("guardrail_result") != "deny":
            self.assertEqual(out.get("model_used"), "llm_error")
            self.assertFalse(out.get("llm_called"))
            self.assertEqual(out.get("reply"), _FIXED_VI)
            self.assertNotIn("upstream_down", out.get("reply") or "")
            self.assertNotIn("HTTPError", out.get("reply") or "")

    def test_deny_still_keeps_principle_keys_in_json(self):
        """Keys OK in API JSON/audit — only learner href/copy are scrubbed."""
        reset_logs()
        auth = self.client.post("/auth/device", json={"device_id": "dev-hygiene-deny"})
        uid = auth.json().get("user_id")
        r = self.client.post(
            "/agent/chat",
            json={"user_id": uid, "message": "Tôi muốn all-in ETF ngay"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("guardrail_result"), "deny")
        keys = body.get("principle_keys") or []
        self.assertTrue(any(_LEAKY.search(str(k)) for k in keys))
        reply = body.get("reply") or ""
        self.assertFalse(_LEAKY.search(reply))

    def test_hard_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
