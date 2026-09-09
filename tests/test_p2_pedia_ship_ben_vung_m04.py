"""P2 Pedia ship module Bền Vững & Di Sản M04 — full WP-04, không pad."""

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
    "SUSTAIN-01": "khu vườn",
    "INSURE-01": "không mất trắng",
    "RETIRE-01": "sương mù",
    "KIDS-01": "bánh phụ",
    "LEGACY-01": "chìa khóa",
    "LEGACY-SOFT-01": "la bàn",
    "BALANCE-01": "balo",
}

FILES = [
    "WP-04-01-ben-vung-tai-chinh.md",
    "WP-04-02-bao-hiem-rui-ro.md",
    "WP-04-03-chuan-bi-tuoi-gia.md",
    "WP-04-04-chi-phi-y-te.md",
    "WP-04-05-giao-duc-tai-chinh-con.md",
    "WP-04-06-di-san-thua-ke.md",
    "WP-04-07-gia-tri-di-san-phi-tai-chinh.md",
    "WP-04-08-song-ben-vung-voi-tien.md",
]

M04_KEYS = [
    "SUSTAIN-01",
    "INSURE-01",
    "RETIRE-01",
    "KIDS-01",
    "LEGACY-01",
    "LEGACY-SOFT-01",
    "BALANCE-01",
]


class TestP2PediaShipBenVungM04(unittest.TestCase):
    def test_eight_wp04_on_disk_full(self):
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
            self.assertEqual(art.get("module"), "04")
            self.assertEqual(art.get("module_title"), "Bền Vững & Di Sản")
            self.assertEqual(art["cta_academy"]["href"], "/app/academy")
            self.assertEqual(art["cta_constitution"]["href"], "/app/constitution")
        self.assertEqual(CONTENT_BY_KEY["INSURE-01"]["wp"], ["WP-04-02", "WP-04-04"])
        self.assertEqual(
            CONTENT_BY_KEY["INSURE-01"]["path_wp_extra"],
            ["WP-04-04-chi-phi-y-te.md"],
        )
        self.assertIn("cây cầu", get_article("INSURE-01").get("body_markdown") or "")
        # CORE-10 mapping intact (LEGACY-01 body refresh OK)
        self.assertEqual(CONTENT_BY_KEY["CORE-10"]["path_wp"], "WP-04-06-di-san-thua-ke.md")
        self.assertEqual(CONTENT_BY_KEY["CORE-10"]["wp"], ["WP-04-06"])
        self.assertEqual(CONTENT_BY_KEY["CORE-10"]["module"], "04")
        self.assertEqual(CONTENT_BY_KEY["LEGACY-01"]["path_wp"], "WP-04-06-di-san-thua-ke.md")
        core10 = get_article("CORE-10")
        self.assertTrue(core10.get("ok"))
        self.assertIn("chìa khóa", core10.get("body_markdown") or "")
        self.assertGreater(len(core10.get("body_markdown") or ""), 3000)
        legacy = get_article("LEGACY-01").get("body_markdown") or ""
        balance = get_article("BALANCE-01").get("body_markdown") or ""
        self.assertNotIn("chắc lời", legacy)
        self.assertNotIn("chắc lời", balance)

    def test_modules_04_and_html_cta_health(self):
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
        self.assertIn("SUSTAIN-", html)
        self.assertIn("INSURE-", html)
        self.assertIn("RETIRE-", html)
        self.assertIn("KIDS-", html)
        self.assertIn("LEGACY-SOFT-", html)
        self.assertIn("LEGACY-", html)
        self.assertIn("BALANCE-", html)
        self.assertNotIn("innerHTML", html)
        self.assertEqual(TARGET_MONTHS, 3)
        client = TestClient(create_app())
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        idx = client.get("/content").json()
        mods = idx.get("modules") or {}
        self.assertIn("04", mods)
        self.assertEqual(mods["04"].get("title"), "Bền Vững & Di Sản")
        keys = {i["principle_key"] for i in mods["04"].get("items") or []}
        for k in M04_KEYS:
            self.assertIn(k, keys, k)
        self.assertIn("CORE-10", keys)
        self.assertIn("01", mods)
        self.assertIn("02", mods)
        self.assertIn("03", mods)
        self.assertIn("05", mods)
        r = client.get("/content/SUSTAIN-01")
        self.assertEqual(r.status_code, 200)
        self.assertIn("khu vườn", r.json().get("body_markdown") or "")
        self.assertGreater(len(r.json().get("body_markdown") or ""), 3000)
        app_page = client.get("/app/content")
        self.assertEqual(app_page.status_code, 200)


if __name__ == "__main__":
    unittest.main()
