"""P2 UI — hot fix contrast navy/gold (chrome only; ban black text on dark)."""

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

SCOPE_PAGES = (
    "home.html",
    "safety.html",
    "chat.html",
    "goals.html",
    "dna.html",
    "onboarding.html",
    "constitution.html",
    "healthscore.html",
    "dual-control.html",
)

# Text-color declarations that paint black / near-black on dark surfaces
_BAD_TEXT_COLOR = re.compile(
    r"color\s*:\s*(?:#000(?:000)?\b|black\b|#0a0a0a\b|#111(?:111)?\b|#1a1a1a\b|#222(?:222)?\b)",
    re.IGNORECASE,
)


def _prop(name: str) -> str:
    m = re.search(rf"--{re.escape(name)}:\s*(#[0-9A-Fa-f]{{6}})", TOKENS)
    assert m, f"missing CSS var --{name}"
    return m.group(1).upper()


class TestP2UiContrastNavyGold(unittest.TestCase):
    def test_sot_tokens_unchanged_navy_gold_danger(self):
        self.assertEqual(_prop("text-primary"), "#F4F1E8")
        self.assertEqual(_prop("text-secondary"), "#A8B0C0")
        self.assertEqual(_prop("text-muted"), "#6B7588")
        self.assertEqual(_prop("text-on-gold"), "#121A28")
        self.assertEqual(_prop("bg-app"), "#121A28")
        self.assertEqual(_prop("bg-surface"), "#1A2536")
        self.assertEqual(_prop("bg-elevated"), "#243044")
        self.assertEqual(_prop("gold-500"), "#D4AF37")
        self.assertEqual(_prop("color-danger"), "#E85D5D")
        self.assertEqual(_prop("border-focus"), "#E8C86A")
        self.assertNotEqual(_prop("color-danger"), _prop("gold-500"))

    def test_shell_light_text_on_navy_and_gold_cta(self):
        self.assertIn("var(--text-primary", SHELL_CSS)
        self.assertIn("var(--bg-app", SHELL_CSS)
        self.assertIn("var(--cta-primary", SHELL_CSS)
        self.assertIn("var(--color-danger", SHELL_CSS)
        # Active tab = gold, not blue
        self.assertIn("#weloraBottomNav a.on", SHELL_CSS)
        self.assertIn("var(--cta-primary", SHELL_CSS.split("#weloraBottomNav a.on")[1][:200])
        self.assertNotIn("background:#3b82f6", SHELL_CSS)
        self.assertNotIn("color:#000", SHELL_CSS.lower())
        self.assertNotIn("color:black", SHELL_CSS.lower())

    def test_scope_pages_no_black_text_color(self):
        for name in SCOPE_PAGES:
            html = (STATIC / name).read_text(encoding="utf-8")
            bad = _BAD_TEXT_COLOR.findall(html)
            self.assertEqual(bad, [], msg=f"{name} has black/near-black text color: {bad}")
            self.assertIn("/static/welora-tokens.css", html, name)
            self.assertIn("/static/shell.css", html, name)
            self.assertIn('data-theme="dark"', html, name)
            # Cards / body use light primary text token
            self.assertIn("--text-primary", html, name)

    def test_safety_checklist_contrast(self):
        safety = (STATIC / "safety.html").read_text(encoding="utf-8")
        self.assertIn(".check-item{", safety)
        self.assertIn("color:var(--text-primary", safety)
        self.assertIn(".check-label{", safety)
        self.assertIn("Checklist cổng", safety)
        self.assertNotRegex(safety, r"color\s*:\s*#000", msg="safety must not use #000 text")

    def test_smoke_serve_tokens_and_pages(self):
        client = TestClient(create_app())
        for path in ("/app", "/app/safety", "/app/chat"):
            r = client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("/static/welora-tokens.css", r.text, path)
            self.assertIn("/static/shell.css", r.text, path)
            self.assertIn('data-theme="dark"', r.text, path)
        t = client.get("/static/welora-tokens.css")
        self.assertEqual(t.status_code, 200)
        self.assertIn("--gold-500: #D4AF37", t.text)
        self.assertIn("--color-danger: #E85D5D", t.text)
        self.assertIn("--text-primary: #F4F1E8", t.text)

    def test_hard_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        b = TestClient(create_app()).get("/health").json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        # chrome-only: gate wiring in shell.js unchanged
        self.assertIn("gate: true", SHELL_JS)
        self.assertIn("safety-gate", SHELL_JS)
        # Mode C markers still present in chat (logic not stripped)
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        self.assertIn("modeC", chat)
        self.assertIn("#denyCta", chat)
        self.assertIn("var(--color-danger", chat)


if __name__ == "__main__":
    unittest.main()
