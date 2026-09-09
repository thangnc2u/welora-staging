"""P2 Pedia ship module Kết Nối & Thực Hành M05 — full WP-05, không pad."""

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
    "ACT-01": "bơi lội",
    "HABIT-01": "đánh răng",
    "ADJUST-01": "Hà Nội vào Đà Nẵng",
    "DECIDE-01": "cái xô",
    "PEER-01": "tập chạy bộ",
    "TOOLS-01": "tưới cây",
    "DRIVE-01": "marathon",
}

FILES = [
    "WP-05-01-tu-kien-thuc-den-hanh-dong.md",
    "WP-05-02-xay-dung-thoi-quen.md",
    "WP-05-03-theo-doi-dieu-chinh.md",
    "WP-05-04-ra-quyet-dinh-hang-ngay.md",
    "WP-05-05-xu-ly-ke-hoach-lech.md",
    "WP-05-06-cong-dong-hoc-hoi.md",
    "WP-05-07-cong-cu-he-thong.md",
    "WP-05-08-duy-tri-dong-luc.md",
]

M05_KEYS = [
    "ACT-01",
    "HABIT-01",
    "ADJUST-01",
    "DECIDE-01",
    "PEER-01",
    "TOOLS-01",
    "DRIVE-01",
]


class TestP2PediaShipKetNoiM05(unittest.TestCase):
    def test_eight_wp05_on_disk_full(self):
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
            self.assertEqual(art.get("module"), "05")
            self.assertEqual(art.get("module_title"), "Kết Nối & Thực Hành")
            self.assertEqual(art["cta_academy"]["href"], "/app/academy")
            self.assertEqual(art["cta_constitution"]["href"], "/app/constitution")
        self.assertEqual(CONTENT_BY_KEY["ADJUST-01"]["wp"], ["WP-05-03", "WP-05-05"])
        self.assertEqual(
            CONTENT_BY_KEY["ADJUST-01"]["path_wp_extra"],
            ["WP-05-05-xu-ly-ke-hoach-lech.md"],
        )
        self.assertIn("trẹo chân", get_article("ADJUST-01").get("body_markdown") or "")
        peer = get_article("PEER-01").get("body_markdown") or ""
        adjust = get_article("ADJUST-01").get("body_markdown") or ""
        self.assertIn("quỹ khẩn cấp", adjust)
        self.assertIn("all-in", peer)
        self.assertNotIn("chắc lời", peer)
        self.assertNotIn("chắc lời", adjust)

    def test_modules_05_and_html_cta_health(self):
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
        self.assertIn("ACT-", html)
        self.assertIn("HABIT-", html)
        self.assertIn("ADJUST-", html)
        self.assertIn("DECIDE-", html)
        self.assertIn("PEER-", html)
        self.assertIn("TOOLS-", html)
        self.assertIn("DRIVE-", html)
        self.assertNotIn("innerHTML", html)
        self.assertEqual(TARGET_MONTHS, 3)
        client = TestClient(create_app())
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        idx = client.get("/content").json()
        mods = idx.get("modules") or {}
        self.assertIn("05", mods)
        self.assertEqual(mods["05"].get("title"), "Kết Nối & Thực Hành")
        keys = {i["principle_key"] for i in mods["05"].get("items") or []}
        for k in M05_KEYS:
            self.assertIn(k, keys, k)
        self.assertIn("01", mods)
        self.assertIn("02", mods)
        self.assertIn("03", mods)
        r = client.get("/content/ACT-01")
        self.assertEqual(r.status_code, 200)
        self.assertIn("bơi lội", r.json().get("body_markdown") or "")
        self.assertGreater(len(r.json().get("body_markdown") or ""), 3000)
        app_page = client.get("/app/content")
        self.assertEqual(app_page.status_code, 200)


if __name__ == "__main__":
    unittest.main()
