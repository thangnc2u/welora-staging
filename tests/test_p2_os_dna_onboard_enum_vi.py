"""P2-OS-14 DNA enums + onboarding Target VI (P1–P6 household)."""

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
        self.assertIn("solo:'Độc thân đô thị 18+'", DNA)
        self.assertIn("young_family:'25–34 Gia đình trẻ khởi đầu'", DNA)
        self.assertIn("couple_no_kids:'35–59 Vợ chồng không con nhỏ'", DNA)
        self.assertIn("sandwich_3gen:'35–59 Ba đời trên một thu nhập'", DNA)
        self.assertIn("pre_retire:'55–64 Cửa sổ 10 năm trước hưu'", DNA)
        self.assertIn("retire_companion:'65+ Tuổi vàng và hộ đồng hành'", DNA)
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
        self.assertIn('value="solo"', OB)
        self.assertIn('value="young_family"', OB)

    def test_onboarding_target(self):
        self.assertIn("Mục tiêu quỹ: 3 tháng", OB)
        self.assertNotIn("Target quỹ", OB)
        self.assertIn("type:'emergency_fund'", OB)


if __name__ == "__main__":
    unittest.main()
