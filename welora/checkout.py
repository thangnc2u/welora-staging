"""Checkout VietQR P0 — CK-01…CK-10 (Phụ lục PRD Checkout thanh toán VietQR).

- Amount is ALWAYS computed server-side from config/pricing_module.json
  (via welora.entitlements). Any client-sent amount is ignored (CK-04).
- Only the webhook or the reconcile job may set PAID (CK-08). returnUrl only
  redirects. Admin manual grant never sets PAID; it is audit-logged.
- Webhook: verify signature → store payment_events (UNIQUE provider_txn_ref)
  → idempotent → compare amount (under → UNDERPAID) → PAID + grant (CK-07).
- 1 PENDING per user per plan: a new order cancels the old link.
- Runtime switch: WELORA_CHECKOUT_ENABLED (default off → 403).

P1 (this module + checkout_pricing / renewal / admin_2fa):
- CK-11 coupons · CK-12 A/B Academy price (fixed group, stored on order)
- CK-13 "Gói của tôi" · CK-14 upgrade credit (by day, round down 1.000đ)
- mục 7 renewal magic link · mục 8 refund (PAY-03 eligibility, REFUND_PENDING →
  REFUNDED, revoke) · UNDERPAID remainder QR · non-prod test hooks (mục 10)

Does not touch Hard Deny R01–R09 / TARGET_MONTHS / Pre-Rule / gate_months.
Lifetime stays OFF (billing_cycle only month|year).
"""

from __future__ import annotations

import calendar
import hashlib
import json
import re
import secrets
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from welora import checkout_pricing as cp
from welora import entitlements as ent
from welora import mailer
from welora.db.connection import get_connection
from welora.db.migrate import migrate
from welora.payments.provider import (
    PaymentProvider,
    ProviderError,
    get_provider,
)

log = logging.getLogger("welora.checkout")

ORDER_STATES = (
    "PENDING",
    "PAID",
    "UNDERPAID",
    "CANCELLED",
    "EXPIRED",
    "REFUND_PENDING",
    "REFUNDED",
)
CHECKOUT_PLANS = ("ACA", "ACA_SV", "OS1", "OS2", "OS2G", "OS3G")
BILLING_CYCLES = ("month", "year")
EXPIRY_MINUTES = 15
RECONCILE_INTERVAL_S = 300
RECONCILE_MIN_AGE_S = 120
UNDERPAID_REFUND_AFTER_S = 24 * 3600
EXPIRED_LATE_PAY_WINDOW_S = 24 * 3600
ORDER_CODE_FLOOR = 1_000_001
DESCRIPTION_PREFIX = "WELORA"
DESCRIPTION_FALLBACK_PREFIX = "WL"
DEFAULT_DESCRIPTION_MAX_LEN = 25  # payOS max; set 9 if bank not linked (PAY-02)
MIN_ADMIN_REASON = 5
RAW_PAYLOAD_MAX = 16_000
ICT = timezone(timedelta(hours=7))
PAID_SOURCES = frozenset({"webhook", "reconcile"})
PAYMENT_EVENT_TYPES = ("webhook.payment", "reconcile.transaction")


class CheckoutError(Exception):
    def __init__(self, status: int, error_code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.error_code = error_code
        self.message = message
        self.extra = extra

    def body(self) -> dict[str, Any]:
        return {"error_code": self.error_code, "message": self.message, **self.extra}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _now(now: Optional[float]) -> float:
    return float(now) if now is not None else time.time()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _ts(iso: Optional[str]) -> float:
    if not iso:
        return 0.0
    dt = datetime.fromisoformat(str(iso))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _ict(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=ICT).strftime("%d/%m/%Y %H:%M ICT")


def add_period(start_ts: float, cycle: str) -> float:
    """start + 1 calendar month / year (day clamped to month length)."""
    dt = datetime.fromtimestamp(start_ts, tz=timezone.utc)
    months = 12 if cycle == "year" else 1
    m = dt.month - 1 + months
    y = dt.year + m // 12
    m = m % 12 + 1
    d = min(dt.day, calendar.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=d).timestamp()


def sub_period(end_ts: float, cycle: str) -> float:
    """end − 1 calendar month / year (inverse of add_period, day clamped)."""
    dt = datetime.fromtimestamp(end_ts, tz=timezone.utc)
    months = 12 if cycle == "year" else 1
    m = dt.month - 1 - months
    y = dt.year + m // 12
    m = m % 12 + 1
    d = min(dt.day, calendar.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=d).timestamp()


def checkout_enabled() -> bool:
    return ent.checkout_runtime_enabled()


def _require_enabled(provider: Optional[PaymentProvider] = None) -> PaymentProvider:
    if not checkout_enabled():
        raise CheckoutError(403, "CHECKOUT_DISABLED", "Sắp mở thanh toán — checkout đang tắt")
    p = provider or get_provider()
    env = (os.environ.get("WELORA_ENV") or "").strip().lower()
    if p.name == "mock" and env in ("production", "prod"):
        raise CheckoutError(503, "MOCK_PROVIDER_IN_PRODUCTION", "Cổng thanh toán chưa cấu hình")
    return p


def build_description(order_code: int, max_len: Optional[int] = None) -> str:
    """WELORA+orderCode; fallback WL + last 7 digits when over payOS limit."""
    if max_len is None:
        try:
            max_len = int(os.environ.get("PAYOS_DESCRIPTION_MAX_LEN") or DEFAULT_DESCRIPTION_MAX_LEN)
        except ValueError:
            max_len = DEFAULT_DESCRIPTION_MAX_LEN
    full = f"{DESCRIPTION_PREFIX}{int(order_code)}"
    if len(full) <= max_len:
        return full
    return f"{DESCRIPTION_FALLBACK_PREFIX}{str(int(order_code))[-7:]}"


def _public_base_url() -> str:
    return (os.environ.get("WELORA_PUBLIC_BASE_URL") or "").strip().rstrip("/")


def return_urls() -> tuple[str, str]:
    base = _public_base_url()
    return f"{base}/app/checkout/return", f"{base}/app/checkout/cancel"


def _is_unique_violation(e: Exception) -> bool:
    name = type(e).__name__
    return "IntegrityError" in name or "UniqueViolation" in name or "unique" in str(e).lower()


def _row(r: Any) -> Optional[dict[str, Any]]:
    if r is None:
        return None
    return {k: r[k] for k in r.keys()}


# ---------------------------------------------------------------------------
# schema
# ---------------------------------------------------------------------------

_schema_lock = threading.RLock()
_schema_ready: set[str] = set()


def _db_key() -> str:
    return (os.environ.get("WELORA_DB_URL") or "").strip() or "<default>"


def ensure_schema() -> None:
    key = _db_key()
    with _schema_lock:
        if key in _schema_ready:
            return
        migrate(None)
        _schema_ready.add(key)


def reset_for_tests() -> None:
    with _schema_lock:
        _schema_ready.clear()


def _conn() -> Any:
    ensure_schema()
    return get_connection(None)


# ---------------------------------------------------------------------------
# pricing (CK-01 / CK-03 / CK-04)
# ---------------------------------------------------------------------------


def _norm_plan_cycle(plan_id: str, billing_cycle: str) -> tuple[str, str]:
    plan = (plan_id or "").strip().upper()
    cycle = (billing_cycle or "").strip().lower()
    if cycle == "lifetime":
        raise CheckoutError(403, "LIFETIME_OFF", "Gói Trọn đời chưa mở bán")
    if plan not in CHECKOUT_PLANS:
        raise CheckoutError(400, "PLAN_NOT_PURCHASABLE", "Gói không bán qua checkout")
    if cycle not in BILLING_CYCLES:
        raise CheckoutError(400, "INVALID_CYCLE", "Chu kỳ phải là month hoặc year")
    return plan, cycle


def _is_preorder(plan: str) -> bool:
    ff = ent.founding_family_status(plan)
    return bool(ff.get("preorder_enabled")) and plan in (ff.get("plans") or [])


def quote(
    plan_id: str,
    billing_cycle: str,
    *,
    now: Optional[float] = None,
    user_id: Optional[str] = None,
    coupon_code: Optional[str] = None,
    conn: Any = None,
) -> dict[str, Any]:
    """Server-side price: config (or A/B variant) − coupon − upgrade credit (CK-04/11/12/14)."""
    plan, cycle = _norm_plan_cycle(plan_id, billing_cycle)
    t = _now(now)
    uid = (user_id or "").strip() or None
    own = conn is None and uid is not None
    c = _conn() if own else conn
    try:
        exp = cp.experiment()
        variant: Optional[str] = None
        if plan == (exp.get("plan") or "ACA"):
            variant = cp.assign_variant(c, uid, now=t) if c is not None else str(exp.get("variant") or "A")
        list_price = cp.list_price(plan, cycle, variant)
        if list_price is None or list_price <= 0:
            raise CheckoutError(400, "PRICE_MISSING", f"Không có giá {plan}/{cycle} trong config")
        monthly = cp.list_price(plan, "month", variant) or 0
        yearly = cp.list_price(plan, "year", variant) or 0

        # CK-14: user holds another (lower) plan → upgrade with prorated credit
        upgrade: Optional[dict[str, Any]] = None
        renew_from: Optional[float] = None
        if uid and c is not None:
            subs = cp.active_subscriptions(c, uid, now=t)
            for sub in subs:
                if sub["plan_id"] == plan and _ts(sub["current_period_end"]) > t:
                    renew_from = _ts(sub["current_period_end"])
            others = [x for x in subs if x["plan_id"] != plan]
            if others:
                top = max(others, key=lambda x: cp.rank(x["plan_id"]))
                if cp.rank(top["plan_id"]) > cp.rank(plan):
                    raise CheckoutError(
                        409, "DOWNGRADE_NOT_SUPPORTED",
                        "Đang có gói cao hơn — hạ gói áp dụng sau khi hết kỳ hiện tại",
                        current_plan=top["plan_id"],
                    )
                upgrade = cp.upgrade_credit(top, now=t)

        # CK-11 coupon (never stacks with student offer; not combined with upgrade credit)
        discount = 0
        code: Optional[str] = None
        if coupon_code and str(coupon_code).strip():
            if upgrade:
                raise CheckoutError(400, "COUPON_NOT_WITH_UPGRADE", "Mã giảm giá không áp dụng khi nâng cấp gói")
            if c is None:
                raise CheckoutError(401, "LOGIN_REQUIRED", "Cần đăng nhập để dùng mã giảm giá")
            code, discount = cp.validate_coupon(
                c, str(coupon_code), plan=plan, cycle=cycle, user_id=uid, list_amount=int(list_price), now=t,
                exclude_pending=(uid, plan) if uid else None,
            )
        credit = 0
        if upgrade:
            step = cp.credit_round_down()
            cap = max(0, int(list_price) - discount - cp.min_amount())
            credit = min(int(upgrade["credit"]), (cap // step) * step)
            upgrade["credit_applied"] = credit
        amount = max(0, int(list_price) - discount - credit)
        info = ent.plan_by_code(plan) or {}
        preorder = _is_preorder(plan)
        start = renew_from if (renew_from and not upgrade) else t
        return {
            "plan_id": plan,
            "plan_name": info.get("name") or plan,
            "billing_cycle": cycle,
            "list_price": int(list_price),
            "discount": discount,
            "coupon_code": code,
            "upgrade": upgrade,
            "upgrade_credit": credit,
            "amount": amount,
            "currency": "VND",
            "members": int(info.get("seat_limit") or 1),
            "year_savings": max(0, monthly * 12 - yearly) if monthly and yearly else 0,
            "expected_period_end": _iso(add_period(start, cycle)),
            "is_renewal": bool(renew_from and not upgrade),
            "is_preorder": preorder,
            "founding_family": ent.founding_family_status(plan) if preorder else None,
            "price_variant": variant,
        }
    finally:
        if own and c is not None:
            c.close()


def _check_purchase_rules(user_id: str, plan: str) -> None:
    if plan == "ACA_SV":
        me = ent.get_me(user_id)
        if not me.get("student"):
            raise CheckoutError(
                403, "STUDENT_REQUIRED", "Gói Academy Sinh viên cần xác thực sinh viên trước"
            )
    blocked, reason = ent.student_os_sell_blocked(user_id, plan)
    if blocked:
        raise CheckoutError(403, "STUDENT_OS_BLOCKED", reason)


# ---------------------------------------------------------------------------
# events
# ---------------------------------------------------------------------------


def _insert_event(
    conn: Any,
    *,
    order_id: Optional[str],
    provider: str,
    event_type: str,
    ref: str,
    amount: int,
    raw: Any,
    signature_valid: bool,
    now: float,
) -> bool:
    """Insert payment_event; False when provider_txn_ref already exists."""
    raw_s = json.dumps(raw, ensure_ascii=False, default=str)
    if len(raw_s) > RAW_PAYLOAD_MAX:
        raw_s = raw_s[:RAW_PAYLOAD_MAX]
    try:
        conn.execute(
            "INSERT INTO payment_events(id, order_id, provider, event_type, provider_txn_ref, "
            "amount, raw_payload, signature_valid, received_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                uuid.uuid4().hex,
                order_id,
                provider,
                event_type,
                ref,
                int(amount or 0),
                raw_s,
                1 if signature_valid else 0,
                _iso(now),
            ),
        )
        conn.commit()
        return True
    except Exception as e:
        if _is_unique_violation(e):
            conn.rollback()
            return False
        raise


def _link_info(conn: Any, order_id: str) -> dict[str, Any]:
    r = conn.execute(
        "SELECT raw_payload FROM payment_events WHERE order_id=? AND event_type='link.created' "
        "ORDER BY received_at DESC LIMIT 1",
        (order_id,),
    ).fetchone()
    if not r:
        return {}
    try:
        return json.loads(r["raw_payload"]) or {}
    except ValueError:
        return {}


# ---------------------------------------------------------------------------
# orders
# ---------------------------------------------------------------------------


def _get_order(conn: Any, *, order_code: Optional[int] = None, order_id: Optional[str] = None):
    if order_id:
        return _row(conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone())
    return _row(conn.execute("SELECT * FROM orders WHERE order_code=?", (int(order_code or 0),)).fetchone())


def _next_order_code(conn: Any) -> int:
    r = conn.execute("SELECT MAX(order_code) AS m FROM orders").fetchone()
    m = r["m"] if r is not None else None
    return max(int(m or 0) + 1, ORDER_CODE_FLOOR)


def _set_status(conn: Any, order_id: str, new: str, *, from_states: tuple[str, ...]) -> bool:
    assert new != "PAID", "PAID only via _settle (webhook / reconcile)"
    marks = ",".join("?" for _ in from_states)
    cur = conn.execute(
        f"UPDATE orders SET status=? WHERE id=? AND status IN ({marks})",
        (new, order_id, *from_states),
    )
    conn.commit()
    return (cur.rowcount or 0) == 1


def _cancel_order(conn: Any, order: dict[str, Any], provider: PaymentProvider, reason: str) -> bool:
    try:
        provider.cancel_payment(int(order["order_code"]), reason)
    except ProviderError as e:
        log.warning("provider cancel failed order=%s err=%s", order["order_code"], e)
    except NotImplementedError:
        pass
    return _set_status(conn, order["id"], "CANCELLED", from_states=("PENDING",))


def public_order(order: dict[str, Any], link: Optional[dict[str, Any]] = None, *, now: Optional[float] = None) -> dict[str, Any]:
    link = link or {}
    t = _now(now)
    exp = _ts(order["expires_at"])
    info = ent.plan_by_code(order["plan_id"]) or {}
    paid = int(order.get("amount_paid") or 0)
    return {
        "order_id": order["id"],
        "order_code": int(order["order_code"]),
        "plan_id": order["plan_id"],
        "plan_name": info.get("name") or order["plan_id"],
        "billing_cycle": order["billing_cycle"],
        "list_price": int(order["list_price"]),
        "discount": int(order["discount"]),
        "amount": int(order["amount"]),
        "amount_paid": paid,
        "amount_remaining": max(0, int(order["amount"]) - paid),
        "currency": "VND",
        "status": order["status"],
        "is_preorder": bool(order.get("is_preorder")),
        "provider": order["provider"],
        "checkout_url": order.get("checkout_url") or "",
        "qr_code": order.get("qr_code") or "",
        "description": link.get("description") or build_description(int(order["order_code"])),
        "account_number": link.get("accountNumber") or "",
        "account_name": link.get("accountName") or "",
        "bin": link.get("bin") or "",
        "expires_at": order["expires_at"],
        "expires_at_ts": int(exp),
        "seconds_left": max(0, int(exp - t)) if order["status"] == "PENDING" else 0,
        "paid_at": order.get("paid_at"),
        "created_at": order["created_at"],
        "coupon_code": order.get("coupon_code"),
        "price_variant": order.get("price_variant"),
        "upgrade_from_plan": order.get("upgrade_from_plan"),
        "upgrade_credit": int(order.get("upgrade_credit") or 0),
        "refund_amount": int(order.get("refund_amount") or 0),
        "refunded_at": order.get("refunded_at"),
        # mục 8: underpaid → new QR for the remainder, 24h to top up
        "remainder_qr": order["status"] == "UNDERPAID" and max(0, int(order["amount"]) - paid) > 0,
        "underpaid_deadline": (
            _iso(_ts(order["created_at"]) + UNDERPAID_REFUND_AFTER_S) if order["status"] == "UNDERPAID" else None
        ),
    }


def create_order(
    *,
    user_id: Optional[str],
    plan_id: str,
    billing_cycle: str,
    client_amount: Any = None,
    coupon_code: Optional[str] = None,
    now: Optional[float] = None,
    provider: Optional[PaymentProvider] = None,
) -> dict[str, Any]:
    p = _require_enabled(provider)
    uid = (user_id or "").strip()
    if not uid:
        raise CheckoutError(401, "LOGIN_REQUIRED", "Cần đăng nhập trước khi thanh toán")
    t = _now(now)
    conn = _conn()
    try:
        q = quote(plan_id, billing_cycle, now=t, user_id=uid, coupon_code=coupon_code, conn=conn)
        plan, cycle = q["plan_id"], q["billing_cycle"]
        _check_purchase_rules(uid, plan)
        if client_amount is not None:
            log.info("client amount ignored (server price used) plan=%s cycle=%s", plan, cycle)
        upgrade_from = (q.get("upgrade") or {}).get("from_plan")
        order: Optional[dict[str, Any]] = None
        for _attempt in range(4):
            # 1 PENDING per user per plan — cancel old link first
            olds = conn.execute(
                "SELECT * FROM orders WHERE user_id=? AND plan_id=? AND status='PENDING'",
                (uid, plan),
            ).fetchall()
            for old in olds:
                _cancel_order(conn, _row(old), p, "replaced_by_new_order")
            code = _next_order_code(conn)
            oid = uuid.uuid4().hex
            try:
                conn.execute(
                    "INSERT INTO orders(id, order_code, user_id, plan_id, billing_cycle, list_price, "
                    "discount, amount, coupon_code, price_variant, provider, status, expires_at, "
                    "amount_paid, is_preorder, created_at, upgrade_from_plan, upgrade_credit) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        oid, code, uid, plan, cycle, q["list_price"], q["discount"], q["amount"],
                        q["coupon_code"], q["price_variant"], p.name, "PENDING",
                        _iso(t + EXPIRY_MINUTES * 60), 0, 1 if q["is_preorder"] else 0, _iso(t),
                        upgrade_from, int(q["upgrade_credit"] or 0),
                    ),
                )
                conn.commit()
                order = _get_order(conn, order_id=oid)
                break
            except Exception as e:
                if _is_unique_violation(e):
                    conn.rollback()
                    continue
                raise
        if order is None:
            raise CheckoutError(409, "ORDER_CONFLICT", "Không tạo được đơn, thử lại")

        return_url, cancel_url = return_urls()
        description = build_description(int(order["order_code"]))
        try:
            link = p.create_payment(
                order_code=int(order["order_code"]),
                amount=int(order["amount"]),
                description=description,
                return_url=return_url,
                cancel_url=cancel_url,
                expired_at=int(t + EXPIRY_MINUTES * 60),
            )
        except (ProviderError, NotImplementedError) as e:
            _set_status(conn, order["id"], "CANCELLED", from_states=("PENDING",))
            log.warning("provider create failed order=%s err=%s", order["order_code"], e)
            raise CheckoutError(502, "PROVIDER_ERROR", "Không tạo được mã thanh toán, thử lại sau")

        conn.execute(
            "UPDATE orders SET provider_link_id=?, checkout_url=?, qr_code=? WHERE id=?",
            (link.provider_link_id, link.checkout_url, link.qr_code, order["id"]),
        )
        conn.commit()
        link_raw = {
            "paymentLinkId": link.provider_link_id,
            "description": link.description or description,
            "accountNumber": link.account_number,
            "accountName": link.account_name,
            "bin": link.bin,
            "amount": link.amount,
            "expiredAt": link.expired_at,
        }
        _insert_event(
            conn, order_id=order["id"], provider=p.name, event_type="link.created",
            ref=f"link:{p.name}:{int(order['order_code'])}", amount=0, raw=link_raw,
            signature_valid=True, now=t,
        )
        order = _get_order(conn, order_id=order["id"])
        ent.emit_event(
            "checkout_started",
            {
                "user_id": uid, "plan": plan, "cycle": cycle, "order_code": int(order["order_code"]),
                "price_variant": q["price_variant"], "coupon": bool(q["coupon_code"]), "upgrade_from": upgrade_from,
            },
        )
        return public_order(order, link_raw, now=t)
    finally:
        conn.close()


def get_order_for_user(user_id: str, order_code: int, *, now: Optional[float] = None) -> dict[str, Any]:
    _require_enabled()
    conn = _conn()
    try:
        order = _get_order(conn, order_code=order_code)
        if not order or order["user_id"] != user_id:
            raise CheckoutError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn")
        t = _now(now)
        if order["status"] == "PENDING" and t > _ts(order["expires_at"]):
            _set_status(conn, order["id"], "EXPIRED", from_states=("PENDING",))
            order = _get_order(conn, order_id=order["id"])
        return public_order(order, _link_info(conn, order["id"]), now=t)
    finally:
        conn.close()


def cancel_order_for_user(user_id: str, order_code: int) -> dict[str, Any]:
    p = _require_enabled()
    conn = _conn()
    try:
        order = _get_order(conn, order_code=order_code)
        if not order or order["user_id"] != user_id:
            raise CheckoutError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn")
        if order["status"] == "PENDING":
            _cancel_order(conn, order, p, "user_cancelled")
        order = _get_order(conn, order_id=order["id"])
        return public_order(order, _link_info(conn, order["id"]))
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# settle / grant (CK-07 / CK-08 / CK-09)
# ---------------------------------------------------------------------------


def _sum_paid(conn: Any, order_id: str) -> int:
    marks = ",".join("?" for _ in PAYMENT_EVENT_TYPES)
    r = conn.execute(
        f"SELECT COALESCE(SUM(amount), 0) AS s FROM payment_events WHERE order_id=? "
        f"AND signature_valid=1 AND event_type IN ({marks})",
        (order_id, *PAYMENT_EVENT_TYPES),
    ).fetchone()
    return int(r["s"] or 0)


def _settle(conn: Any, order_id: str, *, source: str, now: float) -> str:
    """Only path that can set PAID. source ∈ {webhook, reconcile}."""
    if source not in PAID_SOURCES:
        raise ValueError("PAID may only be set by webhook or reconcile")
    order = _get_order(conn, order_id=order_id)
    if not order:
        return "MISSING"
    paid = _sum_paid(conn, order_id)
    amount = int(order["amount"])
    if paid >= amount > 0:
        cur = conn.execute(
            "UPDATE orders SET status='PAID', paid_at=?, amount_paid=? WHERE id=? "
            "AND status IN ('PENDING','UNDERPAID','EXPIRED')",
            (_iso(now), paid, order_id),
        )
        conn.commit()
        if (cur.rowcount or 0) == 1:
            order = _get_order(conn, order_id=order_id)
            sub = _grant_for_order(conn, order, source=source, now=now)
            if paid > amount:
                log.warning("overpaid order=%s paid=%s amount=%s → admin refund", order["order_code"], paid, amount)
            cp.record_redemption(conn, order, now=now)
            _snapshot_usage(conn, order, now=now)
            ent.emit_event(
                "checkout_completed",
                {
                    "order_code": int(order["order_code"]), "plan": order["plan_id"], "source": source,
                    "price_variant": order.get("price_variant"),
                },
            )
            _queue_receipt(conn, order, sub)
        return "PAID"
    if paid > 0:
        conn.execute(
            "UPDATE orders SET amount_paid=? WHERE id=? AND status IN ('PENDING','UNDERPAID','EXPIRED')",
            (paid, order_id),
        )
        conn.execute(
            "UPDATE orders SET status='UNDERPAID' WHERE id=? AND status IN ('PENDING','UNDERPAID')",
            (order_id,),
        )
        conn.commit()
        return (_get_order(conn, order_id=order_id) or {}).get("status", "UNDERPAID")
    return order["status"]


def _grant_for_order(conn: Any, order: dict[str, Any], *, source: str, now: float) -> dict[str, Any]:
    uid, plan, cycle = order["user_id"], order["plan_id"], order["billing_cycle"]
    sub = _row(
        conn.execute("SELECT * FROM subscriptions WHERE user_id=? AND plan_id=?", (uid, plan)).fetchone()
    )
    start = now
    if sub and sub["status"] in ("active", "grace") and _ts(sub["current_period_end"]) > now:
        start = _ts(sub["current_period_end"])  # early renewal: continue from old end
    end = add_period(start, cycle)
    if order.get("upgrade_from_plan"):
        # CK-14: the old plan ends now; its remaining value was credited on this order.
        # Snapshot it first so a refund of this upgrade can restore it (remaining term).
        _snapshot_previous_plan(conn, order, now=now)
        conn.execute(
            "UPDATE subscriptions SET status='expired', current_period_end=? "
            "WHERE user_id=? AND plan_id=? AND status IN ('active','grace')",
            (_iso(now), uid, order["upgrade_from_plan"]),
        )
    if sub:
        conn.execute(
            "UPDATE subscriptions SET status='active', current_period_start=?, current_period_end=?, "
            "last_order_id=? WHERE id=?",
            (_iso(start), _iso(end), order["id"], sub["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO subscriptions(id, user_id, plan_id, status, current_period_start, "
            "current_period_end, last_order_id, members) VALUES (?,?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, uid, plan, "active", _iso(start), _iso(end), order["id"], json.dumps([uid])),
        )
    conn.commit()
    return ent.grant_plan(
        uid, plan, period_start=start, period_end=end, source=source,
        order_code=int(order["order_code"]), is_preorder=bool(order.get("is_preorder")),
    )


def _snapshot_previous_plan(conn: Any, order: dict[str, Any], *, now: float) -> None:
    prev = _row(
        conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND plan_id=? AND status IN ('active','grace')",
            (order["user_id"], order["upgrade_from_plan"]),
        ).fetchone()
    )
    if not prev:
        return
    end = _ts(prev["current_period_end"])
    _insert_event(
        conn, order_id=order["id"], provider="welora", event_type="upgrade.closed_previous",
        ref=f"upgrade:closed:{order['id']}", amount=0,
        raw={
            "subscription_id": prev["id"], "plan_id": prev["plan_id"], "status": prev["status"],
            "period_start": prev["current_period_start"], "period_end": prev["current_period_end"],
            "remaining_s": max(0, int(end - now)), "closed_at": _iso(now),
        },
        signature_valid=True, now=now,
    )


def _restore_previous_plan(conn: Any, order: dict[str, Any], *, now: float) -> dict[str, Any]:
    """Refund of a CK-14 upgrade → give back the old plan with the term it had left
    at the moment of upgrade (now + remaining_s). Only when the upgraded plan's
    subscription has ended after rollback (never two paid plans at once)."""
    if not order.get("upgrade_from_plan"):
        return {}
    ev = _row(
        conn.execute(
            "SELECT * FROM payment_events WHERE order_id=? AND event_type='upgrade.closed_previous'", (order["id"],)
        ).fetchone()
    )
    if not ev:
        return {"previous_plan_restored": False, "previous_plan_note": "no_snapshot"}
    snap = json.loads(ev["raw_payload"] or "{}")
    new_sub = _row(
        conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND plan_id=?", (order["user_id"], order["plan_id"])
        ).fetchone()
    )
    if new_sub and new_sub["status"] in ("active", "grace") and _ts(new_sub["current_period_end"]) > now:
        return {"previous_plan_restored": False, "previous_plan_note": "upgraded_plan_still_active"}
    remaining = int(snap.get("remaining_s") or 0)
    if remaining <= 0:
        return {"previous_plan_restored": False, "previous_plan_note": "no_remaining_term"}
    new_end = now + remaining
    cur = conn.execute(
        "UPDATE subscriptions SET status='active', current_period_end=? WHERE id=? AND user_id=? AND plan_id=?",
        (_iso(new_end), snap.get("subscription_id"), order["user_id"], order["upgrade_from_plan"]),
    )
    conn.commit()
    if (cur.rowcount or 0) != 1:
        return {"previous_plan_restored": False, "previous_plan_note": "previous_subscription_missing"}
    info = {
        "subscription_id": snap.get("subscription_id"), "plan_id": order["upgrade_from_plan"],
        "remaining_s": remaining, "restored_until": _iso(new_end),
    }
    _insert_event(
        conn, order_id=order["id"], provider="welora", event_type="upgrade.restored_previous",
        ref=f"upgrade:restored:{order['id']}", amount=0, raw=info, signature_valid=True, now=now,
    )
    return {"previous_plan_restored": True, "previous_plan": info}


def _user_email(conn: Any, user_id: str) -> Optional[str]:
    try:
        r = conn.execute("SELECT email FROM users WHERE user_id=?", (user_id,)).fetchone()
        return (r["email"] if r else None) or None
    except Exception:
        conn.rollback()
        return None


def receipt_text(order: dict[str, Any], period_end: float) -> tuple[str, str]:
    info = ent.plan_by_code(order["plan_id"]) or {}
    cycle = "tháng" if order["billing_cycle"] == "month" else "năm"
    subject = f"Welora · Biên nhận thanh toán đơn {int(order['order_code'])}"
    amount_vnd = f"{int(order['amount_paid'] or order['amount']):,}".replace(",", ".")
    body = (
        "Biên nhận thanh toán Welora (không phải hoá đơn VAT)\n\n"
        f"Mã đơn: {int(order['order_code'])}\n"
        f"Gói: {info.get('name') or order['plan_id']} ({order['plan_id']}) · chu kỳ {cycle}\n"
        f"Số tiền: {amount_vnd} VND\n"
        f"Thời gian: {_ict(_ts(order['paid_at']))}\n"
        f"Hết hạn: {_ict(period_end)}\n"
    )
    if order.get("is_preorder"):
        body += "\nĐặt trước Founding Family: kích hoạt OS Cá nhân cho chủ hộ đến khi OS 3.10 ra mắt; hoàn 100% nếu trễ.\n"
    body += (
        "\nWelora cung cấp thông tin và công cụ quản lý tài chính cá nhân, không tư vấn đầu tư.\n"
    )
    return subject, body


def _queue_receipt(conn: Any, order: dict[str, Any], sub: dict[str, Any]) -> None:
    email = _user_email(conn, order["user_id"])
    if not email:
        log.info("receipt skipped (no email) order=%s", order["order_code"])
        return
    subject, body = receipt_text(order, float(sub.get("current_period_end") or 0))
    mailer.enqueue(email, subject, body)


# ---------------------------------------------------------------------------
# webhook (mục 5 · CK-07)
# ---------------------------------------------------------------------------


def _int(v: Any) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


# P1 follow-up · UNDERPAID top-up after the 15-min link expired: a later transfer
# may arrive without a usable orderCode (e.g. remainder QR / manual transfer with
# the same content). Match it by transfer description instead.
_DESC_FULL_RE = re.compile(r"(?<![A-Z0-9])" + DESCRIPTION_PREFIX + r"\s*(\d{6,})(?!\d)", re.IGNORECASE)
_DESC_SHORT_RE = re.compile(r"(?<![A-Z0-9])" + DESCRIPTION_FALLBACK_PREFIX + r"\s*(\d{7})(?!\d)", re.IGNORECASE)
TOPUP_STATES = ("PENDING", "UNDERPAID", "EXPIRED")
REMATCH_WINDOW_S = 7 * 86400


def match_order_by_description(conn: Any, description: Any) -> tuple[Optional[dict[str, Any]], str]:
    """(order, method). method ∈ description_full | description_short | ambiguous | none.

    ``WELORA<orderCode>`` → exact order code. ``WL<last 7 digits>`` → the ONLY
    open order (PENDING/UNDERPAID/EXPIRED) whose code ends with those digits;
    several candidates → ``ambiguous`` (left for admin, never guessed).
    """
    text = str(description or "")
    m = _DESC_FULL_RE.search(text)
    if m:
        order = _get_order(conn, order_code=int(m.group(1)))
        if order:
            return order, "description_full"
    m = _DESC_SHORT_RE.search(text)
    if m:
        marks = ",".join("?" for _ in TOPUP_STATES)
        rows = [
            _row(r)
            for r in conn.execute(
                f"SELECT * FROM orders WHERE status IN ({marks}) AND (order_code % 10000000) = ?",
                (*TOPUP_STATES, int(m.group(1))),
            ).fetchall()
        ]
        if len(rows) == 1:
            return rows[0], "description_short"
        if len(rows) > 1:
            return None, "ambiguous"
    return None, "none"


def _record_match(conn: Any, *, order: dict[str, Any], provider: str, ref: str, method: str, description: str, now: float) -> None:
    """Trace (payment_events, amount 0 — not counted by _sum_paid) of a description match."""
    _insert_event(
        conn, order_id=order["id"], provider=provider, event_type="match.description",
        ref=f"match:{ref}", amount=0,
        raw={"method": method, "order_code": int(order["order_code"]), "description": str(description or "")[:200], "ref": ref},
        signature_valid=True, now=now,
    )
    log.info("payment matched by %s order=%s ref=%s", method, order["order_code"], ref)


def handle_webhook(payload: Any, *, now: Optional[float] = None, provider: Optional[PaymentProvider] = None) -> tuple[int, dict[str, Any]]:
    p = _require_enabled(provider)
    t = _now(now)
    if not isinstance(payload, dict):
        return 400, {"ok": False, "error_code": "INVALID_PAYLOAD"}
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    conn = _conn()
    try:
        # 1. signature
        if not p.verify_webhook(payload):
            log.warning(
                "webhook INVALID signature ignored provider=%s orderCode=%s", p.name, data.get("orderCode")
            )
            _insert_event(
                conn, order_id=None, provider=p.name, event_type="webhook.invalid_signature",
                ref=f"invalid:{uuid.uuid4().hex}", amount=_int(data.get("amount")),
                raw=payload, signature_valid=False, now=t,
            )
            return 400, {"ok": False, "error_code": "INVALID_SIGNATURE", "ignored": True}

        order_code = _int(data.get("orderCode"))
        order = _get_order(conn, order_code=order_code) if order_code else None
        success = str(data.get("code", "00")) == "00" and payload.get("success", True) is not False
        ref = str(data.get("reference") or "").strip() or (
            f"{p.name}:{data.get('paymentLinkId')}:{order_code}:{data.get('amount')}:{data.get('transactionDateTime')}"
        )
        matched_by = "order_code" if order else None
        if not order and success:
            # late top-up / transfer without our orderCode → WELORA<code> / WL<7 digits>
            order, method = match_order_by_description(conn, data.get("description"))
            matched_by = method if order else None
            if method == "ambiguous":
                log.warning("webhook description ambiguous ref=%s → admin", ref)
        # 2. store raw (UNIQUE provider_txn_ref → idempotent)
        inserted = _insert_event(
            conn, order_id=order["id"] if order else None, provider=p.name,
            event_type="webhook.payment" if success else "webhook.non_success",
            ref=ref, amount=_int(data.get("amount")), raw=payload, signature_valid=True, now=t,
        )
        if not inserted:
            return 200, {"ok": True, "duplicate": True}
        if not order:
            return 200, {"ok": True, "unknown_order": True}
        if matched_by and matched_by.startswith("description"):
            _record_match(conn, order=order, provider=p.name, ref=ref, method=matched_by, description=data.get("description"), now=t)
        if not success:
            return 200, {"ok": True, "ignored": "non_success"}
        # 3. idempotent on already-settled orders
        if order["status"] in ("PAID", "REFUND_PENDING", "REFUNDED"):
            if order["status"] == "PAID":
                log.warning("second payment on PAID order=%s → admin refund", order["order_code"])
            out: dict[str, Any] = {"ok": True, "idempotent": True, "status": order["status"]}
            if order["status"] == "REFUND_PENDING":
                # top-up arrived after the 24h underpaid window → admin decides (refund or manual grant)
                log.warning("payment on REFUND_PENDING order=%s → needs admin", order["order_code"])
                out["needs_admin"] = True
            return 200, out
        if order["status"] == "CANCELLED":
            log.warning("payment on CANCELLED order=%s → needs admin (CK-10)", order_code)
            return 200, {"ok": True, "needs_admin": True, "status": "CANCELLED"}
        # 4. compare amount → PAID / UNDERPAID
        status = _settle(conn, order["id"], source="webhook", now=t)
        out = {"ok": True, "status": status}
        if matched_by and matched_by != "order_code":
            out["matched_by"] = matched_by
        return 200, out
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# reconcile job (mục 5) — every 5 min, PENDING older than 2 min
# ---------------------------------------------------------------------------


def _rematch_unassigned(conn: Any, *, now: float, summary: dict[str, Any]) -> None:
    """Reconcile side of late top-ups: signed payment events stored with no order
    (unknown orderCode, ambiguous description, or received before this matcher
    existed) are matched again by orderCode / description and settled."""
    rows = [
        _row(r)
        for r in conn.execute(
            "SELECT * FROM payment_events WHERE order_id IS NULL AND signature_valid=1 AND event_type=?",
            ("webhook.payment",),
        ).fetchall()
    ]
    for ev in rows:
        try:
            if now - _ts(ev["received_at"]) > REMATCH_WINDOW_S:
                continue
            raw = json.loads(ev.get("raw_payload") or "{}")
        except (ValueError, TypeError):
            continue
        data = (raw or {}).get("data") if isinstance((raw or {}).get("data"), dict) else {}
        order = _get_order(conn, order_code=_int(data.get("orderCode"))) if _int(data.get("orderCode")) else None
        method = "order_code" if order else "none"
        if not order:
            order, method = match_order_by_description(conn, data.get("description"))
        if not order or order["status"] not in TOPUP_STATES:
            continue
        cur = conn.execute("UPDATE payment_events SET order_id=? WHERE id=? AND order_id IS NULL", (order["id"], ev["id"]))
        conn.commit()
        if (cur.rowcount or 0) != 1:
            continue
        summary["rematched"] += 1
        _record_match(conn, order=order, provider=ev["provider"], ref=ev["provider_txn_ref"], method=method,
                      description=data.get("description"), now=now)
        if _settle(conn, order["id"], source="reconcile", now=now) == "PAID":
            summary["paid"] += 1


def reconcile_once(*, now: Optional[float] = None, provider: Optional[PaymentProvider] = None) -> dict[str, Any]:
    if not checkout_enabled():
        return {"skipped": "checkout_disabled"}
    p = provider or get_provider()
    t = _now(now)
    summary = {
        "checked": 0, "paid": 0, "underpaid": 0, "expired": 0, "cancelled": 0, "refund_pending": 0, "errors": 0,
        "rematched": 0,
    }
    conn = _conn()
    try:
        _rematch_unassigned(conn, now=t, summary=summary)
        rows = [
            _row(r)
            for r in conn.execute(
                "SELECT * FROM orders WHERE status IN ('PENDING','UNDERPAID','EXPIRED')"
            ).fetchall()
        ]
        for order in rows:
            created = _ts(order["created_at"])
            expires = _ts(order["expires_at"])
            st = order["status"]
            if st == "PENDING" and t - created < RECONCILE_MIN_AGE_S:
                continue
            if st == "EXPIRED" and t - expires > EXPIRED_LATE_PAY_WINDOW_S:
                continue
            summary["checked"] += 1
            try:
                remote = p.get_payment(int(order["order_code"]))
            except (ProviderError, NotImplementedError) as e:
                summary["errors"] += 1
                log.warning("reconcile get failed order=%s err=%s", order["order_code"], e)
                if st == "PENDING" and t > expires and _set_status(conn, order["id"], "EXPIRED", from_states=("PENDING",)):
                    summary["expired"] += 1
                continue
            for tx in remote.transactions:
                _insert_event(
                    conn, order_id=order["id"], provider=p.name, event_type="reconcile.transaction",
                    ref=tx.reference, amount=tx.amount, raw=tx.raw, signature_valid=True, now=t,
                )
            new = _settle(conn, order["id"], source="reconcile", now=t)
            if new == "PAID" and st != "PAID":
                summary["paid"] += 1
                continue
            if new == "PENDING":
                if remote.status == "CANCELLED":
                    if _set_status(conn, order["id"], "CANCELLED", from_states=("PENDING",)):
                        summary["cancelled"] += 1
                elif remote.status == "EXPIRED" or t > expires:
                    if _set_status(conn, order["id"], "EXPIRED", from_states=("PENDING",)):
                        summary["expired"] += 1
            elif new == "UNDERPAID":
                if st != "UNDERPAID":
                    summary["underpaid"] += 1
                if t - created > UNDERPAID_REFUND_AFTER_S and _set_status(
                    conn, order["id"], "REFUND_PENDING", from_states=("UNDERPAID",)
                ):
                    summary["refund_pending"] += 1
        return summary
    finally:
        conn.close()


_reconcile_stop = threading.Event()
_reconcile_thread: Optional[threading.Thread] = None


def start_reconcile_loop(interval_s: Optional[float] = None) -> Optional[threading.Thread]:
    """In-process background loop (same FastAPI process, no new Render service)."""
    global _reconcile_thread
    if (os.environ.get("WELORA_CHECKOUT_RECONCILE") or "1").strip() == "0":
        return None
    if _reconcile_thread and _reconcile_thread.is_alive():
        return _reconcile_thread
    try:
        iv = float(interval_s or os.environ.get("WELORA_RECONCILE_INTERVAL_S") or RECONCILE_INTERVAL_S)
    except ValueError:
        iv = RECONCILE_INTERVAL_S
    _reconcile_stop.clear()

    def _loop() -> None:
        while not _reconcile_stop.wait(iv):
            try:
                if checkout_enabled():
                    reconcile_once()
            except Exception as e:  # keep loop alive
                log.warning("reconcile loop error: %s", type(e).__name__)

    _reconcile_thread = threading.Thread(target=_loop, name="welora-reconcile", daemon=True)
    _reconcile_thread.start()
    return _reconcile_thread


def stop_reconcile_loop() -> None:
    _reconcile_stop.set()


# ---------------------------------------------------------------------------
# persisted subscription → entitlements (survives restart)
# ---------------------------------------------------------------------------


def _resolve_subscription(user_id: str) -> Optional[dict[str, Any]]:
    if _db_key() not in _schema_ready:
        return None
    conn = get_connection(None)
    try:
        r = conn.execute(
            "SELECT s.*, o.is_preorder AS is_preorder, o.order_code AS order_code FROM subscriptions s "
            "LEFT JOIN orders o ON o.id = s.last_order_id "
            "WHERE s.user_id=? AND s.status IN ('active','grace') ORDER BY s.current_period_end DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if not r:
            return None
        plan = r["plan_id"]
        if r["is_preorder"]:
            active = ent.founding_family_status(plan).get("activates_as") or "OS1"
        else:
            active = plan
        return {
            "plan": active,
            "subscription": {
                "plan_id": plan,
                "active_plan": active,
                "status": r["status"],
                "current_period_start": _ts(r["current_period_start"]),
                "current_period_end": _ts(r["current_period_end"]),
                "source": "db",
                "order_code": r["order_code"],
                "is_preorder": bool(r["is_preorder"]),
            },
        }
    finally:
        conn.close()


ent.register_subscription_resolver(_resolve_subscription)


# ---------------------------------------------------------------------------
# admin (CK-10)
# ---------------------------------------------------------------------------


def _audit(conn: Any, *, admin_uid: str, action: str, order: Optional[dict[str, Any]], reason: str, detail: dict[str, Any]) -> None:
    conn.execute(
        "INSERT INTO checkout_admin_audit(id, admin_user_id, action, order_id, order_code, reason, detail, created_at) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            uuid.uuid4().hex, admin_uid, action, (order or {}).get("id"),
            (order or {}).get("order_code"), reason, json.dumps(detail, ensure_ascii=False), _iso(time.time()),
        ),
    )
    conn.commit()
    log.info("admin audit action=%s order=%s admin=%s", action, (order or {}).get("order_code"), admin_uid)


def _require_reason(reason: Optional[str]) -> str:
    r = (reason or "").strip()
    if len(r) < MIN_ADMIN_REASON:
        raise CheckoutError(400, "REASON_REQUIRED", f"Cần ghi lý do (tối thiểu {MIN_ADMIN_REASON} ký tự)")
    return r


def admin_search(q: str) -> list[dict[str, Any]]:
    term = (q or "").strip()
    if not term:
        return []
    conn = _conn()
    try:
        params: list[Any] = []
        where = []
        if term.isdigit():
            where.append("o.order_code = ?")
            params.append(int(term))
        where.append("o.user_id = ?")
        params.append(term)
        user_ids: list[str] = []
        try:
            for r in conn.execute(
                "SELECT user_id FROM users WHERE lower(email)=lower(?) OR phone=?", (term, term)
            ).fetchall():
                user_ids.append(r["user_id"])
        except Exception:
            conn.rollback()
        for u in user_ids:
            where.append("o.user_id = ?")
            params.append(u)
        rows = conn.execute(
            f"SELECT o.* FROM orders o WHERE {' OR '.join(where)} ORDER BY o.created_at DESC LIMIT 50",
            tuple(params),
        ).fetchall()
        return [public_order(_row(r)) | {"user_id": r["user_id"]} for r in rows]
    finally:
        conn.close()


def admin_order_detail(order_code: int) -> dict[str, Any]:
    conn = _conn()
    try:
        order = _get_order(conn, order_code=order_code)
        if not order:
            raise CheckoutError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn")
        events = []
        for r in conn.execute(
            "SELECT * FROM payment_events WHERE order_id=? ORDER BY received_at", (order["id"],)
        ).fetchall():
            e = _row(r)
            try:
                e["raw_payload"] = json.loads(e["raw_payload"])
            except ValueError:
                pass
            events.append(e)
        audit = [
            _row(r)
            for r in conn.execute(
                "SELECT * FROM checkout_admin_audit WHERE order_id=? ORDER BY created_at", (order["id"],)
            ).fetchall()
        ]
        sub = _row(
            conn.execute(
                "SELECT * FROM subscriptions WHERE user_id=? AND plan_id=?", (order["user_id"], order["plan_id"])
            ).fetchone()
        )
        return {
            "order": public_order(order, _link_info(conn, order["id"])) | {"user_id": order["user_id"]},
            "events": events,
            "audit": audit,
            "subscription": sub,
        }
    finally:
        conn.close()


def admin_manual_grant(*, admin_uid: str, order_code: int, reason: str) -> dict[str, Any]:
    """Open the plan by hand (sai nội dung CK, mục 8). Never sets PAID."""
    r = _require_reason(reason)
    conn = _conn()
    try:
        order = _get_order(conn, order_code=order_code)
        if not order:
            raise CheckoutError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn")
        sub = _grant_for_order(conn, order, source="admin_manual", now=time.time())
        _audit(conn, admin_uid=admin_uid, action="manual_grant", order=order, reason=r,
               detail={"plan": order["plan_id"], "status_unchanged": order["status"]})
        return {"ok": True, "order_code": int(order["order_code"]), "status": order["status"], "subscription": sub}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# refunds (mục 8 · PAY-03) — REFUND_PENDING → REFUNDED, revoke entitlement
# ---------------------------------------------------------------------------

ACADEMY_FULL_KEY = "academy.lesson.full"


def _refund_rules() -> dict[str, Any]:
    r = cp.rules().get("refund") or {}
    return {
        "window_days": int(r.get("window_days") or 7),
        "max_academy_lessons": int(r.get("max_academy_lessons") or 3),
        "max_os_budget_periods": int(r.get("max_os_budget_periods") or 1),
    }


def _usage_academy_lessons(user_id: str) -> int:
    try:
        from welora import academy

        prof = academy._PROFILES.get(user_id) or {}
        done = set(prof.get("read") or [])
        for nid, st in (prof.get("nodes") or {}).items():
            if (st or {}).get("mastery_level") not in (None, "not_started"):
                done.add(nid)
        return len(done)
    except Exception:
        return 0


def _usage_budget_periods(conn: Any, user_id: str) -> int:
    periods: set[str] = set()
    try:
        from welora import budget

        cur = budget._BUDGETS.get(user_id) or {}
        if cur.get("period"):
            periods.add(str(cur["period"]))
        for k in list(budget._BUDGET_PERIODS):
            if k.startswith(f"{user_id}:"):
                periods.add(k.split(":", 1)[1])
    except Exception:
        pass
    try:
        for r in conn.execute("SELECT period FROM os_budgets WHERE user_id=?", (user_id,)).fetchall():
            periods.add(str(r["period"]))
    except Exception:
        conn.rollback()
    return len(periods)


def _usage_now(conn: Any, user_id: str) -> dict[str, int]:
    return {"academy_lessons": _usage_academy_lessons(user_id), "os_budget_periods": _usage_budget_periods(conn, user_id)}


def _snapshot_usage(conn: Any, order: dict[str, Any], *, now: float) -> None:
    """Baseline at PAID so PAY-03 counts only usage after purchase (free samples excluded)."""
    _insert_event(
        conn, order_id=order["id"], provider="welora", event_type="usage.baseline",
        ref=f"usage:{order['id']}", amount=0, raw=_usage_now(conn, order["user_id"]),
        signature_valid=True, now=now,
    )


def _usage_since_paid(conn: Any, order: dict[str, Any]) -> dict[str, int]:
    base = {"academy_lessons": 0, "os_budget_periods": 0}
    r = conn.execute(
        "SELECT raw_payload FROM payment_events WHERE provider_txn_ref=?", (f"usage:{order['id']}",)
    ).fetchone()
    if r:
        try:
            base.update({k: int(v) for k, v in (json.loads(r["raw_payload"]) or {}).items()})
        except (ValueError, TypeError):
            pass
    cur = _usage_now(conn, order["user_id"])
    return {k: max(0, cur[k] - base.get(k, 0)) for k in cur}


def _refund_eligibility(conn: Any, order: dict[str, Any], *, now: float) -> dict[str, Any]:
    rr = _refund_rules()
    out: dict[str, Any] = {"eligible": False, "order_code": int(order["order_code"]), "rules": rr}
    if order["status"] != "PAID":
        out.update(reason_code="NOT_PAID", message="Chỉ đơn đã thanh toán mới yêu cầu hoàn tiền")
        return out
    if order.get("is_preorder"):
        ff = ent.founding_family_status(order["plan_id"])
        ok = bool(ff.get("preorder_enabled"))
        out.update(
            eligible=ok, policy="preorder_100",
            reason_code="OK" if ok else "PREORDER_LAUNCHED",
            message="Đặt trước gói gia đình: hoàn 100% trước khi gói ra mắt (PRICING-01)"
            if ok else "Gói đã ra mắt — áp dụng chính sách hoàn tiền thường",
        )
        if ok:
            return out
    paid_at = _ts(order.get("paid_at"))
    window_end = paid_at + rr["window_days"] * 86400
    usage = _usage_since_paid(conn, order)
    out.update(policy="pay03_7d", window_ends_at=_iso(window_end), usage=usage)
    info = ent.plan_by_code(order["plan_id"]) or {}
    keys = {e.get("key") for e in info.get("entitlements") or [] if isinstance(e, dict)}
    if now > window_end:
        out.update(reason_code="WINDOW_PASSED", message=f"Quá {rr['window_days']} ngày kể từ khi thanh toán")
    elif ACADEMY_FULL_KEY in keys and usage["academy_lessons"] > rr["max_academy_lessons"]:
        out.update(reason_code="ACADEMY_USED", message=f"Đã học quá {rr['max_academy_lessons']} bài")
    elif order["plan_id"] in ent.OS_PLANS and usage["os_budget_periods"] > rr["max_os_budget_periods"]:
        out.update(reason_code="OS_USED", message=f"Đã dùng quá {rr['max_os_budget_periods']} kỳ ngân sách")
    else:
        out.update(eligible=True, reason_code="OK", message="Đủ điều kiện hoàn 100%")
    return out


def refund_eligibility_for_user(user_id: str, order_code: int, *, now: Optional[float] = None) -> dict[str, Any]:
    _require_enabled()
    conn = _conn()
    try:
        order = _get_order(conn, order_code=order_code)
        if not order or order["user_id"] != user_id:
            raise CheckoutError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn")
        return _refund_eligibility(conn, order, now=_now(now))
    finally:
        conn.close()


def _mark_refund_pending(conn: Any, order: dict[str, Any], *, by: str, reason: str, now: float) -> None:
    if not _set_status(conn, order["id"], "REFUND_PENDING", from_states=("PAID", "UNDERPAID")):
        raise CheckoutError(409, "INVALID_TRANSITION", f"Không chuyển được từ {order['status']}")
    _insert_event(
        conn, order_id=order["id"], provider="welora", event_type="refund.requested",
        ref=f"refund:req:{order['id']}:{uuid.uuid4().hex[:8]}", amount=int(order.get("amount_paid") or 0),
        raw={"by": by, "reason": reason[:500], "from": order["status"]}, signature_valid=True, now=now,
    )
    ent.emit_event("refund_requested", {"order_code": int(order["order_code"]), "by": by})


def request_refund_for_user(user_id: str, order_code: int, reason: str, *, now: Optional[float] = None) -> dict[str, Any]:
    """User taps "Yêu cầu hoàn tiền" — only shown/allowed when PAY-03 eligible."""
    _require_enabled()
    t = _now(now)
    r = _require_reason(reason)
    conn = _conn()
    try:
        order = _get_order(conn, order_code=order_code)
        if not order or order["user_id"] != user_id:
            raise CheckoutError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn")
        el = _refund_eligibility(conn, order, now=t)
        if not el["eligible"]:
            raise CheckoutError(409, "REFUND_NOT_ELIGIBLE", el.get("message") or "Không đủ điều kiện", eligibility=el)
        _mark_refund_pending(conn, order, by="user", reason=r, now=t)
        order = _get_order(conn, order_id=order["id"])
        return public_order(order, _link_info(conn, order["id"]), now=t)
    finally:
        conn.close()


def _refresh_entitlement(user_id: str, *, reason: str) -> None:
    """Recompute in-memory entitlement from DB subscriptions (after refund / downgrade)."""
    restored = _resolve_subscription(user_id)
    if restored:
        ent.set_subscription_state(user_id, restored["plan"], restored["subscription"])
    else:
        ent.revoke_plan(user_id, reason=reason)


def _rollback_subscription(conn: Any, order: dict[str, Any], *, now: float) -> dict[str, Any]:
    """Remove the period this order bought; expire when nothing paid remains."""
    sub = _row(
        conn.execute(
            "SELECT * FROM subscriptions WHERE user_id=? AND plan_id=?", (order["user_id"], order["plan_id"])
        ).fetchone()
    )
    if not sub:
        return {"subscription": None}
    end = sub_period(_ts(sub["current_period_end"]), order["billing_cycle"])
    if end <= now:
        conn.execute(
            "UPDATE subscriptions SET status='expired', current_period_end=? WHERE id=?", (_iso(now), sub["id"])
        )
    else:
        start = min(_ts(sub["current_period_start"]), sub_period(end, order["billing_cycle"]))
        conn.execute(
            "UPDATE subscriptions SET current_period_start=?, current_period_end=? WHERE id=?",
            (_iso(start), _iso(end), sub["id"]),
        )
    conn.commit()
    return {"subscription": _row(conn.execute("SELECT * FROM subscriptions WHERE id=?", (sub["id"],)).fetchone())}


def admin_refund(
    *,
    admin_uid: str,
    order_code: int,
    reason: str,
    stage: str = "request",
    override: bool = False,
    bank_ref: Optional[str] = None,
    amount: Optional[int] = None,
    now: Optional[float] = None,
) -> dict[str, Any]:
    """Record refund (manual bank transfer back to the paying account).

    request  → PAID/UNDERPAID → REFUND_PENDING (PAY-03 checked; override audited)
    complete → REFUND_PENDING → REFUNDED + payment_events refund.completed +
               orders.refund_amount/refunded_at + subscription rollback + revoke
    excess   → overpaid / paid twice: record refund of the extra only (no state change)
    """
    r = _require_reason(reason)
    t = _now(now)
    conn = _conn()
    try:
        order = _get_order(conn, order_code=order_code)
        if not order:
            raise CheckoutError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn")
        detail: dict[str, Any] = {"from": order["status"]}
        if stage == "request":
            if order["status"] == "PAID":
                el = _refund_eligibility(conn, order, now=t)
                detail["eligibility"] = {k: el.get(k) for k in ("eligible", "reason_code", "policy", "usage")}
                if not el["eligible"] and not override:
                    raise CheckoutError(
                        409, "REFUND_NOT_ELIGIBLE", el.get("message") or "Không đủ điều kiện", eligibility=el
                    )
                detail["override"] = bool(override and not el["eligible"])
            _mark_refund_pending(conn, order, by=f"admin:{admin_uid}", reason=r, now=t)
        elif stage == "complete":
            paid = int(order.get("amount_paid") or 0)
            amt = int(amount) if amount not in (None, "") else paid
            if amt <= 0 or amt > max(paid, 0):
                raise CheckoutError(400, "REFUND_AMOUNT_INVALID", "Số tiền hoàn phải > 0 và không vượt số đã trả")
            if not _set_status(conn, order["id"], "REFUNDED", from_states=("REFUND_PENDING",)):
                raise CheckoutError(409, "INVALID_TRANSITION", f"Không chuyển được từ {order['status']}")
            conn.execute(
                "UPDATE orders SET refund_amount=?, refunded_at=? WHERE id=?", (amt, _iso(t), order["id"])
            )
            conn.commit()
            _insert_event(
                conn, order_id=order["id"], provider="welora", event_type="refund.completed",
                ref=f"refund:done:{order['id']}", amount=amt,
                raw={"admin": admin_uid, "bank_ref": (bank_ref or "")[:120], "method": "manual_bank_transfer"},
                signature_valid=True, now=t,
            )
            detail.update(amount=amt, bank_ref=(bank_ref or "")[:120])
            if order.get("paid_at"):  # entitlement was granted → take it back
                detail.update(_rollback_subscription(conn, order, now=t))
                detail.update(_restore_previous_plan(conn, order, now=t))  # CK-14 upgrade refund
                _refresh_entitlement(order["user_id"], reason="refund")
            ent.emit_event("refund_completed", {"order_code": int(order["order_code"]), "amount": amt})
        elif stage == "excess":
            paid = int(order.get("amount_paid") or 0)
            amt = int(amount or 0)
            if amt <= 0 or amt > paid:
                raise CheckoutError(400, "REFUND_AMOUNT_INVALID", "Nhập số tiền hoàn phần thừa")
            _insert_event(
                conn, order_id=order["id"], provider="welora", event_type="refund.excess",
                ref=f"refund:excess:{order['id']}:{uuid.uuid4().hex[:8]}", amount=amt,
                raw={"admin": admin_uid, "bank_ref": (bank_ref or "")[:120]}, signature_valid=True, now=t,
            )
            conn.execute(
                "UPDATE orders SET refund_amount=refund_amount+? WHERE id=?", (amt, order["id"])
            )
            conn.commit()
            detail.update(amount=amt, bank_ref=(bank_ref or "")[:120])
        else:
            raise CheckoutError(400, "INVALID_STAGE", "stage phải là request, complete hoặc excess")
        _audit(conn, admin_uid=admin_uid, action=f"refund_{stage}", order=order, reason=r, detail=detail)
        order = _get_order(conn, order_id=order["id"])
        return {
            "ok": True, "order_code": int(order["order_code"]), "status": order["status"],
            "refund_amount": int(order.get("refund_amount") or 0),
        }
    finally:
        conn.close()


def checkout_config() -> dict[str, Any]:
    from welora.payments.provider import provider_name_from_env

    rr = _refund_rules()
    return {
        "checkout_enabled": checkout_enabled(),
        "plans": list(CHECKOUT_PLANS),
        "billing_cycles": list(BILLING_CYCLES),
        "expiry_minutes": EXPIRY_MINUTES,
        "poll_interval_s": 3,
        "provider": provider_name_from_env(),
        "lifetime_enabled": False,
        "coupons_enabled": True,
        "price_experiment_active": bool(cp.experiment().get("active")),
        "refund_policy": rr,
        "grace_days": ent.GRACE_DAYS,
    }


def qr_svg(user_id: str, order_code: int) -> str:
    """Render order qr_code (VietQR payload) as SVG — same-origin (CSP img-src 'self' data:)."""
    _require_enabled()
    conn = _conn()
    try:
        order = _get_order(conn, order_code=order_code)
        if not order or order["user_id"] != user_id:
            raise CheckoutError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn")
        payload = order.get("qr_code") or ""
        remaining = max(0, int(order["amount"]) - int(order.get("amount_paid") or 0))
        if order["status"] == "UNDERPAID" and remaining > 0:
            link = _link_info(conn, order["id"])
            if link.get("bin") and link.get("accountNumber"):
                from welora import vietqr

                payload = vietqr.build_payload(
                    bin_code=str(link["bin"]), account_number=str(link["accountNumber"]), amount=remaining,
                    description=link.get("description") or build_description(int(order["order_code"])),
                )
    finally:
        conn.close()
    if not payload:
        raise CheckoutError(404, "QR_MISSING", "Đơn chưa có mã QR")
    try:
        import io

        import qrcode
        import qrcode.image.svg
    except ImportError:
        raise CheckoutError(503, "QR_RENDER_UNAVAILABLE", "Không dựng được QR; dùng link thanh toán")
    img = qrcode.make(payload, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode("utf-8")


# ---------------------------------------------------------------------------
# CK-12 prices for the logged-in user (A/B variant applied)
# ---------------------------------------------------------------------------


def prices_for_user(user_id: Optional[str]) -> dict[str, Any]:
    _require_enabled()
    conn = _conn() if user_id else None
    try:
        exp = cp.experiment()
        variant = cp.assign_variant(conn, user_id) if conn is not None else str(exp.get("variant") or "A")
        out: dict[str, Any] = {}
        for plan in CHECKOUT_PLANS:
            v = variant if plan == (exp.get("plan") or "ACA") else None
            out[plan] = {c: cp.list_price(plan, c, v) for c in BILLING_CYCLES}
        return {"plans": out, "price_variant": variant, "experiment_active": bool(exp.get("active"))}
    finally:
        if conn is not None:
            conn.close()


# ---------------------------------------------------------------------------
# CK-13 "Gói của tôi"
# ---------------------------------------------------------------------------


def my_plan(user_id: str, *, now: Optional[float] = None) -> dict[str, Any]:
    _require_enabled()
    t = _now(now)
    conn = _conn()
    try:
        me = ent.get_me(user_id)
        subs = []
        for r in conn.execute(
            "SELECT s.*, o.billing_cycle AS last_cycle FROM subscriptions s LEFT JOIN orders o ON o.id=s.last_order_id "
            "WHERE s.user_id=? ORDER BY s.current_period_end DESC",
            (user_id,),
        ).fetchall():
            row = _row(r)
            end = _ts(row["current_period_end"])
            grace_end = end + ent.GRACE_DAYS * 86400
            state = row["status"]
            if state != "expired":
                state = "active" if t <= end else ("grace" if t <= grace_end else "expired")
            subs.append({
                "plan_id": row["plan_id"],
                "plan_name": (ent.plan_by_code(row["plan_id"]) or {}).get("name") or row["plan_id"],
                "status": state,
                "billing_cycle": row.get("last_cycle") or "month",
                "current_period_start": row["current_period_start"],
                "current_period_end": row["current_period_end"],
                "grace_ends_at": _iso(grace_end),
                "days_left": max(0, int((end - t) // 86400)),
            })
        current = next((x for x in subs if x["status"] in ("active", "grace")), None)
        history = []
        for r in conn.execute(
            "SELECT * FROM orders WHERE user_id=? AND status IN ('PAID','UNDERPAID','REFUND_PENDING','REFUNDED') "
            "ORDER BY created_at DESC LIMIT 50",
            (user_id,),
        ).fetchall():
            o = _row(r)
            item = public_order(o, now=t)
            for k in ("checkout_url", "qr_code", "account_number", "account_name", "bin"):
                item.pop(k, None)
            item["refund"] = _refund_eligibility(conn, o, now=t) if o["status"] == "PAID" else None
            history.append(item)
        actions: dict[str, Any] = {"renew": None, "upgrades": [], "switch_to_year": None}
        if current:
            actions["renew"] = {"plan_id": current["plan_id"], "billing_cycle": current["billing_cycle"]}
            if current["billing_cycle"] == "month":
                m = ent.price_amount(current["plan_id"], "month") or 0
                y = ent.price_amount(current["plan_id"], "year") or 0
                if m and y and m * 12 > y:
                    actions["switch_to_year"] = {
                        "plan_id": current["plan_id"], "month_x12": m * 12, "year": y, "savings": m * 12 - y,
                    }
            for plan in CHECKOUT_PLANS:
                if cp.rank(plan) <= cp.rank(current["plan_id"]):
                    continue
                try:
                    q = quote(plan, current["billing_cycle"], now=t, user_id=user_id, conn=conn)
                    _check_purchase_rules(user_id, plan)
                except CheckoutError:
                    continue
                actions["upgrades"].append({
                    "plan_id": plan, "plan_name": q["plan_name"], "billing_cycle": q["billing_cycle"],
                    "list_price": q["list_price"], "upgrade_credit": q["upgrade_credit"], "amount": q["amount"],
                })
        return {
            "plan": me.get("plan"),
            "in_grace": bool(me.get("in_grace")),
            "renewal_banner": me.get("renewal_banner"),
            "current": current,
            "subscriptions": subs,
            "history": history,
            "actions": actions,
            "grace_days": ent.GRACE_DAYS,
        }
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# mục 7 — one-tap renewal link (magic link, 24h, single use)
# ---------------------------------------------------------------------------


def _magic_hash(token: str) -> str:
    return hashlib.sha256(("welora-renew:" + token).encode("utf-8")).hexdigest()


def create_renewal_link(conn: Any, *, user_id: str, plan_id: str, billing_cycle: str, now: Optional[float] = None) -> str:
    t = _now(now)
    hours = int((cp.rules().get("renewal") or {}).get("magic_link_hours") or 24)
    token = secrets.token_urlsafe(32)
    conn.execute(
        "INSERT INTO renewal_links(token_hash, user_id, plan_id, billing_cycle, expires_at, used_at, created_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (_magic_hash(token), user_id, plan_id, billing_cycle, _iso(t + hours * 3600), None, _iso(t)),
    )
    conn.commit()
    # token in the URL fragment: never sent to servers / access logs
    return f"{_public_base_url()}/app/checkout/renew#t={token}"


def consume_renewal_link(token: str, *, now: Optional[float] = None) -> dict[str, Any]:
    """Exchange magic link → session token + renewal order (opens QR directly)."""
    _require_enabled()
    t = _now(now)
    tok = (token or "").strip()
    if len(tok) < 20:
        raise CheckoutError(400, "RENEW_LINK_INVALID", "Link gia hạn không hợp lệ")
    conn = _conn()
    try:
        row = _row(conn.execute("SELECT * FROM renewal_links WHERE token_hash=?", (_magic_hash(tok),)).fetchone())
        if not row:
            raise CheckoutError(400, "RENEW_LINK_INVALID", "Link gia hạn không hợp lệ")
        if row.get("used_at"):
            raise CheckoutError(410, "RENEW_LINK_USED", "Link đã được dùng — đăng nhập để gia hạn")
        if t > _ts(row["expires_at"]):
            raise CheckoutError(410, "RENEW_LINK_EXPIRED", "Link đã hết hạn (24 giờ) — đăng nhập để gia hạn")
        cur = conn.execute(
            "UPDATE renewal_links SET used_at=? WHERE token_hash=? AND used_at IS NULL", (_iso(t), row["token_hash"])
        )
        conn.commit()
        if (cur.rowcount or 0) != 1:
            raise CheckoutError(410, "RENEW_LINK_USED", "Link đã được dùng — đăng nhập để gia hạn")
        from welora import auth as auth_svc

        u = conn.execute("SELECT role FROM users WHERE user_id=?", (row["user_id"],)).fetchone()
        if not u or ((u["role"] or "").strip().lower() in auth_svc.ADMIN_ROLES):
            raise CheckoutError(403, "RENEW_LINK_FORBIDDEN", "Không dùng link gia hạn cho tài khoản này")
        session = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO auth_tokens(token, user_id, device_id, kind, expires_at) VALUES (?,?,?,?,?)",
            (session, row["user_id"], None, "magic_renew", _iso(t + 24 * 3600)),
        )
        conn.commit()
    finally:
        conn.close()
    order = None
    error = None
    try:
        order = create_order(user_id=row["user_id"], plan_id=row["plan_id"], billing_cycle=row["billing_cycle"])
    except CheckoutError as e:
        error = e.body()
    return {"token": session, "order": order, "error": error, "plan_id": row["plan_id"], "billing_cycle": row["billing_cycle"]}


# ---------------------------------------------------------------------------
# mục 10 sandbox acceptance — NON-PROD test hooks (refused in production)
# ---------------------------------------------------------------------------


def test_hooks_allowed() -> bool:
    env = (os.environ.get("WELORA_ENV") or "").strip().lower()
    if env in ("production", "prod"):
        return False
    return (os.environ.get("WELORA_CHECKOUT_TEST_HOOKS") or "").strip() == "1"


def _require_test_hooks() -> None:
    if not test_hooks_allowed():
        raise CheckoutError(
            403, "TEST_HOOKS_DISABLED",
            "Test hooks chỉ bật ở non-prod với WELORA_CHECKOUT_TEST_HOOKS=1 (luôn tắt ở production)",
        )


def admin_test_shift_subscription(*, admin_uid: str, order_code: int, days: float, reason: str) -> dict[str, Any]:
    """Time-travel: move the order's subscription period back by `days` (e.g. 8 → grace over)."""
    _require_test_hooks()
    r = _require_reason(reason)
    d = float(days)
    if not (0 < d <= 400):
        raise CheckoutError(400, "INVALID_DAYS", "days phải trong (0, 400]")
    conn = _conn()
    try:
        order = _get_order(conn, order_code=order_code)
        if not order:
            raise CheckoutError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn")
        sub = _row(
            conn.execute(
                "SELECT * FROM subscriptions WHERE user_id=? AND plan_id=?", (order["user_id"], order["plan_id"])
            ).fetchone()
        )
        if not sub:
            raise CheckoutError(404, "SUBSCRIPTION_NOT_FOUND", "Đơn chưa có gói")
        sh = d * 86400
        conn.execute(
            "UPDATE subscriptions SET current_period_start=?, current_period_end=? WHERE id=?",
            (_iso(_ts(sub["current_period_start"]) - sh), _iso(_ts(sub["current_period_end"]) - sh), sub["id"]),
        )
        conn.commit()
        _audit(conn, admin_uid=admin_uid, action="test_shift_subscription", order=order, reason=r, detail={"days": d})
        _refresh_entitlement(order["user_id"], reason="test_shift")
        sub = _row(conn.execute("SELECT * FROM subscriptions WHERE id=?", (sub["id"],)).fetchone())
        return {"ok": True, "subscription": sub, "non_prod_only": True}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# admin CK-11 / CK-12 wrappers
# ---------------------------------------------------------------------------


def admin_create_coupon(*, admin_uid: str, body: dict[str, Any]) -> dict[str, Any]:
    r = _require_reason(body.get("reason"))
    conn = _conn()
    try:
        row = cp.create_coupon(conn, admin_uid=admin_uid, body=body)
        _audit(conn, admin_uid=admin_uid, action="coupon_create", order=None, reason=r,
               detail={k: row.get(k) for k in ("code", "kind", "value", "max_redemptions", "plans", "cycles")})
        return {"ok": True, "coupon": row}
    finally:
        conn.close()


def admin_list_coupons() -> list[dict[str, Any]]:
    conn = _conn()
    try:
        return cp.list_coupons(conn)
    finally:
        conn.close()


def admin_set_coupon_active(*, admin_uid: str, code: str, active: bool, reason: str) -> dict[str, Any]:
    r = _require_reason(reason)
    conn = _conn()
    try:
        if not cp.set_coupon_active(conn, code, active):
            raise CheckoutError(404, "COUPON_NOT_FOUND", "Không tìm thấy mã")
        _audit(conn, admin_uid=admin_uid, action="coupon_activate" if active else "coupon_deactivate",
               order=None, reason=r, detail={"code": cp.normalize_code(code)})
        return {"ok": True, "code": cp.normalize_code(code), "active": bool(active)}
    finally:
        conn.close()


def admin_unmatched_payments(limit: int = 100) -> list[dict[str, Any]]:
    """Signed payments that no order could claim (unknown orderCode, no/ambiguous
    description). Read-only; admin resolves via manual grant (CK-10) or refund."""
    conn = _conn()
    try:
        out = []
        for r in conn.execute(
            "SELECT * FROM payment_events WHERE order_id IS NULL AND signature_valid=1 AND event_type=? "
            "ORDER BY received_at DESC LIMIT ?",
            ("webhook.payment", max(1, min(int(limit), 500))),
        ).fetchall():
            ev = _row(r)
            try:
                data = (json.loads(ev.get("raw_payload") or "{}") or {}).get("data") or {}
            except (ValueError, TypeError):
                data = {}
            _, method = match_order_by_description(conn, data.get("description"))
            out.append({
                "reference": ev["provider_txn_ref"], "amount": int(ev["amount"] or 0), "received_at": ev["received_at"],
                "order_code_in_payload": _int(data.get("orderCode")) or None,
                "description": str(data.get("description") or "")[:200],
                "match": method,
            })
        return out
    finally:
        conn.close()


def admin_experiment_stats() -> dict[str, Any]:
    conn = _conn()
    try:
        return cp.experiment_stats(conn)
    finally:
        conn.close()
