"""P2 UX — shell bottom nav on DNA / Hiến pháp / Onboarding / Health-score (ops)."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
SHELL_JS = (STATIC / "shell.js").read_text(encoding="utf-8")

PAGES = {
    "dna": (STATIC / "dna.html").read_text(encoding="utf-8"),
    "constitution": (STATIC / "constitution.html").read_text(encoding="utf-8"),
    "onboarding": (STATIC / "onboarding.html").read_text(encoding="utf-8"),
    "healthscore": (STATIC / "healthscore.html").read_text(encoding="utf-8"),
}

ROUTES = (
    ("/app/dna", "dna"),
    ("/app/constitution", "constitution"),
    ("/app/onboarding", "onboarding"),
    ("/app/health-score", "healthscore"),
)


class TestP2UxShellOpsPages(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_static_pages_include_shell_ops(self):
        for name, html in PAGES.items():
            with self.subTest(page=name):
                self.assertIn('/static/shell.css', html)
                self.assertIn('/static/shell.js', html)
                self.assertIn('data-shell-tab="ops"', html)
                self.assertNotIn('data-shell-tab="home"', html)

    def test_ops_cluster_still_covers_paths(self):
        for frag in (
            'path.indexOf("/app/dna")',
            'path.indexOf("/app/constitution")',
            'path.indexOf("/app/health-score")',
            'path.indexOf("/app/onboarding")',
            'path.indexOf("/app/safety")',
            'path.indexOf("/app/goals")',
        ):
            self.assertIn(frag, SHELL_JS)
        self.assertIn('active = "ops"', SHELL_JS)
        self.assertIn('label: "Điều hành"', SHELL_JS)
        self.assertIn('key: "ops"', SHELL_JS)

    def test_http_smoke_shell_ops_on_pages(self):
        for route, _name in ROUTES:
            with self.subTest(route=route):
                r = self.client.get(route)
                self.assertEqual(r.status_code, 200)
                self.assertIn("/static/shell.js", r.text)
                self.assertIn("/static/shell.css", r.text)
                self.assertIn('data-shell-tab="ops"', r.text)

        # no invented healthscore alias
        alias = self.client.get("/app/healthscore")
        self.assertIn(alias.status_code, (404, 405, 307, 308))

        js = self.client.get("/static/shell.js")
        self.assertEqual(js.status_code, 200)
        self.assertIn("Điều hành", js.text)

    def test_hard_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        b = self.client.get("/health").json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        self.assertTrue((ROOT / "welora" / "mode_c_act.py").is_file())
        # Chat gate still present in shell
        self.assertIn("gate: true", SHELL_JS)
        self.assertIn("/safety-gate", SHELL_JS)


if __name__ == "__main__":
    unittest.main()
