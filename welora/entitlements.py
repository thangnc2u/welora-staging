"""MVP Pricing & Entitlements (P1–P3 · P8 · P9) — FREE / ACA / OS1.

Loads plans/prices from config/pricing_module.json (Pricing Module SoT).
checkout_enabled stays false until legal entity ships. Does not touch
Hard Deny / TARGET_MONTHS / gate_months / Pre-Rule.
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

SELLABLE_MVP = frozenset({"FREE", "ACA", "OS1"})
DEFAULT_PLAN = "FREE"

_lock = threading.RLock()
_module_cache: Optional[dict[str, Any]] = None
_events: list[dict[str, Any]] = []
# user_id -> trial / subscription state (in-memory MVP stub)
_user_state: dict[str, dict[str, Any]] = {}


def _pricing_candidates() -> list[Path]:
    env = (os.environ.get("WELORA_PRICING_MODULE") or "").strip()
    out: list[Path] = []
    if env:
        out.append(Path(env))
    here = Path(__file__).resolve()
    # welora/config/ (shipped with package / Docker COPY welora)
    out.append(here.parent / "config" / "pricing_module.json")
    # repo-root config/ (Render PYTHONPATH=.)
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
        # Force false — never flip checkout on in MVP code path
        raw["checkout_enabled"] = False
        plans = raw.get("plans") or []
        for plan in plans:
            code = str(plan.get("code") or "")
            if code not in SELLABLE_MVP:
                plan["sellable"] = False
        experiments = raw.get("experiments") or []
        if not any(e.get("key") == "aca_price_ab" for e in experiments):
            experiments.append({"key": "aca_price_ab", "active": False, "variant": "A"})
        raw["experiments"] = experiments
        _module_cache = raw
        return copy.deepcopy(_module_cache)


def get_pricing_public() -> dict[str, Any]:
    """Public pricing payload (UI must fetch this — no hard-coded amounts)."""
    mod = load_pricing_module()
    sellable = [p for p in (mod.get("plans") or []) if p.get("code") in SELLABLE_MVP]
    return {
        "currency": mod.get("currency") or "VND",
        "plans": sellable,
        "checkout_enabled": False,
        "experiments": mod.get("experiments") or [
            {"key": "aca_price_ab", "active": False, "variant": "A"}
        ],
        "disclaimer": mod.get("disclaimer") or "",
    }


def get_checkout_config() -> dict[str, Any]:
    mod = load_pricing_module()
    providers = list(mod.get("checkout_providers") or ["momo", "zalopay", "vnpay", "vietqr"])
    return {
        "checkout_enabled": False,
        "providers": providers,
        "banner": mod.get("checkout_banner") or "Sắp mở thanh toán",
    }


def _plan_by_code(code: str) -> Optional[dict[str, Any]]:
    mod = load_pricing_module()
    for p in mod.get("plans") or []:
        if p.get("code") == code:
            return copy.deepcopy(p)
    return None


def _entitlement_keys(plan: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    for e in plan.get("entitlements") or []:
        k = e.get("key") if isinstance(e, dict) else None
        if k:
            keys.append(str(k))
    return keys


def has_entitlement(user_id: Optional[str], key: str) -> bool:
    """Return True if user (or anonymous FREE) holds entitlement key."""
    me = get_me(user_id)
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

    plan_code = state.get("plan") or DEFAULT_PLAN
    trial = state.get("trial")
    if trial and trial.get("status") == "active":
        ends = float(trial.get("ends_at") or 0)
        if ends and time.time() > ends:
            trial = {**trial, "status": "expired"}
            plan_code = DEFAULT_PLAN
        else:
            plan_code = "ACA"

    plan = _plan_by_code(plan_code) or _plan_by_code(DEFAULT_PLAN)
    assert plan is not None
    entitlements = copy.deepcopy(plan.get("entitlements") or [])
    return {
        "user_id": uid,
        "plan": plan_code,
        "seat_limit": plan.get("seat_limit", 1),
        "entitlements": entitlements,
        "subscription": state.get("subscription"),
        "trial": trial,
        "checkout_enabled": False,
    }


def start_aca_trial(
    *,
    user_id: Optional[str],
    phone: str,
    otp_code: Optional[str] = None,
) -> tuple[int, dict[str, Any]]:
    """Stub ACA trial start — phone OTP verification hook (OTP not charged).

    MVP accepts any non-empty otp_code (or skips verify when WELORA_TRIAL_OTP_STUB=1).
    """
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


def _mask_phone(phone: str) -> str:
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) < 4:
        return "****"
    return f"{'*' * max(0, len(digits) - 4)}{digits[-4:]}"


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



# fix typo in function name above — define correct alias
def reset_state_for_tests() -> None:
    global _module_cache
    with _lock:
        _user_state.clear()
        _events.clear()
        _module_cache = None


def health_fields() -> dict[str, Any]:
    """Optional health extension — does not alter gate_months / hard_deny."""
    return {
        "checkout_enabled": False,
        "sellable_plans": sorted(SELLABLE_MVP),
        "pricing_module": True,
    }
