"""P2 Pedia ship module Tự Do Tài Chính M03 — full WP-03, không pad."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.content_map import CONTENT_BY_KEY, get_article
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "welora" / "api" / "static" / "content.html"
CONTENT = ROOT / "content"

SNIPPETS = {
    "FREE-01": "chiếc thuyền",
    "ASSET-01": "hai loại máy",
    "PASSIVE-01": "hai cách lấy nước",
    "INV-01": "trồng cây ăn quả",
    "DIV-01": "vận chuyển trứng",
    "FREE-PLAN-01": "chân núi",
    "FREE-RISK-01": "lái xe đường dài",
}

FILES = [
    "WP-03-01-tu-do-tai-chinh-la-gi.md",
    "WP-03-02-cac-muc-do-tu-do-tai-chinh.md",
    "WP-03-03-tai-san-va-no.md",
    "WP-03-04-thu-nhap-thu-dong.md",
    "WP-03-05-dau-tu-co-ban.md",
    "WP-03-06-da-dang-hoa.md",
    "WP-03-07-ke-hoach-tu-do-tai-chinh.md",
    "WP-03-08-rui-ro-tu-do-tai-chinh.md",
]

M03_KEYS = [
    "FREE-01",
    "ASSET-01",
    "PASSIVE-01",
    "INV-01",
    "DIV-01",
    "FREE-PLAN-01",
    "FREE-RISK-01",
]


class TestP2PediaShipTuDoM03(unittest.TestCase):
    def test_eight_wp03_on_disk_full(self):
        for name in FILES:
            p = CONTENT / name
            self.assertTrue(p.is_file(), name)
            self.assertGreater(p.stat().st_size, 3000, name)
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("chắc lời", text)
            self.assertIn("##", text)

    def test_snippets_and_governance(self):
        for key, needle in SNIPPETS.items():
            art = get_article(key)
            self.assertTrue(art.get("ok"), key)
            self.assertNotEqual(art.get("source_file"), "fallback")
            self.assertIn(needle, art.get("body_markdown") or "", key)
            self.assertGreater(len(art.get("body_markdown") or ""), 3000, key)
            self.assertEqual(art.get("version"), "1.0.0")
            self.assertEqual(art.get("last_reviewed_at"), "2026-09-02")
            self.assertEqual(art.get("status"), "published")
            self.assertIn(art.get("risk_level"), ("low", "medium", "high"))
            self.assertEqual(art.get("module"), "03")
            self.assertEqual(art.get("module_title"), "Tự Do Tài Chính")
            self.assertEqual(art["cta_academy"]["href"], "/app/academy")
            self.assertEqual(art["cta_constitution"]["href"], "/app/constitution")
        self.assertEqual(CONTENT_BY_KEY["FREE-01"]["wp"], ["WP-03-01", "WP-03-02"])
        self.assertEqual(
            CONTENT_BY_KEY["FREE-01"]["path_wp_extra"],
            ["WP-03-02-cac-muc-do-tu-do-tai-chinh.md"],
        )
        self.assertIn("học bơi", get_article("FREE-01").get("body_markdown") or "")
        inv = get_article("INV-01").get("body_markdown") or ""
        div = get_article("DIV-01").get("body_markdown") or ""
        self.assertIn("quỹ khẩn cấp", inv)
        self.assertIn("một kênh duy nhất", inv)
        self.assertIn("quỹ khẩn cấp", div)
        self.assertNotIn("chắc lời", inv)
        self.assertNotIn("chắc lời", div)

    def test_modules_03_and_html_cta_health(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Học sâu hơn", html)
        self.assertIn("/app/academy", html)
        self.assertIn("Xây Hiến pháp Cá nhân", html)
        self.assertIn("/app/constitution", html)
        self.assertIn("Welorademy", html)
        self.assertNotIn("Welora Academy", html)
        self.assertIn('id="ctaAcademy"', html)
        self.assertIn('id="ctaConstitution"', html)
        self.assertIn("j.modules", html)
        self.assertNotIn("j.modules['02']", html)
        self.assertIn("Object.keys(mods)", html)
        self.assertIn("viTag", html)
        self.assertIn("FREE-", html)
        self.assertIn("ASSET-", html)
        self.assertIn("PASSIVE-", html)
        self.assertIn("INV-", html)
        self.assertIn("DIV-", html)
        self.assertIn("FREE-PLAN-", html)
        self.assertIn("FREE-RISK-", html)
        self.assertNotIn("innerHTML", html)
        self.assertEqual(TARGET_MONTHS, 3)
        client = TestClient(create_app())
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        idx = client.get("/content").json()
        mods = idx.get("modules") or {}
        self.assertIn("03", mods)
        self.assertEqual(mods["03"].get("title"), "Tự Do Tài Chính")
        keys = {i["principle_key"] for i in mods["03"].get("items") or []}
        for k in M03_KEYS:
            self.assertIn(k, keys, k)
        self.assertIn("01", mods)
        self.assertIn("02", mods)
        r = client.get("/content/FREE-01")
        self.assertEqual(r.status_code, 200)
        self.assertIn("chiếc thuyền", r.json().get("body_markdown") or "")
        self.assertGreater(len(r.json().get("body_markdown") or ""), 3000)
        app_page = client.get("/app/content")
        self.assertEqual(app_page.status_code, 200)


if __name__ == "__main__":
    unittest.main()
