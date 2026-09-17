"""P2 UI — Welora dark theme design tokens (chrome only)."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
TOKENS = (STATIC / "welora-tokens.css").read_text(encoding="utf-8")
SHELL_CSS = (STATIC / "shell.css").read_text(encoding="utf-8")
SHELL_JS = (STATIC / "shell.js").read_text(encoding="utf-8")


def _prop(name: str) -> str:
    m = re.search(rf"--{re.escape(name)}:\s*(#[0-9A-Fa-f]{{6}})", TOKENS)
    assert m, f"missing CSS var --{name}"
    return m.group(1).upper()


class TestP2UiDarkThemeTokens(unittest.TestCase):
    def test_tokens_file_and_shell_import(self):
        self.assertTrue((STATIC / "welora-tokens.css").is_file())
        self.assertIn('@import url("welora-tokens.css")', SHELL_CSS)
        self.assertIn("--bg-app", TOKENS)
        self.assertIn("--gold-500", TOKENS)
        self.assertIn("--color-danger", TOKENS)
        self.assertIn('setAttribute("data-theme", "dark")', SHELL_JS)

    def test_sot_navy_gold_danger(self):
        self.assertEqual(_prop("navy-950"), "#0B1220")
        self.assertEqual(_prop("navy-900"), "#121A28")
        self.assertEqual(_prop("gold-500"), "#D4AF37")
        self.assertEqual(_prop("gold-400"), "#E8C86A")
        self.assertEqual(_prop("color-danger"), "#E85D5D")
        self.assertEqual(_prop("danger-border"), "#E85D5D")
        # Hard Deny / danger must never equal primary gold
        self.assertNotEqual(_prop("color-danger"), _prop("gold-500"))
        self.assertNotEqual(_prop("color-danger"), _prop("gold-400"))
        self.assertNotIn("#D4AF37", TOKENS.split("--color-danger")[1][:80])

    def test_shell_uses_token_vars_not_legacy_hex(self):
        # Allow var(--token) or var(--token, #SoT-fallback) — both bind design tokens
        self.assertIn("var(--bg-app", SHELL_CSS)
        self.assertIn("var(--cta-primary", SHELL_CSS)
        self.assertIn("var(--color-danger", SHELL_CSS)
        self.assertIn("var(--border-focus", SHELL_CSS)
        self.assertNotIn("background:#0b0f14", SHELL_CSS)
        self.assertNotIn("background:#3b82f6", SHELL_CSS)

    def test_smoke_pages_serve_shell_and_tokens(self):
        client = TestClient(create_app())
        for path in ("/app", "/app/safety", "/app/chat"):
            r = client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("/static/shell.css", r.text, path)
            self.assertIn("/static/shell.js", r.text, path)
        t = client.get("/static/welora-tokens.css")
        self.assertEqual(t.status_code, 200)
        self.assertIn("--color-danger: #E85D5D", t.text)
        self.assertIn("--gold-500: #D4AF37", t.text)
        css = client.get("/static/shell.css")
        self.assertEqual(css.status_code, 200)
        self.assertIn("welora-tokens.css", css.text)

    def test_hard_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        b = TestClient(create_app()).get("/health").json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        # chrome-only: shell.js gate wiring still present
        self.assertIn("gate: true", SHELL_JS)
        self.assertIn("safety-gate", SHELL_JS)


if __name__ == "__main__":
    unittest.main()
