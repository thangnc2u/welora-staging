"""P2 Ticket AI — constitution/dna/goals clear without innerHTML."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"
FILES = ("constitution.html", "dna.html", "goals.html")


class TestP2ClearNoInnerHtml(unittest.TestCase):
    def test_three_files_no_innerhtml(self):
        for name in FILES:
            html = (STATIC / name).read_text(encoding="utf-8")
            self.assertNotIn("innerHTML", html, name)
            self.assertIn("textContent", html, name)
            self.assertIn('id="navHome"', html, name)
            self.assertIn("welora_device_id", html, name)
            self.assertIn("createElement", html, name)

    def test_routes_200(self):
        c = TestClient(create_app())
        for path in ("/app/constitution", "/app/dna", "/app/goals"):
            r = c.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertNotIn("innerHTML", r.text)

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
