"""P2-OS-14 DNA enums + onboarding Target VI."""

from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
DNA = (ROOT / "welora" / "api" / "static" / "dna.html").read_text(encoding="utf-8")
OB = (ROOT / "welora" / "api" / "static" / "onboarding.html").read_text(encoding="utf-8")


class TestP2OsDnaOnboardEnumVi(unittest.TestCase):
    def test_dna_enum_map(self):
        self.assertIn("ENUM_VI", DNA)
        self.assertIn("function enumLabel", DNA)
        self.assertIn("young_single:'Độc thân trẻ'", DNA)
        self.assertIn("established_single:'Độc thân ổn định'", DNA)
        self.assertIn("young_couple:'Mới kết hôn / đôi'", DNA)
        self.assertIn("family:'Gia đình có con'", DNA)
        self.assertIn("pre_retire:'Trước hưu'", DNA)
        self.assertIn("retired:'Nghỉ hưu'", DNA)
        self.assertIn("stable:'Ổn định'", DNA)
        self.assertIn("variable:'Không ổn định'", DNA)
        self.assertIn("alone:'Sống một mình'", DNA)
        self.assertIn("with_family:'Sống cùng gia đình'", DNA)
        self.assertIn("safety:'An Toàn'", DNA)
        self.assertIn("debt:'Trả nợ'", DNA)
        self.assertIn("hold:'Giữ'", DNA)
        self.assertIn("spend:'Tiêu'", DNA)
        self.assertIn("advisor_only:'Chỉ tư vấn'", DNA)
        self.assertIn("'true':'Có'", DNA)
        self.assertIn("'false':'Không'", DNA)
        self.assertIn("enumLabel(value)", DNA)
        self.assertIn("pick(ident,'life_stage')", DNA)
        self.assertIn("value=\"young_single\"", OB)

    def test_onboarding_target(self):
        self.assertIn("Mục tiêu quỹ: 3 tháng", OB)
        self.assertNotIn("Target quỹ", OB)
        self.assertIn("type:'emergency_fund'", OB)


if __name__ == "__main__":
    unittest.main()
