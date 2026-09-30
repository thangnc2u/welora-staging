"""Checkout VietQR P0 — CK-01…CK-10 (Phụ lục PRD Checkout thanh toán VietQR).

All tests use the in-process MockPaymentProvider with an obviously fake
checksum key. No network, never real payOS.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests._db_target import db_env

from welora import auth as auth_svc
from welora import checkout as co
from welora import entitlements as ent
from welora import mailer
from welora.api.app import create_app
from welora.db.connection import get_connection
from welora.payments import provider as prov
from welora.payments.provider import MockPaymentProvider, PayOSProvider, SePayProvider
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
FAKE_CHECKSUM = "fake-test-checksum-key-NOT-REAL"
ENV_KEYS = (
    "WELORA_ENV", "WELORA_STORE", "WELORA_DB_URL", "WELORA_CHECKOUT_ENABLED", "PAYMENT_PROVIDER",
    "MOCK_PAYMENT_CHECKSUM_KEY", "WELORA_MAIL_SYNC", "PAYOS_CLIENT_ID", "PAYOS_API_KEY",
    "PAYOS_CHECKSUM_KEY", "PAYOS_DESCRIPTION_MAX_LEN", "WELORA_PUBLIC_BASE_URL", "WELORA_GUEST_DEMO",
    "WELORA_ADMIN_TOTP_SECRETS",
)
# P1 (mục 9): admin APIs need a TOTP session — obviously fake test secret.
FAKE_TOTP_SECRET = "JBSWY3DPEHPK3PXPFAKEFAKEFAKEFAKE"


class _Base(unittest.TestCase):
    enabled = True

    def setUp(self) -> None:
        self.prev = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ("PAYOS_CLIENT_ID", "PAYOS_API_KEY", "PAYOS_CHECKSUM_KEY", "PAYOS_DESCRIPTION_MAX_LEN"):
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="welora-ck-")
        os.environ["WELORA_ENV"] = "staging"
        os.environ.update(db_env(self.tmp))  # sqlite (default) or WELORA_TEST_POSTGRES_URL
        os.environ["WELORA_GUEST_DEMO"] = "0"
        os.environ["PAYMENT_PROVIDER"] = "mock"
        os.environ["MOCK_PAYMENT_CHECKSUM_KEY"] = FAKE_CHECKSUM
        os.environ["WELORA_MAIL_SYNC"] = "1"
        os.environ["WELORA_PUBLIC_BASE_URL"] = "https://welora-test.invalid"
        if self.enabled:
            os.environ["WELORA_CHECKOUT_ENABLED"] = "1"
        else:
            os.environ.pop("WELORA_CHECKOUT_ENABLED", None)
        ent.reset_state_for_tests()
        co.reset_for_tests()
        self.mock = MockPaymentProvider(FAKE_CHECKSUM)
        prov.set_provider(self.mock)
        self.mails: list[tuple[str, str, str]] = []
        mailer.set_sender(lambda to, s, b: self.mails.append((to, s, b)))
        self.client = TestClient(create_app())
        u = auth_svc.register_guest(email="buyer@example.test", password="Passw0rd!x")
        self.uid, self.token = u["user_id"], u["token"]
        self.h = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self) -> None:
        prov.reset_provider()
        mailer.set_sender(None)
        ent.reset_state_for_tests()
        co.reset_for_tests()
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    # helpers
    def order(self, plan="ACA", cycle="month", **extra):
        r = self.client.post(
            "/api/checkout/v1/orders",
            json={"plan_id": plan, "billing_cycle": cycle, "agree_terms": True, **extra},
            headers=self.h,
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def db_order(self, code):
        conn = get_connection(None)
        try:
            return dict(conn.execute("SELECT * FROM orders WHERE order_code=?", (code,)).fetchone())
        finally:
            conn.close()

    def grants(self):
        return [e for e in ent.list_events(500) if e["event"] == "subscription_granted"]

    def webhook(self, payload):
        return self.client.post("/api/checkout/v1/webhook/payos", json=payload)


class TestCheckoutFlagOff(_Base):
    enabled = False

    def test_flag_off_returns_403(self):
        self.assertFalse(json.loads((ROOT / "config" / "pricing_module.json").read_text())["checkout_enabled"])
        cfg = self.client.get("/api/checkout/v1/config").json()
        self.assertFalse(cfg["checkout_enabled"])
        r = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA"}, headers=self.h)
        self.assertEqual(r.status_code, 403)
        r = self.client.post(
            "/api/checkout/v1/orders", json={"plan_id": "ACA", "agree_terms": True}, headers=self.h
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"]["error_code"], "CHECKOUT_DISABLED")
        self.assertEqual(self.client.get("/api/checkout/v1/orders/1000001", headers=self.h).status_code, 403)
        wh = self.webhook(self.mock.signed_webhook({"orderCode": 1, "amount": 1, "reference": "X", "code": "00"}))
        self.assertEqual(wh.status_code, 403)
        self.assertEqual(co.reconcile_once(), {"skipped": "checkout_disabled"})
        h = self.client.get("/health").json()
        self.assertFalse(h["entitlements"]["checkout_enabled"])
        self.assertFalse(self.client.get("/api/core/v1/entitlements/pricing").json()["checkout_enabled"])


class TestCheckoutVietQR(_Base):
    # --- CK-02 / CK-04 ---------------------------------------------------
    def test_login_required(self):
        r = self.client.post("/api/checkout/v1/orders", json={"plan_id": "ACA", "agree_terms": True})
        self.assertEqual(r.status_code, 401)

    def test_terms_required(self):
        r = self.client.post("/api/checkout/v1/orders", json={"plan_id": "ACA"}, headers=self.h)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["detail"]["error_code"], "TERMS_REQUIRED")

    def test_server_prices_and_client_amount_ignored(self):
        o = self.order("ACA", "month", amount=1000)  # tampered client amount
        expected = ent.price_amount("ACA", "month")
        self.assertEqual(o["amount"], expected)
        self.assertEqual(o["list_price"], expected)
        self.assertNotEqual(o["amount"], 1000)
        self.assertEqual(self.mock.links[o["order_code"]]["amount"], expected)
        row = self.db_order(o["order_code"])
        self.assertEqual(row["amount"], expected)
        self.assertEqual(row["status"], "PENDING")
        self.assertEqual(o["description"], f"WELORA{o['order_code']}")
        self.assertAlmostEqual(o["expires_at_ts"] - time.time(), 15 * 60, delta=10)
        y = self.order("OS1", "year", amount=1)
        self.assertEqual(y["amount"], ent.price_amount("OS1", "year"))

    def test_quote_ck03(self):
        r = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA", "billing_cycle": "year", "amount": 5}, headers=self.h)
        self.assertEqual(r.status_code, 200)
        q = r.json()
        self.assertEqual(q["amount"], ent.price_amount("ACA", "year"))
        self.assertEqual(q["year_savings"], ent.price_amount("ACA", "month") * 12 - ent.price_amount("ACA", "year"))
        self.assertIn("expected_period_end", q)
        self.assertEqual(q["discount"], 0)

    def test_lifetime_free_and_student_rules(self):
        r = self.client.post("/api/checkout/v1/orders", json={"plan_id": "OS1", "billing_cycle": "lifetime", "agree_terms": True}, headers=self.h)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"]["error_code"], "LIFETIME_OFF")
        r = self.client.post("/api/checkout/v1/orders", json={"plan_id": "FREE", "agree_terms": True}, headers=self.h)
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/api/checkout/v1/orders", json={"plan_id": "ACA_SV", "agree_terms": True}, headers=self.h)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.json()["detail"]["error_code"], "STUDENT_REQUIRED")

    def test_description_fallback(self):
        self.assertEqual(co.build_description(1000001, max_len=25), "WELORA1000001")
        self.assertEqual(co.build_description(1234567890123, max_len=9), "WL7890123")
        self.assertLessEqual(len(co.build_description(1234567890123, max_len=9)), 9)
        os.environ["PAYOS_DESCRIPTION_MAX_LEN"] = "9"
        o = self.order()
        self.assertEqual(o["description"], "WL" + str(o["order_code"])[-7:])
        self.assertEqual(self.mock.links[o["order_code"]]["description"], o["description"])

    # --- 1 PENDING per user per plan --------------------------------------
    def test_one_pending_per_user_plan(self):
        a = self.order("ACA")
        b = self.order("ACA")
        self.assertNotEqual(a["order_code"], b["order_code"])
        self.assertEqual(self.db_order(a["order_code"])["status"], "CANCELLED")
        self.assertEqual(self.db_order(b["order_code"])["status"], "PENDING")
        self.assertIn(("cancel", a["order_code"]), self.mock.calls)
        c = self.order("OS1")  # other plan unaffected
        self.assertEqual(self.db_order(b["order_code"])["status"], "PENDING")
        self.assertEqual(self.db_order(c["order_code"])["status"], "PENDING")

    # --- webhook CK-07 -----------------------------------------------------
    def test_bad_signature_rejected(self):
        o = self.order()
        payload = self.mock.simulate_transfer(o["order_code"], o["amount"])
        payload["signature"] = "0" * 64
        r = self.webhook(payload)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error_code"], "INVALID_SIGNATURE")
        forged = dict(self.mock.simulate_transfer(o["order_code"], o["amount"]))
        forged["data"] = {**forged["data"], "amount": o["amount"] * 10}  # tampered data, old signature
        self.assertEqual(self.webhook(forged).status_code, 400)
        self.assertEqual(self.db_order(o["order_code"])["status"], "PENDING")
        self.assertEqual(self.grants(), [])
        self.assertFalse(ent.has_entitlement(self.uid, "academy.lesson.full"))
        conn = get_connection(None)
        try:
            n = conn.execute("SELECT COUNT(*) AS n FROM payment_events WHERE signature_valid=0").fetchone()["n"]
        finally:
            conn.close()
        self.assertEqual(n, 2)

    def test_same_webhook_three_times_grants_once(self):
        o = self.order()
        payload = self.mock.simulate_transfer(o["order_code"], o["amount"])
        results = [self.webhook(payload) for _ in range(3)]
        self.assertTrue(all(r.status_code == 200 for r in results))
        self.assertEqual(results[0].json()["status"], "PAID")
        self.assertTrue(results[1].json().get("duplicate"))
        self.assertTrue(results[2].json().get("duplicate"))
        self.assertEqual(len(self.grants()), 1)
        self.assertEqual(len(self.mails), 1)
        row = self.db_order(o["order_code"])
        self.assertEqual(row["status"], "PAID")
        self.assertEqual(row["amount_paid"], o["amount"])
        self.assertTrue(ent.has_entitlement(self.uid, "academy.lesson.full"))
        # subscription extended by exactly one period
        conn = get_connection(None)
        try:
            sub = dict(conn.execute("SELECT * FROM subscriptions WHERE user_id=?", (self.uid,)).fetchone())
        finally:
            conn.close()
        self.assertAlmostEqual(co._ts(sub["current_period_end"]) - co._ts(sub["current_period_start"]), 31 * 86400, delta=3 * 86400)

    def test_receipt_email_ck09(self):
        o = self.order("OS1", "year")
        self.webhook(self.mock.simulate_transfer(o["order_code"], o["amount"]))
        self.assertEqual(len(self.mails), 1)
        to, subject, body = self.mails[0]
        self.assertEqual(to, "buyer@example.test")
        self.assertIn(str(o["order_code"]), subject)
        self.assertIn("không phải hoá đơn VAT", body)
        self.assertIn("Hết hạn", body)
        self.assertIn("OS1", body)

    def test_underpaid_then_topup(self):
        o = self.order()
        r = self.webhook(self.mock.simulate_transfer(o["order_code"], o["amount"] - 10000))
        self.assertEqual(r.json()["status"], "UNDERPAID")
        view = self.client.get(f"/api/checkout/v1/orders/{o['order_code']}", headers=self.h).json()
        self.assertEqual(view["status"], "UNDERPAID")
        self.assertEqual(view["amount_remaining"], 10000)
        self.assertEqual(self.grants(), [])
        self.assertFalse(ent.has_entitlement(self.uid, "academy.lesson.full"))
        r2 = self.webhook(self.mock.simulate_transfer(o["order_code"], 10000))
        self.assertEqual(r2.json()["status"], "PAID")
        self.assertEqual(len(self.grants()), 1)

    def test_unknown_order_webhook_2xx(self):
        # payOS confirm-webhook sends a sample payload (orderCode 123)
        r = self.webhook(self.mock.signed_webhook({"orderCode": 123, "amount": 3000, "reference": "TFSAMPLE", "code": "00", "desc": "success"}))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["unknown_order"])

    # --- CK-08 returnUrl ---------------------------------------------------
    def test_return_url_does_not_grant(self):
        o = self.order()
        for path in ("/app/checkout/return", "/app/checkout/cancel"):
            r = self.client.get(path, params={"orderCode": o["order_code"], "status": "PAID", "code": "00", "cancel": "false"})
            self.assertEqual(r.status_code, 200)
        self.assertEqual(self.db_order(o["order_code"])["status"], "PENDING")
        self.assertEqual(self.grants(), [])
        self.assertFalse(ent.has_entitlement(self.uid, "academy.lesson.full"))
        with self.assertRaises(ValueError):
            co._settle(None, "x", source="return_url", now=time.time())  # PAID only webhook/reconcile

    # --- reconcile ---------------------------------------------------------
    def test_reconcile_sets_paid_when_webhook_lost(self):
        o = self.order()
        self.mock.simulate_transfer(o["order_code"], o["amount"])  # webhook never delivered
        early = co.reconcile_once(now=time.time() + 30)  # < 2 min → not polled
        self.assertEqual(early["checked"], 0)
        s = co.reconcile_once(now=time.time() + 180)
        self.assertEqual(s["paid"], 1)
        self.assertEqual(self.db_order(o["order_code"])["status"], "PAID")
        self.assertEqual(len(self.grants()), 1)
        # later webhook for the same transaction does not re-grant
        link = self.mock.links[o["order_code"]]
        ref = link["transactions"][0]["reference"]
        again = self.webhook(self.mock.simulate_transfer(o["order_code"], o["amount"], reference=ref))
        self.assertEqual(again.status_code, 200)
        self.assertEqual(len(self.grants()), 1)
        co.reconcile_once(now=time.time() + 600)
        self.assertEqual(len(self.grants()), 1)

    def test_reconcile_expires_and_late_payment(self):
        o = self.order()
        s = co.reconcile_once(now=time.time() + 16 * 60)
        self.assertEqual(s["expired"], 1)
        self.assertEqual(self.db_order(o["order_code"])["status"], "EXPIRED")
        r = self.webhook(self.mock.simulate_transfer(o["order_code"], o["amount"]))
        self.assertEqual(r.json()["status"], "PAID")  # EXPIRED → PAID (tiền về muộn, khớp đơn)
        self.assertEqual(len(self.grants()), 1)

    def test_reconcile_callable_loop_not_new_service(self):
        t = co.start_reconcile_loop(interval_s=3600)
        try:
            self.assertIsNotNone(t)
            self.assertTrue(t.daemon)
        finally:
            co.stop_reconcile_loop()

    def test_persisted_subscription_survives_restart(self):
        o = self.order("OS1")
        self.webhook(self.mock.simulate_transfer(o["order_code"], o["amount"]))
        ent.reset_state_for_tests()  # simulate process restart (in-memory state lost)
        self.assertTrue(ent.has_entitlement(self.uid, "os.core"))

    def test_founding_family_preorder_activates_os1(self):
        o = self.order("OS2", "month")
        self.assertTrue(o["is_preorder"])
        self.webhook(self.mock.simulate_transfer(o["order_code"], o["amount"]))
        me = ent.get_me(self.uid)
        self.assertEqual(me["plan"], "OS1")
        self.assertEqual(me["subscription"]["plan_id"], "OS2")

    def test_qr_svg_and_order_owner_only(self):
        o = self.order()
        r = self.client.get(f"/api/checkout/v1/orders/{o['order_code']}/qr.svg", headers=self.h)
        self.assertEqual(r.status_code, 200)
        self.assertIn("image/svg+xml", r.headers["content-type"])
        other = auth_svc.register_guest(email="other@example.test", password="Passw0rd!y")
        oh = {"Authorization": f"Bearer {other['token']}"}
        self.assertEqual(self.client.get(f"/api/checkout/v1/orders/{o['order_code']}", headers=oh).status_code, 404)

    # --- CK-10 admin ------------------------------------------------------
    def _make_admin(self):
        a = auth_svc.register_guest(email="ops@example.test", password="Passw0rd!z")
        conn = get_connection(None)
        try:
            conn.execute("UPDATE users SET role='admin' WHERE user_id=?", (a["user_id"],))
            conn.commit()
        finally:
            conn.close()
        from welora import admin_2fa

        os.environ["WELORA_ADMIN_TOTP_SECRETS"] = f"{a['user_id']}:{FAKE_TOTP_SECRET}"
        ah = {"Authorization": f"Bearer {a['token']}"}
        r = self.client.post("/api/admin/v1/2fa/verify", json={"code": admin_2fa.totp(FAKE_TOTP_SECRET)}, headers=ah)
        assert r.status_code == 200, r.text
        return a["user_id"], ah

    def test_admin_guard(self):
        self.assertEqual(self.client.get("/api/admin/v1/checkout/orders?q=1").status_code, 401)
        self.assertEqual(self.client.get("/api/admin/v1/checkout/orders?q=1", headers=self.h).status_code, 403)

    def test_admin_search_history_manual_grant_audit(self):
        admin_uid, ah = self._make_admin()
        o = self.order()
        res = self.client.get("/api/admin/v1/checkout/orders", params={"q": "buyer@example.test"}, headers=ah).json()
        self.assertIn(o["order_code"], [x["order_code"] for x in res["orders"]])
        res2 = self.client.get("/api/admin/v1/checkout/orders", params={"q": str(o["order_code"])}, headers=ah).json()
        self.assertEqual(len(res2["orders"]), 1)
        no_reason = self.client.post(f"/api/admin/v1/checkout/orders/{o['order_code']}/grant", json={"reason": ""}, headers=ah)
        self.assertEqual(no_reason.status_code, 400)
        self.assertEqual(no_reason.json()["detail"]["error_code"], "REASON_REQUIRED")
        g = self.client.post(
            f"/api/admin/v1/checkout/orders/{o['order_code']}/grant",
            json={"reason": "Sai nội dung CK, đã đối chiếu sao kê"}, headers=ah,
        )
        self.assertEqual(g.status_code, 200)
        self.assertTrue(ent.has_entitlement(self.uid, "academy.lesson.full"))
        self.assertNotEqual(self.db_order(o["order_code"])["status"], "PAID")  # manual never sets PAID
        d = self.client.get(f"/api/admin/v1/checkout/orders/{o['order_code']}", headers=ah).json()
        self.assertEqual(d["audit"][0]["action"], "manual_grant")
        self.assertEqual(d["audit"][0]["admin_user_id"], admin_uid)
        self.assertIn("link.created", [e["event_type"] for e in d["events"]])

    def test_admin_refund_flow(self):
        _, ah = self._make_admin()
        o = self.order()
        self.webhook(self.mock.simulate_transfer(o["order_code"], o["amount"]))
        base = f"/api/admin/v1/checkout/orders/{o['order_code']}/refund"
        self.assertEqual(self.client.post(base, json={"reason": "x"}, headers=ah).status_code, 400)
        r1 = self.client.post(base, json={"reason": "Yêu cầu hoàn trong 7 ngày", "stage": "request"}, headers=ah)
        self.assertEqual(r1.json()["status"], "REFUND_PENDING")
        r2 = self.client.post(base, json={"reason": "Đã chuyển trả MB", "stage": "complete"}, headers=ah)
        self.assertEqual(r2.json()["status"], "REFUNDED")
        self.assertFalse(ent.has_entitlement(self.uid, "academy.lesson.full"))

    # --- constraints ------------------------------------------------------
    def test_order_states_and_constraints(self):
        self.assertEqual(
            co.ORDER_STATES,
            ("PENDING", "PAID", "UNDERPAID", "CANCELLED", "EXPIRED", "REFUND_PENDING", "REFUNDED"),
        )
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        self.assertFalse(h["entitlements"]["lifetime_enabled"])
        self.assertFalse(ent.load_pricing_module()["checkout_enabled"])  # config default stays off

    def test_mock_provider_forbidden_in_production(self):
        os.environ["WELORA_ENV"] = "production"
        r = self.client.post("/api/checkout/v1/orders", json={"plan_id": "ACA", "agree_terms": True}, headers=self.h)
        self.assertEqual(r.status_code, 503)

    def test_checkout_html_no_hardcoded_prices(self):
        html = (ROOT / "welora" / "api" / "static" / "checkout.html").read_text(encoding="utf-8")
        for amt in ("69000", "490000", "99000", "690000", "29000", "139000", "179000", "229000", "69.000"):
            self.assertNotIn(amt, html)
        self.assertIn("/api/core/v1/entitlements/pricing", html)
        self.assertIn("POLL_MS = 3000", html)
        self.assertNotIn("innerHTML", html)
        self.assertNotIn("amount: ", html.split("/api/checkout/v1/orders\", {")[1][:120])
        admin = (ROOT / "welora" / "api" / "static" / "admin-checkout.html").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", admin)


class TestProviderLayer(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ("PAYOS_CLIENT_ID", "PAYOS_API_KEY", "PAYOS_CHECKSUM_KEY", "PAYMENT_PROVIDER"):
            os.environ.pop(k, None)
        prov.reset_provider()

    def tearDown(self) -> None:
        prov.reset_provider()
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_selection_defaults_to_mock_without_keys(self):
        self.assertEqual(prov.provider_name_from_env(), "mock")
        self.assertIsInstance(prov.get_provider(), MockPaymentProvider)

    def test_selection_payos_with_keys_no_network(self):
        os.environ.update({
            "PAYOS_CLIENT_ID": "fake-client-id", "PAYOS_API_KEY": "fake-api-key",
            "PAYOS_CHECKSUM_KEY": "fake-checksum-key",
        })
        self.assertEqual(prov.provider_name_from_env(), "payos")
        p = prov.get_provider()
        self.assertIsInstance(p, PayOSProvider)
        self.assertNotIn("fake-api-key", repr(p))
        self.assertNotIn("fake-client-id", repr(p))
        os.environ["PAYMENT_PROVIDER"] = "mock"
        self.assertEqual(prov.provider_name_from_env(), "mock")

    def test_payos_signature_mục5(self):
        key = "fake-checksum-key"
        sig = prov.signature_payment_request(
            amount=69000, cancel_url="https://x.invalid/c", description="WELORA1000001",
            order_code=1000001, return_url="https://x.invalid/r", checksum_key=key,
        )
        msg = ("amount=69000&cancelUrl=https://x.invalid/c&description=WELORA1000001"
               "&orderCode=1000001&returnUrl=https://x.invalid/r")
        self.assertEqual(sig, hmac.new(key.encode(), msg.encode(), hashlib.sha256).hexdigest())
        data = {"orderCode": 1, "amount": 2, "desc": None, "b": True}
        expect = hmac.new(key.encode(), b"amount=2&b=true&desc=&orderCode=1", hashlib.sha256).hexdigest()
        self.assertEqual(prov.signature_from_data(data, key), expect)
        p = PayOSProvider(client_id="fake-id", api_key="fake-api", checksum_key=key)
        self.assertTrue(p.verify_webhook({"data": data, "signature": expect}))
        self.assertFalse(p.verify_webhook({"data": {**data, "amount": 3}, "signature": expect}))
        self.assertFalse(p.verify_webhook({"data": data}))

    def test_no_sandbox_host_toggle(self):
        self.assertEqual(prov.PAYOS_BASE_URL, "https://api-merchant.payos.vn")
        src = (ROOT / "welora" / "payments" / "provider.py").read_text(encoding="utf-8")
        self.assertNotIn("PAYOS_SANDBOX", src)
        self.assertNotIn("PAYOS_BASE_URL\")", src)

    def test_sepay_slot_not_implemented(self):
        s = SePayProvider()
        with self.assertRaises(NotImplementedError):
            s.get_payment(1)
        self.assertFalse(s.verify_webhook({}))


if __name__ == "__main__":
    unittest.main()
