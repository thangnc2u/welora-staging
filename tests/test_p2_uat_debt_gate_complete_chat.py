"""P2 UAT — debt gate complete-only + /app navChat gated + chat deny VI labels."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

HOME = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "home.html"
CHAT = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "chat.html"
SAFETY = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "safety.html"


class TestP2UatDebtGateCompleteChat(unittest.TestCase):
    def test_nav_chat_hidden_until_gate_passed(self):
        home = HOME.read_text(encoding="utf-8")
        self.assertIn('id="navChat"', home)
        self.assertIn('id="navChat" href="/app/chat" hidden', home)
        self.assertIn("navChat.hidden=!passed", home)
        safety = SAFETY.read_text(encoding="utf-8")
        self.assertIn("chat.hidden=!passed", safety)
        self.assertIn('id="ctaGateChat"', safety)

    def test_chat_deny_cta_vi_no_raw_keys_in_label(self):
        html = CHAT.read_text(encoding="utf-8")
        self.assertIn('id="denyCta"', html)
        self.assertIn('href="/app/safety"', html)  # learner href: no SAFE-/CORE- leak
        self.assertNotIn("/app/content?key=SAFE-02", html)
        self.assertIn("Đọc nguyên tắc An Toàn", html)
        self.assertNotIn("Đọc nguyên tắc An Toàn (SAFE-02)", html)
        self.assertNotIn("href.replace('/app/content?key=','')", html)
        self.assertNotIn('href.replace("/app/content?key=","")', html)
        self.assertIn("pickDenyLabel", html)
        self.assertIn("L.title", html)
        # Static + JS labels must not concatenate raw SAFE-/CORE- keys
        self.assertNotIn("(SAFE-", html)
        self.assertNotIn("(CORE-", html)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
