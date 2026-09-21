"""P2 UAT+Fix — gold CTA <a> text must be navy (#121A28), never link/cream-on-gold."""

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
SHELL = (STATIC / "shell.css").read_text(encoding="utf-8")

NAVY = "#121A28"
GOLD = "#D4AF37"
CREAM = "#F4F1E8"
LINK = "#E8C86A"
DANGER = "#E85D5D"

# Soft / light text colors that fail on gold
_SOFT_ON_GOLD = re.compile(
    rf"color\s*:\s*(?:var\(--(?:link|text-primary)|{re.escape(LINK)}|{re.escape(CREAM)}|#fff(?:fff)?\b|white\b)",
    re.IGNORECASE,
)


def _prop(name: str) -> str:
    m = re.search(rf"--{re.escape(name)}:\s*(#[0-9A-Fa-f]{{6}})", TOKENS)
    assert m, f"missing --{name}"
    return m.group(1).upper()


def _rule_block(css: str, selector_hint: str, window: int = 280) -> str:
    idx = css.find(selector_hint)
    assert idx >= 0, f"missing selector hint {selector_hint!r}"
    return css[idx : idx + window]


class TestP2FixGoldCtaContrast(unittest.TestCase):
    def test_sot_tokens_navy_on_gold(self):
        self.assertEqual(_prop("text-on-gold"), NAVY)
        self.assertEqual(_prop("gold-500"), GOLD)
        self.assertEqual(_prop("text-primary"), CREAM)
        self.assertEqual(_prop("link"), LINK)
        self.assertEqual(_prop("color-danger"), DANGER)
        self.assertIn("--cta-primary-text: var(--text-on-gold)", TOKENS)
        self.assertIn("--cta-primary: var(--gold-500)", TOKENS)

    def test_shell_excludes_gold_cta_anchors_from_link_rule(self):
        # Link rule must not paint gold CTAs / active tabs
        # Hotfix: must NOT use :not(#weloraBottomNav a) — ID-in-:not inflates specificity
        link_sel = [ln for ln in SHELL.splitlines() if ln.startswith(".welora-shell a:not(")]
        self.assertTrue(link_sel)
        self.assertNotIn("#weloraBottomNav", link_sel[0])
        link_line = [
            ln for ln in SHELL.splitlines()
            if "welora-shell a:not(.pillar)" in ln or "welora-shell a:not(.btn" in ln
        ]
        self.assertTrue(link_line, "shell link rule missing")
        rule = link_line[0]
        for cls in (".btn-primary", ".cta", ".welora-btn-primary", ".on"):
            self.assertIn(f":not({cls})", rule, msg=f"link rule must exclude {cls}")
        # Reinforcing navy-on-gold for <a> CTAs (incl. explicit IDs + !important)
        self.assertIn("a.btn-primary", SHELL)
        self.assertIn(".tabs a.on", SHELL)
        self.assertIn("a#ctaGateChat", SHELL)
        self.assertIn("a#osNudge", SHELL)
        self.assertIn("a#ctaAcademy", SHELL)
        self.assertIn("a#ctaConstitution", SHELL)
        block = _rule_block(SHELL, "/* Gold CTA <a>", window=720)
        self.assertIn("var(--cta-primary-text", block)
        self.assertIn(NAVY, block)
        self.assertIn("!important", block)
        # Must not force soft/link color onto gold CTAs in this block
        self.assertNotIn("var(--link", block)
        self.assertNotIn(CREAM, block)

    def test_shell_btn_primary_navy_text_on_gold(self):
        block = _rule_block(SHELL, ".btn-primary,\n.welora-btn-primary{")
        self.assertIn("var(--cta-primary", block)
        self.assertIn("var(--cta-primary-text", block)
        self.assertIn(NAVY, block)
        self.assertNotRegex(block, _SOFT_ON_GOLD)

    def test_shell_bottom_nav_gold_navy_kept(self):
        block = _rule_block(SHELL, "#weloraBottomNav a.on{")
        self.assertIn("var(--text-on-gold", block)
        self.assertIn(NAVY, block)
        self.assertIn("var(--cta-primary", block)

    def test_content_p0_cta_academy_constitution_navy_on_gold(self):
        html = (STATIC / "content.html").read_text(encoding="utf-8")
        self.assertIn('id="ctaAcademy" class="cta btn-primary"', html)
        self.assertIn('id="ctaConstitution" class="cta btn-primary"', html)
        # Author CSS for gold CTAs
        cta = html.split(".cta,.btn-primary{")[1][:320]
        self.assertIn("var(--cta-primary", cta)
        self.assertIn("var(--cta-primary-text", cta)
        self.assertIn(NAVY, cta)
        self.assertNotRegex(cta, _SOFT_ON_GOLD)

    def test_login_register_p0_tabs_on_navy_on_gold(self):
        for name in ("login.html", "register.html"):
            html = (STATIC / name).read_text(encoding="utf-8")
            tabs = html.split(".tabs a.on{")[1][:220]
            self.assertIn("var(--cta-primary", tabs, name)
            self.assertIn("var(--cta-primary-text", tabs, name)
            self.assertIn(NAVY, tabs, name)
            self.assertNotRegex(tabs, _SOFT_ON_GOLD, msg=name)
            self.assertIn('class="on"', html, name)

    def test_academy_p1_osnudge_btn_primary(self):
        html = (STATIC / "academy.html").read_text(encoding="utf-8")
        self.assertIn('id="osNudge" class="btn-primary"', html)
        btn = html.split("button,.btn-primary{")[1][:280]
        self.assertIn("var(--cta-primary", btn)
        self.assertIn("var(--cta-primary-text", btn)
        self.assertIn(NAVY, btn)
        self.assertNotRegex(btn, _SOFT_ON_GOLD)

    def test_safety_p1_ctagatechat_btn_primary_navy(self):
        html = (STATIC / "safety.html").read_text(encoding="utf-8")
        self.assertIn('id="ctaGateChat" class="btn-primary"', html)
        gate = html.split("#ctaGateChat{")[1][:280]
        self.assertIn("var(--cta-primary", gate)
        self.assertIn("var(--cta-primary-text", gate)
        self.assertIn(NAVY, gate)
        self.assertNotRegex(gate, _SOFT_ON_GOLD)
        # Checklist text links stay link-colored (not gold-bg CTAs)
        check = html.split(".check-item a.cta{")[1][:160]
        self.assertIn("var(--link", check)

    def test_deny_danger_stays_red(self):
        self.assertIn("var(--color-danger", SHELL)
        self.assertIn(DANGER, SHELL)
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        deny = chat.split("#denyCta{")[1][:200]
        self.assertIn("--danger-", deny)
        self.assertNotIn("cta-primary", deny)
        unlock = chat.split("#unlockCtaSafety{")[1][:280]
        self.assertIn("--color-danger", unlock)
        self.assertIn(DANGER, unlock)

    def test_served_pages_and_health_gate(self):
        client = TestClient(create_app())
        for path in (
            "/app/content",
            "/app/login",
            "/app/register",
            "/app/academy",
            "/app/safety",
        ):
            r = client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("welora-tokens.css", r.text, path)
            self.assertIn("shell.css", r.text, path)
        shell = client.get("/static/shell.css")
        self.assertEqual(shell.status_code, 200)
        self.assertIn(":not(.btn-primary)", shell.text)
        self.assertIn(":not(.cta)", shell.text)
        self.assertIn("a.btn-primary", shell.text)
        self.assertIn(".tabs a.on", shell.text)
        content = client.get("/app/content").text
        self.assertIn('id="ctaAcademy" class="cta btn-primary"', content)
        self.assertIn('id="ctaConstitution" class="cta btn-primary"', content)
        safety = client.get("/app/safety").text
        self.assertIn('id="ctaGateChat" class="btn-primary"', safety)
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
        # family_context / form locks still present
        self.assertTrue((STATIC / "family_context.js").is_file())
        self.assertTrue((STATIC / "form_locks.js").is_file())


if __name__ == "__main__":
    unittest.main()
