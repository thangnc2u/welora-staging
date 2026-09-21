"""P2 hotfix — gold CTA getComputedStyle must resolve navy #121A28, never link #E8C86A."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
SHELL = (STATIC / "shell.css").read_text(encoding="utf-8")
SHELL_JS = (STATIC / "shell.js").read_text(encoding="utf-8")

NAVY = "#121A28"
LINK = "#E8C86A"
DANGER = "#E85D5D"
GOLD = "#D4AF37"

FORCE_SELECTORS = (
    "a.btn-primary",
    "a.cta.btn-primary",
    ".tabs a.on",
    "a#ctaGateChat",
    "a#osNudge",
    "a#ctaAcademy",
    "a#ctaConstitution",
)


class TestP2HotfixGoldCtaComputedColor(unittest.TestCase):
    def test_force_navy_important_block(self):
        block_idx = SHELL.find("/* Gold CTA <a>")
        self.assertGreaterEqual(block_idx, 0)
        block = SHELL[block_idx : block_idx + 900]
        for sel in FORCE_SELECTORS:
            self.assertIn(sel, block, msg=sel)
        self.assertIn("!important", block)
        self.assertIn(f"var(--cta-primary-text, {NAVY})", block)
        self.assertIn(NAVY, block)
        # Must not paint link/cream onto gold CTAs
        decl = block.split("{", 1)[-1] if "{" in block else block
        self.assertNotIn("var(--link", decl)
        self.assertNotIn(LINK, decl)

    def test_link_rule_deflated_no_id_not(self):
        """ID inside :not(#weloraBottomNav a) previously beat CTA navy color."""
        link_sel = [ln for ln in SHELL.splitlines() if ln.startswith(".welora-shell a:not(")]
        self.assertTrue(link_sel)
        self.assertNotIn("#weloraBottomNav", link_sel[0])
        link_lines = [ln for ln in SHELL.splitlines() if "welora-shell a:not(" in ln]
        self.assertTrue(link_lines)
        rule = link_lines[0]
        for cls in (".btn-primary", ".cta", ".welora-btn-primary", ".on", ".btn"):
            self.assertIn(f":not({cls})", rule)

    def test_shell_js_no_color_injection(self):
        # shell.js must not set style.color / inject link gold onto CTAs
        self.assertNotIn("style.color", SHELL_JS)
        self.assertNotIn("E8C86A", SHELL_JS)
        self.assertNotIn("setProperty", SHELL_JS)
        self.assertIn('classList.add("welora-shell")', SHELL_JS)

    def test_bottom_nav_gold_navy_pattern_kept(self):
        block = SHELL[SHELL.find("#weloraBottomNav a.on{") :][:220]
        self.assertIn("var(--text-on-gold", block)
        self.assertIn(NAVY, block)
        self.assertIn("var(--cta-primary", block)
        # Bottom-nav must not be forced by the CTA !important block onto wrong colors
        self.assertIn("#weloraBottomNav a.on{", SHELL)

    def test_deny_danger_red_untouched(self):
        self.assertIn(DANGER, SHELL)
        self.assertIn("var(--color-danger", SHELL)
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        deny = chat.split("#denyCta{")[1][:200]
        self.assertIn("--danger-", deny)
        self.assertNotIn("cta-primary", deny)

    def test_markup_classes_and_ids_present(self):
        content = (STATIC / "content.html").read_text(encoding="utf-8")
        self.assertIn('id="ctaAcademy" class="cta btn-primary"', content)
        self.assertIn('id="ctaConstitution" class="cta btn-primary"', content)
        academy = (STATIC / "academy.html").read_text(encoding="utf-8")
        self.assertIn('id="osNudge" class="btn-primary"', academy)
        safety = (STATIC / "safety.html").read_text(encoding="utf-8")
        self.assertIn('id="ctaGateChat" class="btn-primary"', safety)
        for name in ("login.html", "register.html"):
            html = (STATIC / name).read_text(encoding="utf-8")
            self.assertIn(".tabs a.on{", html)
            self.assertIn("var(--cta-primary-text", html.split(".tabs a.on{")[1][:220])

    def test_served_css_and_health_gate(self):
        client = TestClient(create_app())
        shell = client.get("/static/shell.css")
        self.assertEqual(shell.status_code, 200)
        body = shell.text
        self.assertIn("!important", body)
        for sel in FORCE_SELECTORS:
            self.assertIn(sel, body, msg=sel)
        link_sel = [ln for ln in body.splitlines() if ln.startswith(".welora-shell a:not(")]
        self.assertTrue(link_sel)
        self.assertNotIn("#weloraBottomNav", link_sel[0])
        self.assertIn("#weloraBottomNav a.on{", body)
        self.assertIn(NAVY, body)
        # pages still wire tokens + shell
        for path in ("/app/content", "/app/login", "/app/register", "/app/academy", "/app/safety"):
            r = client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("shell.css", r.text, path)
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])

    def test_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        gate = (ROOT / "welora" / "safety_gate.py").read_text(encoding="utf-8")
        self.assertIn("TARGET_MONTHS", gate)
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        self.assertIn("modeC", chat)
        self.assertIn("L-COOL-OFF", chat)
        found_r = False
        for p in (ROOT / "welora").rglob("*.py"):
            txt = p.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"\bR0[1-9]\b", txt):
                found_r = True
                break
        self.assertTrue(found_r, "Hard Deny R01–R09 markers missing")
        self.assertTrue((STATIC / "family_context.js").is_file())
        self.assertTrue((STATIC / "form_locks.js").is_file())


if __name__ == "__main__":
    unittest.main()
