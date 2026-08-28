"""P2 content pack — WP markdown in repo/content, fallback if missing."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.content_map import FALLBACK_BODY, content_root, get_article
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
PACK = (
    "WP-02-01-quy-khan-cap-la-gi.md",
    "WP-02-03-khi-nao-duoc-dung-quy-khan-cap.md",
    "WP-02-04-nen-de-quy-khan-cap-o-dau.md",
    "WP-02-05-snowball-va-avalanche.md",
    "WP-02-06-no-tot-va-no-xau.md",
    "WP-02-08-co-nen-tra-het-no-truoc-khi-dau-tu.md",
    "WP-01-01-tu-duy-ve-tien-la-gi.md",
    "WP-01-07-muc-tieu-tai-chinh.md",
)


class TestP2ContentPack(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get("WELORA_CONTENT_ROOT")
        os.environ.pop("WELORA_CONTENT_ROOT", None)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("WELORA_CONTENT_ROOT", None)
        else:
            os.environ["WELORA_CONTENT_ROOT"] = self._old

    def test_pack_files_exist_and_longer_than_fallback(self):
        for name in PACK:
            p = ROOT / "content" / name
            self.assertTrue(p.is_file(), name)
            text = p.read_text(encoding="utf-8")
            self.assertGreater(len(text.strip()), 200)
            low = text.lower()
            self.assertNotIn("chắc lời", low)
            self.assertNotIn("% mỗi tháng", low)

    def test_default_root_is_repo_content(self):
        os.environ.pop("WELORA_CONTENT_ROOT", None)
        self.assertEqual(content_root(), ROOT / "content")

    def test_get_safe01_from_markdown_not_fallback(self):
        r = self.client.get("/content/SAFE-01")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body.get("ok"))
        self.assertTrue((body.get("body_markdown") or "").strip())
        src = body.get("source_file") or ""
        self.assertTrue(src.endswith(".md"), src)
        self.assertNotEqual(src, "fallback")
        self.assertIn("WP-02-01", src)

    def test_missing_file_still_fallback(self):
        os.environ["WELORA_CONTENT_ROOT"] = "/tmp/welora_empty_content_pack"
        Path("/tmp/welora_empty_content_pack").mkdir(exist_ok=True)
        art = get_article("SAFE-01")
        self.assertTrue(art.get("ok"))
        self.assertEqual(art.get("source_file"), "fallback")
        self.assertTrue((art.get("body_markdown") or "").strip())
        self.assertIn("3 tháng", art.get("body_markdown") or "")
        self.assertEqual(art.get("body_markdown"), FALLBACK_BODY["SAFE-01"])

    def test_render_has_content_root(self):
        yml = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("WELORA_CONTENT_ROOT", yml)
        self.assertIn("content", yml)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
