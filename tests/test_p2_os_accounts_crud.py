"""P0 OS — Accounts CRUD + manual entry + minimal consent (ticket 1/4).

Hard bans untouched: Open Banking · Investments UI · Hard Deny R01–R09 ·
TARGET_MONTHS / gate_months=3 · CORE · Mode C / L-* · Categories/Budget/Tx.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

os.environ.setdefault("WELORA_STORE", "memory")

from fastapi.testclient import TestClient

from welora.agent import (
    CONFIDENCE_THRESHOLD,
    HARD,
    PRIORITY,
    TARGET_MONTHS as AGENT_TARGET,
    run_hard_deny_suite,
)
from welora.api.app import create_app
from welora.fixtures import reset_all_stores
from welora.os_accounts import (
    ACCOUNT_TYPES,
    CONSENT_REQUIRED_VI,
    CONSENT_TEXT_VI,
    SOURCE_MANUAL,
    InMemoryAccountStore,
    reset_account_store,
    service_create_account,
    service_seed_from_persona,
    use_store,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
ACCOUNTS_HTML = ROOT / "welora" / "api" / "static" / "accounts.html"
HOME_HTML = ROOT / "welora" / "api" / "static" / "home.html"
SHELL_JS = ROOT / "welora" / "api" / "static" / "shell.js"
APP_PY = ROOT / "welora" / "api" / "app.py"


class TestP2OsAccountsCrud(unittest.TestCase):
    def setUp(self) -> None:
        reset_all_stores()
        use_store(InMemoryAccountStore())
        reset_account_store()
        self.client = TestClient(create_app())
        self.uid = "user_accounts_p0_01"

    def test_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertEqual(AGENT_TARGET, 3)
        self.assertEqual(CONFIDENCE_THRESHOLD, 0.80)
        self.assertEqual(HARD, {"R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"})
        self.assertEqual(
            PRIORITY,
            ["R01", "R03", "R02", "R08", "R09", "R06", "R07", "R04", "R05"],
        )
        passed_n, failed = run_hard_deny_suite()
        self.assertEqual(failed, [])
        self.assertEqual(passed_n, 8)

    def test_health_gate_months_3_hard_deny_true(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body["gate_months"], 3)
        self.assertTrue(body["hard_deny"])
        self.assertEqual(TARGET_MONTHS, 3)

    def test_consent_gate_blocks_create_without_ack(self):
        r = self.client.post(
            "/os/accounts",
            json={
                "user_id": self.uid,
                "name": "Vietcombank",
                "type": "chi_tieu_hang_ngay",
                "opening_balance": 1_000_000,
                "consent_ack": False,
                "source": "manual",
            },
        )
        self.assertEqual(r.status_code, 400, r.text)
        detail = r.json().get("detail")
        self.assertIsInstance(detail, dict)
        self.assertTrue(detail.get("consent_required"))
        self.assertIn("đồng ý", str(detail.get("error") or "").lower())
        self.assertEqual(detail.get("source"), SOURCE_MANUAL)
        self.assertIn("Open Banking", detail.get("consent_text") or CONSENT_TEXT_VI)

        # Service-level message lock
        code, out = service_create_account({
            "user_id": self.uid,
            "name": "X",
            "consent_ack": False,
        })
        self.assertEqual(code, 400)
        self.assertEqual(out["error"], CONSENT_REQUIRED_VI)

    def test_rejects_non_manual_source(self):
        r = self.client.post(
            "/os/accounts",
            json={
                "user_id": self.uid,
                "name": "Bank OAuth",
                "type": "chi_tieu_hang_ngay",
                "opening_balance": 0,
                "consent_ack": True,
                "source": "open_banking",
            },
        )
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("Open Banking", str(r.json().get("detail") or r.text))

    def test_crud_create_list_update_manual_balance(self):
        r = self.client.post(
            "/os/accounts",
            json={
                "user_id": self.uid,
                "name": "Chi tiêu",
                "type": "chi_tieu_hang_ngay",
                "opening_balance": 2_500_000,
                "consent_ack": True,
                "source": "manual",
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        acc = r.json()
        self.assertEqual(acc["name"], "Chi tiêu")
        self.assertEqual(acc["balance"], 2_500_000)
        self.assertEqual(acc["source"], "manual")
        self.assertTrue(acc["consent_ack"])
        self.assertEqual(acc["status"], "active")
        aid = acc["account_id"]

        lst = self.client.get(f"/os/accounts?user_id={self.uid}")
        self.assertEqual(lst.status_code, 200)
        items = lst.json()["accounts"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["account_id"], aid)
        self.assertEqual(lst.json()["source_policy"], "manual_only")

        patch = self.client.patch(
            f"/os/accounts/{aid}",
            json={"name": "Chi tiêu chính", "type": "tiet_kiem"},
        )
        self.assertEqual(patch.status_code, 200, patch.text)
        self.assertEqual(patch.json()["name"], "Chi tiêu chính")
        self.assertEqual(patch.json()["type"], "tiet_kiem")

        bal = self.client.patch(
            f"/os/accounts/{aid}/balance",
            json={"balance": 3_000_000},
        )
        self.assertEqual(bal.status_code, 200, bal.text)
        self.assertEqual(bal.json()["balance"], 3_000_000)

        got = self.client.get(f"/os/accounts/{aid}")
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["balance"], 3_000_000)

    def test_soft_delete_hide_and_exclude_from_default_list(self):
        r = self.client.post(
            "/os/accounts",
            json={
                "user_id": self.uid,
                "name": "Quỹ dự phòng",
                "type": "tiet_kiem",
                "opening_balance": 5_000_000,
                "consent_ack": True,
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        aid = r.json()["account_id"]

        hide = self.client.post(f"/os/accounts/{aid}/hide")
        self.assertEqual(hide.status_code, 200, hide.text)
        self.assertEqual(hide.json()["status"], "hidden")
        self.assertTrue(hide.json().get("hidden") or hide.json()["status"] == "hidden")

        lst = self.client.get(f"/os/accounts?user_id={self.uid}")
        self.assertEqual(lst.status_code, 200)
        self.assertEqual(lst.json()["count"], 0)

        lst2 = self.client.get(f"/os/accounts?user_id={self.uid}&include_hidden=true")
        self.assertEqual(lst2.status_code, 200)
        self.assertEqual(lst2.json()["count"], 1)
        self.assertEqual(lst2.json()["accounts"][0]["status"], "hidden")

        # DELETE is soft-hide alias
        r2 = self.client.post(
            "/os/accounts",
            json={
                "user_id": self.uid,
                "name": "Nợ thẻ",
                "type": "no",
                "opening_balance": 0,
                "consent_ack": True,
            },
        )
        aid2 = r2.json()["account_id"]
        soft = self.client.delete(f"/os/accounts/{aid2}")
        self.assertEqual(soft.status_code, 200, soft.text)
        self.assertEqual(soft.json()["status"], "hidden")
        # Row still get-able
        self.assertEqual(self.client.get(f"/os/accounts/{aid2}").status_code, 200)

        # Unhide
        un = self.client.patch(f"/os/accounts/{aid}", json={"unhide": True})
        self.assertEqual(un.status_code, 200)
        self.assertEqual(un.json()["status"], "active")

    def test_persona_seed_os_accounts_does_not_replace_crud(self):
        code, out = service_seed_from_persona(self.uid, "P2")
        self.assertEqual(code, 200, out)
        self.assertGreaterEqual(out["count"], 2)
        names = {a["name"] for a in out["created"]}
        self.assertTrue(any("Chi tiêu" in n or "chi tiêu" in n.lower() for n in names) or len(names) >= 2)

        # CRUD still works after seed
        r = self.client.post(
            "/os/accounts",
            json={
                "user_id": self.uid,
                "name": "Tài khoản thêm tay",
                "type": "tiet_kiem",
                "opening_balance": 100_000,
                "consent_ack": True,
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        lst = self.client.get(f"/os/accounts?user_id={self.uid}")
        self.assertGreaterEqual(lst.json()["count"], out["count"] + 1)

        # Idempotent re-seed skips existing names
        code2, out2 = service_seed_from_persona(self.uid, "P2")
        self.assertEqual(code2, 200)
        self.assertEqual(out2["count"], 0)
        self.assertTrue(len(out2["skipped"]) >= 1)

    def test_ui_accounts_page_and_nav(self):
        self.assertTrue(ACCOUNTS_HTML.is_file())
        html = ACCOUNTS_HTML.read_text(encoding="utf-8")
        self.assertIn("consentAck", html)
        self.assertIn("Open Banking", html)
        self.assertIn("/os/accounts", html)
        self.assertIn("Số dư", html)
        self.assertIn("Ẩn", html)
        # No Open Banking OAuth flow
        self.assertNotIn("oauth", html.lower())
        self.assertNotIn("aggregator", html.lower())

        home = HOME_HTML.read_text(encoding="utf-8")
        self.assertIn('id="navAccounts"', home)
        self.assertIn("/app/accounts", home)

        shell = SHELL_JS.read_text(encoding="utf-8")
        self.assertIn('/app/accounts', shell)

        r = self.client.get("/app/accounts")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Tài khoản", r.text)

        # CSV parser route still exists separately — CRUD not replaced
        self.assertIn('@app.post("/parser/csv"', APP_PY.read_text(encoding="utf-8"))
        self.assertIn("chi_tieu_hang_ngay", ACCOUNT_TYPES)

    def test_no_open_banking_investments_surface_in_module(self):
        mod = (ROOT / "welora" / "os_accounts.py").read_text(encoding="utf-8")
        self.assertIn("no Open Banking", mod)
        self.assertNotIn("/oauth", mod.lower())
        self.assertNotIn("authorize_url", mod.lower())
        # Investments type may exist as account type enum; no Investments UI page
        inv = ROOT / "welora" / "api" / "static" / "investments.html"
        self.assertFalse(inv.exists())



if __name__ == "__main__":
    unittest.main()
