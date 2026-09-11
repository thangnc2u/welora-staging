"""P2 UAT-B — shell chrome polish: bottom Chat gate, VI copy, hide raw keys."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
SHELL_JS = (STATIC / "shell.js").read_text(encoding="utf-8")
HOME = (STATIC / "home.html").read_text(encoding="utf-8")
GOALS = (STATIC / "goals.html").read_text(encoding="utf-8")
CORE = (STATIC / "core-constitution.html").read_text(encoding="utf-8")
SAFETY = (STATIC / "safety.html").read_text(encoding="utf-8")
CHAT = (STATIC / "chat.html").read_text(encoding="utf-8")
ACADEMY = (STATIC / "academy.html").read_text(encoding="utf-8")
CONST = (STATIC / "constitution.html").read_text(encoding="utf-8")
CONTENT = (STATIC / "content.html").read_text(encoding="utf-8")


class TestP2UatBShellChromePolish(unittest.TestCase):
    def test_bottom_nav_chat_gated_like_nav_chat(self):
        # #navChat (home) — PR #171 pattern
        self.assertIn('id="navChat" href="/app/chat" hidden', HOME)
        self.assertIn("navChat.hidden=!passed", HOME)
        # #weloraBottomNav Chat tab — default hidden until gate passed
        self.assertIn('id: "tabChat"', SHELL_JS)
        self.assertIn("gate: true", SHELL_JS)
        self.assertIn("a.hidden = true", SHELL_JS)
        self.assertIn("chatLink.hidden = st !== \"passed\"", SHELL_JS)
        self.assertIn("/safety-gate", SHELL_JS)
        self.assertIn("weloraBottomNav", SHELL_JS)

    def test_learner_pages_with_bottom_nav_load_shell(self):
        client = TestClient(create_app())
        for path, tab in (
            ("/app", "home"),
            ("/app/content", "pedia"),
            ("/app/chat", "chat"),
            ("/app/academy", "academy"),
            ("/app/goals", "home"),  # goals maps to home active
            ("/app/safety", "home"),
        ):
            r = client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("/static/shell.js", r.text, path)
            self.assertIn('data-shell-tab="%s"' % tab, r.text, path)

    def test_goals_fill_pedia_no_raw_key_flash(self):
        self.assertIn("function fillPedia", GOALS)
        # never assign raw key to visible title / error
        self.assertNotIn("t.textContent=key;", GOALS)
        self.assertNotIn("t.textContent=d.title||key;", GOALS)
        self.assertNotIn("Chưa có bài cho '+key", GOALS)
        self.assertNotIn('Chưa có bài cho "+key', GOALS)
        self.assertIn("t.textContent='Đang tải…';", GOALS)
        self.assertIn("t.textContent=d.title||'Bài học';", GOALS)
        self.assertIn("ex.textContent='Chưa có bài.';", GOALS)
        # href?key= still OK (API path)
        self.assertIn("/app/content?key=", GOALS)
        self.assertIn("SAFE-01", GOALS)  # keys in pediaKeys map only

    def test_core_constitution_no_raw_codes_in_chrome(self):
        self.assertIn("10 Nguyên lý Bất biến · Welorademy", CORE)
        self.assertNotIn("CORE-01 … CORE-10", CORE)
        self.assertNotIn("c.textContent=a.code", CORE)
        self.assertNotIn("el.appendChild(c);", CORE)
        # served page likewise
        r = TestClient(create_app()).get("/app/core-constitution")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("CORE-01 … CORE-10", r.text)
        self.assertNotRegex(r.text, r"CORE-0[1-9].*CORE-10")

    def test_vi_chat_labels(self):
        for blob, where in ((SHELL_JS, "shell.js"), (CHAT, "chat.html"), (HOME, "home.html")):
            self.assertIn("Chat với Agent", blob, where)
            self.assertNotIn("Chat with Agent", blob, where)
            self.assertNotIn("Trợ lý AI", blob, where)
        self.assertIn("<title>Welora · Chat với Agent</title>", CHAT)
        self.assertIn("<h1>Chat với Agent</h1>", CHAT)

    def test_cta_goal_to_muc_tieu(self):
        self.assertIn("Tạo mục tiêu trên WeloraOS", ACADEMY)
        self.assertNotIn("Tạo Goal trên WeloraOS", ACADEMY)
        self.assertIn("Tạo mục tiêu quỹ khẩn cấp trên WeloraOS", CONST)
        self.assertNotIn("Tạo Goal quỹ khẩn cấp trên WeloraOS", CONST)

    def test_home_demo_prerule_learner_hidden_or_vi(self):
        self.assertIn('class="nav dev-only" id="navDemo"', HOME)
        self.assertIn("Xem thử 8 bước", HOME)
        self.assertIn("Quy tắc trước · gỡ lỗi", HOME)
        self.assertIn('class="nav dev-only" id="navPreRule"', HOME)
        self.assertNotIn(">Demo 8 bước<", HOME)
        self.assertNotIn(">Pre-Rule · gỡ lỗi<", HOME)

    def test_donut_aria_vi(self):
        self.assertIn('aria-label="Biểu đồ vòng điểm sức khỏe từ 0 đến 1000"', HOME)
        self.assertNotIn("Donut điểm", HOME)

    def test_content_error_vi(self):
        self.assertIn("elTitle.textContent='Không tải được'", CONTENT)
        self.assertIn("elBody.textContent='Vui lòng thử lại.'", CONTENT)
        self.assertNotIn("elTitle.textContent='Lỗi'", CONTENT)

    def test_goals_tab_active_maps_home(self):
        self.assertIn('data-shell-tab="home"', GOALS)
        self.assertNotIn('data-shell-tab="goals"', GOALS)
        self.assertIn('forced === "goals"', SHELL_JS)
        self.assertIn('active = "home"', SHELL_JS)

    def test_shell_on_safety(self):
        self.assertIn("/static/shell.js", SAFETY)
        self.assertIn('data-shell-tab="home"', SAFETY)
        self.assertIn("/static/shell.css", SAFETY)
        r = TestClient(create_app()).get("/app/safety")
        self.assertEqual(r.status_code, 200)
        self.assertIn("/static/shell.js", r.text)

    def test_welora_dot_titles_aligned(self):
        for name in ("constitution.html", "dna.html", "otp.html"):
            html = (STATIC / name).read_text(encoding="utf-8")
            self.assertTrue(
                re.search(r"<title>Welora · ", html),
                msg="%s missing Welora · title" % name,
            )

    def test_hard_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        # GATE mastery node still present in safety chrome
        self.assertIn("no_efund_invest", SAFETY)


if __name__ == "__main__":
    unittest.main()
