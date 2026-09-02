"""P0 Hiến pháp Cốt lõi v1 — CORE-01..CORE-10."""

from __future__ import annotations

from pathlib import Path
import json
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.core_constitution import CORE_CODES, get_core_constitution
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "core-constitution.html"
HOME = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "home.html"

CORE08_PRINCIPLE = (
    "Không ai đủ thông minh để đặt cược một chiều trong thế giới đầy rủi ro và ngẫu nhiên. "
    "Đa dạng hóa không chỉ là phân tán tài sản, mà còn là xây dựng nhiều nguồn thu nhập, kỹ năng và lựa chọn trong cuộc sống."
)

REQUIRED = (
    "article_id",
    "code",
    "title",
    "principle",
    "explanation",
    "constraint_type",
    "category",
    "priority",
    "parameters",
    "violation_examples",
    "compliance_examples",
    "is_editable",
    "principle_key",
)


class TestP0CoreConstitutionV1(unittest.TestCase):
    def test_seed_ten_core_codes(self):
        data = get_core_constitution()
        self.assertEqual(data["constitution_id"], "welora_core_v1")
        self.assertEqual(data["owner_type"], "welora_core")
        self.assertEqual(data["version"], "1.0.0")
        self.assertEqual(data["status"], "active")
        self.assertIn("Welorademy", data["title"])
        arts = data["articles"]
        self.assertEqual(len(arts), 10)
        codes = [a["code"] for a in arts]
        self.assertEqual(tuple(codes), CORE_CODES)
        for a in arts:
            for k in REQUIRED:
                self.assertIn(k, a)
            self.assertFalse(a["is_editable"])
            self.assertEqual(a["code"], a["principle_key"])
            self.assertTrue(str(a["principle"]).strip())
            self.assertTrue(str(a["explanation"]).strip())
            self.assertFalse(str(a["code"]).startswith("SAFE-"))
            self.assertFalse(str(a["code"]).startswith("DEBT-"))
        blob = " ".join(codes)
        self.assertNotIn("SAFE-", blob)
        self.assertNotIn("DEBT-", blob)
        core08 = next(a for a in arts if a["code"] == "CORE-08")
        self.assertEqual(core08["principle"], CORE08_PRINCIPLE)
        dumped = json.dumps(data, ensure_ascii=False)
        self.assertNotIn("xúng động", dumped)
        self.assertIn("xung động", dumped)

    def test_api_readonly(self):
        r = TestClient(create_app()).get("/constitution/core")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["owner_type"], "welora_core")
        self.assertEqual(len(b["articles"]), 10)
        self.assertEqual(b["articles"][0]["code"], "CORE-01")
        self.assertEqual(b["articles"][7]["principle"], CORE08_PRINCIPLE)

    def test_html_core_cta(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Cốt lõi", html)
        self.assertIn("CORE-01", html)
        self.assertIn('id="ctaPersonal"', html)
        self.assertIn('href="/app/constitution"', html)
        self.assertIn("/constitution/core", html)
        self.assertNotIn("innerHTML", html)
        home = HOME.read_text(encoding="utf-8")
        self.assertIn('id="navCoreConstitution"', home)
        self.assertIn("Hiến pháp Cốt lõi", home)
        self.assertIn("Hiến pháp cá nhân", home)
        r = TestClient(create_app()).get("/app/core-constitution")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Cốt lõi", r.text)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
