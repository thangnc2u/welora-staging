"""P2 UI hotfix — residual gold CTA / danger deny after #198 live FAIL."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"

BLUE = ("#3b82f6", "#1d4ed8", "#7dd3fc", "#38bdf8")
DENY_WRONG = ("#ff6b6b", "#2a2410")


class TestP2UiGoldNavyHotfixResidual(unittest.TestCase):
    def test_demo_primary_gold_tokens_shell_btn_primary(self):
        demo = (STATIC / "demo.html").read_text(encoding="utf-8")
        self.assertIn("/static/welora-tokens.css", demo)
        self.assertIn("/static/shell.css", demo)
        self.assertIn('class="btn-primary"', demo)
        self.assertIn("Chạy demo", demo)
        self.assertIn("var(--cta-primary", demo)
        self.assertIn("#D4AF37", demo)
        low = demo.lower()
        for h in BLUE:
            self.assertNotIn(h, low)
        self.assertNotIn("#ff6b6b", low)
        self.assertIn("var(--color-danger", demo)

    def test_academy_primary_gold_not_blue(self):
        academy = (STATIC / "academy.html").read_text(encoding="utf-8")
        self.assertIn("/static/welora-tokens.css", academy)
        self.assertIn("/static/shell.css", academy)
        self.assertIn('class="btn-primary"', academy)
        self.assertIn("var(--cta-primary", academy)
        low = academy.lower()
        for h in BLUE:
            self.assertNotIn(h, low)
        # primary button rule resolves gold
        self.assertRegex(
            academy,
            r"button,\s*\.btn-primary\{[^}]*background:var\(--cta-primary",
        )

    def test_safety_chua_dat_gate_fail_danger_not_olive(self):
        safety = (STATIC / "safety.html").read_text(encoding="utf-8")
        self.assertIn("CHƯA ĐẠT", safety)
        fail = safety.split(".badge-card.fail")[1][:240]
        self.assertIn("--danger-", fail)
        self.assertNotIn("color-warning", fail)
        self.assertNotIn("#2a2410", fail.lower())
        check = safety.split(".check-item.fail")[1][:180]
        self.assertIn("--danger-", check)
        self.assertNotIn("#2a2410", check.lower())
        note = safety.split(".hs-note{")[1][:220]
        self.assertIn("--danger-", note)
        self.assertNotIn("#2a2410", note.lower())
        self.assertNotIn("color-warning", note)
        low = safety.lower()
        for h in BLUE:
            self.assertNotIn(h, low)

    def test_chat_unlock_wall_border_and_cta_danger(self):
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        self.assertIn("Cổng An Toàn chưa đạt", chat)
        wall = chat.split("#unlockWall{")[1][:300]
        self.assertIn("--danger-", wall)
        self.assertIn("#E85D5D", wall)
        self.assertNotIn("color-warning", wall)
        cta = chat.split("#unlockCtaSafety{")[1][:280]
        self.assertIn("--color-danger", cta)
        self.assertIn("#E85D5D", cta)
        self.assertNotIn("cta-primary", cta)
        deny = chat.split("#denyCta{")[1][:200]
        self.assertIn("--danger-", deny)
        self.assertNotIn("cta-primary", deny)

    def test_content_cta_gold_optional_p1(self):
        content = (STATIC / "content.html").read_text(encoding="utf-8")
        self.assertIn("/static/welora-tokens.css", content)
        cta = content.split(".cta")[1][:320]
        self.assertIn("--cta-primary", cta)
        self.assertIn("#D4AF37", cta)
        low = content.lower()
        for h in BLUE:
            self.assertNotIn(h, low)

    def test_served_pages_tokens_and_no_blue(self):
        client = TestClient(create_app())
        for path in ("/app/demo", "/app/academy", "/app/safety", "/app/chat", "/app/content"):
            r = client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("welora-tokens.css", r.text, path)
            low = r.text.lower()
            for h in BLUE:
                self.assertNotIn(h, low, msg=f"{path} has {h}")
            for h in DENY_WRONG:
                if path in ("/app/demo", "/app/safety", "/app/chat"):
                    self.assertNotIn(h, low, msg=f"{path} has {h}")
        demo = client.get("/app/demo").text
        self.assertIn("btn-primary", demo)
        self.assertIn("shell.css", demo)
        chat = client.get("/app/chat").text
        unlock = chat.split("#unlockCtaSafety{")[1][:280]
        self.assertIn("--color-danger", unlock)
        self.assertNotIn("cta-primary", unlock)
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])

    def test_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        # Hard Deny / CORE markers remain in tree
        gate = (ROOT / "welora" / "safety_gate.py").read_text(encoding="utf-8")
        self.assertIn("TARGET_MONTHS", gate)
        self.assertEqual(TARGET_MONTHS, 3)
        chat = (STATIC / "chat.html").read_text(encoding="utf-8")
        self.assertIn("modeC", chat)
        self.assertIn("L-COOL-OFF", chat)
        # R01–R09 not stripped from product surface
        deny_mod = ROOT / "welora"
        found_r = False
        for p in deny_mod.rglob("*.py"):
            txt = p.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"\bR0[1-9]\b", txt):
                found_r = True
                break
        self.assertTrue(found_r, "Hard Deny R01–R09 markers missing")


if __name__ == "__main__":
    unittest.main()
