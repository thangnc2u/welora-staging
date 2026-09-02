"""P1 Bài 4.5 — WP-04-06 + WA-04-05 mapped to CORE-10."""

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
    "WA-04-05-di-san-thua-ke.md",
    "WP-04-06-di-san-thua-ke.md",
)


class TestP1ContentBai45(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get("WELORA_CONTENT_ROOT")
        os.environ.pop("WELORA_CONTENT_ROOT", None)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("WELORA_CONTENT_ROOT", None)
        else:
            os.environ["WELORA_CONTENT_ROOT"] = self._old

    def test_files_exist_core10_header(self):
        for name in FILES:
            p = ROOT / "content" / name
            self.assertTrue(p.is_file(), name)
            text = p.read_text(encoding="utf-8")
            self.assertGreater(len(text.strip()), 200)
            self.assertIn("**principle_key:** CORE-10", text)
            low = text.lower()
            self.assertNotIn("welora academy", low)
            self.assertNotIn("chắc lời", low)

    def test_content_map_core10(self):
        meta = CONTENT_BY_KEY["CORE-10"]
        self.assertEqual(meta["title"], "Tiền phục vụ cuộc đời")
        self.assertEqual(meta["module"], "04")
        self.assertEqual(meta["module_title"], "Bền Vững & Di Sản")
        self.assertEqual(meta["wp"], ["WP-04-06"])
        self.assertEqual(meta["wa"], ["WA-04-05"])
        self.assertEqual(meta["path_wp"], "WP-04-06-di-san-thua-ke.md")
        self.assertEqual(meta["path_wa"], "WA-04-05-di-san-thua-ke.md")
        self.assertEqual(meta["risk_level"], "medium")
        self.assertEqual(meta["academy_href"], "/app/academy")

    def test_get_content_core10(self):
        r = self.client.get("/content/CORE-10")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body.get("principle_key"), "CORE-10")
        src = body.get("source_file") or ""
        self.assertIn("WP-04-06", src)
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
