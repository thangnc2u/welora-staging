"""P2 UX — 6 life_stage options (Founder 04/09)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STAGES = [
    ("young_single", "Độc thân trẻ"),
    ("established_single", "Độc thân ổn định"),
    ("young_couple", "Mới kết hôn / đôi"),
    ("family", "Gia đình có con"),
    ("pre_retire", "Trước hưu"),
    ("retired", "Nghỉ hưu"),
]


class TestP2UxOnboardingLifeStages(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.onboard = (ROOT / "welora" / "api" / "static" / "onboarding.html").read_text(encoding="utf-8")
        self.dna = (ROOT / "welora" / "api" / "static" / "dna.html").read_text(encoding="utf-8")

    def test_onboarding_select_has_six_in_order(self):
        start = self.onboard.find('id="life_stage"')
        self.assertGreater(start, 0)
        chunk = self.onboard[start : start + 900]
        pos = 0
        for code, label in STAGES:
            i = chunk.find(f'value="{code}"')
            self.assertGreaterEqual(i, pos, code)
            self.assertIn(label, chunk)
            pos = i
        self.assertNotIn(">Gia đình</option>", self.onboard)

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
