"""P0 OS — Manual transactions + split (ticket 2/4). Keep CSV intact.

Hard bans untouched: Open Banking · Investments UI · Hard Deny R01–R09 ·
TARGET_MONTHS / gate_months=3 · CORE · Mode C / L-* · Categories CRUD · Budget.
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
from welora.os_accounts import InMemoryAccountStore, reset_account_store, use_store as use_account_store
from welora.os_transactions import (
    InMemoryTransactionStore,
    reset_transaction_store,
    use_store as use_tx_store,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
TX_HTML = ROOT / "welora" / "api" / "static" / "transactions.html"
HOME_HTML = ROOT / "welora" / "api" / "static" / "home.html"
SHELL_JS = ROOT / "welora" / "api" / "static" / "shell.js"
APP_PY = ROOT / "welora" / "api" / "app.py"
CSV_PY = ROOT / "welora" / "csv_parser.py"

SAMPLE_CSV = """date,amount,description
01/07/2026,-3500000,Thuê nhà tháng 7
10/07/2026,25000000,Lương
12/07/2026,-1200000,WinMart
"""


class TestP2OsTransactionsManualSplit(unittest.TestCase):
    def setUp(self) -> None:
        reset_all_stores()
        use_account_store(InMemoryAccountStore())
        reset_account_store()
        use_tx_store(InMemoryTransactionStore())
        reset_transaction_store()
        self.client = TestClient(create_app())
        self.uid = "user_tx_p0_01"
        self.aid = self._create_account("Chi tiêu")

    def _create_account(self, name: str = "Chi tiêu") -> str:
        r = self.client.post(
            "/os/accounts",
            json={
                "user_id": self.uid,
                "name": name,
                "type": "chi_tieu_hang_ngay",
                "opening_balance": 5_000_000,
                "consent_ack": True,
                "source": "manual",
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["account_id"]

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

    def test_create_manual_tx_against_account(self):
        r = self.client.post(
            "/os/transactions",
            json={
                "user_id": self.uid,
                "account_id": self.aid,
                "amount": -150_000,
                "category": "Ăn uống",
                "date": "2026-09-20",
                "merchant": "Grab",
                "note": "bữa trưa",
                "consent_ack": True,
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        tx = r.json()
        self.assertEqual(tx["account_id"], self.aid)
        self.assertEqual(tx["amount"], -150_000)
        self.assertEqual(tx["category"], "Ăn uống")
        self.assertEqual(tx["date"], "2026-09-20")
        self.assertEqual(tx["merchant"], "Grab")
        self.assertFalse(tx["is_split"])
        self.assertEqual(tx["splits"], [])
        self.assertEqual(tx["source"], "manual")
        self.assertEqual(tx["status"], "active")

    def test_reject_missing_account(self):
        r = self.client.post(
            "/os/transactions",
            json={
                "user_id": self.uid,
                "account_id": "00000000-0000-0000-0000-000000000099",
                "amount": -10_000,
                "category": "Khác",
                "date": "2026-09-20",
            },
        )
        self.assertEqual(r.status_code, 400, r.text)
        detail = r.json().get("detail")
        self.assertIn("không tồn tại", str(detail))

    def test_reject_hidden_account(self):
        hide = self.client.post(f"/os/accounts/{self.aid}/hide")
        self.assertEqual(hide.status_code, 200, hide.text)
        r = self.client.post(
            "/os/transactions",
            json={
                "user_id": self.uid,
                "account_id": self.aid,
                "amount": -10_000,
                "category": "Khác",
                "date": "2026-09-20",
            },
        )
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("hidden", str(r.json().get("detail") or r.text).lower())

    def test_list_get_patch_soft_delete(self):
        r = self.client.post(
            "/os/transactions",
            json={
                "user_id": self.uid,
                "account_id": self.aid,
                "amount": -200_000,
                "category": "Siêu thị",
                "date": "2026-09-18",
                "merchant": "WinMart",
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        tid = r.json()["transaction_id"]

        lst = self.client.get(f"/os/transactions?user_id={self.uid}")
        self.assertEqual(lst.status_code, 200)
        self.assertEqual(lst.json()["count"], 1)
        self.assertTrue(lst.json().get("csv_parser_separate"))

        lst_acc = self.client.get(
            f"/os/transactions?user_id={self.uid}&account_id={self.aid}"
        )
        self.assertEqual(lst_acc.status_code, 200)
        self.assertEqual(lst_acc.json()["count"], 1)

        got = self.client.get(f"/os/transactions/{tid}")
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["category"], "Siêu thị")

        patch = self.client.patch(
            f"/os/transactions/{tid}",
            json={"category": "Mua sắm", "note": "sửa tay"},
        )
        self.assertEqual(patch.status_code, 200, patch.text)
        self.assertEqual(patch.json()["category"], "Mua sắm")
        self.assertEqual(patch.json()["note"], "sửa tay")

        hide = self.client.post(f"/os/transactions/{tid}/hide")
        self.assertEqual(hide.status_code, 200, hide.text)
        self.assertEqual(hide.json()["status"], "hidden")

        lst2 = self.client.get(f"/os/transactions?user_id={self.uid}")
        self.assertEqual(lst2.json()["count"], 0)

        soft = self.client.post(
            "/os/transactions",
            json={
                "user_id": self.uid,
                "account_id": self.aid,
                "amount": -50_000,
                "category": "Di chuyển",
                "date": "2026-09-19",
            },
        )
        tid2 = soft.json()["transaction_id"]
        deleted = self.client.delete(f"/os/transactions/{tid2}")
        self.assertEqual(deleted.status_code, 200, deleted.text)
        self.assertEqual(deleted.json()["status"], "hidden")
        # Still get-able
        self.assertEqual(self.client.get(f"/os/transactions/{tid2}").status_code, 200)

    def test_split_valid_sum_ok(self):
        r = self.client.post(
            "/os/transactions",
            json={
                "user_id": self.uid,
                "account_id": self.aid,
                "amount": -500_000,
                "category": "Mua sắm",
                "date": "2026-09-21",
                "merchant": "Shopee",
                "splits": [
                    {"amount": -300_000, "category": "Mua sắm", "note": "đồ gia dụng"},
                    {"amount": -200_000, "category": "Ăn uống"},
                ],
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        tx = r.json()
        self.assertTrue(tx["is_split"])
        self.assertEqual(len(tx["splits"]), 2)
        self.assertAlmostEqual(
            sum(s["amount"] for s in tx["splits"]), tx["amount"], places=2
        )

        # Replace via POST /split
        tid = tx["transaction_id"]
        split = self.client.post(
            f"/os/transactions/{tid}/split",
            json={
                "splits": [
                    {"amount": -100_000, "category": "Di chuyển"},
                    {"amount": -150_000, "category": "Siêu thị"},
                    {"amount": -250_000, "category": "Mua sắm"},
                ],
                "merchant": "Grab+Shopee",
            },
        )
        self.assertEqual(split.status_code, 200, split.text)
        self.assertEqual(len(split.json()["splits"]), 3)
        self.assertEqual(split.json()["merchant"], "Grab+Shopee")
        self.assertTrue(split.json()["is_split"])

    def test_split_mismatch_400(self):
        r = self.client.post(
            "/os/transactions",
            json={
                "user_id": self.uid,
                "account_id": self.aid,
                "amount": -500_000,
                "category": "Mua sắm",
                "date": "2026-09-21",
                "merchant": "Shopee",
                "splits": [
                    {"amount": -300_000, "category": "Mua sắm"},
                    {"amount": -100_000, "category": "Ăn uống"},
                ],
            },
        )
        self.assertEqual(r.status_code, 400, r.text)
        self.assertIn("split", str(r.json().get("detail") or r.text).lower())

        # Tolerance boundary: within 0.01 OK
        ok = self.client.post(
            "/os/transactions",
            json={
                "user_id": self.uid,
                "account_id": self.aid,
                "amount": -100.00,
                "category": "Khác",
                "date": "2026-09-21",
                "splits": [
                    {"amount": -50.005, "category": "A"},
                    {"amount": -49.995, "category": "B"},
                ],
            },
        )
        self.assertEqual(ok.status_code, 201, ok.text)

    def test_csv_parser_still_works_smoke(self):
        r = self.client.post(
            "/parser/csv",
            json={"text": SAMPLE_CSV, "filename": "smoke.csv"},
        )
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertTrue(body.get("ok", True) or "transactions" in body)
        self.assertGreaterEqual(len(body.get("transactions") or []), 1)
        # Module file intact
        csv_src = CSV_PY.read_text(encoding="utf-8")
        self.assertIn("def sanitize_csv_text", csv_src)
        self.assertIn("def vn_category_label", csv_src)
        self.assertIn('@app.post("/parser/csv"', APP_PY.read_text(encoding="utf-8"))

    def test_ui_transactions_page_and_nav(self):
        self.assertTrue(TX_HTML.is_file())
        html = TX_HTML.read_text(encoding="utf-8")
        self.assertIn("/os/transactions", html)
        self.assertIn("split", html.lower())
        self.assertIn("Giao dịch", html)
        self.assertNotIn("oauth", html.lower())
        self.assertNotIn("aggregator", html.lower())

        home = HOME_HTML.read_text(encoding="utf-8")
        self.assertIn('id="navTransactions"', home)
        self.assertIn("/app/transactions", home)

        shell = SHELL_JS.read_text(encoding="utf-8")
        self.assertIn("/app/transactions", shell)

        r = self.client.get("/app/transactions")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Giao dịch", r.text)

        inv = ROOT / "welora" / "api" / "static" / "investments.html"
        self.assertFalse(inv.exists())


if __name__ == "__main__":
    unittest.main()
