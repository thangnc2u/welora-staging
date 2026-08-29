"""P2 — DNA label Giai đoạn sống."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "dna.html"


class TestP2DnaLifeStageVi(unittest.TestCase):
    def test_label(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("['Giai đoạn sống', pick(ident,'life_stage')??data.life_stage]", html)
        self.assertIn("\u0111", html)
        self.assertIn("\u1ea1", html)
        self.assertIn("\u1ed1", html)
        self.assertNotIn("['life_stage'", html)
        self.assertIn("pick(ident,'life_stage')", html)
        self.assertIn("data.life_stage", html)
        self.assertIn("['Ổn định thu nhập'", html)
        self.assertIn("['Hoàn cảnh gia đình'", html)
        self.assertIn("['Chi tiêu thiết yếu / tháng'", html)
        self.assertIn("['Tháng quỹ khẩn cấp'", html)
        self.assertIn("['Có nợ nguy hiểm'", html)
        self.assertIn("['Ưu tiên ngắn hạn'", html)
        self.assertIn("['Thói quen thặng dư'", html)
        self.assertIn("['Chấp nhận rủi ro'", html)
        self.assertIn("['Vai trò Agent ưa thích'", html)
        self.assertIn("fields.forEach(([k,v])=>box.appendChild(row(k,v)))", html)
        self.assertIn("<title>DNA tài chính</title>", html)
        self.assertIn("<h1>DNA tài chính</h1>", html)
        self.assertNotIn("innerHTML", html)
        for nid in ("navHome", "dna"):
            self.assertIn(f'id="{nid}"', html)
        self.assertIn("emptyState", html)

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
