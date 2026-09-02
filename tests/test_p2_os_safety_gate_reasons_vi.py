"""P2-OS-05 Safety #gateMeta reason codes → Vietnamese."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = (Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html").read_text(
    encoding="utf-8"
)


class TestP2OsSafetyGateReasonsVi(unittest.TestCase):
    def test_reason_map(self):
        self.assertIn("GATE_REASON_VI", HTML)
        self.assertIn("formatGateReasons", HTML)
        self.assertIn("data_missing:'Thiếu dữ liệu'", HTML)
        self.assertIn("emergency_fund_below_3_months:'Quỹ khẩn cấp dưới 3 tháng'", HTML)
        self.assertIn("dangerous_debt_unhandled:'Nợ nguy hiểm chưa xử lý'", HTML)
        self.assertIn("mastery_missing:'Chưa đạt làm chủ (cần Áp dụng)'", HTML)
        self.assertIn("recent_hard_rule_violation:'Vi phạm Hard Rule gần đây'", HTML)
        self.assertIn("GATE_REASON_VI[c]||c", HTML)
        self.assertIn("join(' · ')", HTML)

    def test_not_raw_join_reasons(self):
        self.assertNotIn("gate.reasons||[]).join(", HTML)
        self.assertIn("formatGateReasons(state.gate&&state.gate.reasons", HTML)

    def test_no_regress_debt_mastery(self):
        self.assertIn('id="debtCard"', HTML)
        self.assertIn('id="ctaGoalsDebt"', HTML)
        self.assertIn('id="masteryState"', HTML)
        self.assertIn('id="gateMeta"', HTML)
        self.assertIn("welora_device_id", HTML)
        self.assertNotIn("innerHTML", HTML)

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
