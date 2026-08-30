"""P2-Agent-80 — answer_confidence threshold 0.80."""

from __future__ import annotations

import unittest

from welora.agent import CONFIDENCE_THRESHOLD, compute_answer_confidence
from welora.chat_service import LOW_CONFIDENCE_REPLY, reset_logs, service_chat
from welora.fixtures import load_pair, reset_all_stores
from welora.safety_gate import TARGET_MONTHS


class TestP2AgentConfidence80(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_all_stores()
        reset_logs()
        cls.pair = load_pair()

    def test_threshold_constant(self):
        self.assertEqual(CONFIDENCE_THRESHOLD, 0.80)
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertLess(compute_answer_confidence("missing"), CONFIDENCE_THRESHOLD)
        self.assertGreaterEqual(compute_answer_confidence("full"), CONFIDENCE_THRESHOLD)

    def test_high_confidence_pass_advisory(self):
        seed = dict(self.pair["passed"]["agent_context_seed"])
        seed["data_confidence"] = "full"
        seed["answer_confidence"] = 0.90
        called = {"n": 0}

        def llm(_sys: str, _msg: str) -> str:
            called["n"] += 1
            return "advisory personalized"

        code, out = service_chat(
            user_id=seed["user_id"],
            message="Xin chào, giải thích giúp quỹ khẩn cấp là gì?",
            context_seed=seed,
            call_llm=llm,
        )
        self.assertEqual(code, 200)
        self.assertEqual(out["guardrail_result"], "pass")
        self.assertGreaterEqual(out["answer_confidence"], 0.80)
        self.assertTrue(out.get("reply"))
        self.assertNotEqual(out["reply"], LOW_CONFIDENCE_REPLY)

    def test_low_confidence_no_personalize(self):
        seed = dict(self.pair["passed"]["agent_context_seed"])
        seed["data_confidence"] = "missing"
        seed["answer_confidence"] = 0.40
        called = {"n": 0}

        def llm(_sys: str, _msg: str) -> str:
            called["n"] += 1
            return "should not run"

        code, out = service_chat(
            user_id=seed["user_id"],
            message="Tôi nên làm gì với tiền dư?",
            context_seed=seed,
            call_llm=llm,
        )
        self.assertEqual(code, 200)
        self.assertLess(out["answer_confidence"], 0.80)
        self.assertFalse(out["llm_called"])
        self.assertEqual(called["n"], 0)
        self.assertEqual(out["model_used"], "rule_only")
        self.assertEqual(out["reply"], LOW_CONFIDENCE_REPLY)
        self.assertIn("Chưa đủ tin cậy", out["confidence_label"])
        self.assertTrue(out.get("content_links"))
        self.assertNotRegex(out["reply"], r"\d")

    def test_deny_wins_even_if_high_confidence(self):
        seed = dict(self.pair["not_passed"]["agent_context_seed"])
        seed["data_confidence"] = "full"
        seed["answer_confidence"] = 0.95
        called = {"n": 0}

        def llm(_sys: str, _msg: str) -> str:
            called["n"] += 1
            return "should not run"

        code, out = service_chat(
            user_id=seed["user_id"],
            message="Tôi muốn all-in ETF ngay",
            context_seed=seed,
            call_llm=llm,
        )
        self.assertEqual(code, 200)
        self.assertEqual(out["guardrail_result"], "deny")
        self.assertEqual(out["model_used"], "rule_only")
        self.assertFalse(out["llm_called"])
        self.assertFalse(out["should_call_llm"])
        self.assertEqual(called["n"], 0)
        self.assertGreaterEqual(out["answer_confidence"], 0.80)

    def test_missing_maps_below_threshold(self):
        self.assertLess(compute_answer_confidence("missing"), 0.80)
        self.assertEqual(compute_answer_confidence("full", override=0.5), 0.5)


if __name__ == "__main__":
    unittest.main()
