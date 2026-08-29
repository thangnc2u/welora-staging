"""P2 Ticket CO — DNA label Chấp nhận rủi ro."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "dna.html"


class TestP2DnaRiskVi(unittest.TestCase):
    def test_label(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn(
            "['Chấp nhận rủi ro', pick(psy,'risk_tolerance')??data.risk_tolerance]",
            html,
        )
        self.assertIn("\u1ea5", html)
        self.assertIn("\u1ead", html)
        self.assertIn("\u1ee7", html)
        self.assertNotIn("['risk_tolerance'", html)
        self.assertIn("pick(psy,'risk_tolerance')", html)
        self.assertIn("data.risk_tolerance", html)
        self.assertIn("['Thói quen thặng dư'", html)
        self.assertIn("['agent_role_preference'", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn('id="navHome"', html)
        self.assertIn('id="dna"', html)
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
