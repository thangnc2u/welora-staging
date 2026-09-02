"""P1 Bài 4.3 — WP-06-01 + WA-06-01 mapped to TAX-01."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.content_map import CONTENT_BY_KEY
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "WA-06-01-toi-uu-thue-hop-ly.md",
    "WP-06-01-toi-uu-thue-hop-ly.md",
)


class TestP1ContentBai43(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get("WELORA_CONTENT_ROOT")
        os.environ.pop("WELORA_CONTENT_ROOT", None)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("WELORA_CONTENT_ROOT", None)
        else:
            os.environ["WELORA_CONTENT_ROOT"] = self._old

    def test_files_exist_tax01_header(self):
        for name in FILES:
            p = ROOT / "content" / name
            self.assertTrue(p.is_file(), name)
            text = p.read_text(encoding="utf-8")
            self.assertGreater(len(text.strip()), 200)
            self.assertIn("**principle_key:** TAX-01", text)
            low = text.lower()
            self.assertNotIn("welora academy", low)
            self.assertNotIn("chắc lời", low)

    def test_content_map_tax01(self):
        meta = CONTENT_BY_KEY["TAX-01"]
        self.assertEqual(meta["title"], "Tối ưu thuế hợp lý")
        self.assertEqual(meta["module"], "06")
        self.assertEqual(meta["module_title"], "Thuế & cấu trúc hợp pháp")
        self.assertEqual(meta["wp"], ["WP-06-01"])
        self.assertEqual(meta["wa"], ["WA-06-01"])
        self.assertEqual(meta["path_wp"], "WP-06-01-toi-uu-thue-hop-ly.md")
        self.assertEqual(meta["path_wa"], "WA-06-01-toi-uu-thue-hop-ly.md")
        self.assertEqual(meta["risk_level"], "medium")
        self.assertEqual(meta["academy_href"], "/app/academy")
        self.assertNotIn("TAX-01", ["CORE-01", "CORE-02", "CORE-03", "CORE-04", "CORE-05", "CORE-06", "CORE-07", "CORE-08", "CORE-09", "CORE-10"])

    def test_get_content_tax01(self):
        r = self.client.get("/content/TAX-01")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("principle_key"), "TAX-01")
        src = body.get("source_file") or ""
        self.assertIn("WP-06-01", src)
        md = body.get("body_markdown") or ""
        self.assertTrue(md.strip())
        self.assertNotIn("Welora Academy", md)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
