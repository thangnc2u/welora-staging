"""P2 UI — normalize gold/navy chrome across app (tokens only; no logic)."""

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

BLUE_HEX = ("#3b82f6", "#1d4ed8", "#7dd3fc", "#38bdf8")
BROWN_OLIVE = ("#2a2410", "#14532d", "#065f46", "#9a3412", "#7f1d1d")

CARD_PAGES = (
    "onboarding.html",
    "dna.html",
    "goals.html",
    "constitution.html",
    "healthscore.html",
    "dual-control.html",
    "login.html",
    "register.html",
)


def _prop(name: str) -> str:
    m = re.search(rf"--{re.escape(name)}:\s*(#[0-9A-Fa-f]{{6}})", TOKENS)
    assert m, f"missing CSS var --{name}"
    return m.group(1).upper()


class TestP2UiGoldNavyNormalize(unittest.TestCase):
    def test_sot_tokens_gold_navy_danger_success(self):
        self.assertEqual(_prop("bg-app"), "#121A28")
        self.assertEqual(_prop("gold-500"), "#D4AF37")
        self.assertEqual(_prop("text-primary"), "#F4F1E8")
        self.assertEqual(_prop("color-danger"), "#E85D5D")
        self.assertEqual(_prop("danger-bg"), "#2A1518")
        self.assertEqual(_prop("success-bg"), "#143028")
        self.assertEqual(_prop("success-text"), "#A8E6C8")
        self.assertNotEqual(_prop("color-danger"), _prop("gold-500"))

    def test_demo_tokens_and_no_blue_cta(self):
        demo = (STATIC / "demo.html").read_text(encoding="utf-8")
        self.assertIn("/static/welora-tokens.css", demo)
        self.assertIn('data-theme="dark"', demo)
        self.assertIn("var(--cta-primary", demo)
        self.assertIn("var(--bg-app", demo)
        self.assertIn("var(--bg-surface", demo)
        self.assertIn("var(--border-default", demo)
        self.assertIn("var(--color-success", demo)
        self.assertIn("var(--color-danger", demo)
        low = demo.lower()
        for h in BLUE_HEX:
            self.assertNotIn(h, low, msg=f"demo still has {h}")

    def test_academy_learn_content_no_sky_blue(self):
        for name in ("academy.html", "content.html"):
            html = (STATIC / name).read_text(encoding="utf-8")
            self.assertIn("/static/welora-tokens.css", html, name)
            self.assertIn('data-theme="dark"', html, name)
            self.assertIn("var(--link", html, name)
            self.assertIn("var(--cta-primary", html, name) if name == "academy.html" else None
            low = html.lower()
            for h in BLUE_HEX:
                self.assertNotIn(h, low, msg=f"{name} still has {h}")

    def test_safety_fail_uses_danger_not_gold_brown(self):
        safety = (STATIC / "safety.html").read_text(encoding="utf-8")
        fail_block = safety.split(".badge-card.fail")[1][:220]
        self.assertIn("--danger-", fail_block)
        self.assertNotIn("color-warning", fail_block)
        self.assertNotIn("#2a2410", fail_block.lower())
        check_fail = safety.split(".check-item.fail")[1][:160]
        self.assertIn("--danger-", check_fail)
        self.assertNotIn("color-warning", check_fail)
        # ok uses success tint
        self.assertIn("var(--success-bg", safety)
        self.assertIn("CHƯA ĐẠT", safety)

    def test_chat_unlock_wall_and_cooloff_danger_undo_success(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        wall = chat.split("#unlockWall{")[1][:280]
        self.assertIn("--danger-", wall)
        self.assertNotIn("color-warning", wall)
        self.assertIn("Cổng An Toàn chưa đạt", chat)
        undo = chat.split("#modeCUndo{")[1][:220]
        self.assertIn("--success-bg", undo)
        self.assertNotIn("#14532d", undo.lower())
        # cool-off stays red family
        self.assertIn("var(--color-danger", chat)
        self.assertIn("var(--danger-bg", chat)
        self.assertNotIn("#7f1d1d", chat.lower())
        # DENY CTA never gold
        deny = chat.split("#denyCta{")[1][:200]
        self.assertIn("--danger-", deny)
        self.assertNotIn("cta-primary", deny)

    def test_goals_badge_done_and_dual_control_msg(self):
        goals = (STATIC / "goals.html").read_text(encoding="utf-8")
        self.assertIn(".badge-done{", goals)
        self.assertIn("var(--success-bg", goals)
        self.assertNotIn("#14532d", goals.lower())
        dual = (STATIC / "dual-control.html").read_text(encoding="utf-8")
        self.assertIn("#msg.ok{", dual)
        self.assertIn("#msg.err{", dual)
        self.assertIn("var(--color-success", dual)
        self.assertIn("var(--color-danger", dual)
        self.assertNotIn("#065f46", dual)
        self.assertNotIn("#9a3412", dual)

    def test_card_text_primary_hex_fallback(self):
        for name in CARD_PAGES:
            html = (STATIC / name).read_text(encoding="utf-8")
            self.assertIn("/static/welora-tokens.css", html, name)
            self.assertRegex(
                html,
                r"\.card\{[^}]*color:var\(--text-primary,\s*#F4F1E8\)",
                msg=f"{name} .card missing --text-primary,#F4F1E8",
            )

    def test_bottom_nav_gold_on_active_deny_not_gold(self):
        self.assertIn("#weloraBottomNav a.on", SHELL_CSS)
        on = SHELL_CSS.split("#weloraBottomNav a.on")[1][:220]
        self.assertIn("var(--cta-primary", on)
        # Hard Deny in shell stays danger
        self.assertIn("var(--color-danger", SHELL_CSS)

    def test_smoke_pages_and_health(self):
        client = TestClient(create_app())
        for path in (
            "/app/demo",
            "/app/academy",
            "/app/learn",
            "/app/content",
            "/app/safety",
            "/app/chat",
            "/app/dual-control",
        ):
            r = client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("welora-tokens.css", r.text, path)
            low = r.text.lower()
            if path in ("/app/demo", "/app/academy", "/app/learn", "/app/content"):
                for h in BLUE_HEX:
                    self.assertNotIn(h, low, msg=f"{path} has {h}")
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])

    def test_hard_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        # Mode C / L-* chrome markers remain (logic not stripped)
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        self.assertIn("modeC", chat)
        self.assertIn("L-COOL-OFF", chat)
        self.assertIn("mode-c", chat.lower())


if __name__ == "__main__":
    unittest.main()
