"""P0 OS — Categories first-class Fixed/Variable/Goals + tags (ticket 3/4).

Hard bans untouched: Open Banking · Investments UI · Hard Deny R01–R09 ·
TARGET_MONTHS / gate_months=3 · CORE · Mode C / L-* · Budget envelopes (ticket 4).
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
    InMemoryAccountStore,
    reset_account_store,
    use_store as use_account_store,
)
from welora.os_categories import (
    DEFAULT_CATEGORIES,
    InMemoryCategoryStore,
    KIND_FIXED,
    KIND_GOALS,
    KIND_VARIABLE,
    PERSONA_BUDGET_TAGS_UNION,
    persona_budget_tags_union,
    reset_category_store,
    use_store as use_category_store,
)
from welora.os_transactions import (
    InMemoryTransactionStore,
    reset_transaction_store,
    use_store as use_tx_store,
)
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
CAT_HTML = ROOT / "welora" / "api" / "static" / "categories.html"
HOME_HTML = ROOT / "welora" / "api" / "static" / "home.html"
SHELL_JS = ROOT / "welora" / "api" / "static" / "shell.js"


class TestP2OsCategoriesCrud(unittest.TestCase):
    def setUp(self) -> None:
        reset_all_stores()
        use_category_store(InMemoryCategoryStore())
        reset_category_store()
        use_account_store(InMemoryAccountStore())
        reset_account_store()
        use_tx_store(InMemoryTransactionStore())
        reset_transaction_store()
        self.client = TestClient(create_app())
        self.uid = "user_categories_p0_01"

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

    def test_defaults_endpoint_has_three_kinds(self):
        r = self.client.get("/os/categories/defaults")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertGreaterEqual(body["count"], 10)
        kinds = {d["kind"] for d in body["defaults"]}
        self.assertEqual(kinds, {KIND_FIXED, KIND_VARIABLE, KIND_GOALS})
        self.assertIn("Cố định", body["kinds"].values())
        self.assertIn("Biến đổi", body["kinds"].values())
        self.assertIn("Mục tiêu", body["kinds"].values())

    def test_seed_defaults_list_shows_fixed_variable_goals(self):
        r = self.client.post(
            "/os/categories/seed-defaults",
            json={"user_id": self.uid},
        )
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["count"], len(DEFAULT_CATEGORIES))

        # Idempotent
        r2 = self.client.post(
            "/os/categories/seed-defaults",
            json={"user_id": self.uid},
        )
        self.assertEqual(r2.status_code, 200, r2.text)
        self.assertEqual(r2.json()["count"], 0)
        self.assertEqual(len(r2.json()["skipped"]), len(DEFAULT_CATEGORIES))

        lst = self.client.get(f"/os/categories?user_id={self.uid}")
        self.assertEqual(lst.status_code, 200, lst.text)
        cats = lst.json()["categories"]
        kinds = {c["kind"] for c in cats}
        self.assertEqual(kinds, {KIND_FIXED, KIND_VARIABLE, KIND_GOALS})
        self.assertGreaterEqual(lst.json()["count"], 10)
        # VI labels present on items
        labels = {c.get("kind_label_vi") for c in cats}
        self.assertTrue({"Cố định", "Biến đổi", "Mục tiêu"} <= labels)

    def test_tags_include_p1_p6_budget_tag_union(self):
        union = set(persona_budget_tags_union())
        self.assertEqual(union, set(PERSONA_BUDGET_TAGS_UNION))
        self.assertTrue(union)

        r = self.client.post(
            "/os/categories/seed-defaults",
            json={"user_id": self.uid},
        )
        self.assertEqual(r.status_code, 200, r.text)
        cats = self.client.get(f"/os/categories?user_id={self.uid}").json()["categories"]
        seeded_tags: set[str] = set()
        for c in cats:
            seeded_tags.update(c.get("tags") or [])
        missing = union - seeded_tags
        self.assertEqual(
            missing,
            set(),
            f"seeded tags missing P1–P6 budget_tags: {sorted(missing)}",
        )

        defaults = self.client.get("/os/categories/defaults").json()
        self.assertEqual(set(defaults["persona_budget_tags"]), union)

    def test_crud_create_list_get_patch(self):
        r = self.client.post(
            "/os/categories",
            json={
                "user_id": self.uid,
                "name": "Ăn vặt",
                "kind": "variable",
                "tags": ["an_vat", "an_uong"],
                "note": "Thử nghiệm",
            },
        )
        self.assertEqual(r.status_code, 201, r.text)
        cat = r.json()
        self.assertEqual(cat["name"], "Ăn vặt")
        self.assertEqual(cat["kind"], "variable")
        self.assertEqual(cat["status"], "active")
        self.assertIn("an_uong", cat["tags"])
        cid = cat["category_id"]

        lst = self.client.get(f"/os/categories?user_id={self.uid}")
        self.assertEqual(lst.status_code, 200)
        self.assertEqual(lst.json()["count"], 1)

        got = self.client.get(f"/os/categories/{cid}")
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["note"], "Thử nghiệm")

        patch = self.client.patch(
            f"/os/categories/{cid}",
            json={"name": "Ăn vặt cuối tuần", "tags": ["an_uong"], "note": "ok"},
        )
        self.assertEqual(patch.status_code, 200, patch.text)
        self.assertEqual(patch.json()["name"], "Ăn vặt cuối tuần")
        self.assertEqual(patch.json()["tags"], ["an_uong"])

    def test_disable_without_history(self):
        r = self.client.post(
            "/os/categories",
            json={"user_id": self.uid, "name": "Temp", "kind": "fixed", "tags": ["tmp"]},
        )
        self.assertEqual(r.status_code, 201, r.text)
        cid = r.json()["category_id"]

        dis = self.client.post(f"/os/categories/{cid}/disable", json={})
        self.assertEqual(dis.status_code, 200, dis.text)
        self.assertEqual(dis.json()["status"], "disabled")
        self.assertTrue(dis.json().get("disabled"))

        lst = self.client.get(f"/os/categories?user_id={self.uid}")
        self.assertEqual(lst.json()["count"], 0)

        lst2 = self.client.get(
            f"/os/categories?user_id={self.uid}&include_disabled=true"
        )
        self.assertEqual(lst2.json()["count"], 1)
        self.assertEqual(lst2.json()["categories"][0]["status"], "disabled")

    def _seed_account_and_tx(self, category_name: str) -> tuple[str, str]:
        acc = self.client.post(
            "/os/accounts",
            json={
                "user_id": self.uid,
                "name": "Ví test",
                "type": "chi_tieu_hang_ngay",
                "opening_balance": 1_000_000,
                "consent_ack": True,
                "source": "manual",
            },
        )
        self.assertEqual(acc.status_code, 201, acc.text)
        aid = acc.json()["account_id"]
        tx = self.client.post(
            "/os/transactions",
            json={
                "user_id": self.uid,
                "account_id": aid,
                "amount": -50_000,
                "category": category_name,
                "date": "2026-09-01",
                "consent_ack": True,
            },
        )
        self.assertEqual(tx.status_code, 201, tx.text)
        return aid, tx.json()["transaction_id"]

    def test_disable_with_history_requires_reassign_then_migrates(self):
        # Seed two categories
        a = self.client.post(
            "/os/categories",
            json={"user_id": self.uid, "name": "Ăn uống", "kind": "variable", "tags": ["an_uong"]},
        )
        b = self.client.post(
            "/os/categories",
            json={"user_id": self.uid, "name": "Khác", "kind": "variable", "tags": ["khac"]},
        )
        self.assertEqual(a.status_code, 201, a.text)
        self.assertEqual(b.status_code, 201, b.text)
        cid_a = a.json()["category_id"]
        cid_b = b.json()["category_id"]

        self._seed_account_and_tx("Ăn uống")

        # Disable without reassign → 400
        bad = self.client.post(f"/os/categories/{cid_a}/disable", json={})
        self.assertEqual(bad.status_code, 400, bad.text)
        detail = bad.json().get("detail") or bad.json()
        if isinstance(detail, dict):
            self.assertTrue(detail.get("reassign_required") or "reassign" in str(detail).lower())
        else:
            self.assertIn("reassign", str(detail).lower())

        # Still active
        self.assertEqual(
            self.client.get(f"/os/categories/{cid_a}").json()["status"],
            "active",
        )

        # Disable with reassign → migrates tx category string
        ok = self.client.post(
            f"/os/categories/{cid_a}/disable",
            json={"reassign_to": cid_b},
        )
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(ok.json()["status"], "disabled")
        self.assertGreaterEqual(ok.json().get("migrated", 0), 1)

        txs = self.client.get(f"/os/transactions?user_id={self.uid}")
        self.assertEqual(txs.status_code, 200, txs.text)
        items = txs.json()["transactions"]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["category"], "Khác")

    def test_reassign_endpoint_then_disable(self):
        a = self.client.post(
            "/os/categories",
            json={"user_id": self.uid, "name": "Grab", "kind": "variable", "tags": ["di_chuyen"]},
        )
        b = self.client.post(
            "/os/categories",
            json={"user_id": self.uid, "name": "Di chuyển", "kind": "variable", "tags": ["di_chuyen"]},
        )
        cid_a, cid_b = a.json()["category_id"], b.json()["category_id"]
        self._seed_account_and_tx("Grab")

        re = self.client.post(
            f"/os/categories/{cid_a}/reassign",
            json={"reassign_to": cid_b},
        )
        self.assertEqual(re.status_code, 200, re.text)
        self.assertGreaterEqual(re.json().get("migrated", 0), 1)

        txs = self.client.get(f"/os/transactions?user_id={self.uid}").json()["transactions"]
        self.assertEqual(txs[0]["category"], "Di chuyển")

        # Now disable without reassign works (no history left under Grab)
        dis = self.client.post(f"/os/categories/{cid_a}/disable", json={})
        self.assertEqual(dis.status_code, 200, dis.text)
        self.assertEqual(dis.json()["status"], "disabled")

    def test_split_category_reassigned_on_disable(self):
        a = self.client.post(
            "/os/categories",
            json={"user_id": self.uid, "name": "Siêu thị", "kind": "variable", "tags": ["sieu_thi"]},
        )
        b = self.client.post(
            "/os/categories",
            json={"user_id": self.uid, "name": "Khác", "kind": "variable", "tags": ["khac"]},
        )
        cid_a, cid_b = a.json()["category_id"], b.json()["category_id"]

        acc = self.client.post(
            "/os/accounts",
            json={
                "user_id": self.uid,
                "name": "TK",
                "type": "chi_tieu_hang_ngay",
                "opening_balance": 0,
                "consent_ack": True,
            },
        )
        aid = acc.json()["account_id"]
        tx = self.client.post(
            "/os/transactions",
            json={
                "user_id": self.uid,
                "account_id": aid,
                "amount": -100_000,
                "category": "Siêu thị",
                "date": "2026-09-02",
                "consent_ack": True,
                "splits": [
                    {"amount": -60_000, "category": "Siêu thị"},
                    {"amount": -40_000, "category": "Khác"},
                ],
            },
        )
        self.assertEqual(tx.status_code, 201, tx.text)
        tid = tx.json()["transaction_id"]

        dis = self.client.post(
            f"/os/categories/{cid_a}/disable",
            json={"reassign_to": cid_b},
        )
        self.assertEqual(dis.status_code, 200, dis.text)

        got = self.client.get(f"/os/transactions/{tid}").json()
        self.assertEqual(got["category"], "Khác")
        split_cats = [s["category"] for s in got["splits"]]
        self.assertEqual(split_cats, ["Khác", "Khác"])

    def test_ui_page_and_nav(self):
        self.assertTrue(CAT_HTML.is_file(), "categories.html missing")
        html = CAT_HTML.read_text(encoding="utf-8")
        self.assertIn("Danh mục", html)
        self.assertIn("/os/categories", html)

        home = HOME_HTML.read_text(encoding="utf-8")
        self.assertIn('id="navCategories"', home)
        self.assertIn("/app/categories", home)

        shell = SHELL_JS.read_text(encoding="utf-8")
        self.assertIn("/app/categories", shell)

        ui = self.client.get("/app/categories")
        self.assertEqual(ui.status_code, 200, ui.text)
        self.assertIn("Danh mục", ui.text)

    def test_smoke_accounts_and_transactions_still_importable(self):
        # Shared fixtures / modules still load
        from tests import test_p2_os_accounts_crud as acc_mod
        from tests import test_p2_os_transactions_manual_split as tx_mod

        self.assertTrue(hasattr(acc_mod, "TestP2OsAccountsCrud"))
        self.assertTrue(hasattr(tx_mod, "TestP2OsTransactionsManualSplit"))

        # One CSV parser smoke (untouched)
        from welora.csv_parser import parse_csv_text

        sample = "date,amount,description\n2026-01-15,-50000,Cafe\n"
        rows = parse_csv_text(sample)
        self.assertGreaterEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
