"""P2-OS-15 Anglicisms bypass / Hard Rule / Parser VI."""

from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SAFETY = (ROOT / "welora" / "api" / "static" / "safety.html").read_text(encoding="utf-8")
HS = (ROOT / "welora" / "api" / "static" / "healthscore.html").read_text(encoding="utf-8")
PARSER = (ROOT / "welora" / "api" / "static" / "parser.html").read_text(encoding="utf-8")
PRERULE = (ROOT / "welora" / "api" / "static" / "prerule.html").read_text(encoding="utf-8")


class TestP2OsAnglicismsVi(unittest.TestCase):
    def test_bypass_bo_qua(self):
        self.assertIn("không bỏ qua Cổng", SAFETY)
        self.assertIn("không bỏ qua Cổng", HS)
        self.assertIn("không bỏ qua Cổng", PARSER)
        self.assertNotIn("bypass", SAFETY.lower())
        self.assertIn("can_bypass_gate_with_score", HS)
        self.assertIn('id="hsBypassNote"', HS)

    def test_hard_rule_luat_cung(self):
        self.assertIn("recent_hard_rule_violation:'Vi phạm Luật cứng gần đây'", SAFETY)
        self.assertNotIn("'Vi phạm Hard Rule", SAFETY)
        self.assertIn("recent_hard_rule_violation", SAFETY)

    def test_parser_sao_ke(self):
        self.assertIn("<title>Welora · Sao kê CSV ngân hàng</title>", PARSER)
        self.assertIn("<h1>Sao kê CSV ngân hàng</h1>", PARSER)
        self.assertIn("/parser/csv", PARSER)

    def test_prerule_tu_choi(self):
        self.assertIn("Từ chối trước LLM", PRERULE)
        self.assertNotIn("Deny trước LLM", PRERULE)
        self.assertIn("<h1>Pre-Rule</h1>", PRERULE)


if __name__ == "__main__":
    unittest.main()
