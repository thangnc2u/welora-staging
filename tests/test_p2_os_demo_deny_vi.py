"""P2-OS-12 Demo Deny → Từ chối."""

from __future__ import annotations

from pathlib import Path
import unittest

from welora.safety_gate import TARGET_MONTHS

HTML = (Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "demo.html").read_text(
    encoding="utf-8"
)


class TestP2OsDemoDenyVi(unittest.TestCase):
    def test_titles_and_map(self):
        self.assertIn("→ Từ chối →", HTML)
        self.assertIn("R01 vẫn từ chối", HTML)
        self.assertIn("<h2>5 · Từ chối (tất tay ETF)</h2>", HTML)
        self.assertIn("<h2>8 · R01 vẫn từ chối</h2>", HTML)
        self.assertNotIn("→ Deny →", HTML)
        self.assertNotIn("R01 vẫn deny", HTML)
        self.assertNotIn("<h2>5 · Deny", HTML)
        self.assertIn("function resultLabel", HTML)
        self.assertIn("'Từ chối cứng'", HTML)
        self.assertIn("==='deny'", HTML)
        self.assertIn("'deny':'ok'", HTML)
        self.assertIn(".deny{", HTML)
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
