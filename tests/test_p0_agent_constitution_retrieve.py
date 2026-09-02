"""P0 Agent — retrieve Hiến pháp Cốt lõi bắt buộc + audit deny."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from welora.agent import evaluate_pre_rules, handle_chat, render_deny
from welora.chat_service import reset_logs, service_chat
from welora.constitution_retrieve import (
    RULE_TO_CORE,
    retrieve_constitution,
    top_core_articles,
)
from welora.core_constitution import CORE_CODES, get_core_constitution
from welora.fixtures import load_pair, reset_all_stores
from welora.pre_rule_service import service_evaluate
from welora.safety_gate import TARGET_MONTHS


class TestP0AgentConstitutionRetrieve(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_all_stores()
        reset_logs()
        cls.pair = load_pair()

    def test_core_seed_intact(self):
        core = get_core_constitution()
        codes = [a["code"] for a in core["articles"]]
        self.assertEqual(tuple(codes), CORE_CODES)
        self.assertEqual(len(codes), 10)
        self.assertTrue(all(c.startswith("CORE-") for c in codes))
        self.assertFalse(any(c.startswith("SAFE-") or c.startswith("DEBT-") for c in codes))

    def test_retrieve_loads_core_before_rules(self):
        bundle = retrieve_constitution(personal_codes=["P-01"])
        self.assertTrue(bundle.ok)
        self.assertGreaterEqual(bundle.core_articles_count, 1)
        self.assertEqual(bundle.constitution_version, "1.0.0")
        self.assertEqual(bundle.personal_codes_count, 1)
        top = top_core_articles(bundle)
        self.assertTrue(top)
        self.assertEqual(top[0].get("constraint_type"), "hard_ban")

    def test_r02_deny_mentions_core07_title(self):
        seed = dict(self.pair["not_passed"]["agent_context_seed"])
        code, out = service_evaluate(
            message="Có nên bắt đầu DCA vào ETF ngay không?",
            context_seed=seed,
        )
        self.assertEqual(code, 200)
        self.assertEqual(out["guardrail_result"], "deny")
        self.assertEqual(out["rule_id"], "R02")
        self.assertFalse(out["should_call_llm"])
        reply = out.get("reply") or ""
        self.assertTrue("CORE-07" in reply or "Phòng thủ" in reply)
        self.assertGreaterEqual(out.get("core_articles_count") or 0, 1)
        self.assertEqual(out.get("constitution_version"), "1.0.0")

    def test_advisory_retrieve_before_llm(self):
        seed = dict(self.pair["passed"]["agent_context_seed"])
        seed["data_confidence"] = "full"
        seed["answer_confidence"] = 0.90
        seen = {"sys": ""}

        def llm(sys: str, _msg: str) -> str:
            seen["sys"] = sys
            return "advisory ok"

        code, out = service_chat(
            user_id=seed["user_id"],
            message="Giải thích giúp quỹ khẩn cấp là gì?",
            context_seed=seed,
            call_llm=llm,
        )
        self.assertEqual(code, 200)
        self.assertEqual(out["guardrail_result"], "pass")
        self.assertTrue(out.get("llm_called"))
        self.assertGreaterEqual(out.get("core_articles_count") or 0, 1)
        self.assertIn("CORE-", seen["sys"])
        self.assertIn("Welorademy", seen["sys"])
        self.assertNotIn("Welora Academy", seen["sys"])

    def test_missing_core_is_safe_deny(self):
        seed = dict(self.pair["passed"]["agent_context_seed"])
        seed["answer_confidence"] = 0.95
        called = {"n": 0}

        def llm(_sys: str, _msg: str) -> str:
            called["n"] += 1
            return "should not run"

        with patch(
            "welora.core_constitution.get_core_constitution",
            return_value={"articles": [], "version": "", "constitution_id": ""},
        ):
            code, out = service_chat(
                user_id=seed["user_id"],
                message="Xin chào",
                context_seed=seed,
                call_llm=llm,
            )
        self.assertEqual(code, 200)
        self.assertEqual(out["guardrail_result"], "deny")
        self.assertFalse(out["llm_called"])
        self.assertEqual(called["n"], 0)
        self.assertIn("Hiến pháp Cốt lõi", out.get("reply") or "")

    def test_low_confidence_still_no_bypass(self):
        seed = dict(self.pair["passed"]["agent_context_seed"])
        seed["data_confidence"] = "missing"
        seed["answer_confidence"] = 0.40
        called = {"n": 0}

        def llm(_s, _m):
            called["n"] += 1
            return "no"

        code, out = service_chat(
            user_id=seed["user_id"],
            message="Tôi nên làm gì với tiền dư?",
            context_seed=seed,
            call_llm=llm,
        )
        self.assertEqual(code, 200)
        self.assertFalse(out["llm_called"])
        self.assertEqual(called["n"], 0)
        self.assertLess(out["answer_confidence"], 0.80)

    def test_gate_not_passed_hard_deny_before_llm(self):
        seed = dict(self.pair["not_passed"]["agent_context_seed"])
        seed["answer_confidence"] = 0.95
        called = {"n": 0}

        def llm(_s, _m):
            called["n"] += 1
            return "no"

        code, out = service_chat(
            user_id=seed["user_id"],
            message="Tôi muốn all-in ETF ngay",
            context_seed=seed,
            call_llm=llm,
        )
        self.assertEqual(code, 200)
        self.assertEqual(out["guardrail_result"], "deny")
        self.assertEqual(out.get("rule_id") or out.get("rule_hit"), "R02")
        self.assertFalse(out["llm_called"])
        self.assertEqual(called["n"], 0)

    def test_detect_logic_unchanged_and_gate_months(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(RULE_TO_CORE["R02"], ["CORE-07"])
        self.assertEqual(RULE_TO_CORE["R05"], ["CORE-05"])
        seed = dict(self.pair["not_passed"]["agent_context_seed"])
        from welora.pre_rule_service import context_from_seed

        ctx = context_from_seed(seed)
        pre = evaluate_pre_rules("Có nên bắt đầu DCA vào ETF ngay không?", ctx)
        self.assertEqual(pre.result, "deny")
        self.assertEqual(pre.primary_hit.rule_id, "R02")

    def test_handle_chat_audit_fields(self):
        from welora.pre_rule_service import context_from_seed

        seed = dict(self.pair["not_passed"]["agent_context_seed"])
        ctx = context_from_seed(seed)
        logs: list = []
        out = handle_chat(seed["user_id"], "Tôi muốn all-in ETF ngay", ctx, logs=logs)
        self.assertEqual(out["guardrail_result"], "deny")
        self.assertIn("CORE-07", out["reply"])
        self.assertTrue(logs)
        self.assertIn("constitution_version", logs[0])
        self.assertIn("personal_codes_count", logs[0])
        self.assertFalse(logs[0]["llm_called"])
        self.assertEqual(logs[0]["rule_id"], "R02")


if __name__ == "__main__":
    unittest.main()
