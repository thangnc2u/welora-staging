"""P2 Ticket AC — WA markdown pack; WP still preferred for GET /content."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.content_map import CONTENT_BY_KEY
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
WA_PACK = (
    "WA-02-01-xay-dung-quy-khan-cap.md",
    "WA-02-02-nguyen-tac-su-dung-quy-khan-cap.md",
    "WA-02-03-lua-chon-noi-giu-quy-khan-cap.md",
    "WA-02-04-chon-phuong-phap-tra-no.md",
    "WA-02-05-nhan-dien-no-tot-no-xau.md",
    "WA-02-07-sap-xep-uu-tien-tra-no-va-dau-tu.md",
    "WA-01-01-xay-dung-tu-duy-ve-tien.md",
    "WA-01-06-dat-muc-tieu-tai-chinh.md",
)


class TestP2ContentWa(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get("WELORA_CONTENT_ROOT")
        os.environ.pop("WELORA_CONTENT_ROOT", None)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("WELORA_CONTENT_ROOT", None)
        else:
            os.environ["WELORA_CONTENT_ROOT"] = self._old

    def test_every_path_wa_file_exists(self):
        for name in WA_PACK:
            p = ROOT / "content" / name
            self.assertTrue(p.is_file(), name)
            text = p.read_text(encoding="utf-8")
            self.assertGreater(len(text.strip()), 200)
            low = text.lower()
            self.assertNotIn("chắc lời", low)

        mapped = {v.get("path_wa") for v in CONTENT_BY_KEY.values() if v.get("path_wa")}
        for rel in mapped:
            if rel in WA_PACK or (ROOT / "content" / rel).is_file():
                self.assertTrue((ROOT / "content" / rel).is_file(), rel)

    def test_safe01_still_wp_not_fallback(self):
        r = self.client.get("/content/SAFE-01")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        src = body.get("source_file") or ""
        self.assertTrue(src.endswith(".md"), src)
        self.assertNotEqual(src, "fallback")
        self.assertIn("WP-02-01", src)
        self.assertTrue((body.get("body_markdown") or "").strip())

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
