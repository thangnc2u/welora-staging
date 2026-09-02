"""P1 Pedia ship module An Toàn WP-02 — full Module02, không pad."""

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
    "SAFE-01": "bảo vệ chứ không phải",
    "SAFE-02": "bình chữa cháy",
    "SAFE-03": "an toàn gốc",
    "DEBT-01": "Nợ tốt",
    "DEBT-02": "Snowball",
    "DEBT-03": "trả hết nợ trước khi",
}

FILES = [
    "WP-02-01-quy-khan-cap-la-gi.md",
    "WP-02-02-cach-xay-dung-quy-khan-cap.md",
    "WP-02-03-khi-nao-duoc-dung-quy-khan-cap.md",
    "WP-02-04-nen-de-quy-khan-cap-o-dau.md",
    "WP-02-05-snowball-va-avalanche.md",
    "WP-02-06-no-tot-va-no-xau.md",
    "WP-02-07-cach-lap-ke-hoach-tra-no.md",
    "WP-02-08-co-nen-tra-het-no-truoc-khi-dau-tu.md",
]


class TestP1PediaShipAnToan(unittest.TestCase):
    def test_eight_wp02_on_disk_full(self):
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
            self.assertEqual(art.get("version"), "1.0.0")
            self.assertEqual(art.get("last_reviewed_at"), "2026-09-02")
            self.assertIn(art.get("risk_level"), ("medium", "high"))
            self.assertEqual(art["cta_academy"]["href"], "/app/academy")
            self.assertEqual(art["cta_constitution"]["href"], "/app/constitution")
        self.assertEqual(CONTENT_BY_KEY["SAFE-01"]["wp"], ["WP-02-01", "WP-02-02"])
        self.assertEqual(CONTENT_BY_KEY["DEBT-02"]["wp"], ["WP-02-05", "WP-02-07"])

    def test_html_cta_and_health(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Học sâu hơn", html)
        self.assertIn("/app/academy", html)
        self.assertIn("Xây Hiến pháp Cá nhân", html)
        self.assertIn("/app/constitution", html)
        self.assertIn("Welorademy", html)
        self.assertNotIn("Welora Academy", html)
        self.assertIn('id="ctaAcademy"', html)
        self.assertIn('id="ctaConstitution"', html)
        self.assertNotIn("innerHTML", html)
        self.assertEqual(TARGET_MONTHS, 3)
        client = TestClient(create_app())
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        idx = client.get("/content").json()
        self.assertIn("02", idx.get("modules") or {})
        r = client.get("/content/SAFE-01")
        self.assertEqual(r.status_code, 200)
        self.assertIn("bảo vệ chứ không phải", r.json().get("body_markdown") or "")
        self.assertGreater(len(r.json().get("body_markdown") or ""), 3000)


if __name__ == "__main__":
    unittest.main()
