"""Pricing & Entitlements — P1–P9 (MVP + P4–P7).

Loads plans/prices from config/pricing_module.json (Pricing Module SoT).
checkout_enabled stays false until legal entity ships. Does not touch
Hard Deny / TARGET_MONTHS / gate_months / Pre-Rule.

P4 ACA_SV student path · P5 household seats + Founding Family ·
P6 upgrade/downgrade prorate preview · P7 Lifetime gated OFF to M3.2.
"""

from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

# Plans listed on /pricing + public API for this phase (P1–P7).
LISTED_PLANS = frozenset({"FREE", "ACA", "ACA_SV", "OS1", "OS2", "OS2G", "OS3G"})
OS_PLANS = frozenset({"OS1", "OS2", "OS2G", "OS3G"})
ACADEMY_PLANS = frozenset({"ACA", "ACA_SV"})
DEFAULT_PLAN = "FREE"
GRACE_DAYS = 7  # PAY-04
OS_ENTITLEMENT_PREFIXES = ("os.",)

_lock = threading.RLock()
_module_cache: Optional[dict[str, Any]] = None
_events: list[dict[str, Any]] = []
# user_id -> trial / subscription / student / seats state (in-memory stub)
_user_state: dict[str, dict[str, Any]] = {}


def _pricing_candidates() -> list[Path]:
    env = (os.environ.get("WELORA_PRICING_MODULE") or "").strip()
    out: list[Path] = []
    if env:
        out.append(Path(env))
    here = Path(__file__).resolve()
    out.append(here.parent / "config" / "pricing_module.json")
    out.append(here.parent.parent / "config" / "pricing_module.json")
    return out


def pricing_module_path() -> Path:
    for p in _pricing_candidates():
        if p.is_file():
            return p
    raise FileNotFoundError(
        "pricing_module.json not found; set WELORA_PRICING_MODULE or ship config/"
    )


def load_pricing_module(*, force: bool = False) -> dict[str, Any]:
    """Load Pricing Module JSON once (thread-safe)."""
    global _module_cache
    with _lock:
        if _module_cache is not None and not force:
            return copy.deepcopy(_module_cache)
        path = pricing_module_path()
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("pricing_module.json must be an object")
        # Force false — never flip checkout on in code path
        raw["checkout_enabled"] = False
        lifetime = raw.get("lifetime") or {}
        lifetime["enabled"] = False
        lifetime["sellable"] = False
        raw["lifetime"] = lifetime
        plans = raw.get("plans") or []
        for plan in plans:
            code = str(plan.get("code") or "")
            if code not in LISTED_PLANS:
                plan["sellable"] = False
            # Strip purchasable lifetime prices while flag OFF
            prices = []
            for pr in plan.get("prices") or []:
                pr = dict(pr)
                if pr.get("interval") == "lifetime":
                    pr["sellable"] = False
                    pr["locked"] = True
                prices.append(pr)
            plan["prices"] = prices
        experiments = raw.get("experiments") or []
        if not any(e.get("key") == "aca_price_ab" for e in experiments):
            experiments.append({"key": "aca_price_ab", "active": False, "variant": "A"})
        raw["experiments"] = experiments
        _module_cache = raw
        return copy.deepcopy(_module_cache)


def _lifetime_enabled() -> bool:
    mod = load_pricing_module()
    return bool((mod.get("lifetime") or {}).get("enabled"))


def checkout_runtime_enabled() -> bool:
    """Checkout VietQR runtime switch.

    Config ``checkout_enabled`` is always forced False (default / production).
    Only the env ``WELORA_CHECKOUT_ENABLED=1`` opens checkout for a non-prod
    test channel; unset → checkout + webhook endpoints answer 403.
    """
    raw = (os.environ.get("WELORA_CHECKOUT_ENABLED") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def get_pricing_public() -> dict[str, Any]:
    """Public pricing payload (UI must fetch this — no hard-coded amounts)."""
    mod = load_pricing_module()
    plans_out: list[dict[str, Any]] = []
    for p in mod.get("plans") or []:
        if p.get("code") not in LISTED_PLANS:
            continue
        plan = copy.deepcopy(p)
        # Annotate lifetime rows as locked when flag off
        for pr in plan.get("prices") or []:
            if pr.get("interval") == "lifetime":
                pr["sellable"] = False
                pr["locked"] = True
                pr["label"] = "Trọn đời (sắp mở)"
        plans_out.append(plan)
    return {
        "currency": mod.get("currency") or "VND",
        "plans": plans_out,
        "checkout_enabled": checkout_runtime_enabled(),
        "seat_addon": copy.deepcopy(mod.get("seat_addon") or {}),
        "lifetime": {
            "enabled": False,
            "sellable": False,
            "banner": (mod.get("lifetime") or {}).get("banner")
            or "Founding Lifetime sắp mở (chưa bán)",
            "unlock_at": (mod.get("lifetime") or {}).get("unlock_at") or "M3.2",
        },
        "founding_family": copy.deepcopy(mod.get("founding_family") or {}),
        "student": copy.deepcopy(mod.get("student") or {}),
        "plan_change": copy.deepcopy(mod.get("plan_change") or {}),
        "experiments": mod.get("experiments") or [
            {"key": "aca_price_ab", "active": False, "variant": "A"}
        ],
        "disclaimer": mod.get("disclaimer") or "",
    }


def get_checkout_config() -> dict[str, Any]:
    mod = load_pricing_module()
    providers = list(mod.get("checkout_providers") or ["momo", "zalopay", "vnpay", "vietqr"])
    return {
        "checkout_enabled": checkout_runtime_enabled(),
        "providers": providers,
        "banner": mod.get("checkout_banner") or "Sắp mở thanh toán",
    }


def _plan_by_code(code: str) -> Optional[dict[str, Any]]:
    mod = load_pricing_module()
    for p in mod.get("plans") or []:
        if p.get("code") == code:
            return copy.deepcopy(p)
    return None


def _price_amount(plan_code: str, interval: str) -> Optional[int]:
    plan = _plan_by_code(plan_code)
    if not plan:
        return None
    for pr in plan.get("prices") or []:
        if pr.get("interval") == interval:
            return int(pr.get("amount") or 0)
    return None


def price_amount(plan_code: str, interval: str) -> Optional[int]:
    """Server-side price (VND int) from pricing_module.json — never from client."""
    return _price_amount(plan_code, interval)


def plan_by_code(code: str) -> Optional[dict[str, Any]]:
    return _plan_by_code(code)


def _entitlement_keys(plan: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for e in plan.get("entitlements") or []:
        k = e.get("key") if isinstance(e, dict) else None
        if k:
            keys.append(str(k))
    return keys


def _is_os_key(key: str) -> bool:
    return any(key.startswith(p) for p in OS_ENTITLEMENT_PREFIXES)


def _student_blocks_os(state: dict[str, Any], plan_code: str) -> bool:
    if plan_code == "ACA_SV":
        return True
    student = state.get("student") or {}
    if student.get("status") in ("free_active", "verified", "aca_sv"):
        return True
    if student.get("blocks_os"):
        return True
    return False


def has_entitlement(user_id: Optional[str], key: str) -> bool:
    """Return True if user (or anonymous FREE) holds entitlement key."""
    me = get_me(user_id)
    # Student path never grants OS even if plan entitlements were misconfigured
    if _is_os_key(key) and me.get("blocks_os"):
        return False
    for e in me.get("entitlements") or []:
        if isinstance(e, dict) and e.get("key") == key:
            return True
        if e == key:
            return True
    return False


def get_me(user_id: Optional[str] = None) -> dict[str, Any]:
    """Current entitlements — defaults to FREE when no subscription/trial."""
    uid = (user_id or "").strip() or "anonymous"
    with _lock:
        state = copy.deepcopy(_user_state.get(uid) or {})
    if not state and uid != "anonymous" and _subscription_resolver is not None:
        try:
            restored = _subscription_resolver(uid)
        except Exception:
            restored = None
        if restored:
            state = copy.deepcopy(restored)

    plan_code = state.get("plan") or DEFAULT_PLAN
    trial = state.get("trial")
    student = state.get("student")
    now = time.time()

    # Paid subscription (checkout): past period end + 7-day grace (PAY-04) → FREE
    sub = state.get("subscription") or {}
    in_grace = False
    grace_ends_at = None
    if sub.get("current_period_end"):
        end = float(sub.get("current_period_end") or 0)
        grace_ends_at = end + GRACE_DAYS * 86400
        if sub.get("status") == "expired" or now > grace_ends_at:
            plan_code = DEFAULT_PLAN
        elif now > end:
            in_grace = True  # PAY-04: full access + renewal banner

    if trial and trial.get("status") == "active":
        ends = float(trial.get("ends_at") or 0)
        if ends and now > ends:
            trial = {**trial, "status": "expired"}
            if not state.get("subscription") and not (student and student.get("status") == "free_active"):
                plan_code = DEFAULT_PLAN
        else:
            plan_code = "ACA"

    if student and student.get("status") == "free_active":
        ends = float(student.get("free_ends_at") or 0)
        if ends and now > ends:
            student = {**student, "status": "free_expired", "plan": "ACA_SV"}
            plan_code = "ACA_SV"
        else:
            # During free year, entitlements match ACA_SV (academy full, no OS)
            plan_code = "ACA_SV"

    plan = _plan_by_code(plan_code) or _plan_by_code(DEFAULT_PLAN)
    assert plan is not None
    entitlements = copy.deepcopy(plan.get("entitlements") or [])
    blocks_os = _student_blocks_os(state, plan_code)
    if blocks_os:
        entitlements = [
            e
            for e in entitlements
            if not (isinstance(e, dict) and _is_os_key(str(e.get("key") or "")))
        ]

    seats = state.get("seats") or {
        "used": 1,
        "limit": plan.get("seat_limit", 1),
        "extra": 0,
    }

    return {
        "user_id": uid,
        "plan": plan_code,
        "seat_limit": plan.get("seat_limit", 1),
        "seats": seats,
        "entitlements": entitlements,
        "subscription": state.get("subscription"),
        "trial": trial,
        "student": student,
        "blocks_os": blocks_os,
        "founding_family": state.get("founding_family"),
        "checkout_enabled": False,
        "lifetime_enabled": False,
        "in_grace": in_grace,
        "grace_ends_at": grace_ends_at if in_grace else None,
        "renewal_banner": (
            "Gói đã hết hạn — bạn vẫn dùng đầy đủ trong thời gian ân hạn 7 ngày. Gia hạn để không bị hạ về Free."
            if in_grace
            else None
        ),
    }


def start_aca_trial(
    *,
    user_id: Optional[str],
    phone: str,
    otp_code: Optional[str] = None,
) -> tuple[int, dict[str, Any]]:
    """Stub ACA trial start — phone OTP verification hook (OTP not charged)."""
    phone_clean = (phone or "").strip()
    if len(phone_clean) < 8:
        return 400, {"error_code": "INVALID_PHONE", "message": "Số điện thoại không hợp lệ"}

    stub = (os.environ.get("WELORA_TRIAL_OTP_STUB") or "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    code = (otp_code or "").strip()
    if not stub and not code:
        return 400, {
            "error_code": "OTP_REQUIRED",
            "message": "Cần mã OTP để bắt đầu dùng thử Academy",
        }
    if code and len(code) < 4 and not stub:
        return 400, {"error_code": "OTP_INVALID", "message": "Mã OTP không hợp lệ"}

    aca = _plan_by_code("ACA")
    if not aca or not aca.get("trial"):
        return 500, {"error_code": "TRIAL_UNAVAILABLE", "message": "Trial ACA chưa cấu hình"}

    days = int((aca.get("trial") or {}).get("days") or 30)
    verification = (aca.get("trial") or {}).get("verification") or "phone_otp"
    uid = (user_id or "").strip() or f"trial-{uuid.uuid4().hex[:12]}"
    now = time.time()
    trial = {
        "plan": "ACA",
        "status": "active",
        "days": days,
        "verification": verification,
        "phone_masked": _mask_phone(phone_clean),
        "started_at": now,
        "ends_at": now + days * 86400,
        "otp_verified": True if (stub or code) else False,
    }
    with _lock:
        _user_state[uid] = {
            "plan": "ACA",
            "trial": trial,
            "subscription": None,
        }
    emit_event(
        "trial.aca.started",
        {"user_id": uid, "days": days, "verification": verification},
    )
    return 200, {
        "ok": True,
        "user_id": uid,
        "plan": "ACA",
        "trial": trial,
        "entitlements": aca.get("entitlements") or [],
        "checkout_enabled": False,
        "message": f"Dùng thử Academy {days} ngày (OTP stub)",
    }


def start_student_path(
    *,
    user_id: Optional[str],
    student_id: str,
    verification_method: str = "edu_vn_email_otp",
    email: Optional[str] = None,
) -> tuple[int, dict[str, Any]]:
    """P4 — verify student → 365 days ACA free, then ACA_SV. Blocks OS sell path."""
    sid = (student_id or "").strip()
    if len(sid) < 4:
        return 400, {
            "error_code": "INVALID_STUDENT_ID",
            "message": "Mã số sinh viên không hợp lệ",
        }
    method = (verification_method or "").strip() or "edu_vn_email_otp"
    if method == "edu_vn_email_otp":
        em = (email or "").strip().lower()
        if not em.endswith(".edu.vn"):
            return 400, {
                "error_code": "INVALID_EDU_EMAIL",
                "message": "Cần email đuôi .edu.vn để xác thực OTP",
            }

    mod = load_pricing_module()
    student_cfg = mod.get("student") or {}
    free_days = int(student_cfg.get("free_days") or 365)
    aca_sv = _plan_by_code("ACA_SV")
    if not aca_sv:
        return 500, {"error_code": "ACA_SV_MISSING", "message": "Gói ACA_SV chưa cấu hình"}

    uid = (user_id or "").strip() or f"sv-{uuid.uuid4().hex[:12]}"
    # One-time per student_id / phone — reject reuse
    with _lock:
        for existing_uid, st in _user_state.items():
            prev = (st.get("student") or {}).get("student_id_hash")
            if prev and prev == _hash_student_id(sid):
                return 409, {
                    "error_code": "STUDENT_OFFER_USED",
                    "message": "Ưu đãi sinh viên đã được dùng cho mã này",
                    "user_id": existing_uid,
                }

    now = time.time()
    student = {
        "status": "free_active",
        "plan_after": "ACA_SV",
        "student_id_hash": _hash_student_id(sid),
        "verification_method": method,
        "free_days": free_days,
        "free_started_at": now,
        "free_ends_at": now + free_days * 86400,
        "blocks_os": True,
        "no_lifetime": True,
        "email_masked": _mask_email(email) if email else None,
    }
    with _lock:
        prev = _user_state.get(uid) or {}
        _user_state[uid] = {
            **prev,
            "plan": "ACA_SV",
            "student": student,
            "subscription": None,
            # Clear ACA trial stacking — Addendum: no stack with P3 trial
            "trial": None,
        }
    emit_event(
        "student_verified",
        {"user_id": uid, "free_days": free_days, "method": method},
    )
    entitlements = [
        e
        for e in (aca_sv.get("entitlements") or [])
        if not (isinstance(e, dict) and _is_os_key(str(e.get("key") or "")))
    ]
    return 200, {
        "ok": True,
        "user_id": uid,
        "plan": "ACA_SV",
        "student": student,
        "entitlements": entitlements,
        "blocks_os": True,
        "os_sell_blocked": True,
        "lifetime_available": False,
        "checkout_enabled": False,
        "message": f"Sinh viên: {free_days} ngày Academy miễn phí → sau đó ACA_SV",
    }


def student_os_sell_blocked(user_id: Optional[str], target_plan: str) -> tuple[bool, str]:
    """P4 — student path must not sell OS packages."""
    me = get_me(user_id)
    if not me.get("blocks_os") and me.get("plan") != "ACA_SV":
        return False, ""
    if target_plan in OS_PLANS or (target_plan or "").startswith("OS"):
        return True, "Đường sinh viên (ACA_SV) không bán gói OS"
    return False, ""


def quote_seat_addon(*, extra_seats: int, plan_code: Optional[str] = None) -> dict[str, Any]:
    """P5 — quote additional household seats from config (19k/person/month)."""
    mod = load_pricing_module()
    addon = mod.get("seat_addon") or {}
    unit = int(addon.get("amount_monthly") or 19000)
    n = max(0, int(extra_seats))
    plan = _plan_by_code(plan_code) if plan_code else None
    seat_limit = (plan or {}).get("seat_limit") if plan else None
    return {
        "extra_seats": n,
        "amount_monthly_per_seat": unit,
        "amount_monthly_total": unit * n,
        "currency": addon.get("currency") or mod.get("currency") or "VND",
        "plan_code": plan_code,
        "plan_seat_limit": seat_limit,
        "checkout_enabled": False,
        "chargeable": False,
        "message": "Báo giá seat thêm — checkout vẫn tắt",
    }


def founding_family_status(plan_code: Optional[str] = None) -> dict[str, Any]:
    """P5 — Founding Family pre-order flag until OS 3.10."""
    mod = load_pricing_module()
    ff = copy.deepcopy(mod.get("founding_family") or {})
    plans = list(ff.get("plans") or ["OS2", "OS2G", "OS3G"])
    code = (plan_code or "").strip()
    return {
        "preorder_enabled": bool(ff.get("preorder_enabled", True)),
        "until": ff.get("until") or "OS 3.10",
        "activates_as": ff.get("activates_as") or "OS1",
        "plans": plans,
        "applies": (not code) or (code in plans),
        "banner": ff.get("banner")
        or "Founding Family pre-order — kích hoạt OS1 cho owner đến khi OS 3.10",
        "checkout_enabled": False,
    }


def preview_plan_change(
    *,
    from_plan: str,
    to_plan: str,
    interval: str = "month",
    days_remaining: int = 15,
    days_in_period: int = 30,
    user_id: Optional[str] = None,
) -> tuple[int, dict[str, Any]]:
    """P6 — upgrade/downgrade + prorate preview (no real charge; checkout off)."""
    src = (from_plan or "").strip().upper()
    dst = (to_plan or "").strip().upper()
    iv = (interval or "month").strip().lower()
    if iv == "lifetime":
        return 400, {
            "error_code": "LIFETIME_OFF",
            "message": "Founding Lifetime chưa mở bán (flag OFF đến M3.2)",
            "lifetime_enabled": False,
            "checkout_enabled": False,
        }
    if src not in LISTED_PLANS or dst not in LISTED_PLANS:
        return 400, {
            "error_code": "UNKNOWN_PLAN",
            "message": "Gói nguồn hoặc đích không hợp lệ",
        }
    if src == dst:
        return 400, {
            "error_code": "SAME_PLAN",
            "message": "Gói nguồn và đích trùng nhau",
        }

    blocked, reason = student_os_sell_blocked(user_id, dst)
    if blocked:
        return 403, {
            "error_code": "STUDENT_OS_BLOCKED",
            "message": reason,
            "from_plan": src,
            "to_plan": dst,
            "checkout_enabled": False,
        }

    if iv not in ("month", "year", "free"):
        return 400, {"error_code": "INVALID_INTERVAL", "message": "Kỳ thanh toán không hợp lệ"}

    amount_from = _price_amount(src, iv if iv != "free" else "month")
    amount_to = _price_amount(dst, iv if iv != "free" else "month")
    if amount_from is None:
        amount_from = 0
    if amount_to is None:
        return 400, {
            "error_code": "PRICE_MISSING",
            "message": f"Không có giá {dst}/{iv} trong config",
        }

    period = max(1, int(days_in_period))
    remain = max(0, min(int(days_remaining), period))

    # Rank for upgrade vs downgrade (by monthly list price when available)
    rank = {"FREE": 0, "ACA_SV": 1, "ACA": 2, "OS1": 3, "OS2": 4, "OS2G": 5, "OS3G": 6}
    direction = "upgrade" if rank.get(dst, 0) > rank.get(src, 0) else "downgrade"

    daily_from = amount_from / period
    daily_to = amount_to / period
    credit = daily_from * remain
    charge = daily_to * remain
    prorate_due = 0
    effective = "immediate"

    mod = load_pricing_module()
    pc = mod.get("plan_change") or {}

    if direction == "upgrade":
        prorate_due = max(0, int(round(charge - credit)))
        # ACA → OS: credit unused ACA toward OS (aca_credit_toward_os)
        if src in ACADEMY_PLANS and dst in OS_PLANS and pc.get("aca_credit_toward_os", True):
            prorate_due = max(0, int(round(charge - credit)))
        effective = "immediate" if pc.get("upgrade_immediate", True) else "next_period"
    else:
        # Downgrade next period — no charge now
        prorate_due = 0
        effective = "next_period" if pc.get("downgrade_next_period", True) else "immediate"
        credit = 0.0
        charge = 0.0

    ff = None
    if dst in (founding_family_status().get("plans") or []):
        ff = founding_family_status(dst)

    emit_event(
        "plan_change_preview",
        {"from_plan": src, "to_plan": dst, "direction": direction, "prorate_due": prorate_due},
    )

    return 200, {
        "ok": True,
        "from_plan": src,
        "to_plan": dst,
        "interval": iv,
        "direction": direction,
        "days_remaining": remain,
        "days_in_period": period,
        "amount_from": amount_from,
        "amount_to": amount_to,
        "credit": int(round(credit)),
        "charge_gross": int(round(charge)),
        "prorate_due": prorate_due,
        "currency": (mod.get("currency") or "VND"),
        "effective": effective,
        "checkout_enabled": False,
        "chargeable": False,
        "lifetime_enabled": False,
        "founding_family": ff,
        "message": "Xem trước nâng/hạ gói — không thu tiền (checkout tắt)",
    }


def lifetime_purchase_blocked() -> dict[str, Any]:
    """P7 — Founding Lifetime gated OFF until M3.2."""
    mod = load_pricing_module()
    lt = mod.get("lifetime") or {}
    return {
        "allowed": False,
        "lifetime_enabled": False,
        "sellable": False,
        "unlock_at": lt.get("unlock_at") or "M3.2",
        "inventory_per_plan": lt.get("inventory_per_plan") or 1000,
        "early_bird_slots": lt.get("early_bird_slots") or 200,
        "early_bird_discount_pct": lt.get("early_bird_discount_pct") or 30,
        "banner": lt.get("banner") or "Founding Lifetime sắp mở (chưa bán)",
        "checkout_enabled": False,
        "message": "Lifetime flag OFF — wire model/config only, không bán thật",
    }


def _mask_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 4:
        return "****"
    return f"{'*' * max(0, len(digits) - 4)}{digits[-4:]}"


def _mask_email(email: Optional[str]) -> Optional[str]:
    if not email or "@" not in email:
        return None
    local, _, domain = email.partition("@")
    if len(local) <= 2:
        return f"**@{domain}"
    return f"{local[0]}***{local[-1]}@{domain}"


def _hash_student_id(student_id: str) -> str:
    # Lightweight non-crypto stub hash for MVP in-memory dedupe (not for storage of PII)
    import hashlib

    return hashlib.sha256(student_id.strip().encode("utf-8")).hexdigest()[:32]


def emit_event(event: str, payload: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """P8 Event Bus hook — in-memory ring for MVP; assign A/B when pricing_view."""
    name = (event or "").strip() or "unknown"
    body = dict(payload or {})
    exp = assign_experiment("aca_price_ab")
    record = {
        "id": uuid.uuid4().hex,
        "event": name,
        "payload": body,
        "experiment": exp,
        "ts": time.time(),
    }
    with _lock:
        _events.append(record)
        if len(_events) > 500:
            del _events[:-500]
    return {"ok": True, "event": record}


def assign_experiment(key: str = "aca_price_ab") -> dict[str, Any]:
    """A/B hook — default inactive variant A (aca_price_ab)."""
    mod = load_pricing_module()
    for e in mod.get("experiments") or []:
        if e.get("key") == key:
            return {
                "key": key,
                "active": bool(e.get("active")),
                "variant": e.get("variant") or "A",
            }
    return {"key": key, "active": False, "variant": "A"}


def list_events(limit: int = 50) -> list[dict[str, Any]]:
    with _lock:
        return copy.deepcopy(_events[-limit:])


# --- Checkout grant hooks (CK-07) -------------------------------------------
_subscription_resolver: Optional[Any] = None


def register_subscription_resolver(fn: Optional[Any]) -> None:
    """Checkout registers a DB lookup so paid plans survive process restarts."""
    global _subscription_resolver
    _subscription_resolver = fn


def grant_plan(
    user_id: str,
    plan_code: str,
    *,
    period_start: float,
    period_end: float,
    source: str,
    order_code: Optional[int] = None,
    is_preorder: bool = False,
) -> dict[str, Any]:
    """Grant a paid plan. Founding Family pre-order activates OS1 for owner."""
    uid = (user_id or "").strip()
    if not uid:
        raise ValueError("user_id required")
    active_plan = plan_code
    if is_preorder:
        ff = founding_family_status(plan_code)
        active_plan = ff.get("activates_as") or "OS1"
    subscription = {
        "plan_id": plan_code,
        "active_plan": active_plan,
        "status": "active",
        "current_period_start": period_start,
        "current_period_end": period_end,
        "source": source,
        "order_code": order_code,
        "is_preorder": bool(is_preorder),
    }
    with _lock:
        prev = _user_state.get(uid) or {}
        _user_state[uid] = {
            **prev,
            "plan": active_plan,
            "subscription": subscription,
            "trial": None,
        }
    emit_event(
        "subscription_granted",
        {"user_id": uid, "plan": plan_code, "source": source, "order_code": order_code},
    )
    return subscription


def set_subscription_state(user_id: str, plan_code: str, subscription: Optional[dict[str, Any]]) -> None:
    """Quietly restore a paid plan from DB (no grant event) — refunds / renewal job."""
    uid = (user_id or "").strip()
    if not uid:
        return
    with _lock:
        prev = _user_state.get(uid) or {}
        _user_state[uid] = {**prev, "plan": plan_code, "subscription": copy.deepcopy(subscription)}


def revoke_plan(user_id: str, *, reason: str = "") -> None:
    uid = (user_id or "").strip()
    with _lock:
        prev = _user_state.get(uid) or {}
        sub = dict(prev.get("subscription") or {})
        if sub:
            sub["status"] = "expired"
        _user_state[uid] = {**prev, "plan": DEFAULT_PLAN, "subscription": sub or None}
    emit_event("subscription_revoked", {"user_id": uid, "reason": reason})


def reset_state_for_tests() -> None:
    global _module_cache
    with _lock:
        _user_state.clear()
        _events.clear()
        _module_cache = None


def health_fields() -> dict[str, Any]:
    """Optional health extension — does not alter gate_months / hard_deny."""
    return {
        "checkout_enabled": checkout_runtime_enabled(),
        "sellable_plans": sorted(LISTED_PLANS),
        "pricing_module": True,
        "lifetime_enabled": False,
        "founding_family_preorder": True,
    }


# Back-compat alias used by older tests / imports
SELLABLE_MVP = LISTED_PLANS
