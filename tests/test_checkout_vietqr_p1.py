"""Checkout VietQR P1 — CK-11…CK-14 · mục 7 renewal/grace · mục 8 refund · mục 9 2FA · mục 10 hooks.

MockPaymentProvider only (fake checksum key); no network, never real payOS.
Fake TOTP secrets only.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests._db_target import db_env

from welora import academy, admin_2fa
from welora import auth as auth_svc
from welora import budget
from welora import checkout as co
from welora import checkout_pricing as cp
from welora import entitlements as ent
from welora import mailer, push, renewal, vietqr
from welora.api.app import create_app
from welora.db.connection import get_connection
from welora.payments import provider as prov
from welora.payments.provider import MockPaymentProvider
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
FAKE_CHECKSUM = "fake-test-checksum-key-NOT-REAL"
FAKE_TOTP = "JBSWY3DPEHPK3PXPFAKEFAKEFAKEFAKE"
FAKE_TOTP_2 = "KRSXG5CTMVRXEZLUFAKEFAKEFAKEFAKE"
DAY = 86400
ENV_KEYS = (
    "WELORA_ENV", "WELORA_STORE", "WELORA_DB_URL", "WELORA_CHECKOUT_ENABLED", "PAYMENT_PROVIDER",
    "MOCK_PAYMENT_CHECKSUM_KEY", "WELORA_MAIL_SYNC", "PAYOS_CLIENT_ID", "PAYOS_API_KEY",
    "PAYOS_CHECKSUM_KEY", "PAYOS_DESCRIPTION_MAX_LEN", "WELORA_PUBLIC_BASE_URL", "WELORA_GUEST_DEMO",
    "WELORA_ADMIN_TOTP_SECRETS", "WELORA_CHECKOUT_TEST_HOOKS", "WELORA_PRICING_MODULE", "WELORA_RENEWAL_JOB",
)


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ("PAYOS_CLIENT_ID", "PAYOS_API_KEY", "PAYOS_CHECKSUM_KEY", "PAYOS_DESCRIPTION_MAX_LEN",
                  "WELORA_ADMIN_TOTP_SECRETS", "WELORA_CHECKOUT_TEST_HOOKS", "WELORA_PRICING_MODULE"):
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="welora-ck1-")
        os.environ.update({
            "WELORA_ENV": "staging", **db_env(self.tmp),  # sqlite (default) or WELORA_TEST_POSTGRES_URL
            "WELORA_GUEST_DEMO": "0", "PAYMENT_PROVIDER": "mock", "MOCK_PAYMENT_CHECKSUM_KEY": FAKE_CHECKSUM,
            "WELORA_MAIL_SYNC": "1", "WELORA_PUBLIC_BASE_URL": "https://welora-test.invalid",
            "WELORA_CHECKOUT_ENABLED": "1",
        })
        ent.reset_state_for_tests()
        co.reset_for_tests()
        academy.reset_academy_store()
        budget.reset_budget_store()
        self.mock = MockPaymentProvider(FAKE_CHECKSUM)
        prov.set_provider(self.mock)
        self.mails: list[tuple[str, str, str]] = []
        mailer.set_sender(lambda to, s, b: self.mails.append((to, s, b)))
        self.pushes: list[tuple[str, str, str, dict]] = []
        push.set_sender(lambda u, t, b, d: self.pushes.append((u, t, b, d)))
        self.client = TestClient(create_app())
        u = auth_svc.register_guest(email="buyer@example.test", password="Passw0rd!x")
        self.uid, self.token = u["user_id"], u["token"]
        self.h = {"Authorization": f"Bearer {self.token}"}

    def tearDown(self) -> None:
        prov.reset_provider()
        mailer.set_sender(None)
        push.set_sender(None)
        ent.reset_state_for_tests()
        co.reset_for_tests()
        academy.reset_academy_store()
        budget.reset_budget_store()
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- helpers ----------------------------------------------------------
    def user(self, email):
        u = auth_svc.register_guest(email=email, password="Passw0rd!q")
        return u["user_id"], {"Authorization": f"Bearer {u['token']}"}

    def order(self, plan="ACA", cycle="month", h=None, expect=200, **extra):
        r = self.client.post(
            "/api/checkout/v1/orders",
            json={"plan_id": plan, "billing_cycle": cycle, "agree_terms": True, **extra},
            headers=h or self.h,
        )
        self.assertEqual(r.status_code, expect, r.text)
        return r.json()

    def pay(self, o, amount=None):
        r = self.client.post(
            "/api/checkout/v1/webhook/payos",
            json=self.mock.simulate_transfer(o["order_code"], o["amount"] if amount is None else amount),
        )
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def q(self, sql, params=()):
        conn = get_connection(None)
        try:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def x(self, sql, params=()):
        conn = get_connection(None)
        try:
            conn.execute(sql, params)
            conn.commit()
        finally:
            conn.close()

    def sub(self, uid=None, plan="ACA"):
        rows = self.q("SELECT * FROM subscriptions WHERE user_id=? AND plan_id=?", (uid or self.uid, plan))
        return rows[0] if rows else None

    def shift_sub(self, days, uid=None, plan="ACA"):
        s = self.sub(uid, plan)
        self.x(
            "UPDATE subscriptions SET current_period_start=?, current_period_end=? WHERE id=?",
            (co._iso(co._ts(s["current_period_start"]) - days * DAY), co._iso(co._ts(s["current_period_end"]) - days * DAY), s["id"]),
        )
        co._refresh_entitlement(uid or self.uid, reason="test")

    def admin(self, email="ops@example.test", secret=FAKE_TOTP, verify=True):
        uid, h = self.user(email)
        self.x("UPDATE users SET role='admin' WHERE user_id=?", (uid,))
        cur = os.environ.get("WELORA_ADMIN_TOTP_SECRETS", "")
        if secret:
            os.environ["WELORA_ADMIN_TOTP_SECRETS"] = ",".join(x for x in (cur, f"{uid}:{secret}") if x)
        if verify:
            r = self.client.post("/api/admin/v1/2fa/verify", json={"code": admin_2fa.totp(secret)}, headers=h)
            self.assertEqual(r.status_code, 200, r.text)
        return uid, h


# ===========================================================================
# CK-11 coupons
# ===========================================================================


class TestCK11Coupons(_Base):
    def mk(self, ah, **body):
        base = {"code": "WELCOME20", "kind": "percent", "value": 20, "reason": "Chiến dịch chào mừng"}
        base.update(body)
        return self.client.post("/api/admin/v1/checkout/coupons", json=base, headers=ah)

    def test_coupon_applied_server_side_and_redeemed_once_per_user(self):
        _, ah = self.admin()
        self.assertEqual(self.mk(ah, plans=["ACA"]).status_code, 200)
        q = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA", "coupon_code": "welcome20"}, headers=self.h).json()
        price = ent.price_amount("ACA", "month")
        self.assertEqual(q["discount"], price * 20 // 100)
        self.assertEqual(q["amount"], price - q["discount"])
        self.assertEqual(q["coupon_code"], "WELCOME20")
        o = self.order(coupon_code="WELCOME20", amount=1)  # client amount ignored
        self.assertEqual(o["amount"], price - q["discount"])
        # replacing my own PENDING order with the same code is fine (1-PENDING rule)
        o = self.order(coupon_code="WELCOME20")
        self.assertEqual(self.pay(o)["status"], "PAID")
        self.assertEqual(len(self.q("SELECT * FROM coupon_redemptions WHERE coupon_code='WELCOME20'")), 1)
        again = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA", "coupon_code": "WELCOME20"}, headers=self.h)
        self.assertEqual(again.json()["detail"]["error_code"], "COUPON_ALREADY_USED")
        lst = self.client.get("/api/admin/v1/checkout/coupons", headers=ah).json()["coupons"]
        self.assertEqual(lst[0]["redeemed"], 1)
        audit = self.q("SELECT * FROM checkout_admin_audit WHERE action='coupon_create'")
        self.assertEqual(len(audit), 1)

    def test_coupon_validity_count_plan_rules(self):
        _, ah = self.admin()
        self.assertEqual(self.mk(ah, code="ONE", max_redemptions=1).status_code, 200)
        self.assertEqual(self.mk(ah, code="OSONLY", plans=["OS1"]).status_code, 200)
        self.assertEqual(self.mk(ah, code="OLD", ends_at="2020-01-01T00:00:00+00:00").status_code, 200)
        self.assertEqual(self.mk(ah, code="LATER", starts_at="2099-01-01T00:00:00+00:00").status_code, 200)
        self.assertEqual(self.mk(ah, code="YEARLY", cycles=["year"]).status_code, 200)
        self.assertEqual(self.mk(ah, code="FIX", kind="fixed", value=10_000).status_code, 200)
        self.assertEqual(self.mk(ah, code="ONE").status_code, 409)
        self.assertEqual(self.mk(ah, code="SVCODE", plans=["ACA_SV"]).json()["detail"]["error_code"], "COUPON_NOT_WITH_STUDENT")

        def err(code, plan="ACA", cycle="month", h=None):
            r = self.client.post("/api/checkout/v1/quote", json={"plan_id": plan, "billing_cycle": cycle, "coupon_code": code}, headers=h or self.h)
            return r.json().get("detail", {}).get("error_code") if r.status_code != 200 else "OK"

        self.assertEqual(err("NOPE"), "COUPON_INVALID")
        self.assertEqual(err("x"), "COUPON_INVALID")
        self.assertEqual(err("OSONLY"), "COUPON_PLAN_NOT_APPLICABLE")
        self.assertEqual(err("OSONLY", plan="OS1"), "OK")
        self.assertEqual(err("OLD"), "COUPON_EXPIRED")
        self.assertEqual(err("LATER"), "COUPON_NOT_STARTED")
        self.assertEqual(err("YEARLY"), "COUPON_CYCLE_NOT_APPLICABLE")
        fx = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA", "coupon_code": "FIX"}, headers=self.h).json()
        self.assertEqual(fx["discount"], 10_000)
        # max_redemptions: user A holds the only slot with a live PENDING order
        o = self.order(coupon_code="ONE")
        self.pay(o)
        _, bh = self.user("b@example.test")
        self.assertEqual(err("ONE", h=bh), "COUPON_EXHAUSTED")
        # deactivate
        self.client.post("/api/admin/v1/checkout/coupons/FIX/active", json={"active": False, "reason": "Hết chiến dịch"}, headers=ah)
        self.assertEqual(err("FIX", h=bh), "COUPON_INVALID")

    def test_coupon_never_stacks_with_student_offer(self):
        _, ah = self.admin()
        self.mk(ah, code="ALL10", value=10)
        r = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA_SV", "coupon_code": "ALL10"}, headers=self.h)
        self.assertEqual(r.json()["detail"]["error_code"], "COUPON_NOT_WITH_STUDENT")
        code, _ = ent.start_student_path(user_id=self.uid, student_id="SV123456", verification_method="edu_vn_email_otp", email="sv@hust.edu.vn")
        self.assertEqual(code, 200)
        r = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA", "coupon_code": "ALL10"}, headers=self.h)
        self.assertEqual(r.json()["detail"]["error_code"], "COUPON_NOT_WITH_STUDENT")

    def test_coupon_never_below_min_amount(self):
        _, ah = self.admin()
        self.mk(ah, code="FREE100", value=100)
        q = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA", "coupon_code": "FREE100"}, headers=self.h).json()
        self.assertEqual(q["amount"], cp.min_amount())


# ===========================================================================
# CK-12 A/B price test
# ===========================================================================


class TestCK12PriceAB(_Base):
    def activate(self):
        raw = json.loads((ROOT / "welora" / "config" / "pricing_module.json").read_text(encoding="utf-8"))
        raw["experiments"][0]["active"] = True
        path = Path(self.tmp) / "pricing.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        os.environ["WELORA_PRICING_MODULE"] = str(path)
        ent.reset_state_for_tests()
        return raw["experiments"][0]

    def test_inactive_everyone_variant_a_config_price(self):
        q = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA"}, headers=self.h).json()
        self.assertEqual(q["price_variant"], "A")
        self.assertEqual(q["list_price"], ent.price_amount("ACA", "month"))
        self.assertEqual(self.q("SELECT * FROM experiment_assignments"), [])

    def test_active_fixed_group_stored_on_order_and_measured(self):
        exp = self.activate()
        b_price = exp["variant_prices"]["B"]["month"]
        seen = {}
        for i in range(12):
            uid, h = self.user(f"ab{i}@example.test")
            v1 = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA"}, headers=h).json()
            v2 = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA"}, headers=h).json()
            self.assertEqual(v1["price_variant"], v2["price_variant"])  # fixed group
            seen[v1["price_variant"]] = (uid, h, v1)
        self.assertEqual(set(seen), {"A", "B"})
        self.assertEqual(seen["B"][2]["list_price"], b_price)
        self.assertEqual(seen["A"][2]["list_price"], ent.price_amount("ACA", "month"))
        # prices endpoint shows the user's variant price
        pr = self.client.get("/api/checkout/v1/prices", headers=seen["B"][1]).json()
        self.assertEqual(pr["plans"]["ACA"]["month"], b_price)
        self.assertEqual(pr["price_variant"], "B")
        ob = self.order(h=seen["B"][1])
        self.assertEqual(ob["price_variant"], "B")
        self.assertEqual(ob["amount"], b_price)
        self.pay(ob)
        # variant does not affect other plans
        self.assertIsNone(self.client.post("/api/checkout/v1/quote", json={"plan_id": "OS1"}, headers=seen["B"][1]).json()["price_variant"])
        _, ah = self.admin()
        st = self.client.get("/api/admin/v1/checkout/experiments/aca_price_ab", headers=ah).json()
        self.assertTrue(st["active"])
        self.assertEqual(st["variants"]["B"]["orders_paid"], 1)
        self.assertEqual(st["variants"]["B"]["conversion_qr_to_paid"], 1.0)


# ===========================================================================
# CK-13 my plan · CK-14 upgrade
# ===========================================================================


class TestCK13MyPlanCK14Upgrade(_Base):
    def test_my_plan_page_and_api(self):
        self.assertEqual(self.client.get("/app/my-plan").status_code, 200)
        self.assertEqual(self.client.get("/api/checkout/v1/my-plan").status_code, 401)
        empty = self.client.get("/api/checkout/v1/my-plan", headers=self.h).json()
        self.assertIsNone(empty["current"])
        o = self.order("ACA", "month")
        self.pay(o)
        d = self.client.get("/api/checkout/v1/my-plan", headers=self.h).json()
        self.assertEqual(d["current"]["plan_id"], "ACA")
        self.assertEqual(d["current"]["status"], "active")
        self.assertEqual(d["current"]["current_period_end"], self.sub()["current_period_end"])
        self.assertEqual(d["history"][0]["order_code"], o["order_code"])
        self.assertTrue(d["history"][0]["refund"]["eligible"])
        self.assertNotIn("qr_code", d["history"][0])
        self.assertEqual(d["actions"]["renew"], {"plan_id": "ACA", "billing_cycle": "month"})
        m, y = ent.price_amount("ACA", "month"), ent.price_amount("ACA", "year")
        self.assertEqual(d["actions"]["switch_to_year"]["savings"], m * 12 - y)
        self.assertIn("OS1", [u["plan_id"] for u in d["actions"]["upgrades"]])
        html = (ROOT / "welora" / "api" / "static" / "my-plan.html").read_text(encoding="utf-8")
        for amt in ("69000", "490000", "99000", "69.000"):
            self.assertNotIn(amt, html)
        self.assertNotIn("innerHTML", html)
        self.assertIn("/api/checkout/v1/my-plan", html)

    def test_upgrade_credit_by_day_rounded_down_1000(self):
        o = self.order("ACA", "month")
        self.pay(o)
        self.shift_sub(10)  # 10 days used
        s = self.sub()
        days_total = round((co._ts(s["current_period_end"]) - co._ts(s["current_period_start"])) / DAY)
        days_left = int((co._ts(s["current_period_end"]) - time.time()) // DAY)
        value = ent.price_amount("ACA", "month")
        expected_credit = int(value * days_left / days_total // 1000) * 1000
        q = self.client.post("/api/checkout/v1/quote", json={"plan_id": "OS1"}, headers=self.h).json()
        self.assertEqual(q["upgrade"]["from_plan"], "ACA")
        self.assertEqual(q["upgrade_credit"], expected_credit)
        self.assertEqual(q["upgrade_credit"] % 1000, 0)
        self.assertGreater(q["upgrade_credit"], 0)
        self.assertEqual(q["amount"], ent.price_amount("OS1", "month") - expected_credit)
        # coupons are not combined with upgrade credit
        r = self.client.post("/api/checkout/v1/quote", json={"plan_id": "OS1", "coupon_code": "ANY10"}, headers=self.h)
        self.assertEqual(r.json()["detail"]["error_code"], "COUPON_NOT_WITH_UPGRADE")
        up = self.order("OS1", "month")
        self.assertEqual(up["upgrade_from_plan"], "ACA")
        self.assertEqual(up["upgrade_credit"], expected_credit)
        self.assertEqual(self.pay(up)["status"], "PAID")
        self.assertEqual(self.sub(plan="ACA")["status"], "expired")
        self.assertEqual(self.sub(plan="OS1")["status"], "active")
        self.assertTrue(ent.has_entitlement(self.uid, "os.personal"))

    def test_downgrade_rejected(self):
        self.pay(self.order("OS1", "month"))
        r = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA"}, headers=self.h)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["detail"]["error_code"], "DOWNGRADE_NOT_SUPPORTED")

    def test_upgrade_credit_function_rounding(self):
        now = time.time()
        sub = {"plan_id": "ACA", "current_period_start": co._iso(now - 7 * DAY), "current_period_end": co._iso(now + 23 * DAY + 3600),
               "last_cycle": "month", "last_list_price": 69000, "last_discount": 0, "last_status": "PAID", "last_amount_paid": 69000}
        c = cp.upgrade_credit(sub, now=now)
        self.assertEqual(c["days_left"], 23)
        self.assertEqual(c["credit"], int(69000 * 23 / 30 // 1000) * 1000)  # 52.900 → 52.000
        self.assertEqual(c["credit"], 52000)
        unpaid = dict(sub, last_status="PENDING", last_amount_paid=0)
        self.assertEqual(cp.upgrade_credit(unpaid, now=now)["credit"], 0)


# ===========================================================================
# mục 7 renewal reminders · grace 7 days · downgrade FREE
# ===========================================================================


class TestRenewalGrace(_Base):
    def setUp(self) -> None:
        super().setUp()
        self.o = self.order("ACA", "month")
        self.pay(self.o)
        self.mails.clear()
        self.end = co._ts(self.sub()["current_period_end"])

    def test_month_schedule_email_push_grace_then_free_data_kept(self):
        budget._BUDGETS[self.uid] = {"period": "2026-09", "lines": [{"category": "food", "amount": 1}]}
        academy._profile(self.uid)["read"].append("N01-01")
        r = renewal.run_once(now=self.end - 5 * DAY)
        self.assertEqual(r["reminders"], 0)
        r = renewal.run_once(now=self.end - 3 * DAY + 60)
        self.assertEqual((r["reminders"], r["emails"], r["pushes"]), (1, 1, 1))
        self.assertIn("hết hạn sau 3 ngày", self.mails[-1][1])
        self.assertIn("/app/checkout/renew#t=", self.mails[-1][2])
        self.assertIn("tiết kiệm", self.mails[-1][2])  # monthly → yearly upsell
        self.assertIn("không tư vấn đầu tư", self.mails[-1][2])
        self.assertEqual(renewal.run_once(now=self.end - 3 * DAY + 120)["reminders"], 0)  # idempotent
        r = renewal.run_once(now=self.end + 60)
        self.assertEqual(r["reminders"], 1)
        self.assertEqual(r["grace"], 1)
        self.assertEqual(self.sub()["status"], "grace")
        # grace: full access + banner (PAY-04)
        orig = self.sub()
        into_grace = (self.end - time.time()) / DAY + 1  # wall-clock now = end + 1 day
        self.shift_sub(into_grace)
        me = ent.get_me(self.uid)
        self.assertTrue(me["in_grace"])
        self.assertTrue(me["renewal_banner"])
        self.assertTrue(ent.has_entitlement(self.uid, "academy.lesson.full"))
        self.x("UPDATE subscriptions SET current_period_start=?, current_period_end=? WHERE id=?",
               (orig["current_period_start"], orig["current_period_end"], orig["id"]))
        co._refresh_entitlement(self.uid, reason="test")
        r = renewal.run_once(now=self.end + 3 * DAY + 60)
        self.assertEqual((r["reminders"], r["pushes"]), (1, 1))
        n_push = len(self.pushes)
        r = renewal.run_once(now=self.end + 7 * DAY + 60)
        self.assertEqual(r["downgraded"], 1)
        self.assertEqual(len(self.pushes), n_push)  # final = email only
        self.assertIn("Free", self.mails[-1][1])
        self.assertIn("vẫn được giữ nguyên", self.mails[-1][2])
        self.assertEqual(self.sub()["status"], "expired")
        self.assertEqual(ent.get_me(self.uid)["plan"], "FREE")
        self.assertFalse(ent.has_entitlement(self.uid, "academy.lesson.full"))
        # data kept (mục 7): budget + learning progress untouched
        self.assertEqual(budget._BUDGETS[self.uid]["period"], "2026-09")
        self.assertIn("N01-01", academy._PROFILES[self.uid]["read"])
        steps = {r["step"]: r["status"] for r in self.q("SELECT step, status FROM renewal_reminders")}
        self.assertEqual(steps, {"d-3": "sent", "d0": "sent", "d+3": "sent", "d+7": "sent"})

    def test_missed_steps_only_latest_sent(self):
        r = renewal.run_once(now=self.end + 3 * DAY + 60)
        self.assertEqual((r["reminders"], r["skipped_steps"]), (1, 2))
        self.assertEqual(len(self.mails), 1)

    def test_year_schedule_d14_email_only(self):
        uid, h = self.user("year@example.test")
        o = self.order("OS1", "year", h=h)
        self.pay(o)
        end = co._ts(self.sub(uid, "OS1")["current_period_end"])
        n_push = len(self.pushes)
        renewal.run_once(now=end - 14 * DAY + 60)
        sid = self.sub(uid, "OS1")["id"]
        rows = self.q("SELECT step, channels FROM renewal_reminders WHERE subscription_id=? AND status='sent'", (sid,))
        self.assertEqual([(r["step"], json.loads(r["channels"])) for r in rows], [("d-14", ["email"])])
        self.assertFalse([p for p in self.pushes[n_push:] if p[0] == uid])
        self.assertNotIn("tiết kiệm", self.mails[-1][2])  # yearly → no upsell line

    def test_magic_link_one_tap_renewal(self):
        renewal.run_once(now=self.end - 3 * DAY + 60)
        body = self.mails[-1][2]
        tok = body.split("/app/checkout/renew#t=")[1].split()[0]
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM renewal_links WHERE token_hash=?", (tok,))[0]["n"], 0)  # hashed
        self.assertEqual(self.client.get("/app/checkout/renew").status_code, 200)
        r = self.client.post("/api/checkout/v1/renew/magic", json={"token": tok})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertEqual(d["order"]["plan_id"], "ACA")
        self.assertEqual(d["order"]["status"], "PENDING")
        sh = {"Authorization": f"Bearer {d['token']}"}
        self.assertEqual(self.client.get(f"/api/checkout/v1/orders/{d['order']['order_code']}", headers=sh).status_code, 200)
        self.assertEqual(self.client.post("/api/checkout/v1/renew/magic", json={"token": tok}).status_code, 410)
        self.assertEqual(self.client.post("/api/checkout/v1/renew/magic", json={"token": "x" * 40}).status_code, 400)
        # early renewal (mục 10): new end = old end + 1 period
        self.pay(d["order"])
        self.assertEqual(co._ts(self.sub()["current_period_end"]), co.add_period(self.end, "month"))

    def test_magic_link_expired_and_admin_refused(self):
        conn = co._conn()
        try:
            link = co.create_renewal_link(conn, user_id=self.uid, plan_id="ACA", billing_cycle="month", now=time.time() - 25 * 3600)
        finally:
            conn.close()
        tok = link.split("#t=")[1]
        self.assertEqual(self.client.post("/api/checkout/v1/renew/magic", json={"token": tok}).json()["detail"]["error_code"], "RENEW_LINK_EXPIRED")
        auid, _ = self.admin(verify=False)
        conn = co._conn()
        try:
            link = co.create_renewal_link(conn, user_id=auid, plan_id="ACA", billing_cycle="month")
        finally:
            conn.close()
        r = self.client.post("/api/checkout/v1/renew/magic", json={"token": link.split("#t=")[1]})
        self.assertEqual(r.status_code, 403)

    def test_loop_in_process_and_disable(self):
        os.environ["WELORA_RENEWAL_JOB"] = "0"
        self.assertIsNone(renewal.start_loop(0.05))
        os.environ["WELORA_RENEWAL_JOB"] = "1"
        th = renewal.start_loop(0.05)
        self.assertTrue(th.is_alive())
        renewal.stop_loop()
        th.join(1)
        self.assertFalse(th.is_alive())

    def test_disabled_flag_skips(self):
        os.environ.pop("WELORA_CHECKOUT_ENABLED")
        self.assertEqual(renewal.run_once(), {"skipped": "checkout_disabled"})


# ===========================================================================
# mục 8 refund (PAY-03)
# ===========================================================================


class TestRefund(_Base):
    def test_user_request_then_admin_complete_revokes(self):
        o = self.order("ACA", "month")
        self.pay(o)
        el = self.client.get(f"/api/checkout/v1/orders/{o['order_code']}/refund-eligibility", headers=self.h).json()
        self.assertTrue(el["eligible"])
        self.assertEqual(el["policy"], "pay03_7d")
        r = self.client.post(f"/api/checkout/v1/orders/{o['order_code']}/refund-request", json={"reason": "Không phù hợp"}, headers=self.h)
        self.assertEqual(r.json()["status"], "REFUND_PENDING")
        self.assertTrue(ent.has_entitlement(self.uid, "academy.lesson.full"))  # kept until refunded
        _, ah = self.admin()
        base = f"/api/admin/v1/checkout/orders/{o['order_code']}/refund"
        self.assertEqual(self.client.post(base, json={"reason": "", "stage": "complete"}, headers=ah).status_code, 400)
        bad = self.client.post(base, json={"reason": "Đã chuyển trả", "stage": "complete", "amount": o["amount"] + 1}, headers=ah)
        self.assertEqual(bad.json()["detail"]["error_code"], "REFUND_AMOUNT_INVALID")
        done = self.client.post(base, json={"reason": "Đã chuyển trả MB", "stage": "complete", "bank_ref": "FT123"}, headers=ah).json()
        self.assertEqual(done["status"], "REFUNDED")
        self.assertEqual(done["refund_amount"], o["amount"])
        row = self.q("SELECT * FROM orders WHERE order_code=?", (o["order_code"],))[0]
        self.assertTrue(row["refunded_at"])
        ev = self.q("SELECT * FROM payment_events WHERE event_type='refund.completed'")
        self.assertEqual(len(ev), 1)
        self.assertEqual(json.loads(ev[0]["raw_payload"])["bank_ref"], "FT123")
        self.assertEqual(self.sub()["status"], "expired")
        self.assertFalse(ent.has_entitlement(self.uid, "academy.lesson.full"))
        actions = [a["action"] for a in self.q("SELECT action FROM checkout_admin_audit")]
        self.assertIn("refund_complete", actions)
        # REFUNDED → nothing further
        self.assertEqual(self.client.post(base, json={"reason": "lặp lại", "stage": "complete"}, headers=ah).status_code, 409)

    def test_window_7_days_and_admin_override_audited(self):
        o = self.order("ACA", "month")
        self.pay(o)
        paid = co._ts(self.q("SELECT paid_at FROM orders WHERE order_code=?", (o["order_code"],))[0]["paid_at"])
        with self.assertRaises(co.CheckoutError) as cm:
            co.request_refund_for_user(self.uid, o["order_code"], "Muốn hoàn", now=paid + 8 * DAY)
        self.assertEqual(cm.exception.error_code, "REFUND_NOT_ELIGIBLE")
        auid, _ = self.admin()
        with self.assertRaises(co.CheckoutError):
            co.admin_refund(admin_uid=auid, order_code=o["order_code"], reason="Khách xin", now=paid + 8 * DAY)
        r = co.admin_refund(admin_uid=auid, order_code=o["order_code"], reason="Ngoại lệ founder duyệt", override=True, now=paid + 8 * DAY)
        self.assertEqual(r["status"], "REFUND_PENDING")
        a = self.q("SELECT detail FROM checkout_admin_audit WHERE action='refund_request'")[0]
        self.assertTrue(json.loads(a["detail"])["override"])

    def test_academy_lessons_after_purchase_counted(self):
        prof = academy._profile(self.uid)
        prof["read"].extend(["N01-01", "N01-02", "N01-03", "N01-04", "N01-05"])  # free samples before buying
        o = self.order("ACA", "month")
        self.pay(o)
        self.assertTrue(co.refund_eligibility_for_user(self.uid, o["order_code"])["eligible"])
        prof["read"].extend(["N02-01", "N02-02", "N02-03", "N03-01"])  # 4 lessons after purchase
        el = co.refund_eligibility_for_user(self.uid, o["order_code"])
        self.assertFalse(el["eligible"])
        self.assertEqual(el["reason_code"], "ACADEMY_USED")

    def test_os_budget_periods(self):
        o = self.order("OS1", "month")
        self.pay(o)
        budget._BUDGET_PERIODS[f"{self.uid}:2026-09"] = {"period": "2026-09"}
        self.assertTrue(co.refund_eligibility_for_user(self.uid, o["order_code"])["eligible"])
        budget._BUDGET_PERIODS[f"{self.uid}:2026-10"] = {"period": "2026-10"}
        el = co.refund_eligibility_for_user(self.uid, o["order_code"])
        self.assertEqual(el["reason_code"], "OS_USED")

    def test_early_renewal_refund_rolls_back_one_period(self):
        o1 = self.order("ACA", "month")
        self.pay(o1)
        end1 = self.sub()["current_period_end"]
        o2 = self.order("ACA", "month")
        self.pay(o2)
        self.assertNotEqual(self.sub()["current_period_end"], end1)
        auid, _ = self.admin()
        co.admin_refund(admin_uid=auid, order_code=o2["order_code"], reason="Hoàn kỳ gia hạn")
        co.admin_refund(admin_uid=auid, order_code=o2["order_code"], reason="Đã chuyển trả", stage="complete")
        s = self.sub()
        self.assertEqual(s["status"], "active")
        self.assertEqual(co._ts(s["current_period_end"]), co._ts(end1))
        self.assertTrue(ent.has_entitlement(self.uid, "academy.lesson.full"))

    def test_preorder_refund_anytime_before_launch(self):
        o = self.order("OS2", "month")
        self.assertTrue(o["is_preorder"])
        self.pay(o)
        paid = co._ts(self.q("SELECT paid_at FROM orders WHERE order_code=?", (o["order_code"],))[0]["paid_at"])
        conn = co._conn()
        try:
            el = co._refund_eligibility(conn, co._get_order(conn, order_code=o["order_code"]), now=paid + 60 * DAY)
        finally:
            conn.close()
        self.assertTrue(el["eligible"])
        self.assertEqual(el["policy"], "preorder_100")

    def test_excess_refund_no_state_change_and_underpaid_refund_no_revoke(self):
        o = self.order("ACA", "month")
        self.pay(o, o["amount"] + 5000)
        auid, _ = self.admin()
        r = co.admin_refund(admin_uid=auid, order_code=o["order_code"], reason="Hoàn phần thừa", stage="excess", amount=5000, bank_ref="FT9")
        self.assertEqual((r["status"], r["refund_amount"]), ("PAID", 5000))
        self.assertTrue(ent.has_entitlement(self.uid, "academy.lesson.full"))
        self.assertEqual(len(self.q("SELECT * FROM payment_events WHERE event_type='refund.excess'")), 1)

    def test_underpaid_refund_does_not_revoke_other_period(self):
        o1 = self.order("ACA", "month")
        self.pay(o1)
        o2 = self.order("ACA", "month")  # renewal, only partly paid
        self.assertEqual(self.pay(o2, 10000)["status"], "UNDERPAID")
        auid, _ = self.admin()
        co.admin_refund(admin_uid=auid, order_code=o2["order_code"], reason="Hoàn phần đã chuyển")
        r = co.admin_refund(admin_uid=auid, order_code=o2["order_code"], reason="Đã chuyển trả", stage="complete")
        self.assertEqual((r["status"], r["refund_amount"]), ("REFUNDED", 10000))
        self.assertEqual(self.sub()["status"], "active")
        self.assertTrue(ent.has_entitlement(self.uid, "academy.lesson.full"))


# ===========================================================================
# mục 9 admin 2FA
# ===========================================================================


class TestAdmin2FA(_Base):
    def test_all_admin_checkout_apis_require_totp_session(self):
        routes = [
            ("GET", "/api/admin/v1/checkout/orders?q=1", None),
            ("GET", "/api/admin/v1/checkout/orders/1000001", None),
            ("POST", "/api/admin/v1/checkout/orders/1000001/grant", {"reason": "abcdef"}),
            ("POST", "/api/admin/v1/checkout/orders/1000001/refund", {"reason": "abcdef"}),
            ("POST", "/api/admin/v1/checkout/reconcile", None),
            ("POST", "/api/admin/v1/checkout/confirm-webhook", {"webhook_url": "https://x.invalid/h"}),
            ("GET", "/api/admin/v1/checkout/coupons", None),
            ("POST", "/api/admin/v1/checkout/coupons", {"code": "AAA", "kind": "fixed", "value": 1}),
            ("POST", "/api/admin/v1/checkout/coupons/AAA/active", {"active": False}),
            ("GET", "/api/admin/v1/checkout/experiments/aca_price_ab", None),
            ("POST", "/api/admin/v1/checkout/renewal/run", {}),
            ("POST", "/api/admin/v1/checkout/test/shift-subscription", {"order_code": 1, "days": 1}),
        ]
        auid, ah = self.admin(secret=None, verify=False)  # admin role, no secret
        for m, url, body in routes:
            self.assertEqual(self.client.request(m, url, json=body).status_code, 401, url)
            self.assertEqual(self.client.request(m, url, json=body, headers=self.h).status_code, 403, url)
            r = self.client.request(m, url, json=body, headers=ah)
            self.assertEqual(r.status_code, 403, url)
            self.assertEqual(r.json()["detail"]["error_code"], "ADMIN_2FA_NOT_ENROLLED")
        os.environ["WELORA_ADMIN_TOTP_SECRETS"] = f"{auid}:{FAKE_TOTP}"
        for m, url, body in routes:
            r = self.client.request(m, url, json=body, headers=ah)
            self.assertEqual(r.status_code, 401, url)
            self.assertEqual(r.json()["detail"]["error_code"], "ADMIN_2FA_REQUIRED")
        ok = self.client.post("/api/admin/v1/2fa/verify", json={"code": admin_2fa.totp(FAKE_TOTP)}, headers=ah)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(self.client.get("/api/admin/v1/checkout/orders?q=1", headers=ah).status_code, 200)
        self.assertTrue(self.client.get("/api/admin/v1/2fa/status", headers=ah).json()["session"])
        self.client.post("/api/admin/v1/2fa/logout", headers=ah)
        self.assertEqual(self.client.get("/api/admin/v1/checkout/orders?q=1", headers=ah).status_code, 401)

    def test_wrong_code_replay_lockout_and_token_binding(self):
        auid, ah = self.admin(verify=False)
        self.assertEqual(self.client.post("/api/admin/v1/2fa/verify", json={"code": "000000"}, headers=ah).json()["detail"]["error_code"], "ADMIN_2FA_INVALID")
        code = admin_2fa.totp(FAKE_TOTP)
        self.assertEqual(self.client.post("/api/admin/v1/2fa/verify", json={"code": code}, headers=ah).status_code, 200)
        r = self.client.post("/api/admin/v1/2fa/verify", json={"code": code}, headers=ah)
        self.assertEqual(r.json()["detail"]["error_code"], "ADMIN_2FA_REPLAY")
        # session is bound to the bearer token: another token of the same admin has no session
        conn = get_connection(None)
        try:
            tok2 = auth_svc._issue_token(conn, auid, kind="device")
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(self.client.get("/api/admin/v1/checkout/orders?q=1", headers={"Authorization": f"Bearer {tok2}"}).status_code, 401)
        self.assertEqual(self.client.get("/api/admin/v1/checkout/orders?q=1", headers=ah).status_code, 200)
        # other admin with own secret cannot use the first admin's code
        buid, bh = self.admin("ops2@example.test", secret=FAKE_TOTP_2, verify=False)
        self.assertEqual(self.client.get("/api/admin/v1/checkout/orders?q=1", headers=bh).status_code, 401)
        for _ in range(5):
            self.client.post("/api/admin/v1/2fa/verify", json={"code": "123456"}, headers=bh)
        r = self.client.post("/api/admin/v1/2fa/verify", json={"code": admin_2fa.totp(FAKE_TOTP_2)}, headers=bh)
        self.assertEqual(r.status_code, 429)
        # a student / guest token can never verify
        self.assertEqual(self.client.post("/api/admin/v1/2fa/verify", json={"code": "123456"}, headers=self.h).status_code, 403)

    def test_totp_rfc6238_vector_and_no_secret_in_db(self):
        import base64

        s = base64.b32encode(b"12345678901234567890").decode()
        self.assertEqual(admin_2fa._hotp(s, 59 // 30, 8), "94287082")
        self.assertEqual(admin_2fa._hotp(s, 1111111109 // 30, 8), "07081804")
        self.admin()
        conn = get_connection(None)
        try:
            if hasattr(conn, "iterdump"):  # sqlite
                dump = "\n".join(conn.iterdump())
            else:  # postgres (WELORA_TEST_POSTGRES_URL): every row of every table as text
                tables = [r["table_name"] for r in conn.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema='public'").fetchall()]
                dump = "\n".join(
                    str(dict(r)) for t in tables for r in conn.execute(f'SELECT * FROM "{t}"').fetchall()
                )
        finally:
            conn.close()
        self.assertNotIn(FAKE_TOTP, dump)

    def test_admin_page_prompts_2fa(self):
        html = (ROOT / "welora" / "api" / "static" / "admin-checkout.html").read_text(encoding="utf-8")
        self.assertIn("/api/admin/v1/2fa/verify", html)
        self.assertNotIn("innerHTML", html)
        self.assertEqual(self.client.get("/app/admin/checkout").status_code, 200)


# ===========================================================================
# mục 10 sandbox acceptance readiness · remainder QR · constraints
# ===========================================================================


class TestMuc10Readiness(_Base):
    def test_test_hooks_non_prod_only(self):
        o = self.order("ACA", "month")
        self.pay(o)
        _, ah = self.admin()
        body = {"order_code": o["order_code"], "days": 8, "reason": "Nghiệm thu hết ân hạn"}
        r = self.client.post("/api/admin/v1/checkout/test/shift-subscription", json=body, headers=ah)
        self.assertEqual(r.json()["detail"]["error_code"], "TEST_HOOKS_DISABLED")
        self.assertEqual(
            self.client.post("/api/admin/v1/checkout/renewal/run", json={"now_offset_days": 40}, headers=ah).status_code, 403
        )
        os.environ["WELORA_CHECKOUT_TEST_HOOKS"] = "1"
        os.environ["WELORA_ENV"] = "production"
        self.assertEqual(self.client.post("/api/admin/v1/checkout/test/shift-subscription", json=body, headers=ah).status_code, 403)
        os.environ["WELORA_ENV"] = "staging"
        # time-travel past period end + 7 days, then run the renewal job → FREE, data kept
        shift_days = (co._ts(self.sub()["current_period_end"]) - time.time()) / DAY + 8
        body["days"] = shift_days
        r = self.client.post("/api/admin/v1/checkout/test/shift-subscription", json=body, headers=ah)
        self.assertEqual(r.status_code, 200, r.text)
        run = self.client.post("/api/admin/v1/checkout/renewal/run", json={}, headers=ah).json()
        self.assertEqual(run["downgraded"], 1)
        self.assertEqual(ent.get_me(self.uid)["plan"], "FREE")
        self.assertIn("test_shift_subscription", [a["action"] for a in self.q("SELECT action FROM checkout_admin_audit")])

    def test_underpaid_remainder_qr(self):
        o = self.order("ACA", "month")
        full_svg = self.client.get(f"/api/checkout/v1/orders/{o['order_code']}/qr.svg", headers=self.h).text
        self.assertEqual(self.pay(o, o["amount"] - 20000)["status"], "UNDERPAID")
        st = self.client.get(f"/api/checkout/v1/orders/{o['order_code']}", headers=self.h).json()
        self.assertTrue(st["remainder_qr"])
        self.assertEqual(st["amount_remaining"], 20000)
        self.assertTrue(st["underpaid_deadline"])
        svg = self.client.get(f"/api/checkout/v1/orders/{o['order_code']}/qr.svg", headers=self.h).text
        self.assertIn("<svg", svg)
        self.assertNotEqual(svg, full_svg)
        payload = vietqr.build_payload(bin_code="970422", account_number="0000000000", amount=20000, description=st["description"])
        self.assertIn("540520000", payload)
        self.assertEqual(payload[-4:], vietqr.crc16_ccitt(payload[:-4]))
        self.assertEqual(vietqr.crc16_ccitt("123456789"), "29B1")

    def test_push_sender_default_noop(self):
        push.set_sender(None)
        self.assertFalse(push.send(self.uid, "t", "b"))

    def test_constraints_unchanged(self):
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        self.assertFalse(h["entitlements"]["lifetime_enabled"])
        self.assertFalse(ent.load_pricing_module()["checkout_enabled"])
        self.assertFalse(ent.load_pricing_module()["lifetime"]["enabled"])
        r = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA", "billing_cycle": "lifetime"}, headers=self.h)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(
            json.loads((ROOT / "config" / "pricing_module.json").read_text(encoding="utf-8")),
            json.loads((ROOT / "welora" / "config" / "pricing_module.json").read_text(encoding="utf-8")),
        )
        renew_html = (ROOT / "welora" / "api" / "static" / "checkout-renew.html").read_text(encoding="utf-8")
        self.assertNotIn("innerHTML", renew_html)
        self.assertIn("location.hash", renew_html)

    def test_flag_off_p1_endpoints_403(self):
        os.environ.pop("WELORA_CHECKOUT_ENABLED")
        for m, url, body in (
            ("GET", "/api/checkout/v1/my-plan", None),
            ("GET", "/api/checkout/v1/prices", None),
            ("POST", "/api/checkout/v1/renew/magic", {"token": "y" * 30}),
            ("POST", "/api/checkout/v1/orders/1000001/refund-request", {"reason": "abcdef"}),
        ):
            self.assertEqual(self.client.request(m, url, json=body, headers=self.h).status_code, 403, url)


if __name__ == "__main__":
    unittest.main()
