"""P2 hotfix — fleet-wide friendly UI (VN labels + hide snake/tech IDs).

UI/labels/copy ONLY. Does not touch Hard Deny R01–R09 · TARGET_MONTHS /
gate_months · Pre-Rule · Open Banking API · Investments · pillar 4/Agent ·
Goals API · dual-control/API identity logic.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("WELORA_STORE", "memory")

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.fixtures import reset_all_stores
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"

LABELS_JS = (STATIC / "friendly_labels.js").read_text(encoding="utf-8")
CATEGORIES_HTML = (STATIC / "categories.html").read_text(encoding="utf-8")
BUDGET_HTML = (STATIC / "budget.html").read_text(encoding="utf-8")
FORGOT_HTML = (STATIC / "forgot-password.html").read_text(encoding="utf-8")
RESET_HTML = (STATIC / "reset-password.html").read_text(encoding="utf-8")
ACADEMY_HTML = (STATIC / "academy.html").read_text(encoding="utf-8")
DUAL_HTML = (STATIC / "dual-control.html").read_text(encoding="utf-8")
CHAT_HTML = (STATIC / "chat.html").read_text(encoding="utf-8")
DEMO_HTML = (STATIC / "demo.html").read_text(encoding="utf-8")
TX_HTML = (STATIC / "transactions.html").read_text(encoding="utf-8")
PARSER_HTML = (STATIC / "parser.html").read_text(encoding="utf-8")
ONBOARD_HTML = (STATIC / "onboarding.html").read_text(encoding="utf-8")
LOGIN_HTML = (STATIC / "login.html").read_text(encoding="utf-8")


def _option_texts(html: str) -> list[str]:
    return re.findall(r"<option\b[^>]*>(.*?)</option>", html, flags=re.I | re.S)


def _label_texts(html: str) -> list[str]:
    return re.findall(r"<label\b[^>]*>(.*?)</label>", html, flags=re.I | re.S)


class TestP2HotfixFleetFriendlyUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def setUp(self) -> None:
        reset_all_stores()

    def test_friendly_labels_js_exists_with_maps(self):
        self.assertTrue((STATIC / "friendly_labels.js").is_file())
        self.assertIn("GOAL_TYPE", LABELS_JS)
        self.assertIn("ACT_KIND", LABELS_JS)
        self.assertIn("CATEGORY_TAG", LABELS_JS)
        self.assertIn("emergency_fund", LABELS_JS)
        self.assertIn("withdraw_emergency_fund", LABELS_JS)
        self.assertIn("an_uong", LABELS_JS)
        self.assertIn("function labelGoalType", LABELS_JS)
        self.assertIn("function labelActKind", LABELS_JS)
        self.assertIn("function labelCategoryTag", LABELS_JS)
        # unknown → em dash, never dump raw
        self.assertIn('"—"', LABELS_JS)
        self.assertIn("MODE_C", LABELS_JS)
        self.assertIn("OBS", LABELS_JS)

    def test_pages_wire_friendly_labels(self):
        for name, html in (
            ("categories", CATEGORIES_HTML),
            ("budget", BUDGET_HTML),
            ("parser", PARSER_HTML),
            ("dual-control", DUAL_HTML),
            ("chat", CHAT_HTML),
        ):
            with self.subTest(page=name):
                self.assertIn("/static/friendly_labels.js", html)

    def test_reset_forgot_no_user_facing_reset_token_label(self):
        # JS/API field names may remain; visible labels / muted / errors must not
        labels = " ".join(_label_texts(RESET_HTML))
        self.assertNotIn("reset_token", labels)
        self.assertIn("Mã đặt lại mật khẩu", RESET_HTML)
        self.assertNotIn("Cần reset_token", RESET_HTML)
        self.assertIn("Cần mã đặt lại mật khẩu", RESET_HTML)
        # forgot intro / stub chrome
        self.assertNotIn("Nhận reset_token", FORGOT_HTML)
        self.assertNotIn(">reset_token (staging stub)<", FORGOT_HTML)
        self.assertIn("Mã đặt lại (bản staging)", FORGOT_HTML)

    def test_categories_no_snake_placeholder_or_budget_tags_intro(self):
        self.assertNotIn("an_uong, sieu_thi", CATEGORIES_HTML)
        self.assertNotIn("placeholder=\"an_uong", CATEGORIES_HTML)
        self.assertNotIn("budget_tags", CATEGORIES_HTML)
        self.assertIn("ăn uống, siêu thị", CATEGORIES_HTML)
        self.assertIn("gắn thẻ ngân sách", CATEGORIES_HTML)
        self.assertIn("labelCategoryTags", CATEGORIES_HTML)

    def test_budget_no_visible_auto_overwrite(self):
        self.assertNotIn("auto_overwrite", BUDGET_HTML)
        self.assertIn("chuyển số dư", BUDGET_HTML)
        self.assertIn("labelGoalType", BUDGET_HTML)

    def test_academy_error_no_user_id(self):
        self.assertNotIn("Thiếu user_id", ACADEMY_HTML)
        self.assertIn("Thiếu phiên đăng nhập", ACADEMY_HTML)

    def test_dual_control_masks_companion_uuid(self):
        # Must not assign companion UUID directly into visible input
        self.assertNotIn(
            'companionInput").value=cid',
            DUAL_HTML.replace("\n", ""),
        )
        self.assertNotRegex(
            DUAL_HTML,
            r'companionInput"\)\.value\s*=\s*cid\b',
        )
        self.assertIn('Đã gắn', DUAL_HTML)
        self.assertIn("dataset.masked", DUAL_HTML)
        self.assertIn('_cinp.value="Đã gắn"', DUAL_HTML)
        self.assertIn("labelActKind", DUAL_HTML)
        self.assertIn("chế độ Hành động", DUAL_HTML)
        # #213 not regressed
        self.assertIn("Đã đăng nhập trên thiết bị này", DUAL_HTML)
        self.assertIn("Mã người đồng hành", DUAL_HTML)
        self.assertNotIn("user_companion_01", DUAL_HTML)

    def test_chat_no_raw_act_kind_dump(self):
        # confirm bubble uses labelActKind, not raw d.act_kind alone
        self.assertIn("labelActKind", CHAT_HTML)
        self.assertIn("Chế độ Hành động", CHAT_HTML)
        self.assertNotIn("Mode C · Hành động", CHAT_HTML)
        self.assertIn("người đồng hành", CHAT_HTML)
        self.assertNotIn("để companion xác nhận", CHAT_HTML)

    def test_demo_persona_options_still_vn_no_snake_in_option(self):
        opts = _option_texts(DEMO_HTML)
        self.assertTrue(any("P2 · Gia đình trẻ" in o for o in opts), opts)
        self.assertTrue(any("P4 · Ba đời" in o for o in opts), opts)
        for o in opts:
            self.assertNotIn("young_family", o)
            self.assertNotIn("sandwich_3gen", o)
        self.assertIn("Chân dung demo", DEMO_HTML)

    def test_p1_tx_onboard_parser_login(self):
        self.assertIn("Cửa hàng / ứng dụng", TX_HTML)
        self.assertNotIn("Merchant (tuỳ chọn)", TX_HTML)
        self.assertNotIn("Ngày (ISO)", TX_HTML)
        self.assertIn("Tách dòng", TX_HTML)
        self.assertNotIn("Thêm dòng split", TX_HTML)
        self.assertIn("Không kết nối ngân hàng", TX_HTML)
        self.assertNotIn("take-home", ONBOARD_HTML)
        self.assertIn("Ba đời trên một thu nhập", ONBOARD_HTML)
        self.assertIn("ngày, số tiền, mô tả", PARSER_HTML)
        self.assertIn('placeholder="Dán CSV: ngày, số tiền, mô tả', PARSER_HTML)
        self.assertNotIn('placeholder="Dán CSV (date,amount,description)', PARSER_HTML)
        self.assertIn('aria-label="Thẻ đăng nhập"', LOGIN_HTML)
        self.assertNotIn("Auth tabs", LOGIN_HTML)
        self.assertIn("Khách / demo", LOGIN_HTML)

    def test_target_months_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])

    def test_routes_200(self):
        for path in (
            "/app/categories",
            "/app/budget",
            "/app/forgot-password",
            "/app/reset-password",
            "/app/academy",
            "/app/dual-control",
            "/app/chat",
            "/app/demo",
            "/app/transactions",
            "/app/parser",
            "/app/onboarding",
            "/app/login",
            "/static/friendly_labels.js",
        ):
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200, path)


if __name__ == "__main__":
    unittest.main()
