"""P2-OS-13 Logs Cổng + demo step7 VI."""

from __future__ import annotations

from pathlib import Path
import unittest

from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
LOGS = (ROOT / "welora" / "api" / "static" / "logs.html").read_text(encoding="utf-8")
DEMO = (ROOT / "welora" / "api" / "static" / "demo.html").read_text(encoding="utf-8")


class TestP2OsLogsGateDemoStep7Vi(unittest.TestCase):
    def test_logs_gate_map(self):
        self.assertIn("GATE_VI", LOGS)
        self.assertIn("passed:'ĐẠT'", LOGS)
        self.assertIn("not_passed:'CHƯA ĐẠT'", LOGS)
        self.assertIn("function gateLabel", LOGS)
        self.assertIn("gateLabel(row.safety_gate_status)", LOGS)
        self.assertIn("row.safety_gate_status", LOGS)

    def test_demo_step7(self):
        self.assertIn("'Trạng thái: '", DEMO)
        self.assertIn("' · Tháng phủ: '", DEMO)
        self.assertIn("function gateLabel", DEMO)
        self.assertIn("'passed'?'ĐẠT'", DEMO)
        self.assertIn("'not_passed'?'CHƯA ĐẠT'", DEMO)
        self.assertIn("r.d.status==='passed'", DEMO)
        self.assertNotIn("'status: '", DEMO)
        self.assertNotIn("'months_covered: '", DEMO)
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
