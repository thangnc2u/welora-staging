"""P2 hotfix — /app/categories «Hiện danh mục đã vô hiệu» checkbox overflow (~375px).

CSS/layout only. Hard Deny · TARGET_MONTHS / gate_months · categories disable API untouched.
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
from welora.os_categories import (
    InMemoryCategoryStore,
    reset_category_store,
    use_store as use_category_store,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES_HTML = (ROOT / "welora" / "api" / "static" / "categories.html").read_text(
    encoding="utf-8"
)


class TestP2HotfixCategoriesShowDisabledOverflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def setUp(self) -> None:
        reset_all_stores()
        use_category_store(InMemoryCategoryStore())
        reset_category_store()

    def test_categories_html_checkbox_width_auto(self):
        # Global input width:100% must not stretch #showDisabled
        self.assertIn('input[type="checkbox"]', CATEGORIES_HTML)
        self.assertRegex(
            CATEGORIES_HTML,
            r'input\[type=["\']checkbox["\']\]\{[^}]*width:\s*auto',
        )
        self.assertRegex(
            CATEGORIES_HTML,
            r'input\[type=["\']checkbox["\']\]\{[^}]*flex-shrink:\s*0',
        )

    def test_show_disabled_row_flex_min_width(self):
        self.assertIn('id="showDisabled"', CATEGORIES_HTML)
        self.assertIn("Hiện danh mục đã vô hiệu", CATEGORIES_HTML)
        self.assertIn("show-disabled", CATEGORIES_HTML)
        self.assertRegex(
            CATEGORIES_HTML,
            r"\.show-disabled\{[^}]*display:\s*flex",
        )
        self.assertRegex(
            CATEGORIES_HTML,
            r"\.show-disabled\{[^}]*min-width:\s*0",
        )
        # Text node can wrap without blowing the card frame
        self.assertTrue(
            "overflow-wrap:anywhere" in CATEGORIES_HTML
            or "word-break:break-word" in CATEGORIES_HTML
            or "overflow-wrap:break-word" in CATEGORIES_HTML,
            msg="show-disabled text needs wrap/break protection",
        )
        # Label wired to checkbox
        self.assertIn('for="showDisabled"', CATEGORIES_HTML)
        self.assertIn('class="show-disabled"', CATEGORIES_HTML)

    def test_app_categories_200_spotcheck(self):
        r = self.client.get("/app/categories")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('id="showDisabled"', body)
        self.assertIn("Hiện danh mục đã vô hiệu", body)
        self.assertRegex(
            body,
            r'input\[type=["\']checkbox["\']\]\{[^}]*width:\s*auto',
        )
        self.assertIn(".show-disabled{", body)

    def test_disable_list_api_still_works(self):
        """Soft smoke: disable without history + include_disabled list (no API logic change)."""
        uid = "user_show_disabled_overflow_01"
        cr = self.client.post(
            "/os/categories",
            json={
                "user_id": uid,
                "name": "Danh mục test overflow",
                "kind": "variable",
            },
        )
        self.assertIn(cr.status_code, (200, 201), cr.text)
        cid = cr.json()["category_id"]
        self.assertTrue(cid)

        dis = self.client.post(f"/os/categories/{cid}/disable", json={})
        self.assertIn(dis.status_code, (200, 204), dis.text)
        self.assertEqual(dis.json().get("status"), "disabled")

        listed = self.client.get(f"/os/categories?user_id={uid}")
        self.assertEqual(listed.status_code, 200)
        ids = [
            c.get("category_id")
            for c in (
                listed.json().get("categories") or listed.json().get("items") or []
            )
        ]
        self.assertNotIn(cid, ids)

        with_disabled = self.client.get(
            f"/os/categories?user_id={uid}&include_disabled=true"
        )
        self.assertEqual(with_disabled.status_code, 200)
        disabled_ids = [
            c.get("category_id")
            for c in (
                with_disabled.json().get("categories")
                or with_disabled.json().get("items")
                or []
            )
        ]
        self.assertIn(cid, disabled_ids)

    def test_health_gate_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])

    def test_no_goals_accounts_scope_leak(self):
        # This hotfix is /app/categories only — goals/accounts must not get show-disabled
        goals = (ROOT / "welora" / "api" / "static" / "goals.html").read_text(
            encoding="utf-8"
        )
        accounts = (ROOT / "welora" / "api" / "static" / "accounts.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("show-disabled", goals)
        self.assertNotIn("show-disabled", accounts)
        # accounts may keep show-hidden from #209
        self.assertIn("show-hidden", accounts)
        # Sanity: categories page still has showDisabled hook
        self.assertIsNotNone(re.search(r'id=["\']showDisabled["\']', CATEGORIES_HTML))


if __name__ == "__main__":
    unittest.main()
