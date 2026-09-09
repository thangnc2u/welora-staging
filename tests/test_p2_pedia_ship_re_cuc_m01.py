"""P2 Pedia ship module Rễ Cục M01 — full WP-01, không pad."""

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
    "MIND-01": "money mindset",
    "FLOW-01": "Hai mặt của dòng tiền",
    "BUDG-01": "không có bản đồ",
    "BUDG-02": "ước lượng cho có",
    "TRACK-01": "không bỏ cuộc",
    "GOAL-01": "SMART",
    "TIME-01": "compound",
}

FILES = [
    "WP-01-01-tu-duy-ve-tien-la-gi.md",
    "WP-01-02-thu-nhap-va-chi-tieu.md",
    "WP-01-03-ngan-sach-la-gi.md",
    "WP-01-04-lap-ngan-sach-thuc-te.md",
    "WP-01-05-quy-tac-50-30-20.md",
    "WP-01-06-theo-doi-chi-tieu.md",
    "WP-01-07-muc-tieu-tai-chinh.md",
    "WP-01-08-lai-kep-va-gia-tri-thoi-gian.md",
]

M01_KEYS = ["MIND-01", "FLOW-01", "BUDG-01", "BUDG-02", "TRACK-01", "GOAL-01", "TIME-01"]


class TestP2PediaShipReCucM01(unittest.TestCase):
    def test_eight_wp01_on_disk_full(self):
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
            self.assertEqual(art.get("module"), "01")
            self.assertEqual(art.get("module_title"), "Rễ Cục")
            self.assertEqual(art["cta_academy"]["href"], "/app/academy")
            self.assertEqual(art["cta_constitution"]["href"], "/app/constitution")
        self.assertEqual(CONTENT_BY_KEY["BUDG-01"]["wp"], ["WP-01-03", "WP-01-05"])
        self.assertEqual(
            CONTENT_BY_KEY["BUDG-01"]["path_wp_extra"],
            ["WP-01-05-quy-tac-50-30-20.md"],
        )
        self.assertIn("50/30/20", get_article("BUDG-01").get("body_markdown") or "")

    def test_modules_01_and_html_cta_health(self):
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
        self.assertIn("MIND-", html)
        self.assertNotIn("innerHTML", html)
        self.assertEqual(TARGET_MONTHS, 3)
        client = TestClient(create_app())
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        idx = client.get("/content").json()
        mods = idx.get("modules") or {}
        self.assertIn("01", mods)
        self.assertEqual(mods["01"].get("title"), "Rễ Cục")
        keys = {i["principle_key"] for i in mods["01"].get("items") or []}
        for k in M01_KEYS:
            self.assertIn(k, keys, k)
        self.assertIn("02", mods)
        r = client.get("/content/MIND-01")
        self.assertEqual(r.status_code, 200)
        self.assertIn("money mindset", r.json().get("body_markdown") or "")
        self.assertGreater(len(r.json().get("body_markdown") or ""), 3000)
        app_page = client.get("/app/content")
        self.assertEqual(app_page.status_code, 200)


if __name__ == "__main__":
    unittest.main()
