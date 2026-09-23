"""P2 hotfix — /app/accounts «Hiện tài khoản đã ẩn» checkbox overflow (~375px).

CSS/layout only. Hard Deny · TARGET_MONTHS / gate_months · hide/unhide API untouched.
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
from welora.os_accounts import InMemoryAccountStore, reset_account_store, use_store
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS_HTML = (ROOT / "welora" / "api" / "static" / "accounts.html").read_text(
    encoding="utf-8"
)


class TestP2HotfixAccountsShowHiddenOverflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def setUp(self) -> None:
        reset_all_stores()
        use_store(InMemoryAccountStore())
        reset_account_store()

    def test_accounts_html_checkbox_width_auto(self):
        # Global input width:100% must not stretch #showHidden
        self.assertIn('input[type="checkbox"]', ACCOUNTS_HTML)
        self.assertRegex(
            ACCOUNTS_HTML,
            r'input\[type=["\']checkbox["\']\]\{[^}]*width:\s*auto',
        )
        self.assertRegex(
            ACCOUNTS_HTML,
            r'input\[type=["\']checkbox["\']\]\{[^}]*flex-shrink:\s*0',
        )

    def test_show_hidden_row_flex_min_width(self):
        self.assertIn('id="showHidden"', ACCOUNTS_HTML)
        self.assertIn("Hiện tài khoản đã ẩn", ACCOUNTS_HTML)
        self.assertIn("show-hidden", ACCOUNTS_HTML)
        self.assertRegex(
            ACCOUNTS_HTML,
            r"\.show-hidden\{[^}]*display:\s*flex",
        )
        self.assertRegex(
            ACCOUNTS_HTML,
            r"\.show-hidden\{[^}]*min-width:\s*0",
        )
        # Text node can wrap without blowing the card frame
        self.assertTrue(
            "overflow-wrap:anywhere" in ACCOUNTS_HTML
            or "word-break:break-word" in ACCOUNTS_HTML
            or "overflow-wrap:break-word" in ACCOUNTS_HTML,
            msg="show-hidden text needs wrap/break protection",
        )
        # Label wired to checkbox
        self.assertIn('for="showHidden"', ACCOUNTS_HTML)
        self.assertIn('class="show-hidden"', ACCOUNTS_HTML)

    def test_app_accounts_200_spotcheck(self):
        r = self.client.get("/app/accounts")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('id="showHidden"', body)
        self.assertIn("Hiện tài khoản đã ẩn", body)
        self.assertRegex(
            body,
            r'input\[type=["\']checkbox["\']\]\{[^}]*width:\s*auto',
        )
        # Consent checkbox override still present (must not regress)
        self.assertIn(".consent input{width:auto", body)

    def test_hide_unhide_api_still_works(self):
        uid = "user_show_hidden_overflow_01"
        cr = self.client.post(
            "/os/accounts",
            json={
                "user_id": uid,
                "name": "Ví test overflow",
                "type": "chi_tieu_hang_ngay",
                "opening_balance": 100_000,
                "consent_ack": True,
                "source": "manual",
            },
        )
        self.assertIn(cr.status_code, (200, 201), cr.text)
        aid = cr.json()["account_id"]
        self.assertTrue(aid)

        hr = self.client.post(f"/os/accounts/{aid}/hide")
        self.assertIn(hr.status_code, (200, 204), hr.text)

        listed = self.client.get(f"/os/accounts?user_id={uid}")
        self.assertEqual(listed.status_code, 200)
        ids = [
            a.get("account_id")
            for a in (listed.json().get("accounts") or listed.json().get("items") or [])
        ]
        self.assertNotIn(aid, ids)

        with_hidden = self.client.get(
            f"/os/accounts?user_id={uid}&include_hidden=true"
        )
        self.assertEqual(with_hidden.status_code, 200)
        hidden_ids = [
            a.get("account_id")
            for a in (
                with_hidden.json().get("accounts")
                or with_hidden.json().get("items")
                or []
            )
        ]
        self.assertIn(aid, hidden_ids)

        ur = self.client.patch(
            f"/os/accounts/{aid}",
            json={"unhide": True},
        )
        self.assertEqual(ur.status_code, 200, ur.text)

        listed2 = self.client.get(f"/os/accounts?user_id={uid}")
        ids2 = [
            a.get("account_id")
            for a in (
                listed2.json().get("accounts") or listed2.json().get("items") or []
            )
        ]
        self.assertIn(aid, ids2)

    def test_health_gate_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])

    def test_no_goals_scope_leak(self):
        # This hotfix is /app/accounts only — goals.html must stay untouched
        goals = (ROOT / "welora" / "api" / "static" / "goals.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("show-hidden", goals)
        # Sanity: accounts page still has showHidden hook
        self.assertIsNotNone(re.search(r'id=["\']showHidden["\']', ACCOUNTS_HTML))


if __name__ == "__main__":
    unittest.main()
