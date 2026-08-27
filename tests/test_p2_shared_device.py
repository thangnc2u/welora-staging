"""P2 shared device identity — localStorage.welora_device_id on 4 screens."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"


class TestP2SharedDevice(unittest.TestCase):
    def test_four_html_share_welora_device_id(self):
        names = ("onboarding.html", "safety.html", "chat.html", "demo.html")
        for name in names:
            html = (STATIC / name).read_text(encoding="utf-8")
            self.assertIn("welora_device_id", html, name)
            self.assertIn("localStorage", html, name)

    def test_no_prefix_only_mint(self):
        ob = (STATIC / "onboarding.html").read_text(encoding="utf-8")
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        demo = (STATIC / "demo.html").read_text(encoding="utf-8")
        self.assertNotIn("'mob-'+Date.now()", ob)
        self.assertNotIn('"mob-"+Date.now()', ob)
        self.assertNotIn("'chat-'+Date.now()", chat)
        self.assertNotIn('"chat-"+Date.now()', chat)
        self.assertNotIn("'demo-'+Date.now()", demo)
        self.assertNotIn('"demo-"+Date.now()', demo)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
