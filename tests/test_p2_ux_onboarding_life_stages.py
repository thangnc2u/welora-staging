"""P2 UX — 6 household options P1–P6 (PRD v2; replaces life_stage 04/09)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STAGES = [
    ("solo", "Độc thân đô thị 18+"),
    ("young_family", "25–34 Gia đình trẻ khởi đầu"),
    ("couple_no_kids", "35–59 Vợ chồng không con nhỏ"),
    ("sandwich_3gen", "35–59 Ba đời trên một thu nhập"),
    ("pre_retire", "55–64 Cửa sổ 10 năm trước hưu"),
    ("retire_companion", "65+ Tuổi vàng và hộ đồng hành"),
]


class TestP2UxOnboardingLifeStages(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.onboard = (ROOT / "welora" / "api" / "static" / "onboarding.html").read_text(encoding="utf-8")
        self.dna = (ROOT / "welora" / "api" / "static" / "dna.html").read_text(encoding="utf-8")

    def test_onboarding_select_has_six_in_order(self):
        start = self.onboard.find('id="household"')
        self.assertGreater(start, 0)
        chunk = self.onboard[start : start + 1200]
        pos = 0
        for code, label in STAGES:
            i = chunk.find(f'value="{code}"')
            self.assertGreaterEqual(i, pos, code)
            self.assertIn(label, chunk)
            pos = i
        self.assertNotIn('value="young_single"', chunk)

    def test_dna_enum_maps_six(self):
        for code, label in STAGES:
            self.assertIn(code, self.dna)
            self.assertIn(label, self.dna)
        self.assertIn("enumLabel", self.dna)

    def test_pages_200_and_health(self):
        self.assertEqual(self.client.get("/app/onboarding").status_code, 200)
        self.assertEqual(self.client.get("/app/dna").status_code, 200)
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
