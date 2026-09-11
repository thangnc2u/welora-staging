"""P2 UAT — agent P3: pre-pass greeting + R05 VI + chat unlock wall."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.agent import (
    CONFIDENCE_THRESHOLD,
    DENY_TEMPLATES,
    HARD,
    PRIORITY,
    TARGET_MONTHS as AGENT_TARGET,
    evaluate_pre_rules,
)
from welora.api.app import create_app
from welora.chat_service import reset_logs, service_chat
from welora.fixtures import load_pair, reset_all_stores
from welora.mastery import NODE_NO_EFUND
from welora.pre_rule_service import context_from_seed
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "welora" / "api" / "static" / "chat.html"
SHELL = ROOT / "welora" / "api" / "static" / "shell.js"
HOME = ROOT / "welora" / "api" / "static" / "home.html"


class TestP2UatAgentP3Polish(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        reset_all_stores()
        reset_logs()
        cls.pair = load_pair()
        cls.html = CHAT.read_text(encoding="utf-8")
        cls.shell = SHELL.read_text(encoding="utf-8")
        cls.home = HOME.read_text(encoding="utf-8")

    def setUp(self) -> None:
        self.client = TestClient(create_app())

    # --- (1) pre-pass greeting richer than bare «Sẵn sàng»; post-pass chips kept ---
    def test_pre_pass_greeting_richer_than_bare_san_sang(self):
        html = self.html
        self.assertNotIn("add('Sẵn sàng'", html)
        self.assertNotIn('add("Sẵn sàng"', html)
        self.assertIn("GREETING_PRE", html)
        self.assertIn("GREETING_POST", html)
        self.assertIn("Cổng An Toàn chưa đạt", html)
        self.assertIn("Từ chối cứng", html)
        self.assertGreater(len("Cổng An Toàn chưa đạt. Hoàn thành Cổng trước khi chat. Từ chối cứng vẫn áp dụng trước tư vấn."), len("Sẵn sàng"))
        self.assertIn("add(GREETING_PRE", html)
        self.assertIn("add(GREETING_POST", html)
        # post-pass chips from #175 still present; only shown when passed
        self.assertIn("POST_PASS_CHIPS", html)
        self.assertIn("showPostPassChips", html)
        self.assertIn("Quỹ khẩn cấp nên giữ thế nào?", html)
        self.assertIn("Tiền dư sau An Toàn dùng ra sao?", html)
        self.assertIn("if(gate && gate.status==='passed')", html)
        self.assertIn("showPostPassChips()", html)
        # no fake passed: post-pass chips not shown on pre-pass path
        pre_idx = html.index("showUnlockWall();")
        pre_block = html[pre_idx : pre_idx + 180]
        self.assertNotIn("showPostPassChips", pre_block)
        self.assertNotIn("innerHTML", html)

    def test_optional_pre_pass_chips_do_not_fake_passed(self):
        html = self.html
        self.assertIn('id="prePassChips"', html)
        # pre-pass chips are links to safety/onboarding — not POST_PASS_CHIPS
        pre_start = html.index('id="prePassChips"')
        pre_end = html.index("</div>", html.index("<a href=\"/app/onboarding\">Thiết lập Hiến pháp</a>"))
        pre = html[pre_start:pre_end]
        self.assertIn('href="/app/safety"', pre)
        self.assertIn('href="/app/onboarding"', pre)
        self.assertNotIn("Quỹ khẩn cấp nên giữ thế nào?", pre)
        self.assertNotIn("Tiền dư sau An Toàn dùng ra sao?", pre)
        self.assertNotIn("status==='passed'", pre)

    # --- (2) R05 DENY_TEMPLATES VI; id/logic unchanged ---
    def test_r05_deny_template_vi_no_fomo(self):
        body = DENY_TEMPLATES["R05"]
        self.assertNotIn("FOMO", body)
        self.assertNotIn("fomo", body.lower())
        self.assertIn("nỗi sợ bỏ lỡ", body)
        self.assertIn("Cảm xúc", body)
        self.assertIn("chắc lời", body)
        self.assertIn("R05", HARD)
        self.assertIn("R05", PRIORITY)
        self.assertEqual(PRIORITY[-1], "R05")

        seed = dict(self.pair["not_passed"]["agent_context_seed"])
        code, out = service_chat(
            user_id=seed["user_id"],
            message="Cam kết giúp tôi chắc lời 20% mỗi năm nhé",
            context_seed=seed,
        )
        self.assertEqual(code, 200)
        self.assertEqual(out.get("guardrail_result"), "deny")
        self.assertEqual(out.get("rule_id") or out.get("rule_hit"), "R05")
        reply = out.get("reply") or ""
        self.assertNotIn("FOMO", reply)
        self.assertIn("nỗi sợ bỏ lỡ", reply)
        self.assertIn("Cảm xúc", reply)
        self.assertIn("CORE-05", out.get("principle_keys") or [])
        self.assertFalse(out.get("llm_called"))
        self.assertEqual(out.get("model_used"), "rule_only")

        # detect logic / keywords unchanged — still deny on passed gate too
        passed = dict(self.pair["passed"]["agent_context_seed"])
        ctx = context_from_seed(passed)
        pre = evaluate_pre_rules("Cam kết giúp tôi chắc lời 20% mỗi năm nhé", ctx)
        self.assertEqual(pre.result, "deny")
        self.assertEqual(pre.primary_hit.rule_id, "R05")
        self.assertFalse(pre.should_call_llm)

    # --- (3) direct /app/chat unlock wall; shell Chat tab still gated ---
    def test_chat_unlock_wall_vi_cta(self):
        html = self.html
        self.assertIn('id="unlockWall"', html)
        self.assertIn("function showUnlockWall", html)
        self.assertIn("function hideUnlockWall", html)
        self.assertIn('id="unlockCtaSafety"', html)
        self.assertIn('href="/app/safety"', html)
        self.assertIn("Mở Cổng An Toàn", html)
        self.assertIn('id="unlockCtaOnboard"', html)
        self.assertIn('href="/app/onboarding"', html)
        self.assertIn("Bắt đầu · Hiến pháp", html)
        self.assertIn('id="f" hidden', html)
        self.assertIn("chatForm.hidden=true", html)
        self.assertIn("chatForm.hidden=false", html)
        # show wall when not passed / fetch error — never fake passed
        self.assertIn("showUnlockWall();", html)
        self.assertIn("hideUnlockWall();", html)
        r = self.client.get("/app/chat")
        self.assertEqual(r.status_code, 200)
        self.assertIn('id="unlockWall"', r.text)
        self.assertIn("Mở Cổng An Toàn", r.text)
        self.assertIn("/app/safety", r.text)
        self.assertIn("/app/onboarding", r.text)
        self.assertNotIn('id="gateBadge"', r.text)

    def test_shell_chat_tab_still_hidden_until_passed(self):
        self.assertIn('id: "tabChat"', self.shell)
        self.assertIn("gate: true", self.shell)
        self.assertIn("a.hidden = true", self.shell)
        self.assertIn('chatLink.hidden = st !== "passed"', self.shell)
        self.assertIn('id="navChat" href="/app/chat" hidden', self.home)
        self.assertIn("navChat.hidden=!passed", self.home)

    # --- (4) optional RuleHit.reason R02/R08 VI ---
    def test_rulehit_reason_r02_r08_vi(self):
        seed = dict(self.pair["not_passed"]["agent_context_seed"])
        ctx = context_from_seed(seed)
        r02 = evaluate_pre_rules("Có nên bắt đầu DCA vào ETF ngay không?", ctx)
        self.assertEqual(r02.result, "deny")
        self.assertEqual(r02.primary_hit.rule_id, "R02")
        self.assertNotIn("Passed", r02.primary_hit.reason)
        self.assertIn("chưa đạt", r02.primary_hit.reason)

        r08 = evaluate_pre_rules("Mở Stage 3 giúp tôi", ctx)
        self.assertEqual(r08.result, "deny")
        self.assertEqual(r08.primary_hit.rule_id, "R08")
        self.assertNotIn("Passed", r08.primary_hit.reason)
        self.assertNotIn("Stage 3", r08.primary_hit.reason)
        self.assertIn("Giai đoạn 3", r08.primary_hit.reason)
        self.assertIn("chưa đạt", r08.primary_hit.reason)

    # --- hard constraints held ---
    def test_hard_deny_ids_gate_months_mastery_confidence_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(AGENT_TARGET, 3)
        self.assertEqual(CONFIDENCE_THRESHOLD, 0.80)
        self.assertEqual(
            set(HARD),
            {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"},
        )
        self.assertEqual(
            PRIORITY,
            ["R01", "R03", "R02", "R08", "R09", "R06", "R07", "R04", "R05"],
        )
        self.assertEqual(NODE_NO_EFUND, "no_efund_invest")
        b = self.client.get("/health").json()
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        # #175 / #179 hygiene still in chat.html
        self.assertIn("function stripMdMarkers", self.html)
        self.assertIn("function isLeakyHref", self.html)
        self.assertIn("function pickHref", self.html)
        self.assertIn("Đọc nguyên tắc An Toàn", self.html)


if __name__ == "__main__":
    unittest.main()
