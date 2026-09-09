"""P2 — Remove M06 tax: TAX-01 / WP-WA-06-01 gone; health gate intact."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.content_map import CONTENT_BY_KEY, FALLBACK_BODY
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
GONE_FILES = (
    "WA-06-01-toi-uu-thue-hop-ly.md",
    "WP-06-01-toi-uu-thue-hop-ly.md",
)


class TestP2RemoveTaxM06(unittest.TestCase):
    def setUp(self) -> None:
        self._old = os.environ.get("WELORA_CONTENT_ROOT")
        os.environ.pop("WELORA_CONTENT_ROOT", None)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("WELORA_CONTENT_ROOT", None)
        else:
            os.environ["WELORA_CONTENT_ROOT"] = self._old

    def test_tax_content_files_gone(self):
        for name in GONE_FILES:
            self.assertFalse((ROOT / "content" / name).exists(), name)

    def test_content_map_no_tax01_or_wp_wa_06(self):
        self.assertNotIn("TAX-01", CONTENT_BY_KEY)
        self.assertNotIn("TAX-01", FALLBACK_BODY)
        blob = str(CONTENT_BY_KEY) + str(FALLBACK_BODY)
        self.assertNotIn("WP-06-01", blob)
        self.assertNotIn("WA-06-01", blob)
        self.assertNotIn("TAX-01", blob)

    def test_get_content_tax01_404(self):
        r = self.client.get("/content/TAX-01")
        self.assertEqual(r.status_code, 404)

    def test_list_content_no_module_06_or_tax01(self):
        r = self.client.get("/content")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        items = body.get("items") or []
        keys = {i.get("principle_key") for i in items}
        self.assertNotIn("TAX-01", keys)
        modules = body.get("modules") or {}
        self.assertNotIn("06", modules)
        for mid, bucket in modules.items():
            title = (bucket.get("title") or "").lower()
            self.assertNotIn("thuế", title)
            self.assertNotIn("thue", title)
            for row in bucket.get("items") or []:
                self.assertNotEqual(row.get("principle_key"), "TAX-01")
                self.assertNotEqual(str(row.get("module")), "06")

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
