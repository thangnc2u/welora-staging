"""P2-OS-11 Metrics+Logs Deny → VI."""

from __future__ import annotations

from pathlib import Path
import unittest

from welora.safety_gate import TARGET_MONTHS

METRICS = (Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "metrics.html").read_text(
    encoding="utf-8"
)
LOGS = (Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "logs.html").read_text(
    encoding="utf-8"
)


class TestP2OsMetricsLogsDenyVi(unittest.TestCase):
    def test_metrics_labels(self):
        self.assertIn("Từ chối cứng không gọi LLM · Từ chối có gọi LLM phải = 0", METRICS)
        self.assertIn("Từ chối có gọi LLM", METRICS)
        self.assertIn(">Từ chối cứng<", METRICS)
        self.assertIn("Tổng từ chối", METRICS)
        self.assertNotIn(">Hard Deny<", METRICS)
        self.assertNotIn("Tổng deny", METRICS)
        self.assertIn('id="mDenyLlm"', METRICS)
        self.assertIn('id="mHardDeny"', METRICS)
        self.assertIn('id="mDenyTotal"', METRICS)
        self.assertIn("d.deny_with_llm_calls", METRICS)
        self.assertIn("d.hard_deny", METRICS)
        self.assertIn("d.deny_total", METRICS)

    def test_logs_subtitle(self):
        self.assertIn("Từ chối · luật · gọi LLM · không lộ id", LOGS)
        self.assertNotIn("Deny · luật", LOGS)
        self.assertIn("row.guardrail_result", LOGS)
        self.assertIn("/agent/decision-logs?user_id=", LOGS)
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
