"""Pricing P4–P7 — ACA_SV, seats, plan-change/prorate, Lifetime OFF, OS2/OS2G/OS3G."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from welora import entitlements as ent
from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
CONFIG_JSON = ROOT / "config" / "pricing_module.json"


class TestPricingP4P7(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = {
            k: os.environ.get(k)
            for k in ("WELORA_ENV", "WELORA_STORE", "WELORA_LLM_PROVIDER", "WELORA_TRIAL_OTP_STUB")
        }
        os.environ["WELORA_ENV"] = "staging"
        os.environ["WELORA_STORE"] = "sqlite"
        os.environ["WELORA_LLM_PROVIDER"] = "stub"
        os.environ["WELORA_TRIAL_OTP_STUB"] = "1"
        ent.reset_state_for_tests()
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        ent.reset_state_for_tests()
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    # --- P4 ACA_SV ---
    def test_p4_aca_sv_amounts_and_no_lifetime(self):
        raw = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
        sv = next(p for p in raw["plans"] if p["code"] == "ACA_SV")
        amounts = {pr["interval"]: pr["amount"] for pr in sv["prices"]}
        self.assertEqual(amounts["month"], 29000)
        self.assertEqual(amounts["year"], 249000)
        self.assertNotIn("lifetime", amounts)
        self.assertTrue(sv.get("blocks_os"))
        self.assertFalse(sv.get("lifetime_available", True))

        api = self.client.get("/api/core/v1/entitlements/pricing").json()
        sv_api = next(p for p in api["plans"] if p["code"] == "ACA_SV")
        month = next(pr for pr in sv_api["prices"] if pr["interval"] == "month")
        self.assertEqual(month["amount"], 29000)

    def test_p4_student_path_blocks_os(self):
        r = self.client.post(
            "/api/core/v1/entitlements/student/start",
            json={
                "student_id": "SV2026001",
                "verification_method": "edu_vn_email_otp",
                "email": "sv@student.edu.vn",
                "user_id": "u-sv-1",
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["plan"], "ACA_SV")
        self.assertTrue(body["blocks_os"])
        self.assertTrue(body["os_sell_blocked"])
        self.assertFalse(body["lifetime_available"])
        self.assertEqual(body["student"]["free_days"], 365)

        has_full = self.client.get(
            "/api/core/v1/entitlements/has",
            params={"key": "academy.lesson.full", "user_id": "u-sv-1"},
        )
        self.assertTrue(has_full.json()["allowed"])
        has_os = self.client.get(
            "/api/core/v1/entitlements/has",
            params={"key": "os.core", "user_id": "u-sv-1"},
        )
        self.assertFalse(has_os.json()["allowed"])
        has_os2 = self.client.get(
            "/api/core/v1/entitlements/has",
            params={"key": "os.personal", "user_id": "u-sv-1"},
        )
        self.assertFalse(has_os2.json()["allowed"])

        # Plan-change to OS blocked on student path
        blocked = self.client.post(
            "/api/core/v1/entitlements/plan-change/preview",
            json={
                "from_plan": "ACA_SV",
                "to_plan": "OS1",
                "interval": "month",
                "user_id": "u-sv-1",
            },
        )
        self.assertEqual(blocked.status_code, 403)
        detail = blocked.json().get("detail") or blocked.json()
        self.assertEqual(detail["error_code"], "STUDENT_OS_BLOCKED")

    def test_p4_student_id_one_time(self):
        payload = {
            "student_id": "SV-ONCE-99",
            "email": "a@school.edu.vn",
            "user_id": "u-sv-a",
        }
        self.assertEqual(
            self.client.post("/api/core/v1/entitlements/student/start", json=payload).status_code,
            200,
        )
        again = self.client.post(
            "/api/core/v1/entitlements/student/start",
            json={**payload, "user_id": "u-sv-b"},
        )
        self.assertEqual(again.status_code, 409)
        detail = again.json().get("detail") or again.json()
        self.assertEqual(detail["error_code"], "STUDENT_OFFER_USED")

    # --- P5 seats + Founding Family ---
    def test_p5_seat_addon_19k_from_config(self):
        raw = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
        self.assertEqual(raw["seat_addon"]["amount_monthly"], 19000)
        r = self.client.get(
            "/api/core/v1/entitlements/seats/quote",
            params={"extra_seats": 3, "plan_code": "OS2"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["amount_monthly_per_seat"], 19000)
        self.assertEqual(body["amount_monthly_total"], 57000)
        self.assertFalse(body["checkout_enabled"])
        self.assertFalse(body["chargeable"])
        self.assertEqual(body["plan_seat_limit"], 2)

    def test_p5_founding_family_preorder_flag(self):
        r = self.client.get("/api/core/v1/entitlements/founding-family")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["preorder_enabled"])
        self.assertEqual(body["until"], "OS 3.10")
        self.assertEqual(body["activates_as"], "OS1")
        self.assertEqual(body["plans"], ["OS2", "OS2G", "OS3G"])
        self.assertFalse(body["checkout_enabled"])

        api = self.client.get("/api/core/v1/entitlements/pricing").json()
        self.assertTrue(api["founding_family"]["preorder_enabled"])

    def test_p5_os_family_seat_limits(self):
        raw = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
        limits = {p["code"]: p["seat_limit"] for p in raw["plans"]}
        self.assertEqual(limits["OS2"], 2)
        self.assertEqual(limits["OS2G"], 5)
        self.assertEqual(limits["OS3G"], 9)

    # --- P6 upgrade/downgrade prorate ---
    def test_p6_upgrade_prorate_preview_checkout_off(self):
        r = self.client.post(
            "/api/core/v1/entitlements/plan-change/preview",
            json={
                "from_plan": "ACA",
                "to_plan": "OS1",
                "interval": "month",
                "days_remaining": 15,
                "days_in_period": 30,
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["direction"], "upgrade")
        self.assertEqual(body["effective"], "immediate")
        self.assertFalse(body["checkout_enabled"])
        self.assertFalse(body["chargeable"])
        # ACA 69000 → OS1 99000, half period: credit 34500, charge 49500, due 15000
        self.assertEqual(body["amount_from"], 69000)
        self.assertEqual(body["amount_to"], 99000)
        self.assertEqual(body["prorate_due"], 15000)

    def test_p6_downgrade_next_period(self):
        r = self.client.post(
            "/api/core/v1/entitlements/plan-change/preview",
            json={
                "from_plan": "OS1",
                "to_plan": "ACA",
                "interval": "month",
                "days_remaining": 10,
                "days_in_period": 30,
            },
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["direction"], "downgrade")
        self.assertEqual(body["effective"], "next_period")
        self.assertEqual(body["prorate_due"], 0)
        self.assertFalse(body["checkout_enabled"])

    # --- P7 Lifetime OFF ---
    def test_p7_lifetime_flag_off(self):
        raw = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
        self.assertFalse(raw["lifetime"]["enabled"])
        self.assertFalse(raw["lifetime"]["sellable"])
        r = self.client.get("/api/core/v1/entitlements/lifetime")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["allowed"])
        self.assertFalse(body["lifetime_enabled"])
        self.assertEqual(body["unlock_at"], "M3.2")
        self.assertFalse(body["checkout_enabled"])

        blocked = self.client.post(
            "/api/core/v1/entitlements/plan-change/preview",
            json={"from_plan": "OS1", "to_plan": "OS2", "interval": "lifetime"},
        )
        self.assertEqual(blocked.status_code, 400)
        detail = blocked.json().get("detail") or blocked.json()
        self.assertEqual(detail["error_code"], "LIFETIME_OFF")

    # --- OS2 / OS2G / OS3G present ---
    def test_os_family_prices_in_config_and_api(self):
        raw = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
        amounts = {
            (p["code"], pr["interval"]): pr["amount"]
            for p in raw["plans"]
            for pr in p["prices"]
        }
        self.assertEqual(amounts[("OS2", "month")], 139000)
        self.assertEqual(amounts[("OS2", "year")], 990000)
        self.assertEqual(amounts[("OS2G", "month")], 179000)
        self.assertEqual(amounts[("OS2G", "year")], 1290000)
        self.assertEqual(amounts[("OS3G", "month")], 229000)
        self.assertEqual(amounts[("OS3G", "year")], 1690000)
        # Lifetime amounts wired but not sellable
        self.assertEqual(amounts[("OS2", "lifetime")], 3490000)
        self.assertEqual(amounts[("OS3G", "lifetime")], 5990000)

        api = self.client.get("/api/core/v1/entitlements/pricing").json()
        codes = [p["code"] for p in api["plans"]]
        self.assertIn("OS2", codes)
        self.assertIn("OS2G", codes)
        self.assertIn("OS3G", codes)
        os2 = next(p for p in api["plans"] if p["code"] == "OS2")
        life = next(pr for pr in os2["prices"] if pr["interval"] == "lifetime")
        self.assertFalse(life.get("sellable", True))
        self.assertTrue(life.get("locked"))

    def test_gate_hard_deny_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        self.assertFalse(h["entitlements"]["checkout_enabled"])


if __name__ == "__main__":
    unittest.main()
