"""P2 Native UI /app/content — readable article, fallback body, no JSON dump."""

from __future__ import annotations

from pathlib import Path
import os
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

CONTENT_HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "content.html"


class TestP2ContentUi(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["WELORA_CONTENT_ROOT"] = "/tmp/welora_empty_content"
        Path("/tmp/welora_empty_content").mkdir(parents=True, exist_ok=True)
        self.client = TestClient(create_app())

    def test_content_html_ids_no_json_stringify(self):
        html = CONTENT_HTML.read_text(encoding="utf-8")
        self.assertIn('id="contentKey"', html)
        self.assertIn('id="contentTitle"', html)
        self.assertIn('id="contentBody"', html)
        self.assertNotIn("JSON.stringify", html)
        self.assertIn("/app/chat", html)
        self.assertIn("/app/safety", html)

    def test_get_content_safe02_fallback_body(self):
        r = self.client.get("/content/SAFE-02")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d.get("ok"))
        self.assertTrue(str(d.get("title") or "").strip())
        self.assertTrue(str(d.get("body_markdown") or "").strip())
        self.assertNotIn("%/năm chắc", d["body_markdown"])

    def test_get_content_ticket_e_keys_still_have_body(self):
        for key in ("SAFE-01", "SAFE-02", "DEBT-03", "CORE-07"):
            r = self.client.get(f"/content/{key}")
            self.assertEqual(r.status_code, 200, key)
            d = r.json()
            self.assertTrue(d.get("ok"), key)
            self.assertTrue(str(d.get("body_markdown") or "").strip(), key)

    def test_get_content_five_new_fallback_keys(self):
        for key in ("SAFE-03", "DEBT-01", "DEBT-02", "CORE-01", "CORE-05"):
            r = self.client.get(f"/content/{key}")
            self.assertEqual(r.status_code, 200, key)
            d = r.json()
            self.assertTrue(d.get("ok"), key)
            self.assertTrue(str(d.get("body_markdown") or "").strip(), key)

    def test_health_untouched(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
