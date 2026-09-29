"""Pricing & Entitlements — P1–P3 · P8 · P9 (+ listed P4–P7 plans on config/API)."""

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
PRICING_HTML = ROOT / "welora" / "api" / "static" / "pricing.html"
CONFIG_JSON = ROOT / "config" / "pricing_module.json"
CONFIG_PKG = ROOT / "welora" / "config" / "pricing_module.json"

EXPECTED_CODES = ["FREE", "ACA", "ACA_SV", "OS1", "OS2", "OS2G", "OS3G"]


class TestPricingEntitlementsMvp(unittest.TestCase):
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

    def test_config_json_plans_and_checkout_off(self):
        raw = json.loads(CONFIG_JSON.read_text(encoding="utf-8"))
        pkg = json.loads(CONFIG_PKG.read_text(encoding="utf-8"))
        self.assertEqual(raw, pkg)
        codes = [p["code"] for p in raw["plans"]]
        self.assertEqual(codes, EXPECTED_CODES)
        self.assertFalse(raw["checkout_enabled"])
        self.assertFalse(raw["lifetime"]["enabled"])
        amounts = {
            (p["code"], pr["interval"]): pr["amount"]
            for p in raw["plans"]
            for pr in p["prices"]
        }
        self.assertEqual(amounts[("FREE", "free")], 0)
        self.assertEqual(amounts[("ACA", "month")], 69000)
        self.assertEqual(amounts[("ACA", "year")], 490000)
        self.assertEqual(amounts[("OS1", "month")], 99000)
        self.assertEqual(amounts[("OS1", "year")], 690000)
        aca = next(p for p in raw["plans"] if p["code"] == "ACA")
        self.assertEqual(aca["trial"]["days"], 30)
        self.assertEqual(aca["trial"]["verification"], "phone_otp")
        exp = raw["experiments"][0]
        self.assertEqual(exp["key"], "aca_price_ab")
        self.assertFalse(exp["active"])
        self.assertEqual(exp["variant"], "A")

    def test_pricing_api_shape(self):
        r = self.client.get("/api/core/v1/entitlements/pricing")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["currency"], "VND")
        self.assertFalse(body["checkout_enabled"])
        codes = [p["code"] for p in body["plans"]]
        self.assertEqual(codes, EXPECTED_CODES)
        for p in body["plans"]:
            self.assertTrue(p["sellable"])
        aca = next(p for p in body["plans"] if p["code"] == "ACA")
        month = next(pr for pr in aca["prices"] if pr["interval"] == "month")
        self.assertEqual(month["amount"], 69000)
        self.assertEqual(aca["trial"]["days"], 30)
        self.assertIn("không tư vấn đầu tư", body["disclaimer"])
        self.assertIn("affiliate", body["disclaimer"])
        exps = body["experiments"]
        self.assertTrue(any(e["key"] == "aca_price_ab" and e["active"] is False for e in exps))
        self.assertFalse(body["lifetime"]["enabled"])

    def test_checkout_config_disabled(self):
        r = self.client.get("/api/core/v1/entitlements/checkout/config")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertFalse(body["checkout_enabled"])
        self.assertIn("Sắp mở thanh toán", body["banner"])
        self.assertIn("momo", body["providers"])

    def test_me_defaults_free(self):
        r = self.client.get("/api/core/v1/entitlements/me")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["plan"], "FREE")
        self.assertFalse(body["checkout_enabled"])
        keys = [e["key"] for e in body["entitlements"]]
        self.assertIn("pedia.read", keys)
        self.assertIn("academy.lesson.sample", keys)

    def test_has_entitlement_free(self):
        r = self.client.get("/api/core/v1/entitlements/has", params={"key": "pedia.read"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["allowed"])
        r2 = self.client.get("/api/core/v1/entitlements/has", params={"key": "os.personal"})
        self.assertEqual(r2.status_code, 200)
        self.assertFalse(r2.json()["allowed"])

    def test_trial_aca_otp_stub(self):
        r = self.client.post(
            "/api/core/v1/entitlements/trial/aca/start",
            json={"phone": "+84901234567", "otp_code": "123456", "user_id": "u-trial-1"},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["plan"], "ACA")
        self.assertEqual(body["trial"]["days"], 30)
        self.assertEqual(body["trial"]["verification"], "phone_otp")
        me = self.client.get("/api/core/v1/entitlements/me", params={"user_id": "u-trial-1"})
        self.assertEqual(me.json()["plan"], "ACA")
        has = self.client.get(
            "/api/core/v1/entitlements/has",
            params={"key": "academy.lesson.full", "user_id": "u-trial-1"},
        )
        self.assertTrue(has.json()["allowed"])

    def test_event_bus_and_ab_hook(self):
        r = self.client.post(
            "/api/core/v1/entitlements/events",
            json={"event": "pricing.view", "payload": {"path": "/pricing"}},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["event"]["experiment"]["key"], "aca_price_ab")
        self.assertFalse(body["event"]["experiment"]["active"])
        self.assertEqual(body["event"]["experiment"]["variant"], "A")
        ab = self.client.get("/api/core/v1/entitlements/experiments/aca_price_ab")
        self.assertEqual(ab.status_code, 200)
        self.assertFalse(ab.json()["active"])
        self.assertEqual(ab.json()["variant"], "A")

    def test_pricing_page_deep_link(self):
        for path in ("/pricing", "/pricing/", "/app/pricing"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("Bảng giá", r.text)
            self.assertIn("firewallDisclaimer", r.text)
            self.assertIn("/api/core/v1/entitlements/pricing", r.text)
            self.assertIn("Sắp mở thanh toán", r.text)
            # No hard-coded Approved amounts in HTML/JS source
            self.assertNotIn("69000", r.text)
            self.assertNotIn("490000", r.text)
            self.assertNotIn("99000", r.text)
            self.assertNotIn("690000", r.text)

    def test_pricing_html_file_no_baked_prices(self):
        html = PRICING_HTML.read_text(encoding="utf-8")
        self.assertIn("firewallDisclaimer", html)
        self.assertIn("/api/core/v1/entitlements/pricing", html)
        for amt in ("69000", "49.000", "490000", "99000", "690000", "69.000", "29000", "19000"):
            self.assertNotIn(amt, html)
        self.assertIn("formatVnd", html)
        self.assertIn("plan-change/preview", html)

    def test_health_gate_months_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["service"], "welora")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        self.assertIn("entitlements", b)
        self.assertFalse(b["entitlements"]["checkout_enabled"])
        self.assertEqual(sorted(b["entitlements"]["sellable_plans"]), sorted(EXPECTED_CODES))
        self.assertFalse(b["entitlements"].get("lifetime_enabled", True))

    def test_helper_has_entitlement(self):
        self.assertTrue(ent.has_entitlement(None, "pedia.read"))
        self.assertFalse(ent.has_entitlement(None, "academy.lesson.full"))


if __name__ == "__main__":
    unittest.main()
