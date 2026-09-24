"""P2 hotfix — polish Persona demo VN + dual-control hide tech IDs.

UI/labels/copy ONLY. Does not touch Hard Deny · TARGET_MONTHS / gate_months ·
API identity · dual-control backend logic · Open Banking · Investments · pillar 4.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("WELORA_STORE", "memory")

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.fixtures import reset_all_stores
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
DEMO_HTML = (ROOT / "welora" / "api" / "static" / "demo.html").read_text(
    encoding="utf-8"
)
DUAL_HTML = (ROOT / "welora" / "api" / "static" / "dual-control.html").read_text(
    encoding="utf-8"
)


def _option_texts(html: str) -> list[str]:
    return re.findall(r"<option\b[^>]*>(.*?)</option>", html, flags=re.I | re.S)


class TestP2HotfixPolishPersonaDualUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def setUp(self) -> None:
        reset_all_stores()

    def test_demo_persona_options_friendly_vn(self):
        opts = _option_texts(DEMO_HTML)
        self.assertTrue(any("P2 · Gia đình trẻ" in o for o in opts), opts)
        self.assertTrue(any("P4 · Ba đời" in o for o in opts), opts)
        for o in opts:
            self.assertNotIn("young_family", o)
            self.assertNotIn("sandwich_3gen", o)

    def test_demo_option_values_and_personas_keys_intact(self):
        self.assertIn('value="P2"', DEMO_HTML)
        self.assertIn('value="P4"', DEMO_HTML)
        # Internal JS PERSONAS keys remain for API payloads
        self.assertIn("young_family", DEMO_HTML)
        self.assertIn("sandwich_3gen", DEMO_HTML)
        self.assertIn("PERSONAS", DEMO_HTML)

    def test_dual_control_no_user_facing_tech_ids(self):
        # Forbidden user-facing needles
        self.assertNotIn("user_companion_01", DUAL_HTML)
        self.assertNotIn("(pending_dual)", DUAL_HTML)
        self.assertNotIn("(companion)", DUAL_HTML)
        self.assertNotIn("L-DUAL-CONTROL", DUAL_HTML)
        self.assertNotIn("Companion xác nhận", DUAL_HTML)
        # Label must not expose companion_user_id as visible label text
        self.assertNotRegex(
            DUAL_HTML,
            r"<label\b[^>]*>[^<]*companion_user_id[^<]*</label>",
            msg="companion_user_id must not appear as label text",
        )
        # Friendly VN copy present
        self.assertIn("Mã người đồng hành", DUAL_HTML)
        self.assertIn("Nhập mã từ thiết bị thứ hai", DUAL_HTML)
        self.assertIn("Đã đăng nhập trên thiết bị này", DUAL_HTML)
        self.assertIn("Đã gắn người đồng hành", DUAL_HTML)
        self.assertIn(
            "Chưa gắn người đồng hành — thao tác đồng kiểm sẽ bị từ chối.",
            DUAL_HTML,
        )
        self.assertIn("Xác nhận (người đồng hành)", DUAL_HTML)
        self.assertIn("Chủ · Người đồng hành", DUAL_HTML)
        self.assertIn("Chờ đồng kiểm", DUAL_HTML)
        self.assertIn("Đồng kiểm", DUAL_HTML)

    def test_dual_control_api_hooks_intact(self):
        self.assertIn("/os/companion", DUAL_HTML)
        self.assertIn("companion_user_id", DUAL_HTML)  # JSON body / API field
        self.assertIn("companion-confirm", DUAL_HTML)
        self.assertIn("row-btns", DUAL_HTML)
        self.assertIn("/agent/mode-c/companion-confirm", DUAL_HTML)

    def test_routes_200(self):
        for path in ("/app/demo", "/app/dual-control"):
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200, path)

    def test_health_gate_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
