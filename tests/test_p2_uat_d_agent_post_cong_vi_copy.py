"""P2 UAT-D — agent post-Cổng VI copy (no CORE leak + R08/muted)."""

from __future__ import annotations

import re
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.agent import DENY_TEMPLATES, HARD, PRIORITY, TARGET_MONTHS as AGENT_TARGET
from welora.api.app import create_app
from welora.chat_service import advisory_stub, reset_logs, service_chat
from welora.constitution_retrieve import advisory_system_prefix, retrieve_constitution
from welora.fixtures import load_pair, reset_all_stores
from welora.mastery import NODE_NO_EFUND
from welora.safety_gate import TARGET_MONTHS

CHAT = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "chat.html"
_RAW_KEY = re.compile(r"\b(?:SAFE|CORE|DEBT|PC)-")
_RAW_REPLY = re.compile(r"CORE-|SAFE-|DEBT-|PC-|\(Emergency Fund\)")


class TestP2UatDAgentPostCongViCopy(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_all_stores()
        reset_logs()
        cls.pair = load_pair()

    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_advisory_prefix_no_raw_keys(self):
        seed = dict(self.pair["passed"]["agent_context_seed"])
        codes = list(seed.get("personal_constitution_codes") or [])
        bundle = retrieve_constitution(personal_codes=codes, user_id=seed["user_id"])
        self.assertTrue(bundle.ok)
        prefix = advisory_system_prefix(bundle)
        self.assertTrue(prefix.strip())
        self.assertNotRegex(prefix, _RAW_KEY)
        self.assertIn("Phòng thủ", prefix)
        self.assertIn("CẤM nhắc mã nguyên lý nội bộ", prefix)
        self.assertIn("Welorademy", prefix)

    def test_gate_passed_advisory_reply_no_code_leak(self):
        seed = dict(self.pair["passed"]["agent_context_seed"])
        seed["data_confidence"] = "full"
        seed["answer_confidence"] = 0.95

        def llm(sys: str, msg: str) -> str:
            # Simulate a well-behaved model; also assert prompt hygiene
            self.assertNotRegex(sys, _RAW_KEY)
            return (
                "Cổng An Toàn đã đạt. Bạn có thể giữ quỹ khẩn cấp và hỏi khung rủi ro "
                "cho phần tiền dư — quyết định cuối cùng thuộc về bạn."
            )

        code, out = service_chat(
            user_id=seed["user_id"],
            message="Giải thích giúp quỹ khẩn cấp là gì?",
            context_seed=seed,
            call_llm=llm,
        )
        self.assertEqual(code, 200)
        self.assertEqual(out.get("guardrail_result"), "pass")
        reply = out.get("reply") or ""
        self.assertNotRegex(reply, _RAW_REPLY)
        self.assertNotIn("(Emergency Fund)", reply)

    def test_r08_deny_template_vi_no_passed_stage_en(self):
        body = DENY_TEMPLATES["R08"]
        self.assertNotIn("Passed", body)
        self.assertNotIn("Stage 3", body)
        self.assertIn("Giai đoạn 3", body)
        self.assertIn("chưa đạt", body)
        self.assertIn("R08", HARD)
        self.assertIn("R08", PRIORITY)

        seed = dict(self.pair["not_passed"]["agent_context_seed"])
        code, out = service_chat(
            user_id=seed["user_id"],
            message="Mở Stage 3 giúp tôi",
            context_seed=seed,
        )
        self.assertEqual(code, 200)
        self.assertEqual(out.get("guardrail_result"), "deny")
        self.assertEqual(out.get("rule_id") or out.get("rule_hit"), "R08")
        reply = out.get("reply") or ""
        self.assertNotIn("Passed", reply)
        self.assertNotIn("Stage 3", reply)
        self.assertIn("Giai đoạn 3", reply)
        self.assertIn("chưa đạt", reply)
        self.assertNotRegex(reply, r"\b(?:SAFE|CORE|DEBT)-\d{2}\b")
        self.assertIn("CORE-07", out.get("principle_keys") or [])

    def test_muted_and_stub_no_llm_jargon(self):
        html = CHAT.read_text(encoding="utf-8")
        self.assertIn("Từ chối cứng trước tư vấn · An Toàn ≥ 3 tháng", html)
        self.assertNotIn("trước LLM", html)
        self.assertIn('id="suggestChips"', html)
        self.assertIn("POST_PASS_CHIPS", html)
        self.assertIn("/users/", html)
        self.assertIn("safety-gate", html)

        passed = advisory_stub("xin chào", "passed")
        not_passed = advisory_stub("xin chào", "not_passed")
        self.assertNotIn("advisory", passed.lower())
        self.assertNotIn("advisory", not_passed.lower())
        self.assertIn("tư vấn", passed)
        self.assertIn("An Toàn", not_passed)

    def test_hard_deny_ids_gate_months_mastery_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(AGENT_TARGET, 3)
        self.assertEqual(
            set(HARD),
            {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"},
        )
        self.assertEqual(NODE_NO_EFUND, "no_efund_invest")
        b = self.client.get("/health").json()
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
