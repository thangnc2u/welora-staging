"""Checkout P1 pricing — CK-11 coupons · CK-12 A/B Academy price · CK-14 upgrade credit.

Everything is computed server-side. Prices and rules come from
config/pricing_module.json (``experiments`` + ``checkout_rules``); coupons live
in the DB (created by admins behind 2FA). Nothing here is hard-coded per price.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import uuid
from typing import Any, Optional

from welora import entitlements as ent

EXPERIMENT_KEY = "aca_price_ab"
PLAN_RANK = {"FREE": 0, "ACA_SV": 1, "ACA": 2, "OS1": 3, "OS2": 4, "OS2G": 5, "OS3G": 6}
COUPON_RE = re.compile(r"^[A-Z0-9_-]{3,32}$")
STUDENT_STATES = ("free_active", "verified", "aca_sv", "free_expired")


def rules() -> dict[str, Any]:
    return dict(ent.load_pricing_module().get("checkout_rules") or {})


def min_amount() -> int:
    return int(rules().get("min_amount") or 2000)


def credit_round_down() -> int:
    return max(1, int(rules().get("upgrade_credit_round_down") or 1000))


def _err(status: int, code: str, msg: str, **extra: Any):
    from welora.checkout import CheckoutError

    return CheckoutError(status, code, msg, **extra)


# ---------------------------------------------------------------------------
# CK-12 A/B test (fixed group per user, stored on order.price_variant)
# ---------------------------------------------------------------------------


def experiment() -> dict[str, Any]:
    for e in ent.load_pricing_module().get("experiments") or []:
        if e.get("key") == EXPERIMENT_KEY:
            return dict(e)
    return {"key": EXPERIMENT_KEY, "active": False, "variant": "A"}


def _bucket(user_id: str, split: dict[str, Any]) -> str:
    names = sorted(split) or ["A"]
    total = sum(max(0, int(split[n] or 0)) for n in names) or 1
    h = int(hashlib.sha256(f"{EXPERIMENT_KEY}:{user_id}".encode("utf-8")).hexdigest(), 16) % total
    acc = 0
    for n in names:
        acc += max(0, int(split[n] or 0))
        if h < acc:
            return n
    return names[-1]


def assign_variant(conn: Any, user_id: Optional[str], *, now: Optional[float] = None) -> str:
    """Return the user's fixed variant. Inactive experiment → default variant, not persisted."""
    exp = experiment()
    default = str(exp.get("variant") or "A")
    uid = (user_id or "").strip()
    if not exp.get("active") or not uid:
        return default
    r = conn.execute(
        "SELECT variant FROM experiment_assignments WHERE user_id=? AND experiment_key=?", (uid, EXPERIMENT_KEY)
    ).fetchone()
    if r:
        return str(r["variant"])
    variant = _bucket(uid, exp.get("split") or {"A": 50, "B": 50})
    try:
        conn.execute(
            "INSERT INTO experiment_assignments(user_id, experiment_key, variant, assigned_at) VALUES (?,?,?,?)",
            (uid, EXPERIMENT_KEY, variant, _iso(now)),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        r = conn.execute(
            "SELECT variant FROM experiment_assignments WHERE user_id=? AND experiment_key=?", (uid, EXPERIMENT_KEY)
        ).fetchone()
        variant = str(r["variant"]) if r else variant
    ent.emit_event("experiment_assigned", {"key": EXPERIMENT_KEY, "variant": variant})
    return variant


def list_price(plan: str, cycle: str, variant: Optional[str]) -> Optional[int]:
    """Config price, overridden by the A/B variant price for the experiment plan."""
    base = ent.price_amount(plan, cycle)
    exp = experiment()
    if variant and plan == (exp.get("plan") or "ACA"):
        vp = (exp.get("variant_prices") or {}).get(variant) or {}
        if vp.get(cycle):
            return int(vp[cycle])
    return base


def experiment_stats(conn: Any) -> dict[str, Any]:
    exp = experiment()
    plan = exp.get("plan") or "ACA"
    out: dict[str, Any] = {"key": EXPERIMENT_KEY, "active": bool(exp.get("active")), "plan": plan, "variants": {}}
    for r in conn.execute(
        "SELECT variant, COUNT(*) AS n FROM experiment_assignments WHERE experiment_key=? GROUP BY variant",
        (EXPERIMENT_KEY,),
    ).fetchall():
        out["variants"].setdefault(r["variant"], {})["assigned_users"] = int(r["n"])
    for r in conn.execute(
        "SELECT price_variant AS v, COUNT(*) AS orders, COUNT(DISTINCT user_id) AS users, "
        "SUM(CASE WHEN status IN ('PAID','REFUND_PENDING','REFUNDED') THEN 1 ELSE 0 END) AS paid "
        "FROM orders WHERE plan_id=? AND price_variant IS NOT NULL GROUP BY price_variant",
        (plan,),
    ).fetchall():
        v = out["variants"].setdefault(r["v"], {})
        v["orders_created"] = int(r["orders"] or 0)
        v["users_with_order"] = int(r["users"] or 0)
        v["orders_paid"] = int(r["paid"] or 0)
        v["conversion_qr_to_paid"] = round((v["orders_paid"] / v["orders_created"]), 4) if v["orders_created"] else 0.0
    return out


# ---------------------------------------------------------------------------
# CK-11 coupons
# ---------------------------------------------------------------------------


def _iso(now: Optional[float]) -> str:
    from welora.checkout import _iso as iso

    return iso(time.time() if now is None else float(now))


def normalize_code(code: Optional[str]) -> str:
    return (code or "").strip().upper()


def _is_student(user_id: str) -> bool:
    st = ent.get_me(user_id).get("student") or {}
    return st.get("status") in STUDENT_STATES


def _coupon_row(conn: Any, code: str) -> Optional[dict[str, Any]]:
    r = conn.execute("SELECT * FROM coupons WHERE code=?", (code,)).fetchone()
    return {k: r[k] for k in r.keys()} if r else None


def _uses(
    conn: Any, code: str, *, now: float, user_id: Optional[str] = None,
    exclude_pending: Optional[tuple[str, str]] = None,
) -> int:
    """PAID redemptions + in-flight PENDING orders (not yet expired) using the code.

    exclude_pending=(user_id, plan): that user's PENDING order for the plan is about
    to be replaced (1-PENDING rule), so it must not count.
    """
    from welora.checkout import _iso as iso

    q = "SELECT COUNT(*) AS n FROM coupon_redemptions WHERE coupon_code=?"
    p: list[Any] = [code]
    q2 = "SELECT COUNT(*) AS n FROM orders WHERE coupon_code=? AND status='PENDING' AND expires_at > ?"
    p2: list[Any] = [code, iso(now)]
    if user_id:
        q += " AND user_id=?"
        p.append(user_id)
        q2 += " AND user_id=?"
        p2.append(user_id)
    if exclude_pending:
        q2 += " AND NOT (user_id=? AND plan_id=?)"
        p2.extend(exclude_pending)
    a = conn.execute(q, tuple(p)).fetchone()
    b = conn.execute(q2, tuple(p2)).fetchone()
    return int(a["n"] or 0) + int(b["n"] or 0)


def validate_coupon(
    conn: Any, code: str, *, plan: str, cycle: str, user_id: Optional[str], list_amount: int, now: float,
    exclude_pending: Optional[tuple[str, str]] = None,
) -> tuple[str, int]:
    """Return (normalized code, discount) or raise CheckoutError."""
    c = normalize_code(code)
    if not COUPON_RE.match(c):
        raise _err(400, "COUPON_INVALID", "Mã giảm giá không hợp lệ")
    excluded = rules().get("coupon_excluded_plans") or ["ACA_SV"]
    if plan in excluded or (user_id and _is_student(user_id)):
        raise _err(400, "COUPON_NOT_WITH_STUDENT", "Mã giảm giá không cộng dồn với ưu đãi sinh viên")
    row = _coupon_row(conn, c)
    if not row or not int(row.get("active") or 0):
        raise _err(400, "COUPON_INVALID", "Mã giảm giá không tồn tại hoặc đã tắt")
    from welora.checkout import _ts

    if row.get("starts_at") and now < _ts(row["starts_at"]):
        raise _err(400, "COUPON_NOT_STARTED", "Mã giảm giá chưa đến ngày áp dụng")
    if row.get("ends_at") and now > _ts(row["ends_at"]):
        raise _err(400, "COUPON_EXPIRED", "Mã giảm giá đã hết hạn")
    plans = json.loads(row.get("plans") or "[]")
    cycles = json.loads(row.get("cycles") or "[]")
    if plans and plan not in plans:
        raise _err(400, "COUPON_PLAN_NOT_APPLICABLE", "Mã giảm giá không áp dụng cho gói này")
    if cycles and cycle not in cycles:
        raise _err(400, "COUPON_CYCLE_NOT_APPLICABLE", "Mã giảm giá không áp dụng cho chu kỳ này")
    if row.get("max_redemptions") is not None and _uses(conn, c, now=now, exclude_pending=exclude_pending) >= int(row["max_redemptions"]):
        raise _err(400, "COUPON_EXHAUSTED", "Mã giảm giá đã hết lượt")
    if user_id and _uses(conn, c, now=now, user_id=user_id, exclude_pending=exclude_pending) >= int(row.get("per_user_limit") or 1):
        raise _err(400, "COUPON_ALREADY_USED", "Bạn đã dùng mã giảm giá này")
    if row["kind"] == "percent":
        discount = int(list_amount) * min(100, int(row["value"])) // 100
    else:
        discount = int(row["value"])
    discount = max(0, min(discount, int(list_amount) - min_amount()))
    return c, discount


def record_redemption(conn: Any, order: dict[str, Any], *, now: float) -> None:
    if not order.get("coupon_code"):
        return
    try:
        conn.execute(
            "INSERT INTO coupon_redemptions(id, coupon_code, order_id, user_id, discount, redeemed_at) "
            "VALUES (?,?,?,?,?,?)",
            (uuid.uuid4().hex, order["coupon_code"], order["id"], order["user_id"], int(order["discount"] or 0), _iso(now)),
        )
        conn.commit()
    except Exception:
        conn.rollback()  # already recorded (UNIQUE order_id)


def create_coupon(conn: Any, *, admin_uid: str, body: dict[str, Any]) -> dict[str, Any]:
    code = normalize_code(body.get("code"))
    if not COUPON_RE.match(code):
        raise _err(400, "COUPON_INVALID", "Mã 3–32 ký tự A-Z 0-9 _ -")
    kind = (body.get("kind") or "").strip().lower()
    if kind not in ("percent", "fixed"):
        raise _err(400, "COUPON_KIND", "kind phải là percent hoặc fixed")
    try:
        value = int(body.get("value") or 0)
    except (TypeError, ValueError):
        value = 0
    if value <= 0 or (kind == "percent" and value > 100):
        raise _err(400, "COUPON_VALUE", "Giá trị giảm không hợp lệ")
    plans = [str(p).upper() for p in (body.get("plans") or [])]
    excluded = rules().get("coupon_excluded_plans") or ["ACA_SV"]
    if any(p in excluded for p in plans):
        raise _err(400, "COUPON_NOT_WITH_STUDENT", "Không tạo mã cho gói sinh viên")
    cycles = [str(c).lower() for c in (body.get("cycles") or [])]
    if any(c not in ("month", "year") for c in cycles):
        raise _err(400, "COUPON_CYCLE", "Chu kỳ month|year")
    mx = body.get("max_redemptions")
    try:
        conn.execute(
            "INSERT INTO coupons(code, kind, value, plans, cycles, starts_at, ends_at, max_redemptions, "
            "per_user_limit, active, created_by, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                code, kind, value, json.dumps(plans), json.dumps(cycles), body.get("starts_at") or None,
                body.get("ends_at") or None, int(mx) if mx not in (None, "") else None,
                max(1, int(body.get("per_user_limit") or 1)), 1, admin_uid, _iso(None),
            ),
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        from welora.checkout import _is_unique_violation

        if _is_unique_violation(e):
            raise _err(409, "COUPON_EXISTS", "Mã đã tồn tại")
        raise
    return _coupon_row(conn, code) or {}


def list_coupons(conn: Any) -> list[dict[str, Any]]:
    out = []
    for r in conn.execute("SELECT * FROM coupons ORDER BY created_at DESC").fetchall():
        row = {k: r[k] for k in r.keys()}
        row["plans"] = json.loads(row.get("plans") or "[]")
        row["cycles"] = json.loads(row.get("cycles") or "[]")
        n = conn.execute("SELECT COUNT(*) AS n FROM coupon_redemptions WHERE coupon_code=?", (row["code"],)).fetchone()
        row["redeemed"] = int(n["n"] or 0)
        out.append(row)
    return out


def set_coupon_active(conn: Any, code: str, active: bool) -> bool:
    cur = conn.execute("UPDATE coupons SET active=? WHERE code=?", (1 if active else 0, normalize_code(code)))
    conn.commit()
    return (cur.rowcount or 0) == 1


# ---------------------------------------------------------------------------
# CK-14 upgrade credit (prorate by day, round down to 1.000đ)
# ---------------------------------------------------------------------------


def rank(plan: str) -> int:
    return PLAN_RANK.get((plan or "").upper(), 0)


def active_subscriptions(conn: Any, user_id: str, *, now: float) -> list[dict[str, Any]]:
    from welora.checkout import _ts

    grace = int((rules().get("renewal") or {}).get("grace_days") or ent.GRACE_DAYS)
    out = []
    for r in conn.execute(
        "SELECT s.*, o.billing_cycle AS last_cycle, o.list_price AS last_list_price, o.discount AS last_discount, "
        "o.status AS last_status, o.amount_paid AS last_amount_paid FROM subscriptions s "
        "LEFT JOIN orders o ON o.id = s.last_order_id WHERE s.user_id=? AND s.status IN ('active','grace')",
        (user_id,),
    ).fetchall():
        row = {k: r[k] for k in r.keys()}
        if _ts(row["current_period_end"]) + grace * 86400 >= now:
            out.append(row)
    return out


def upgrade_credit(sub: dict[str, Any], *, now: float) -> dict[str, Any]:
    """Remaining value of the old plan by whole days, rounded DOWN to 1.000đ."""
    from welora.checkout import _ts, sub_period

    start, end = _ts(sub["current_period_start"]), _ts(sub["current_period_end"])
    cycle = sub.get("last_cycle") or "month"
    paid = (sub.get("last_status") in ("PAID",)) and int(sub.get("last_amount_paid") or 0) > 0
    value = int(sub.get("last_list_price") or 0) - int(sub.get("last_discount") or 0) if paid else 0
    days_total = max(1, round((end - start) / 86400))
    days_left = max(0, int((end - max(now, start)) // 86400))
    raw = value * min(days_left, days_total) / days_total
    if now < start:  # early-renewed: tail of the previous (already paid) period at list price
        prev_start = sub_period(start, cycle)
        prev_days = max(1, round((start - prev_start) / 86400))
        prev_left = int((start - now) // 86400)
        price = int(ent.price_amount(sub["plan_id"], cycle) or 0)
        raw += price * min(prev_left, prev_days) / prev_days
        days_left += prev_left
    step = credit_round_down()
    credit = int(raw // step) * step
    return {
        "from_plan": sub["plan_id"],
        "from_cycle": cycle,
        "days_left": days_left,
        "days_in_period": days_total,
        "period_value": value,
        "credit": max(0, credit),
        "rounded_down_to": step,
    }
