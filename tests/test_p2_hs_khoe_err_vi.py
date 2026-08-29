"""P2 Ticket CS — health-score error Điểm sức khỏe (ỏ U+1ECF)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "healthscore.html"


class TestP2HsKhoeErrVi(unittest.TestCase):
    def test_error(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("textContent='Không đọc được điểm sức khỏe'", html)
        self.assertIn("\u00f4", html)
        self.assertIn("\u1ecd", html)
        self.assertIn("\u01b0", html)
        self.assertIn("\u1ee3", html)
        self.assertIn("\u1ecf", html)
        self.assertNotIn("Không đọc được điểm sức khởe", html)
        self.assertNotIn("khởe", html)
        self.assertNotIn("\u1edf", html)
        self.assertIn("<title>Welora · Điểm sức khỏe</title>", html)
        self.assertIn("<h1>Điểm sức khỏe</h1>", html)
        self.assertIn("Điểm không bypass Cổng An Toàn", html)
        self.assertNotIn("innerHTML", html)
        for nid in ("navHome", "hsScore", "hsLevel", "hsBypassNote", "hsComponents", "hsErr"):
            self.assertIn(f'id="{nid}"', html)

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
