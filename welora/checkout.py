"""Checkout VietQR P0 — CK-01…CK-10 (Phụ lục PRD Checkout thanh toán VietQR).

- Amount is ALWAYS computed server-side from config/pricing_module.json
  (via welora.entitlements). Any client-sent amount is ignored (CK-04).
- Only the webhook or the reconcile job may set PAID (CK-08). returnUrl only
  redirects. Admin manual grant never sets PAID; it is audit-logged.
- Webhook: verify signature → store payment_events (UNIQUE provider_txn_ref)
  → idempotent → compare amount (under → UNDERPAID) → PAID + grant (CK-07).
- 1 PENDING per user per plan: a new order cancels the old link.
- Runtime switch: WELORA_CHECKOUT_ENABLED (default off → 403).

Does not touch Hard Deny R01–R09 / TARGET_MONTHS / Pre-Rule / gate_months.
Lifetime stays OFF (billing_cycle only month|year).
"""

from __future__ import annotations

import calendar
import json
import logging
import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

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


def quote(plan_id: str, billing_cycle: str, *, now: Optional[float] = None) -> dict[str, Any]:
    plan, cycle = _norm_plan_cycle(plan_id, billing_cycle)
    list_price = ent.price_amount(plan, cycle)
    if list_price is None or list_price <= 0:
        raise CheckoutError(400, "PRICE_MISSING", f"Không có giá {plan}/{cycle} trong config")
    discount = 0  # CK-11 coupons are P1
    amount = max(0, int(list_price) - discount)
    monthly = ent.price_amount(plan, "month") or 0
    yearly = ent.price_amount(plan, "year") or 0
    info = ent.plan_by_code(plan) or {}
    t = _now(now)
    preorder = _is_preorder(plan)
    return {
        "plan_id": plan,
        "plan_name": info.get("name") or plan,
        "billing_cycle": cycle,
        "list_price": int(list_price),
        "discount": discount,
        "amount": amount,
        "currency": "VND",
        "members": int(info.get("seat_limit") or 1),
        "year_savings": max(0, monthly * 12 - yearly) if monthly and yearly else 0,
        "expected_period_end": _iso(add_period(t, cycle)),
        "is_preorder": preorder,
        "founding_family": ent.founding_family_status(plan) if preorder else None,
        "price_variant": ent.assign_experiment("aca_price_ab").get("variant") if plan == "ACA" else None,
    }


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
    }


def create_order(
    *,
    user_id: Optional[str],
    plan_id: str,
    billing_cycle: str,
    client_amount: Any = None,
    now: Optional[float] = None,
    provider: Optional[PaymentProvider] = None,
) -> dict[str, Any]:
    p = _require_enabled(provider)
    uid = (user_id or "").strip()
    if not uid:
        raise CheckoutError(401, "LOGIN_REQUIRED", "Cần đăng nhập trước khi thanh toán")
    q = quote(plan_id, billing_cycle, now=now)
    plan, cycle = q["plan_id"], q["billing_cycle"]
    _check_purchase_rules(uid, plan)
    if client_amount is not None:
        log.info("client amount ignored (server price used) plan=%s cycle=%s", plan, cycle)

    t = _now(now)
    conn = _conn()
    try:
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
                    "amount_paid, is_preorder, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        oid, code, uid, plan, cycle, q["list_price"], q["discount"], q["amount"],
                        None, q["price_variant"], p.name, "PENDING",
                        _iso(t + EXPIRY_MINUTES * 60), 0, 1 if q["is_preorder"] else 0, _iso(t),
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
            {"user_id": uid, "plan": plan, "cycle": cycle, "order_code": int(order["order_code"])},
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
            ent.emit_event(
                "checkout_completed",
                {"order_code": int(order["order_code"]), "plan": order["plan_id"], "source": source},
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
        if not success:
            return 200, {"ok": True, "ignored": "non_success"}
        # 3. idempotent on already-settled orders
        if order["status"] in ("PAID", "REFUND_PENDING", "REFUNDED"):
            if order["status"] == "PAID":
                log.warning("second payment on PAID order=%s → admin refund", order_code)
            return 200, {"ok": True, "idempotent": True, "status": order["status"]}
        if order["status"] == "CANCELLED":
            log.warning("payment on CANCELLED order=%s → needs admin (CK-10)", order_code)
            return 200, {"ok": True, "needs_admin": True, "status": "CANCELLED"}
        # 4. compare amount → PAID / UNDERPAID
        status = _settle(conn, order["id"], source="webhook", now=t)
        return 200, {"ok": True, "status": status}
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# reconcile job (mục 5) — every 5 min, PENDING older than 2 min
# ---------------------------------------------------------------------------


def reconcile_once(*, now: Optional[float] = None, provider: Optional[PaymentProvider] = None) -> dict[str, Any]:
    if not checkout_enabled():
        return {"skipped": "checkout_disabled"}
    p = provider or get_provider()
    t = _now(now)
    summary = {"checked": 0, "paid": 0, "underpaid": 0, "expired": 0, "cancelled": 0, "refund_pending": 0, "errors": 0}
    conn = _conn()
    try:
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


def admin_refund(*, admin_uid: str, order_code: int, reason: str, stage: str = "request") -> dict[str, Any]:
    """Record refund: request → REFUND_PENDING; complete → REFUNDED + revoke."""
    r = _require_reason(reason)
    conn = _conn()
    try:
        order = _get_order(conn, order_code=order_code)
        if not order:
            raise CheckoutError(404, "ORDER_NOT_FOUND", "Không tìm thấy đơn")
        if stage == "request":
            ok = _set_status(conn, order["id"], "REFUND_PENDING", from_states=("PAID", "UNDERPAID"))
        elif stage == "complete":
            ok = _set_status(conn, order["id"], "REFUNDED", from_states=("REFUND_PENDING",))
            if ok:
                conn.execute(
                    "UPDATE subscriptions SET status='expired' WHERE user_id=? AND plan_id=?",
                    (order["user_id"], order["plan_id"]),
                )
                conn.commit()
                ent.revoke_plan(order["user_id"], reason="refund")
        else:
            raise CheckoutError(400, "INVALID_STAGE", "stage phải là request hoặc complete")
        if not ok:
            raise CheckoutError(409, "INVALID_TRANSITION", f"Không chuyển được từ {order['status']}")
        _audit(conn, admin_uid=admin_uid, action=f"refund_{stage}", order=order, reason=r,
               detail={"from": order["status"]})
        order = _get_order(conn, order_id=order["id"])
        return {"ok": True, "order_code": int(order["order_code"]), "status": order["status"]}
    finally:
        conn.close()


def checkout_config() -> dict[str, Any]:
    from welora.payments.provider import provider_name_from_env

    return {
        "checkout_enabled": checkout_enabled(),
        "plans": list(CHECKOUT_PLANS),
        "billing_cycles": list(BILLING_CYCLES),
        "expiry_minutes": EXPIRY_MINUTES,
        "poll_interval_s": 3,
        "provider": provider_name_from_env(),
        "lifetime_enabled": False,
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
