"""Checkout VietQR P1 follow-ups — renewal Web Push · late UNDERPAID top-up ·
upgrade-refund restores previous plan · /pricing A/B price.

MockPaymentProvider only (fake checksum key); Web Push transport mocked — no
network. VAPID / subscription keys are generated per test (not secrets).
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import struct
import time
import uuid

from welora import checkout as co
from welora import checkout_pricing as cp
from welora import entitlements as ent
from welora import push, renewal, webpush
from welora.safety_gate import TARGET_MONTHS

from tests.test_checkout_vietqr_p1 import DAY, ROOT, _Base

PUSH_ENV = ("WELORA_PUSH_PROVIDER", "WELORA_VAPID_PUBLIC_KEY", "WELORA_VAPID_PRIVATE_KEY", "WELORA_VAPID_SUBJECT")
FCM = "https://fcm.googleapis.com/fcm/send/"


def _ua_keys():
    """Browser-side subscription keys (what PushManager.subscribe returns)."""
    from cryptography.hazmat.primitives.asymmetric import ec

    priv = ec.generate_private_key(ec.SECP256R1())
    return priv, webpush.b64u(webpush._pub_bytes(priv.public_key())), webpush.b64u(os.urandom(16))


def _decrypt(body: bytes, ua_priv, ua_pub_b64: str, auth_b64: str) -> bytes:
    """Receiver side of RFC 8291 (independent of encrypt()) — proves the wire format."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt, rs, idlen = body[:16], struct.unpack(">I", body[16:20])[0], body[20]
    as_pub_raw = body[21:21 + idlen]
    ct = body[21 + idlen:]
    assert rs == 4096 and idlen == 65
    ecdh = ua_priv.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub_raw))
    ua_pub = webpush.b64u_decode(ua_pub_b64)
    ikm = webpush._hkdf(webpush.b64u_decode(auth_b64), ecdh, b"WebPush: info\x00" + ua_pub + as_pub_raw, 32)
    cek = webpush._hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = webpush._hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    pt = AESGCM(cek).decrypt(nonce, ct, None)
    assert pt.endswith(b"\x02")
    return pt[:-1]


class _PushBase(_Base):
    def setUp(self) -> None:
        self.prev_push = {k: os.environ.get(k) for k in PUSH_ENV}
        for k in PUSH_ENV:
            os.environ.pop(k, None)
        super().setUp()
        self.sent: list[tuple[str, dict, bytes]] = []
        self.status = 201
        webpush.set_transport(self._transport)

    def tearDown(self) -> None:
        webpush.set_transport(None)
        super().tearDown()
        for k, v in self.prev_push.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _transport(self, url, headers, body):
        self.sent.append((url, dict(headers), bytes(body)))
        return self.status

    def enable_webpush(self):
        pub, priv = webpush.generate_vapid()
        os.environ.update({
            "WELORA_PUSH_PROVIDER": "webpush", "WELORA_VAPID_PUBLIC_KEY": pub,
            "WELORA_VAPID_PRIVATE_KEY": priv, "WELORA_VAPID_SUBJECT": "mailto:ops@example.test",
        })
        push.set_sender(None)  # real resolution: explicit sender → webpush → log
        return pub

    def subscribe(self, h=None, endpoint=None):
        priv, pub, auth = _ua_keys()
        ep = endpoint or FCM + uuid.uuid4().hex
        r = self.client.post(
            "/api/push/v1/subscriptions", json={"endpoint": ep, "keys": {"p256dh": pub, "auth": auth}}, headers=self.h if h is None else h
        )
        return r, (priv, pub, auth, ep)


# ===========================================================================
# 1) renewal push actually sent (Web Push / VAPID)
# ===========================================================================


class TestWebPush(_PushBase):
    def test_rfc8291_appendix_a_vector(self):
        body = webpush.encrypt(
            b"When I grow up, I want to be a watermelon",
            ua_public_b64="BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4",
            auth_secret_b64="BTBZMqHH6r4Tts7J_aSIgg",
            salt=webpush.b64u_decode("DGv6ra1nlYgDCS1FRnbzlw"),
            as_private_raw=webpush.b64u_decode("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"),
        )
        self.assertEqual(
            webpush.b64u(body),
            "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6e3vCYLocInmYWAmS6TlzAC8w"
            "EqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZwbuwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN",
        )

    def test_encrypt_roundtrip_and_vapid_jwt(self):
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

        priv, pub, auth = _ua_keys()
        msg = "Gói Học viện hết hạn sau 3 ngày".encode()
        self.assertEqual(_decrypt(webpush.encrypt(msg, ua_public_b64=pub, auth_secret_b64=auth), priv, pub, auth), msg)
        vpub = self.enable_webpush()
        hdr = webpush.vapid_headers(FCM + "abc", now=1_800_000_000)["Authorization"]
        self.assertTrue(hdr.startswith("vapid t="))
        jwt, k = hdr[len("vapid t="):].split(", k=")
        self.assertEqual(k, vpub)
        head, claims, sig = jwt.split(".")
        c = json.loads(webpush.b64u_decode(claims))
        self.assertEqual(c["aud"], "https://fcm.googleapis.com")
        self.assertEqual(c["sub"], "mailto:ops@example.test")
        self.assertEqual(c["exp"], 1_800_000_000 + 12 * 3600)  # ≤ 24h (RFC 8292)
        self.assertEqual(json.loads(webpush.b64u_decode(head))["alg"], "ES256")
        raw = webpush.b64u_decode(sig)
        der = encode_dss_signature(int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:], "big"))
        key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), webpush.b64u_decode(vpub))
        key.verify(der, f"{head}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))  # raises if invalid

    def test_default_is_log_only_no_network(self):
        push.set_sender(None)
        self.assertFalse(webpush.enabled())
        self.assertEqual(self.client.get("/api/push/v1/vapid-public-key").json(), {"enabled": False, "public_key": None})
        r, _ = self.subscribe()
        self.assertEqual(r.status_code, 503)
        self.assertFalse(push.send(self.uid, "t", "b"))
        # provider flag alone (no keys) stays safe
        os.environ["WELORA_PUSH_PROVIDER"] = "webpush"
        self.assertFalse(webpush.enabled())
        self.assertFalse(push.send(self.uid, "t", "b"))
        self.assertEqual(self.sent, [])

    def test_subscribe_api_login_and_ssrf_allowlist(self):
        vpub = self.enable_webpush()
        self.assertEqual(self.client.get("/api/push/v1/vapid-public-key").json(), {"enabled": True, "public_key": vpub})
        r, _ = self.subscribe(h={})
        self.assertEqual(r.status_code, 401)
        for bad in ("http://fcm.googleapis.com/x", "https://127.0.0.1/x", "https://evil.example/fcm.googleapis.com",
                    "https://fcm.googleapis.com.evil.example/x"):
            r, _ = self.subscribe(endpoint=bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertEqual(r.json()["detail"]["error_code"], "PUSH_ENDPOINT_NOT_ALLOWED")
        r = self.client.post("/api/push/v1/subscriptions", json={"endpoint": FCM + "x", "keys": {"p256dh": "AAAA", "auth": "AAAA"}}, headers=self.h)
        self.assertEqual(r.json()["detail"]["error_code"], "PUSH_KEYS_INVALID")
        r, (_, _, _, ep) = self.subscribe()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(len(webpush.subscriptions_for(self.uid)), 1)
        d = self.client.request("DELETE", "/api/push/v1/subscriptions", json={"endpoint": ep}, headers=self.h).json()
        self.assertTrue(d["removed"])
        self.assertEqual(webpush.subscriptions_for(self.uid), [])

    def test_renewal_reminder_delivered_encrypted_to_push_service(self):
        self.enable_webpush()
        _, (priv, pub, auth, ep) = self.subscribe()
        o = self.order("ACA", "month")
        self.pay(o)
        end = co._ts(self.sub()["current_period_end"])
        r = renewal.run_once(now=end - 3 * DAY + 60)
        self.assertEqual((r["reminders"], r["emails"], r["pushes"]), (1, 1, 1))
        self.assertEqual(len(self.sent), 1)
        url, headers, body = self.sent[0]
        self.assertEqual(url, ep)
        self.assertEqual(headers["Content-Encoding"], "aes128gcm")
        self.assertEqual(headers["TTL"], str(webpush.DEFAULT_TTL_S))
        self.assertTrue(headers["Authorization"].startswith("vapid t="))
        msg = json.loads(_decrypt(body, priv, pub, auth))
        self.assertIn("hết hạn sau 3 ngày", msg["title"])
        self.assertIn("/app/checkout/renew#t=", msg["url"])
        self.assertEqual(msg["data"]["type"], "renewal")
        self.assertTrue(self.q("SELECT last_success_at FROM push_subscriptions")[0]["last_success_at"])
        # idempotent reminder → no second push
        renewal.run_once(now=end - 3 * DAY + 120)
        self.assertEqual(len(self.sent), 1)

    def test_gone_subscription_disabled_and_errors_never_break_job(self):
        self.enable_webpush()
        self.subscribe()
        self.status = 410
        self.assertFalse(push.send(self.uid, "t", "b"))
        self.assertTrue(self.q("SELECT disabled_at FROM push_subscriptions")[0]["disabled_at"])
        self.assertFalse(push.send(self.uid, "t", "b"))
        self.assertEqual(len(self.sent), 1)  # disabled → not retried
        self.subscribe()
        webpush.set_transport(lambda *a: (_ for _ in ()).throw(OSError("down")))
        for _ in range(webpush.MAX_FAILURES):
            self.assertFalse(push.send(self.uid, "t", "b"))
        self.assertEqual(webpush.subscriptions_for(self.uid), [])  # disabled after MAX_FAILURES

    def test_service_worker_page_optin_and_keygen(self):
        r = self.client.get("/app/sw.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("javascript", r.headers["content-type"])
        self.assertIn("showNotification", r.text)
        self.assertIn("notificationclick", r.text)
        self.assertIn("self.location.origin", r.text)  # same-origin click targets only
        html = (ROOT / "welora" / "api" / "static" / "my-plan.html").read_text(encoding="utf-8")
        self.assertIn('src="/static/push-optin.js"', html)
        js = (ROOT / "welora" / "api" / "static" / "push-optin.js").read_text(encoding="utf-8")
        self.assertIn("/api/push/v1/vapid-public-key", js)
        self.assertIn('register("/app/sw.js"', js)
        self.assertNotIn("innerHTML", js)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(webpush._main(["gen-vapid"]), 0)
        out = dict(l.split("=", 1) for l in buf.getvalue().splitlines() if "=" in l and not l.startswith("#"))
        self.assertEqual(len(webpush.b64u_decode(out["WELORA_VAPID_PUBLIC_KEY"])), 65)
        self.assertEqual(len(webpush.b64u_decode(out["WELORA_VAPID_PRIVATE_KEY"])), 32)


# ===========================================================================
# 2) UNDERPAID top-up after the 15-min link expired
# ===========================================================================


class TestLateTopUp(_Base):
    def underpaid_expired(self, short=20000):
        o = self.order("ACA", "month")
        self.assertEqual(self.pay(o, o["amount"] - short)["status"], "UNDERPAID")
        # 15-min payment link is over (payOS side + our expires_at)
        self.x("UPDATE orders SET expires_at=? WHERE order_code=?", (co._iso(time.time() - 20 * 60), o["order_code"]))
        self.mock.links[int(o["order_code"])]["status"] = "EXPIRED"
        return o

    def hook(self, **data):
        base = {"amount": 0, "code": "00", "desc": "success", "currency": "VND"}
        base.update(data)
        r = self.client.post("/api/checkout/v1/webhook/payos", json=self.mock.signed_webhook(base))
        self.assertEqual(r.status_code, 200, r.text)
        return r.json()

    def order_row(self, o):
        return self.q("SELECT * FROM orders WHERE order_code=?", (o["order_code"],))[0]

    def test_webhook_without_ordercode_matched_by_welora_description(self):
        o = self.underpaid_expired()
        desc = co.build_description(o["order_code"])
        r = self.hook(amount=20000, description=f"CSUQ5V0 {desc.lower()} FT26273", reference="TOPUP-1")
        self.assertEqual((r["status"], r["matched_by"]), ("PAID", "description_full"))
        row = self.order_row(o)
        self.assertEqual(row["amount_paid"], o["amount"])
        self.assertTrue(ent.has_entitlement(self.uid, "academy.lesson.full"))
        self.assertEqual(self.sub()["status"], "active")
        # idempotent: same bank reference again → no double count / second grant
        self.assertTrue(self.hook(amount=20000, description=desc, reference="TOPUP-1")["duplicate"])
        self.assertEqual(self.order_row(o)["amount_paid"], o["amount"])
        self.assertEqual(co._sum_paid(co._conn(), row["id"]), o["amount"])
        m = self.q("SELECT * FROM payment_events WHERE event_type='match.description'")
        self.assertEqual(len(m), 1)
        self.assertEqual(json.loads(m[0]["raw_payload"])["method"], "description_full")

    def test_unknown_ordercode_wl_short_description_and_accumulation(self):
        o = self.underpaid_expired(short=30000)
        wl = f"WL{str(o['order_code'])[-7:]}"
        # payOS could report a different (unknown) orderCode for a transfer outside the link
        r1 = self.hook(orderCode=987654321, amount=10000, description=f"NGUYEN VAN A {wl}", reference="TOPUP-A")
        self.assertEqual((r1["status"], r1["matched_by"]), ("UNDERPAID", "description_short"))
        self.assertEqual(self.order_row(o)["amount_paid"], o["amount"] - 20000)
        r2 = self.hook(amount=20000, description=wl, reference="TOPUP-B")
        self.assertEqual(r2["status"], "PAID")
        self.assertEqual(self.order_row(o)["amount_paid"], o["amount"])
        self.assertEqual(len(self.q("SELECT * FROM subscriptions WHERE user_id=?", (self.uid,))), 1)

    def test_ambiguous_short_code_left_for_admin_manual_grant(self):
        o1 = self.underpaid_expired()
        o2 = self.order("OS1", "month", h=self.user("second@example.test")[1])
        # force a WL collision: same last 7 digits, both open
        self.x("UPDATE orders SET order_code=? WHERE order_code=?", (int(o1["order_code"]) + 10_000_000, o2["order_code"]))
        wl = f"WL{str(o1['order_code'])[-7:]}"
        conn = co._conn()
        try:
            self.assertEqual(co.match_order_by_description(conn, wl), (None, "ambiguous"))
            self.assertEqual(co.match_order_by_description(conn, "no code here")[1], "none")
            # prefix must stand alone (no "XWELORA…" false match)
            self.assertEqual(co.match_order_by_description(conn, f"XWELORA{o1['order_code']}")[1], "none")
            self.assertEqual(co.match_order_by_description(conn, f"ck welora {o1['order_code']}")[1], "description_full")
        finally:
            conn.close()
        r = self.hook(amount=20000, description=wl, reference="TOPUP-AMB")
        self.assertTrue(r["unknown_order"])
        self.assertEqual(self.order_row(o1)["status"], "UNDERPAID")
        _, ah = self.admin()
        self.assertEqual(self.client.get("/api/admin/v1/checkout/unmatched-payments", headers=self.h).status_code, 403)
        items = self.client.get("/api/admin/v1/checkout/unmatched-payments", headers=ah).json()["items"]
        self.assertEqual([(i["reference"], i["amount"], i["match"]) for i in items], [("TOPUP-AMB", 20000, "ambiguous")])
        # fallback kept: admin manual grant (audited, never sets PAID)
        g = self.client.post(f"/api/admin/v1/checkout/orders/{o1['order_code']}/grant", json={"reason": "Đối soát sao kê: chuyển bù"}, headers=ah)
        self.assertEqual(g.status_code, 200, g.text)
        self.assertTrue(ent.has_entitlement(self.uid, "academy.lesson.full"))
        self.assertNotEqual(self.order_row(o1)["status"], "PAID")

    def test_reconcile_after_link_expired_webhook_lost(self):
        o = self.underpaid_expired()
        self.mock.simulate_transfer(o["order_code"], 20000, reference="TOPUP-R")  # webhook never delivered
        s = co.reconcile_once()
        self.assertEqual(s["paid"], 1)
        self.assertEqual(self.order_row(o)["status"], "PAID")
        self.assertEqual(co.reconcile_once()["paid"], 0)  # PAID no longer polled
        self.assertEqual(self.order_row(o)["amount_paid"], o["amount"])

    def test_reconcile_rematches_unassigned_signed_events(self):
        o = self.underpaid_expired()
        # stored before the matcher existed (P1 kept unknown_order events with order_id NULL)
        payload = self.mock.signed_webhook({"amount": 20000, "description": co.build_description(o["order_code"]),
                                            "reference": "LEGACY-1", "code": "00"})
        conn = co._conn()
        try:
            co._insert_event(conn, order_id=None, provider="mock", event_type="webhook.payment", ref="LEGACY-1",
                             amount=20000, raw=payload, signature_valid=True, now=time.time())
            # an unsigned/invalid event must never be claimed
            co._insert_event(conn, order_id=None, provider="mock", event_type="webhook.invalid_signature", ref="BAD-1",
                             amount=20000, raw=payload, signature_valid=False, now=time.time())
        finally:
            conn.close()
        s = co.reconcile_once()
        self.assertEqual((s["rematched"], s["paid"]), (1, 1))
        self.assertEqual(self.order_row(o)["status"], "PAID")
        self.assertEqual(self.order_row(o)["amount_paid"], o["amount"])
        self.assertEqual(co.reconcile_once()["rematched"], 0)
        self.assertIsNone(self.q("SELECT order_id FROM payment_events WHERE provider_txn_ref='BAD-1'")[0]["order_id"])

    def test_topup_after_refund_pending_needs_admin(self):
        o = self.underpaid_expired()
        self.x("UPDATE orders SET status='REFUND_PENDING' WHERE order_code=?", (o["order_code"],))
        r = self.hook(amount=20000, description=co.build_description(o["order_code"]), reference="TOPUP-LATE")
        self.assertTrue(r["needs_admin"])
        self.assertEqual(self.order_row(o)["status"], "REFUND_PENDING")
        self.assertFalse(ent.has_entitlement(self.uid, "academy.lesson.full"))


# ===========================================================================
# 3) refunding an upgrade restores the previous plan (remaining term)
# ===========================================================================


class TestUpgradeRefundRestore(_Base):
    def test_refund_upgrade_restores_previous_plan_remaining_term(self):
        self.pay(self.order("ACA", "month"))
        self.shift_sub(10)  # 10 days of Academy used
        aca_end_before = co._ts(self.sub(plan="ACA")["current_period_end"])
        up = self.order("OS1", "month")
        t_up = time.time()
        self.assertEqual(self.pay(up)["status"], "PAID")
        self.assertEqual(self.sub(plan="ACA")["status"], "expired")
        snap = self.q("SELECT * FROM payment_events WHERE event_type='upgrade.closed_previous'")
        self.assertEqual(len(snap), 1)
        remaining = json.loads(snap[0]["raw_payload"])["remaining_s"]
        self.assertAlmostEqual(remaining, aca_end_before - t_up, delta=5)
        auid, _ = self.admin()
        t_ref = time.time() + 2 * DAY  # refund completed 2 days later
        co.admin_refund(admin_uid=auid, order_code=up["order_code"], reason="Khách đổi ý", stage="request", override=True, now=t_ref - 60)
        out = co.admin_refund(admin_uid=auid, order_code=up["order_code"], reason="Đã chuyển trả", stage="complete",
                              bank_ref="FT999", now=t_ref)
        self.assertEqual(out["status"], "REFUNDED")
        self.assertEqual(self.sub(plan="OS1")["status"], "expired")
        aca = self.sub(plan="ACA")
        self.assertEqual(aca["status"], "active")
        # remaining term counted from the refund, not the original end date
        self.assertAlmostEqual(co._ts(aca["current_period_end"]), t_ref + remaining, delta=2)
        self.assertEqual(ent.get_me(self.uid)["plan"], "ACA")
        self.assertTrue(ent.has_entitlement(self.uid, "academy.lesson.full"))
        self.assertFalse(ent.has_entitlement(self.uid, "os.personal"))
        ev = self.q("SELECT * FROM payment_events WHERE event_type='upgrade.restored_previous'")
        self.assertEqual(len(ev), 1)
        self.assertEqual(json.loads(ev[0]["raw_payload"])["plan_id"], "ACA")
        audit = [json.loads(a["detail"]) for a in self.q("SELECT detail FROM checkout_admin_audit WHERE action='refund_complete'")]
        self.assertTrue(audit[0]["previous_plan_restored"])
        self.assertEqual(audit[0]["previous_plan"]["plan_id"], "ACA")

    def test_plain_refund_has_no_restore(self):
        o = self.order("ACA", "month")
        self.pay(o)
        auid, _ = self.admin()
        co.admin_refund(admin_uid=auid, order_code=o["order_code"], reason="Khách đổi ý", stage="request")
        co.admin_refund(admin_uid=auid, order_code=o["order_code"], reason="Đã chuyển trả", stage="complete")
        self.assertEqual(self.q("SELECT * FROM payment_events WHERE event_type LIKE 'upgrade.%'"), [])
        self.assertEqual(ent.get_me(self.uid)["plan"], "FREE")


# ===========================================================================
# 4) /pricing shows the A/B price (experiment default OFF)
# ===========================================================================


class TestPricingAB(_Base):
    def activate(self):
        raw = json.loads((ROOT / "welora" / "config" / "pricing_module.json").read_text(encoding="utf-8"))
        raw["experiments"][0]["active"] = True
        path = os.path.join(self.tmp, "pricing.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(raw, f)
        os.environ["WELORA_PRICING_MODULE"] = path
        ent.reset_state_for_tests()

    def aca(self, payload, interval="month"):
        plan = [p for p in payload["plans"] if p["code"] == "ACA"][0]
        return [pr for pr in plan["prices"] if pr["interval"] == interval][0]

    def test_config_variant_b_49000_both_copies_default_off(self):
        for path in (ROOT / "config" / "pricing_module.json", ROOT / "welora" / "config" / "pricing_module.json"):
            exp = [e for e in json.loads(path.read_text(encoding="utf-8"))["experiments"] if e["key"] == "aca_price_ab"][0]
            self.assertFalse(exp["active"], path)
            self.assertEqual(exp["plan"], "ACA")
            self.assertEqual(exp["variant_prices"]["B"]["month"], 49000, path)
        html = (ROOT / "welora" / "api" / "static" / "pricing.html").read_text(encoding="utf-8")
        for amt in ("49000", "49.000", "69000", "69.000"):
            self.assertNotIn(amt, html)
        self.assertIn("pricingHeaders.Authorization", html)

    def test_off_price_unchanged_for_everyone(self):
        os.environ.pop("WELORA_CHECKOUT_ENABLED")
        expected = ent.get_pricing_public()
        anon = self.client.get("/api/core/v1/entitlements/pricing").json()
        me = self.client.get("/api/core/v1/entitlements/pricing", headers=self.h).json()
        self.assertEqual(anon, expected)
        self.assertEqual(me, expected)
        self.assertEqual(self.aca(me)["amount"], ent.price_amount("ACA", "month"))
        self.assertNotIn("price_variant", me)
        self.assertEqual(self.q("SELECT * FROM experiment_assignments"), [])

    def test_on_sticky_variant_price_matches_checkout_quote(self):
        self.activate()
        base_month, base_year = ent.price_amount("ACA", "month"), ent.price_amount("ACA", "year")
        b_price = cp.experiment()["variant_prices"]["B"]["month"]
        groups = {}
        for i in range(12):
            _, h = self.user(f"pab{i}@example.test")
            p1 = self.client.get("/api/core/v1/entitlements/pricing", headers=h).json()
            p2 = self.client.get("/api/core/v1/entitlements/pricing", headers=h).json()
            self.assertEqual(p1["price_variant"], p2["price_variant"])  # sticky
            groups[p1["price_variant"]] = (h, p1)
        self.assertEqual(set(groups), {"A", "B"})
        hb, pb = groups["B"]
        self.assertEqual(self.aca(pb)["amount"], b_price)
        self.assertEqual(b_price, 49000)
        self.assertEqual(self.aca(pb)["base_amount"], base_month)
        self.assertEqual(self.aca(pb)["ab_variant"], "B")
        self.assertEqual(self.aca(pb, "year")["amount"], base_year)  # no B year price in config
        self.assertTrue(self.aca(pb, "lifetime")["locked"])
        os_plan = [p for p in pb["plans"] if p["code"] == "OS1"][0]
        self.assertEqual(os_plan["prices"][0]["amount"], ent.price_amount("OS1", os_plan["prices"][0]["interval"]))
        ha, pa = groups["A"]
        self.assertEqual(self.aca(pa)["amount"], base_month)
        self.assertNotIn("ab_variant", self.aca(pa))
        anon = self.client.get("/api/core/v1/entitlements/pricing").json()
        self.assertEqual(self.aca(anon)["amount"], base_month)  # anonymous → control price
        # same group + same price at checkout
        qb = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA"}, headers=hb).json()
        self.assertEqual((qb["price_variant"], qb["list_price"]), ("B", self.aca(pb)["amount"]))
        qa = self.client.post("/api/checkout/v1/quote", json={"plan_id": "ACA"}, headers=ha).json()
        self.assertEqual((qa["price_variant"], qa["list_price"]), ("A", base_month))
        # still works with checkout off (production today)
        os.environ.pop("WELORA_CHECKOUT_ENABLED")
        self.assertEqual(self.aca(self.client.get("/api/core/v1/entitlements/pricing", headers=hb).json())["amount"], b_price)


class TestFollowupConstraints(_Base):
    def test_constraints_unchanged(self):
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        self.assertFalse(h["entitlements"]["lifetime_enabled"])
        mod = ent.load_pricing_module()
        self.assertFalse(mod["checkout_enabled"])
        self.assertFalse(mod["lifetime"]["enabled"])
        self.assertEqual(
            json.loads((ROOT / "config" / "pricing_module.json").read_text(encoding="utf-8")),
            json.loads((ROOT / "welora" / "config" / "pricing_module.json").read_text(encoding="utf-8")),
        )
