"""
Mode C — Act nội bộ OS (MVP).

Founder 15/09: Mode C Act = still G1 (user confirm) ≠ L2 Action Tools.
Source: phụ lục PRD trụ 4 §3.3 Mode C.

- ALLOW: tạo phong bì / quỹ tiết kiệm nội bộ, khóa lấy chéo (stub OK),
  nhắc BHYT/BHTN/đóng bù (schedule only), checklist di sản (no legal will).
- DENY: ticker / ILP mới / chuyển tiền ngân hàng / L2 external money.
- Gate: safety-gate passed + answer_confidence ≥ CONFIDENCE_THRESHOLD (0.80).
- Confirm before write · undo 24h · log mode + policy_version + persona + rule_id.
- Full L-* policy_engine.evaluate() choke-point before any OS write (P2 OS router).
- L-DUAL-CONTROL (Founder 15/09 B): lock / ceiling / estate need companion;
  missing companion → DENY; has companion → pending_dual → companion confirm.
- L-COOL-OFF (Founder 15/09): rút/chuyển quỹ KH dưới sàn persona HOẶC ≥20% quỹ
  → pending_cool_off + lý do + chờ 24h (P1–P5). P6 → dual-control, không tự cool-off.
- Persist Mode C state to SQLite (proposals / pending_* / confirmed / undone +
  companion by user_id) when WELORA_STORE=sqlite or WELORA_MODE_C_DB is set.
- Does NOT replace Hard Deny R01–R09 / Pre-Rule order / TARGET_MONTHS / CORE-*.
  Undo Act 24h remains separate from cooling-off wait.
  No bank aggregator · no new Postgres.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from welora.agent import CONFIDENCE_THRESHOLD
from welora.safety_gate import TARGET_MONTHS, compute_months_covered
from welora import policy_engine
from welora.policy_engine import (
    POLICY_VERSION as ROUTER_POLICY_VERSION,
    SIDE_PENDING_COOL_OFF,
    SIDE_PENDING_DUAL,
    evaluate as policy_evaluate,
)

# Additive L-* router — never replaces Hard Deny R01–R09.
POLICY_VERSION = ROUTER_POLICY_VERSION  # L-router-1.0
POLICY_DUAL_CONTROL = "L-DUAL-CONTROL"
POLICY_COOL_OFF = "L-COOL-OFF"
MODE_C = "C"
MODE_C_CHIP = "Mode C · Hành động"
MODE_C_DISCLAIMER = "Hành động trên OS — có thể hoàn tác trong 24 giờ"
UNDO_HOURS = 24
COOL_OFF_HOURS = 24
TRANSFER_PCT_THRESHOLD = 0.20  # ≥20% quỹ KH → cool-off (take-home productization out of MVP)

ACT_CREATE_ENVELOPE = "create_envelope"
ACT_LOCK_ENVELOPE = "lock_envelope"
ACT_CHANGE_CEILING = "change_envelope_ceiling"
ACT_BH_REMINDER = "schedule_bh_reminder"
ACT_ESTATE_CHECKLIST = "open_estate_checklist"
ACT_WITHDRAW_EFUND = "withdraw_emergency_fund"

ALLOWED_ACTS = frozenset(
    {
        ACT_CREATE_ENVELOPE,
        ACT_LOCK_ENVELOPE,
        ACT_CHANGE_CEILING,
        ACT_BH_REMINDER,
        ACT_ESTATE_CHECKLIST,
        ACT_WITHDRAW_EFUND,
    }
)

# Dual-control MVP (Founder 15/09 B): ceiling change + lock + estate.
# No P6 persona router → apply conservatively to these acts.
DUAL_CONTROL_ACTS = frozenset(
    {
        ACT_LOCK_ENVELOPE,
        ACT_CHANGE_CEILING,
        ACT_ESTATE_CHECKLIST,
    }
)

DENY_MISSING_COMPANION_VI = (
    "Cần người đồng hành (vợ/chồng/con) để thực hiện hành động này. "
    "Thiếu người thứ 2 — từ chối theo L-DUAL-CONTROL. "
    "Gắn companion trong Điều hành · Đồng kiểm trước khi thử lại."
)
PENDING_DUAL_VI = (
    "Đã đề xuất — chờ người đồng hành xác nhận trong app (đồng kiểm 2 người). "
    "Chưa ghi vào OS cho đến khi companion xác nhận. Bạn có thể hủy đề xuất đang chờ."
)

COOL_OFF_WARN_VI = (
    "CẢNH BÁO ĐỎ — L-COOL-OFF: hành động chạm quỹ khẩn cấp (dưới sàn persona "
    "hoặc ≥20% quỹ). Bắt buộc nhập lý do + chờ 24 giờ trước khi xác nhận ghi OS. "
    "Không ghi ngay. Hoàn tác Act 24h là cơ chế khác — không thay cooling-off."
)
PENDING_COOL_OFF_VI = (
    "Đã ghi nhận đề xuất cooling-off — chờ đủ 24 giờ rồi xác nhận. "
    "Xác nhận sớm vẫn ở trạng thái pending_cool_off (chưa ghi OS)."
)
COOL_OFF_NEED_REASON_VI = (
    "Cần nhập lý do không rỗng trước khi vào hàng chờ cooling-off (L-COOL-OFF)."
)
P6_COOL_OFF_ESCALATE_VI = (
    "P6 — không cho tự override bằng cooling-off một mình. "
    "Cần người đồng hành (L-DUAL-CONTROL). Cooling-off không đủ."
)

# Persona floor months (MVP stub — full P1–P6 router out of MVP).
# TARGET_MONTHS (=3) stays HARD for Safety Gate; cool-off floor may use persona months.
PERSONA_FLOOR_MONTHS: dict[str, int] = {
    "P1": TARGET_MONTHS,  # PRD 3–6 → MVP uses TARGET_MONTHS
    "P2": 6,
    "P3": 6,
    "P4": 6,
    "P5": 6,
    "P6": 6,  # cool-off self-override forbidden; dual instead
}
DEFAULT_PERSONA = "P1"

# External / L2 — always DENY in Mode C (G1≠L2).
EXTERNAL_DENY: dict[str, dict[str, str]] = {
    "buy_ticker": {
        "rule": "L-NO-TICKER",
        "reason": "Cấm đặt lệnh / khuyến nghị mua mã CK cụ thể (Mode C ≠ L2).",
    },
    "ilp_new": {
        "rule": "L-NO-ILP-NEW",
        "reason": "Cấm đề xuất / tạo lead ILP mới. Agent không nộp hồ sơ BH.",
    },
    "bank_transfer": {
        "rule": "L-FIDUCIARY",
        "reason": "Cấm chuyển tiền ra ngân hàng / đối tác ngoài OS (không phải L2 Action Tools).",
    },
}

# Cross-take lock: data model supports locked flag; transfer between locked envelopes DENY.
CROSS_TAKE_SUPPORTED = True
CROSS_TAKE_NOTE = (
    "Envelope.locked + cross_take_forbidden=true chặn lấy chéo nội bộ. "
    "Full P4 L-ENVELOPE matrix out of scope MVP."
)

_ENVELOPES: dict[str, dict[str, Any]] = {}  # id -> record
_ENVELOPES_BY_USER: dict[str, list[str]] = {}
_REMINDERS: dict[str, dict[str, Any]] = {}
_REMINDERS_BY_USER: dict[str, list[str]] = {}
_ESTATE: dict[str, dict[str, Any]] = {}  # user_id -> checklist
_PROPOSALS: dict[str, dict[str, Any]] = {}
_ACT_LOGS: list[dict[str, Any]] = []
_UNDO: dict[str, dict[str, Any]] = {}  # act_id -> undo token
_COMPANIONS: dict[str, dict[str, Any]] = {}  # primary_user_id -> link
_PERSONAS: dict[str, str] = {}  # user_id -> P1..P6 (MVP stub, no full router)
_CLOCK_OFFSET: timedelta = timedelta(0)  # UAT clock inject


# --- SQLite persist (optional; memory remains API source of truth) ---
def _persist_mod():
    from welora import mode_c_persist as mcp
    return mcp


def _persist_enabled() -> bool:
    try:
        return _persist_mod().is_enabled()
    except Exception:
        return False


def enable_mode_c_persist(path: str | None = None) -> str:
    """Enable SQLite write-through + migrate schema. Returns DB path."""
    mcp = _persist_mod()
    p = mcp.configure(path)
    return str(p)


def disable_mode_c_persist() -> None:
    _persist_mod().disable()


def clear_mode_c_memory() -> None:
    """Drop in-memory Mode C dicts without touching SQLite (restart sim)."""
    global _CLOCK_OFFSET
    _ENVELOPES.clear()
    _ENVELOPES_BY_USER.clear()
    _REMINDERS.clear()
    _REMINDERS_BY_USER.clear()
    _ESTATE.clear()
    _PROPOSALS.clear()
    _ACT_LOGS.clear()
    _UNDO.clear()
    _COMPANIONS.clear()
    _PERSONAS.clear()
    _CLOCK_OFFSET = timedelta(0)


def reload_mode_c_from_sqlite() -> dict:
    """Load Mode C state from SQLite into memory (after clear_mode_c_memory)."""
    mcp = _persist_mod()
    if not mcp.is_enabled():
        mcp.maybe_autoconfigure()
    data = mcp.load_all()
    clear_mode_c_memory()
    _COMPANIONS.update(data.get("companions") or {})
    _PROPOSALS.update(data.get("proposals") or {})
    _UNDO.update(data.get("undos") or {})
    _ENVELOPES.update(data.get("envelopes") or {})
    _ENVELOPES_BY_USER.update(data.get("envelopes_by_user") or {})
    _REMINDERS.update(data.get("reminders") or {})
    _REMINDERS_BY_USER.update(data.get("reminders_by_user") or {})
    _ESTATE.update(data.get("estates") or {})
    _PERSONAS.update(data.get("personas") or {})
    _ACT_LOGS.extend(data.get("act_logs") or [])
    return {
        "proposals": len(_PROPOSALS),
        "companions": len(_COMPANIONS),
        "undos": len(_UNDO),
        "envelopes": len(_ENVELOPES),
        "schema_version": mcp.schema_version(),
        "path": str(mcp.get_path()) if mcp.get_path() else None,
    }


def _persist_proposal(prop: dict) -> None:
    if _persist_enabled():
        _persist_mod().save_proposal(prop)


def _persist_companion(rec: dict) -> None:
    if _persist_enabled():
        _persist_mod().save_companion(rec)


def _persist_undo(meta: dict) -> None:
    if _persist_enabled():
        _persist_mod().save_undo(meta)


def _persist_envelope(rec: dict) -> None:
    if _persist_enabled():
        _persist_mod().save_envelope(rec)


def _persist_delete_envelope(envelope_id: str, user_id: str) -> None:
    if _persist_enabled():
        _persist_mod().delete_envelope(envelope_id, user_id)


def _persist_reminder(rec: dict) -> None:
    if _persist_enabled():
        _persist_mod().save_reminder(rec)


def _persist_delete_reminder(reminder_id: str, user_id: str) -> None:
    if _persist_enabled():
        _persist_mod().delete_reminder(reminder_id, user_id)


def _persist_estate(user_id: str, rec) -> None:
    if _persist_enabled():
        _persist_mod().save_estate(user_id, rec)


def _persist_persona(user_id: str, persona: str) -> None:
    if _persist_enabled():
        _persist_mod().save_persona(user_id, persona)


def _persist_act_log(entry: dict) -> None:
    if _persist_enabled():
        _persist_mod().append_act_log(entry)


# Autoconfigure when staging uses sqlite store (idempotent; tests stay memory).
# On process start with persist enabled, hydrate memory from SQLite (survive restart).
try:
    if _persist_mod().maybe_autoconfigure():
        data = _persist_mod().load_all()
        _COMPANIONS.update(data.get("companions") or {})
        _PROPOSALS.update(data.get("proposals") or {})
        _UNDO.update(data.get("undos") or {})
        _ENVELOPES.update(data.get("envelopes") or {})
        _ENVELOPES_BY_USER.update(data.get("envelopes_by_user") or {})
        _REMINDERS.update(data.get("reminders") or {})
        _REMINDERS_BY_USER.update(data.get("reminders_by_user") or {})
        _ESTATE.update(data.get("estates") or {})
        _PERSONAS.update(data.get("personas") or {})
        if data.get("act_logs"):
            _ACT_LOGS.extend(data["act_logs"])
except Exception:
    pass



def reset_mode_c_store() -> None:
    """Clear Mode C memory; if SQLite persist is on, wipe DB tables too."""
    clear_mode_c_memory()
    try:
        mcp = _persist_mod()
        if mcp.is_enabled():
            mcp.clear_all()
    except Exception:
        pass


def inject_clock_advance(*, hours: float = 0, seconds: float = 0) -> None:
    """UAT / pytest: advance Mode C wall clock without sleeping."""
    global _CLOCK_OFFSET
    _CLOCK_OFFSET = _CLOCK_OFFSET + timedelta(hours=float(hours), seconds=float(seconds))


def _now() -> datetime:
    return datetime.now(timezone.utc) + _CLOCK_OFFSET


def _now_iso() -> str:
    return _now().isoformat()


def _norm(s: str) -> str:
    return (s or "").lower().strip()


def detect_external_deny(message: str) -> Optional[dict[str, str]]:
    """DENY buy ticker / ILP new / bank transfer — never Mode C ALLOW."""
    n = _norm(message)
    ticker_keys = [
        "mua mã",
        "mua cổ",
        "đặt lệnh",
        "ticker",
        "mã ck",
        "all-in mã",
        "nói mã",
        "cho mã",
        "mã nào",
    ]
    ilp_keys = [
        "mua ilp",
        "ký ilp",
        "ilp mới",
        "bảo hiểm liên kết đầu tư",
        "mở ilp",
        "mua bảo hiểm liên kết",
    ]
    bank_keys = [
        "chuyển tiền ngân hàng",
        "chuyển khoản ra",
        "bank transfer",
        "chuyển tiền ra ngoài",
        "rút về ngân hàng",
        "chuyển tới stk",
        "chuyển đến số tài khoản",
    ]
    if any(k in n for k in ticker_keys):
        return dict(EXTERNAL_DENY["buy_ticker"])
    if any(k in n for k in ilp_keys):
        return dict(EXTERNAL_DENY["ilp_new"])
    if any(k in n for k in bank_keys):
        return dict(EXTERNAL_DENY["bank_transfer"])
    return None


def detect_mode_c_act(message: str) -> Optional[str]:
    """Map user intent → allowed Mode C act kind (or None)."""
    n = _norm(message)
    if detect_external_deny(message):
        return None

    envelope_keys = [
        "tạo phong bì",
        "mở phong bì",
        "tạo quỹ tiết kiệm",
        "phong bì mới",
        "tạo envelope",
        "lập phong bì",
        "quỹ tiết kiệm nội bộ",
    ]
    lock_keys = [
        "khóa phong bì",
        "cấm lấy chéo",
        "khóa lấy chéo",
        "lock envelope",
        "không lấy chéo",
    ]
    ceiling_keys = [
        "đổi trần",
        "đổi hạn mức",
        "đặt trần",
        "sửa trần",
        "change ceiling",
        "đổi trần phong bì",
        "nâng trần phong bì",
        "hạ trần phong bì",
        "đổi target phong bì",
    ]
    bh_keys = [
        "nhắc bhyt",
        "nhắc bhtn",
        "nhắc đóng bù",
        "đặt lịch bhyt",
        "đặt lịch bhtn",
        "nhắc bảo hiểm y tế",
        "nhắc bảo hiểm thất nghiệp",
        "đóng bù bhxh",
        "nhắc bhxh",
    ]
    estate_keys = [
        "checklist di sản",
        "mở checklist di sản",
        "checklist di chúc",
        "checklist ủy quyền",
        "danh sách di sản",
    ]
    # Internal OS withdraw/transfer from emergency fund (quỹ KH) — cool-off may apply.
    # Not bank_transfer (still EXTERNAL_DENY). Not Hard Deny invest path (Agent R01).
    withdraw_keys = [
        "rút quỹ khẩn cấp",
        "rút quỹ kh",
        "lấy quỹ khẩn cấp",
        "lấy quỹ kh",
        "chuyển từ quỹ khẩn cấp",
        "chuyển từ quỹ kh",
        "rút khỏi quỹ khẩn cấp",
        "giảm quỹ khẩn cấp",
        "withdraw emergency fund",
        "transfer from emergency fund",
        "chuyển ≥20% quỹ",
        "chuyển 20% quỹ",
    ]

    if any(k in n for k in lock_keys):
        return ACT_LOCK_ENVELOPE
    if any(k in n for k in ceiling_keys):
        return ACT_CHANGE_CEILING
    if any(k in n for k in withdraw_keys):
        return ACT_WITHDRAW_EFUND
    if any(k in n for k in envelope_keys):
        return ACT_CREATE_ENVELOPE
    if any(k in n for k in bh_keys):
        return ACT_BH_REMINDER
    if any(k in n for k in estate_keys):
        return ACT_ESTATE_CHECKLIST
    return None


def _gate_ok(gate_status: str, answer_confidence: float) -> tuple[bool, Optional[str]]:
    if gate_status != "passed":
        return False, "Cổng An Toàn chưa đạt — Mode C Act chỉ khi Đạt cổng."
    if float(answer_confidence) < CONFIDENCE_THRESHOLD:
        return False, "Chưa đủ tin cậy (cần ≥ 80%) — không đề xuất Mode C Act."
    return True, None


def resolve_server_gate_confidence(user_id: str) -> tuple[str, float]:
    """Resolve gate + answer_confidence from live server state.

    Client-supplied gate_status / answer_confidence MUST be ignored at HTTP
    boundaries (propose/confirm). Fail closed → not_passed / 0.0.
    """
    if not user_id:
        return "not_passed", 0.0
    try:
        from welora.pre_rule_service import context_from_user

        ctx = context_from_user(str(user_id))
        status = str(ctx.safety_gate.status or "not_passed")
        conf = float(ctx.answer_confidence if ctx.answer_confidence is not None else 0.0)
        return status, conf
    except Exception:
        return "not_passed", 0.0


def get_companion(user_id: str) -> Optional[dict[str, Any]]:
    """Return companion link for primary user, or None."""
    if not user_id:
        return None
    return _COMPANIONS.get(str(user_id))


def set_companion(*, user_id: str, companion_user_id: str) -> tuple[int, dict[str, Any]]:
    """Attach one companion_user_id (2nd device/user) for dual-control."""
    if not user_id:
        return 400, {"error": "user_id is required"}
    cid = (companion_user_id or "").strip()
    if not cid:
        return 400, {"error": "companion_user_id is required"}
    if cid == user_id:
        return 400, {
            "error": "companion_user_id must differ from user_id",
            "reply": "Người đồng hành phải khác chính bạn.",
        }
    rec = {
        "user_id": user_id,
        "companion_user_id": cid,
        "linked_at": _now_iso(),
        "policy_version": POLICY_DUAL_CONTROL,
    }
    _COMPANIONS[user_id] = rec
    _persist_companion(rec)
    return 200, {
        "ok": True,
        "link": rec,
        "reply": f"Đã gắn người đồng hành «{cid}». Các Act đồng kiểm sẽ cần xác nhận 2 người.",
        "policy_version": POLICY_DUAL_CONTROL,
    }


def list_companions(user_id: str) -> tuple[int, dict[str, Any]]:
    """Minimal list API — 0 or 1 companion for staging MVP."""
    if not user_id:
        return 400, {"error": "user_id is required"}
    link = get_companion(user_id)
    items = [link] if link else []
    return 200, {
        "items": items,
        "companion_user_id": (link or {}).get("companion_user_id"),
        "policy_version": POLICY_DUAL_CONTROL,
    }


def requires_dual_control(act_kind: str) -> bool:
    return act_kind in DUAL_CONTROL_ACTS


def get_persona(user_id: str) -> str:
    """MVP persona stub (no full P1–P6 router). Default P1."""
    if not user_id:
        return DEFAULT_PERSONA
    p = (_PERSONAS.get(str(user_id)) or DEFAULT_PERSONA).upper().strip()
    if p not in PERSONA_FLOOR_MONTHS:
        return DEFAULT_PERSONA
    return p


def set_persona(*, user_id: str, persona: str) -> tuple[int, dict[str, Any]]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    p = (persona or "").upper().strip()
    if p not in PERSONA_FLOOR_MONTHS:
        return 400, {
            "error": "invalid persona",
            "allowed": sorted(PERSONA_FLOOR_MONTHS.keys()),
        }
    _PERSONAS[str(user_id)] = p
    _persist_persona(str(user_id), p)
    return 200, {
        "ok": True,
        "user_id": user_id,
        "persona": p,
        "floor_months": PERSONA_FLOOR_MONTHS[p],
        "policy_version": POLICY_COOL_OFF,
        "note": "Full P1–P6 router out of MVP — staging stub only.",
    }


def is_p6_persona(user_id: str) -> bool:
    return get_persona(user_id) == "P6"


def persona_floor_months(user_id: str) -> int:
    return int(PERSONA_FLOOR_MONTHS.get(get_persona(user_id), TARGET_MONTHS))


def _get_efund_goal(user_id: str):
    """Load active emergency fund goal from shared goals store (may be None)."""
    try:
        from welora import goals_api

        return goals_api.STORE.get_active_for_user(str(user_id))
    except Exception:
        return None


def evaluate_cool_off_trigger(
    *,
    user_id: str,
    amount: float,
    current_amount: Optional[float] = None,
    essential_expense_monthly: Optional[float] = None,
) -> dict[str, Any]:
    """Return whether withdraw/transfer triggers L-COOL-OFF.

    (a) remaining < persona floor amount, OR
    (b) amount ≥ 20% of current emergency fund.
    """
    goal = _get_efund_goal(user_id)
    cur = float(current_amount) if current_amount is not None else float(
        (goal.current_amount if goal else 0.0) or 0.0
    )
    essential = float(essential_expense_monthly) if essential_expense_monthly is not None else float(
        (goal.essential_expense_monthly if goal else 0.0) or 0.0
    )
    amt = max(0.0, float(amount or 0))
    floor_m = persona_floor_months(user_id)
    floor_amount = essential * floor_m if essential > 0 else 0.0
    remaining = max(0.0, cur - amt)
    pct = (amt / cur) if cur > 0 else (1.0 if amt > 0 else 0.0)
    below_floor = essential > 0 and remaining < floor_amount
    large_transfer = cur > 0 and pct >= TRANSFER_PCT_THRESHOLD
    # If no EF model / zero balance but amount requested — treat as cool-off when amount>0
    # only if we can evaluate; without goal+essential, still cool-off on ≥20% when cur known.
    triggered = bool(amt > 0 and (below_floor or large_transfer))
    return {
        "triggered": triggered,
        "below_floor": below_floor,
        "large_transfer": large_transfer,
        "amount": amt,
        "current_amount": cur,
        "remaining": remaining,
        "floor_months": floor_m,
        "floor_amount": floor_amount,
        "transfer_pct": round(pct, 4),
        "threshold_pct": TRANSFER_PCT_THRESHOLD,
        "persona": get_persona(user_id),
        "goal_id": getattr(goal, "goal_id", None),
        "months_covered_after": (
            compute_months_covered(remaining, essential) if essential > 0 else None
        ),
    }


def _deny_missing_companion(*, user_id: str, act_kind: str) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": MODE_C,
        "mode_chip": MODE_C_CHIP,
        "disclaimer": MODE_C_DISCLAIMER,
        "policy_version": POLICY_DUAL_CONTROL,
        "guardrail_result": "deny",
        "rule": POLICY_DUAL_CONTROL,
        "reply": DENY_MISSING_COMPANION_VI,
        "needs_confirm": False,
        "needs_companion_confirm": False,
        "act_proposal": None,
        "act_kind": act_kind,
        "user_id": user_id,
        "dual_control_required": True,
        "companion_missing": True,
    }


def _proposal_payload(
    *,
    proposal_id: str,
    user_id: str,
    act_kind: str,
    summary: str,
    params: dict[str, Any],
    status: str = "proposed",
    companion_user_id: Optional[str] = None,
    policy_version: Optional[str] = None,
    reason: Optional[str] = None,
    cool_off_until: Optional[str] = None,
    cool_off_meta: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    dual = requires_dual_control(act_kind) or status == "pending_dual"
    cool = status == "pending_cool_off"
    if policy_version:
        pv = policy_version
    elif cool:
        pv = POLICY_COOL_OFF
    elif dual and companion_user_id:
        pv = POLICY_DUAL_CONTROL
    else:
        pv = POLICY_VERSION
    needs_companion = bool(companion_user_id) and status == "pending_dual"
    if cool:
        hint = PENDING_COOL_OFF_VI
    elif needs_companion:
        hint = PENDING_DUAL_VI
    else:
        hint = "Xác nhận để ghi vào WeloraOS. Có thể hoàn tác trong 24 giờ."
    return {
        "proposal_id": proposal_id,
        "user_id": user_id,
        "companion_user_id": companion_user_id,
        "mode": MODE_C,
        "mode_chip": MODE_C_CHIP,
        "disclaimer": MODE_C_DISCLAIMER,
        "policy_version": pv,
        "act_kind": act_kind,
        "summary": summary,
        "params": params,
        "needs_confirm": (not needs_companion) and status == "proposed",
        "needs_companion_confirm": needs_companion,
        "needs_cool_off_wait": cool,
        "confirm_hint": hint,
        "status": status,
        "dual_control_required": dual and not cool,
        "cool_off_required": cool,
        "reason": reason,
        "cool_off_until": cool_off_until,
        "cool_off": cool_off_meta,
        "warning_level": "red" if cool else None,
        "warning_vi": COOL_OFF_WARN_VI if cool else None,
        "created_at": _now_iso(),
    }



def build_policy_act(
    *,
    act_kind: Optional[str],
    message: str = "",
    params: Optional[dict[str, Any]] = None,
    phase: str = "propose",
    status: Optional[str] = None,
    cool_off: Optional[dict[str, Any]] = None,
    cool_off_ready: bool = False,
    cool_off_escalated_to_dual: bool = False,
    dual_control_required: bool = False,
    intent: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    act: dict[str, Any] = {
        "kind": act_kind,
        "act_kind": act_kind,
        "message": message or "",
        "params": dict(params or {}),
        "phase": phase,
        "mode": MODE_C,
    }
    if status:
        act["status"] = status
    if cool_off is not None:
        act["cool_off"] = cool_off
    if cool_off_ready:
        act["cool_off_ready"] = True
    if cool_off_escalated_to_dual:
        act["cool_off_escalated_to_dual"] = True
    if dual_control_required:
        act["dual_control_required"] = True
    if intent:
        act["intent"] = intent
        act["external_intent"] = intent
    if extra:
        act.update(extra)
    return act


def build_policy_os_state(
    *,
    user_id: str,
    gate_status: str = "passed",
    answer_confidence: float = 0.90,
    companion: Optional[dict[str, Any]] = None,
    cool_off: Optional[dict[str, Any]] = None,
    proposal_status: Optional[str] = None,
    cool_off_ready: bool = False,
    companion_confirming: bool = False,
    companion_verified: bool = False,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    persona = get_persona(user_id)
    link = companion if companion is not None else get_companion(user_id)
    state: dict[str, Any] = {
        "user_id": user_id,
        "persona": persona,
        "gate_status": gate_status,
        "answer_confidence": float(answer_confidence),
        "companion": link,
        "mode": MODE_C,
        "phase": "propose",
    }
    if cool_off is not None:
        state["cool_off"] = cool_off
    if proposal_status:
        state["proposal_status"] = proposal_status
    if cool_off_ready:
        state["cool_off_ready"] = True
    if companion_confirming:
        state["companion_confirming"] = True
    if companion_verified:
        state["companion_verified"] = True
    if extra:
        state.update(extra)
    return state


def run_os_policy(
    *,
    user_id: str,
    act: dict[str, Any],
    os_state: Optional[dict[str, Any]] = None,
) -> Any:
    """Single choke-point: policy_engine.evaluate before OS mutate."""
    persona = get_persona(user_id)
    state = os_state or build_policy_os_state(user_id=user_id)
    state.setdefault("persona", persona)
    decision = policy_evaluate(act, persona, state)
    return decision


def _policy_deny_payload(
    *,
    user_id: str,
    act_kind: Optional[str],
    decision: Any,
) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": MODE_C,
        "mode_chip": MODE_C_CHIP,
        "disclaimer": MODE_C_DISCLAIMER,
        "policy_version": decision.policy_version,
        "guardrail_result": "deny",
        "rule": decision.rule_id,
        "rule_id": decision.rule_id,
        "reply": (
            f"Từ chối Mode C ({decision.rule_id}): {decision.message_vi}\n"
            "Mode C chỉ hành động nội bộ OS (G1 confirm) — không phải L2 Action Tools."
        ),
        "needs_confirm": False,
        "act_proposal": None,
        "act_kind": act_kind,
        "user_id": user_id,
        "persona": decision.persona,
        "escalate_flag": bool(decision.escalate_flag),
        "policy_log": decision.to_log(),
    }


def _append_policy_log(
    *,
    user_id: str,
    decision: Any,
    act_kind: Optional[str] = None,
    event: str = "policy_evaluate",
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    entry = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "mode": MODE_C,
        "policy_version": decision.policy_version,
        "persona": decision.persona or get_persona(user_id),
        "rule_id": decision.rule_id,
        "tools_called": list(decision.tools_called or []),
        "escalate_flag": bool(decision.escalate_flag),
        "verdict": decision.verdict,
        "act_kind": act_kind,
        "event": event,
        "timestamp": _now_iso(),
    }
    if extra:
        entry.update(extra)
    _ACT_LOGS.append(entry)
    _persist_act_log(entry)
    return entry



def propose_act(
    *,
    user_id: str,
    message: str,
    gate_status: str,
    answer_confidence: float,
    params: Optional[dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> tuple[int, dict[str, Any]]:
    """Propose a Mode C act (no write). External intents → DENY.

    Cool-off: withdraw/transfer quỹ KH below floor or ≥20% → pending_cool_off
    (reason required). P6 on same trigger → dual-control escalate, not self cool-off.
    """
    if not user_id:
        return 400, {"error": "user_id is required"}

    # --- External / L2 shapes → policy router DENY (no OS write) ---
    ext = detect_external_deny(message)
    if ext:
        intent_map = {
            "L-NO-TICKER": "buy_ticker",
            "L-NO-ILP-NEW": "ilp_new",
            "L-FIDUCIARY": "bank_transfer",
        }
        intent = intent_map.get(ext["rule"])
        decision = run_os_policy(
            user_id=user_id,
            act=build_policy_act(
                act_kind=intent,
                message=message,
                intent=intent,
                phase="propose",
            ),
            os_state=build_policy_os_state(
                user_id=user_id,
                gate_status=gate_status,
                answer_confidence=answer_confidence,
            ),
        )
        _append_policy_log(
            user_id=user_id, decision=decision, act_kind=intent, event="propose_deny_external"
        )
        if decision.verdict == "DENY":
            out = _policy_deny_payload(user_id=user_id, act_kind=intent, decision=decision)
            # keep legacy reply shape for Mode C external deny tests
            out["reply"] = (
                f"Từ chối Mode C: {ext['reason']}\n"
                "Mode C chỉ hành động nội bộ OS (G1 confirm) — không phải L2 Action Tools."
            )
            out["rule"] = ext["rule"]
            out["policy_version"] = POLICY_VERSION
            return 200, out
        # fall through only if router unexpectedly ALLOWs — still DENY fail-closed
        return 200, {
            "ok": False,
            "mode": MODE_C,
            "mode_chip": MODE_C_CHIP,
            "disclaimer": MODE_C_DISCLAIMER,
            "policy_version": POLICY_VERSION,
            "guardrail_result": "deny",
            "rule": ext["rule"],
            "reply": (
                f"Từ chối Mode C: {ext['reason']}\n"
                "Mode C chỉ hành động nội bộ OS (G1 confirm) — không phải L2 Action Tools."
            ),
            "needs_confirm": False,
            "act_proposal": None,
        }

    # Speculative intent (L-NO-SPEC) even when not in EXTERNAL_DENY map
    spec_decision = run_os_policy(
        user_id=user_id,
        act=build_policy_act(act_kind=None, message=message, phase="propose"),
        os_state=build_policy_os_state(
            user_id=user_id,
            gate_status=gate_status,
            answer_confidence=answer_confidence,
        ),
    )
    if spec_decision.verdict == "DENY" and spec_decision.rule_id in {
        "L-NO-SPEC",
        "L-EMERGENCY",
        "L-ESTATE",
        "L-NO-TICKER",
        "L-NO-ILP-NEW",
        "L-FIDUCIARY",
    }:
        # Only short-circuit message-only denies when no Mode C act would match;
        # estate checklist messages must still reach act detection.
        maybe_act = detect_mode_c_act(message)
        if maybe_act is None or spec_decision.rule_id in {
            "L-NO-SPEC",
            "L-NO-TICKER",
            "L-NO-ILP-NEW",
            "L-FIDUCIARY",
            "L-EMERGENCY",
        }:
            if maybe_act is None or spec_decision.rule_id != "L-ESTATE":
                _append_policy_log(
                    user_id=user_id,
                    decision=spec_decision,
                    act_kind=None,
                    event="propose_deny_message",
                )
                return 200, _policy_deny_payload(
                    user_id=user_id, act_kind=None, decision=spec_decision
                )

    act_kind = detect_mode_c_act(message)
    if not act_kind:
        return 200, {
            "ok": False,
            "mode": None,
            "reply": None,
            "act_proposal": None,
            "needs_confirm": False,
            "policy_version": POLICY_VERSION,
        }

    ok, gate_reason = _gate_ok(gate_status, answer_confidence)
    if not ok:
        return 200, {
            "ok": False,
            "mode": MODE_C,
            "mode_chip": MODE_C_CHIP,
            "disclaimer": MODE_C_DISCLAIMER,
            "policy_version": POLICY_VERSION,
            "guardrail_result": "deny",
            "reply": gate_reason,
            "needs_confirm": False,
            "act_proposal": None,
            "gate_blocked": True,
        }

    params = dict(params or {})
    reason_text = (reason if reason is not None else params.pop("reason", None)) or ""
    reason_text = str(reason_text).strip()

    cool_meta: Optional[dict[str, Any]] = None

    if act_kind == ACT_CREATE_ENVELOPE:
        title = params.get("title") or _extract_envelope_title(message) or "Phong bì tiết kiệm"
        target = float(params.get("target_amount") or 0)
        params = {"title": title, "target_amount": target, "locked": False, "cross_take_forbidden": False}
        summary = f"Tạo phong bì «{title}» trên WeloraOS"
    elif act_kind == ACT_LOCK_ENVELOPE:
        eid = params.get("envelope_id") or _latest_envelope_id(user_id)
        params = {"envelope_id": eid, "cross_take_forbidden": True, "locked": True}
        summary = "Khóa phong bì — cấm lấy chéo"
        if not eid:
            summary = "Khóa phong bì — cần phong bì hiện có (sẽ stub nếu chưa có)"
    elif act_kind == ACT_CHANGE_CEILING:
        eid = params.get("envelope_id") or _latest_envelope_id(user_id)
        new_ceil = float(params.get("target_amount") or params.get("new_ceiling") or 0)
        if new_ceil <= 0:
            new_ceil = _extract_ceiling_amount(message) or 0.0
        params = {"envelope_id": eid, "target_amount": new_ceil, "new_ceiling": new_ceil}
        summary = f"Đổi trần phong bì → {int(new_ceil):,} ₫".replace(",", ".")
        if not eid:
            summary = "Đổi trần phong bì — cần phong bì hiện có (sẽ stub nếu chưa có)"
    elif act_kind == ACT_BH_REMINDER:
        kind = params.get("reminder_kind") or _detect_bh_kind(message)
        params = {
            "reminder_kind": kind,
            "schedule_only": True,
            "no_submit_forms": True,
            "no_forge_signature": True,
        }
        summary = f"Đặt nhắc {kind} (chỉ lịch — không nộp hồ sơ / không giả chữ ký)"
    elif act_kind == ACT_WITHDRAW_EFUND:
        amount = float(params.get("amount") or 0)
        if amount <= 0:
            amount = _extract_ceiling_amount(message) or 0.0
        cur_override = params.get("current_amount")
        ess_override = params.get("essential_expense_monthly")
        cool_meta = evaluate_cool_off_trigger(
            user_id=user_id,
            amount=amount,
            current_amount=float(cur_override) if cur_override is not None else None,
            essential_expense_monthly=float(ess_override) if ess_override is not None else None,
        )
        if amount <= 0:
            return 400, {
                "error": "amount required for withdraw_emergency_fund",
                "mode": MODE_C,
                "policy_version": POLICY_COOL_OFF,
                "reply": "Cần số tiền rút/chuyển từ quỹ khẩn cấp.",
            }
        params = {
            "amount": amount,
            "goal_id": cool_meta.get("goal_id"),
            "current_amount": cool_meta.get("current_amount"),
            "remaining": cool_meta.get("remaining"),
            "floor_amount": cool_meta.get("floor_amount"),
            "floor_months": cool_meta.get("floor_months"),
            "transfer_pct": cool_meta.get("transfer_pct"),
            "to_envelope_id": params.get("to_envelope_id"),
            "internal_only": True,
            "no_bank_transfer": True,
        }
        summary = (
            f"Rút/chuyển {int(amount):,} ₫ từ quỹ khẩn cấp (nội bộ OS)".replace(",", ".")
        )
    else:  # estate
        params = {
            "checklist_only": True,
            "no_legal_will": True,
            "items": list(
                params.get("items")
                or [
                    "Di chúc / người hưởng (checklist)",
                    "Ủy quyền y tế / tài sản (checklist)",
                    "Hẹn luật sư hộ (escalate — không soạn di chúc có hiệu lực)",
                ]
            ),
        }
        summary = "Mở checklist di sản (không soạn di chúc pháp lý)"

    # --- Policy router choke-point (before any OS write / pending create) ---
    decision = run_os_policy(
        user_id=user_id,
        act=build_policy_act(
            act_kind=act_kind,
            message=message,
            params=params,
            phase="propose",
            cool_off=cool_meta,
            dual_control_required=requires_dual_control(act_kind),
        ),
        os_state=build_policy_os_state(
            user_id=user_id,
            gate_status=gate_status,
            answer_confidence=answer_confidence,
            cool_off=cool_meta,
        ),
    )
    _append_policy_log(
        user_id=user_id,
        decision=decision,
        act_kind=act_kind,
        event="propose_evaluate",
    )

    if decision.verdict == "DENY":
        out = _policy_deny_payload(user_id=user_id, act_kind=act_kind, decision=decision)
        if decision.rule_id == POLICY_DUAL_CONTROL:
            # Preserve #186 missing-companion shape
            deny = _deny_missing_companion(user_id=user_id, act_kind=act_kind)
            deny["rule_id"] = decision.rule_id
            deny["persona"] = decision.persona
            deny["policy_log"] = decision.to_log()
            if decision.meta.get("cool_off_escalated_to_dual") or (
                cool_meta and cool_meta.get("triggered") and is_p6_persona(user_id)
            ):
                deny["reply"] = P6_COOL_OFF_ESCALATE_VI + " " + DENY_MISSING_COMPANION_VI
                deny["cool_off_escalated_to_dual"] = True
                deny["cool_off"] = cool_meta
            return 200, deny
        return 200, out

    if decision.verdict == "ESCALATE":
        side = decision.side_effect
        # P6 cool-off → dual: need companion or DENY
        if side == SIDE_PENDING_DUAL:
            link = get_companion(user_id)
            if not link or not link.get("companion_user_id"):
                deny = _deny_missing_companion(user_id=user_id, act_kind=act_kind)
                if decision.meta.get("cool_off_escalated_to_dual") or (
                    cool_meta and cool_meta.get("triggered") and is_p6_persona(user_id)
                ):
                    deny["reply"] = P6_COOL_OFF_ESCALATE_VI + " " + DENY_MISSING_COMPANION_VI
                    deny["cool_off_escalated_to_dual"] = True
                    deny["cool_off"] = cool_meta
                deny["rule_id"] = POLICY_DUAL_CONTROL
                deny["persona"] = decision.persona
                deny["policy_log"] = decision.to_log()
                deny["escalate_flag"] = True
                return 200, deny

            companion_id = str(link.get("companion_user_id"))
            pid = str(uuid.uuid4())
            prop = _proposal_payload(
                proposal_id=pid,
                user_id=user_id,
                act_kind=act_kind,
                summary=summary,
                params=params,
                status="pending_dual",
                companion_user_id=companion_id,
                policy_version=POLICY_DUAL_CONTROL,
                reason=reason_text or None,
                cool_off_meta=cool_meta,
            )
            if decision.meta.get("cool_off_escalated_to_dual") or (
                cool_meta and cool_meta.get("triggered") and is_p6_persona(user_id)
            ):
                prop["cool_off_escalated_to_dual"] = True
            _PROPOSALS[pid] = prop
            _persist_proposal(prop)
            if prop.get("cool_off_escalated_to_dual"):
                reply = (
                    f"{MODE_C_CHIP}\n{MODE_C_DISCLAIMER}\n\n"
                    f"{P6_COOL_OFF_ESCALATE_VI}\n"
                    f"Đề xuất đồng kiểm: {summary}.\n"
                    f"{PENDING_DUAL_VI}\n"
                    f"Người đồng hành: {companion_id}."
                )
                return 200, {
                    "ok": True,
                    "mode": MODE_C,
                    "mode_chip": MODE_C_CHIP,
                    "disclaimer": MODE_C_DISCLAIMER,
                    "policy_version": POLICY_DUAL_CONTROL,
                    "guardrail_result": "pass",
                    "rule": POLICY_DUAL_CONTROL,
                    "rule_id": POLICY_DUAL_CONTROL,
                    "reply": reply,
                    "needs_confirm": False,
                    "needs_companion_confirm": True,
                    "act_proposal": prop,
                    "dual_control_required": True,
                    "cool_off_escalated_to_dual": True,
                    "status": "pending_dual",
                    "user_id": user_id,
                    "companion_user_id": companion_id,
                    "cool_off": cool_meta,
                    "warning_level": "red",
                    "warning_vi": P6_COOL_OFF_ESCALATE_VI,
                    "persona": decision.persona,
                    "escalate_flag": True,
                    "policy_log": decision.to_log(),
                }

            reply = (
                f"{MODE_C_CHIP}\n{MODE_C_DISCLAIMER}\n\n"
                f"Đề xuất đồng kiểm: {summary}.\n"
                f"{PENDING_DUAL_VI}\n"
                f"Người đồng hành: {companion_id}."
            )
            return 200, {
                "ok": True,
                "mode": MODE_C,
                "mode_chip": MODE_C_CHIP,
                "disclaimer": MODE_C_DISCLAIMER,
                "policy_version": POLICY_DUAL_CONTROL,
                "guardrail_result": "pass",
                "rule": POLICY_DUAL_CONTROL,
                "rule_id": POLICY_DUAL_CONTROL,
                "reply": reply,
                "needs_confirm": False,
                "needs_companion_confirm": True,
                "act_proposal": prop,
                "dual_control_required": True,
                "status": "pending_dual",
                "user_id": user_id,
                "companion_user_id": companion_id,
                "persona": decision.persona,
                "escalate_flag": True,
                "policy_log": decision.to_log(),
            }

        if side == SIDE_PENDING_COOL_OFF:
            # P1–P5 cool-off path — require non-empty reason (#187)
            if not reason_text:
                return 200, {
                    "ok": False,
                    "mode": MODE_C,
                    "mode_chip": "L-COOL-OFF · Cảnh báo đỏ",
                    "disclaimer": MODE_C_DISCLAIMER,
                    "policy_version": POLICY_COOL_OFF,
                    "guardrail_result": "pass",
                    "rule": POLICY_COOL_OFF,
                    "rule_id": POLICY_COOL_OFF,
                    "reply": f"{COOL_OFF_WARN_VI}\n{COOL_OFF_NEED_REASON_VI}",
                    "needs_confirm": False,
                    "needs_reason": True,
                    "needs_cool_off_wait": True,
                    "act_proposal": None,
                    "status": "pending_cool_off",
                    "warning_level": "red",
                    "warning_vi": COOL_OFF_WARN_VI,
                    "cool_off": cool_meta,
                    "persona": decision.persona,
                    "escalate_flag": True,
                    "policy_log": decision.to_log(),
                    "ui": {
                        "chip": "L-COOL-OFF · Chờ 24 giờ",
                        "tone": "danger",
                        "require_reason": True,
                    },
                }

            cool_until = (_now() + timedelta(hours=COOL_OFF_HOURS)).isoformat()
            pid = str(uuid.uuid4())
            prop = _proposal_payload(
                proposal_id=pid,
                user_id=user_id,
                act_kind=act_kind,
                summary=summary,
                params=params,
                status="pending_cool_off",
                policy_version=POLICY_COOL_OFF,
                reason=reason_text,
                cool_off_until=cool_until,
                cool_off_meta=cool_meta,
            )
            _PROPOSALS[pid] = prop
            _persist_proposal(prop)
            reply = (
                f"{MODE_C_CHIP}\n{COOL_OFF_WARN_VI}\n\n"
                f"Đề xuất: {summary}.\n"
                f"Lý do: {reason_text}\n"
                f"{PENDING_COOL_OFF_VI}\n"
                f"Mở khóa xác nhận sau: {cool_until}"
            )
            return 200, {
                "ok": True,
                "mode": MODE_C,
                "mode_chip": "L-COOL-OFF · Chờ 24 giờ",
                "disclaimer": MODE_C_DISCLAIMER,
                "policy_version": POLICY_COOL_OFF,
                "guardrail_result": "pass",
                "rule": POLICY_COOL_OFF,
                "rule_id": POLICY_COOL_OFF,
                "reply": reply,
                "needs_confirm": False,
                "needs_cool_off_wait": True,
                "needs_reason": False,
                "act_proposal": prop,
                "status": "pending_cool_off",
                "cool_off_until": cool_until,
                "reason": reason_text,
                "warning_level": "red",
                "warning_vi": COOL_OFF_WARN_VI,
                "cool_off": cool_meta,
                "persona": decision.persona,
                "escalate_flag": True,
                "policy_log": decision.to_log(),
                "ui": {
                    "chip": "L-COOL-OFF · Chờ 24 giờ",
                    "tone": "danger",
                    "require_reason": False,
                },
            }

        # Unknown escalate → fail closed
        return 200, _policy_deny_payload(user_id=user_id, act_kind=act_kind, decision=decision)

    # ALLOW — normal propose (no dual / no cool-off)
    companion_id = None
    status = "proposed"
    pid = str(uuid.uuid4())
    prop = _proposal_payload(
        proposal_id=pid,
        user_id=user_id,
        act_kind=act_kind,
        summary=summary,
        params=params,
        status=status,
        companion_user_id=companion_id,
    )
    _PROPOSALS[pid] = prop
    _persist_proposal(prop)

    reply = (
        f"{MODE_C_CHIP}\n{MODE_C_DISCLAIMER}\n\n"
        f"Đề xuất: {summary}.\n"
        "Nhấn Xác nhận để ghi vào OS (có thể hoàn tác trong 24 giờ)."
    )
    return 200, {
        "ok": True,
        "mode": MODE_C,
        "mode_chip": MODE_C_CHIP,
        "disclaimer": MODE_C_DISCLAIMER,
        "policy_version": POLICY_VERSION,
        "guardrail_result": "pass",
        "rule_id": decision.rule_id,
        "reply": reply,
        "needs_confirm": True,
        "act_proposal": prop,
        "persona": decision.persona,
        "escalate_flag": False,
        "policy_log": decision.to_log(),
    }



def _extract_envelope_title(message: str) -> Optional[str]:
    n = message.strip()
    for prefix in (
        "Tạo phong bì",
        "tạo phong bì",
        "Mở phong bì",
        "mở phong bì",
        "Tạo quỹ tiết kiệm",
        "tạo quỹ tiết kiệm",
        "Lập phong bì",
        "lập phong bì",
    ):
        if n.startswith(prefix):
            rest = n[len(prefix) :].strip(" :·—-")
            if rest:
                return rest[:80]
    return None


def _extract_ceiling_amount(message: str) -> Optional[float]:
    """Parse a VND-ish amount from ceiling-change messages (best-effort)."""
    import re

    n = message.replace(".", "").replace(",", "")
    m = re.search(r"(\d{4,})", n)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            return None
    return None


def _detect_bh_kind(message: str) -> str:
    n = _norm(message)
    if "bhtn" in n or "thất nghiệp" in n:
        return "BHTN"
    if "đóng bù" in n or "bhxh" in n:
        return "BHXH_topup"
    return "BHYT"


def _latest_envelope_id(user_id: str) -> Optional[str]:
    ids = _ENVELOPES_BY_USER.get(user_id) or []
    for eid in reversed(ids):
        if eid in _ENVELOPES and _ENVELOPES[eid].get("status") == "active":
            return eid
    return None


def _cool_off_elapsed(prop: dict[str, Any], *, advance: bool = False) -> tuple[bool, Optional[str]]:
    """Return (ready, cool_off_until_iso). advance=True skips real wait (UAT header/clock)."""
    if advance:
        return True, prop.get("cool_off_until")
    until_s = prop.get("cool_off_until")
    if not until_s:
        # Fallback: created_at + COOL_OFF_HOURS
        created = prop.get("created_at")
        if not created:
            return False, None
        until = datetime.fromisoformat(created) + timedelta(hours=COOL_OFF_HOURS)
    else:
        until = datetime.fromisoformat(until_s)
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return _now() >= until, until.isoformat()


def confirm_act(
    *,
    user_id: str,
    proposal_id: str,
    confirm: bool,
    gate_status: str = "passed",
    answer_confidence: float = 0.90,
    cool_off_advance: bool = False,
) -> tuple[int, dict[str, Any]]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    if not confirm:
        return 400, {
            "error": "confirm required",
            "hint": "User phải xác nhận (G1) trước khi Mode C ghi OS.",
            "mode": MODE_C,
            "policy_version": POLICY_VERSION,
        }
    prop = _PROPOSALS.get(proposal_id)
    if not prop or prop.get("user_id") != user_id:
        return 404, {"error": "proposal not found"}
    if prop.get("status") == "confirmed":
        return 409, {"error": "proposal already confirmed", "act_id": prop.get("act_id")}
    if prop.get("status") == "cancelled":
        return 409, {"error": "proposal cancelled"}

    # Fail-closed: dual-control pending cannot be written by primary confirm /
    # client spoof flags. Only companion_confirm_act writes OS.
    # withdraw_efund is NOT in DUAL_CONTROL_ACTS unless escalated to pending_dual.
    if prop.get("status") == "pending_dual" or (
        requires_dual_control(prop.get("act_kind") or "")
        and prop.get("status") != "pending_cool_off"
    ):
        return 403, {
            "error": "dual_control_required",
            "rule": POLICY_DUAL_CONTROL,
            "policy_version": POLICY_DUAL_CONTROL,
            "mode": MODE_C,
            "reply": (
                "Hành động này cần xác nhận người đồng hành (L-DUAL-CONTROL). "
                "Không ghi OS qua confirm một mình / cờ client."
            ),
            "needs_companion_confirm": True,
            "proposal_id": proposal_id,
            "companion_user_id": prop.get("companion_user_id"),
        }

    # Cool-off gate: early confirm stays pending (no OS write).
    if prop.get("status") == "pending_cool_off":
        reason_stored = str(prop.get("reason") or "").strip()
        if not reason_stored:
            return 200, {
                "ok": False,
                "status": "pending_cool_off",
                "needs_reason": True,
                "rule": POLICY_COOL_OFF,
                "policy_version": POLICY_COOL_OFF,
                "mode": MODE_C,
                "reply": COOL_OFF_NEED_REASON_VI,
                "warning_level": "red",
                "warning_vi": COOL_OFF_WARN_VI,
                "proposal_id": proposal_id,
            }
        ready, until_iso = _cool_off_elapsed(prop, advance=bool(cool_off_advance))
        if not ready:
            return 200, {
                "ok": False,
                "status": "pending_cool_off",
                "still_pending": True,
                "needs_cool_off_wait": True,
                "rule": POLICY_COOL_OFF,
                "policy_version": POLICY_COOL_OFF,
                "mode": MODE_C,
                "mode_chip": "L-COOL-OFF · Chờ 24 giờ",
                "reply": (
                    f"{PENDING_COOL_OFF_VI} Còn chờ đến {until_iso}. "
                    "Xác nhận sớm không ghi OS."
                ),
                "cool_off_until": until_iso,
                "warning_level": "red",
                "warning_vi": COOL_OFF_WARN_VI,
                "proposal_id": proposal_id,
                "act_proposal": prop,
            }

    ok, reason = _gate_ok(gate_status, answer_confidence)
    if not ok:
        return 403, {
            "error": reason,
            "mode": MODE_C,
            "policy_version": (
                POLICY_COOL_OFF if prop.get("status") == "pending_cool_off" else POLICY_VERSION
            ),
        }

    act_kind = prop["act_kind"]
    params = dict(prop.get("params") or {})

    # --- Policy router choke-point before OS write ---
    cool_ready = False
    if prop.get("status") == "pending_cool_off":
        cool_ready, _ = _cool_off_elapsed(prop, advance=bool(cool_off_advance))
    decision = run_os_policy(
        user_id=user_id,
        act=build_policy_act(
            act_kind=act_kind,
            params=params,
            phase="confirm",
            status=prop.get("status"),
            cool_off=prop.get("cool_off"),
            cool_off_ready=cool_ready,
            cool_off_escalated_to_dual=bool(prop.get("cool_off_escalated_to_dual")),
            dual_control_required=requires_dual_control(act_kind),
        ),
        os_state=build_policy_os_state(
            user_id=user_id,
            gate_status=gate_status,
            answer_confidence=answer_confidence,
            proposal_status=prop.get("status"),
            cool_off=prop.get("cool_off"),
            cool_off_ready=cool_ready,
            extra={"phase": "confirm"},
        ),
    )
    _append_policy_log(
        user_id=user_id,
        decision=decision,
        act_kind=act_kind,
        event="confirm_evaluate",
        extra={"proposal_id": proposal_id},
    )
    if decision.verdict in ("DENY", "ESCALATE"):
        # DENY/ESCALATE must not write. Cool-off still-pending already handled above;
        # dual primary confirm blocked here as fail-closed.
        code = 403 if decision.rule_id == POLICY_DUAL_CONTROL else 200
        return code, {
            "ok": False,
            "error": "policy_blocked",
            "mode": MODE_C,
            "mode_chip": MODE_C_CHIP,
            "policy_version": decision.policy_version,
            "rule": decision.rule_id,
            "rule_id": decision.rule_id,
            "reply": decision.message_vi,
            "guardrail_result": "deny",
            "escalate_flag": bool(decision.escalate_flag),
            "persona": decision.persona,
            "policy_log": decision.to_log(),
            "proposal_id": proposal_id,
            "needs_companion_confirm": decision.rule_id == POLICY_DUAL_CONTROL,
            "status": prop.get("status"),
        }

    act_id = str(uuid.uuid4())
    applied: dict[str, Any]

    if act_kind == ACT_CREATE_ENVELOPE:
        applied = _write_envelope(user_id, params, act_id)
    elif act_kind == ACT_LOCK_ENVELOPE:
        applied = _write_lock(user_id, params, act_id)
    elif act_kind == ACT_CHANGE_CEILING:
        applied = _write_ceiling(user_id, params, act_id)
    elif act_kind == ACT_BH_REMINDER:
        applied = _write_reminder(user_id, params, act_id)
    elif act_kind == ACT_ESTATE_CHECKLIST:
        applied = _write_estate(user_id, params, act_id)
    elif act_kind == ACT_WITHDRAW_EFUND:
        applied = _write_withdraw_efund(user_id, params, act_id)
    else:
        return 400, {"error": f"unsupported act_kind: {act_kind}"}

    undo_until = (_now() + timedelta(hours=UNDO_HOURS)).isoformat()
    undo_token = str(uuid.uuid4())
    _UNDO[act_id] = {
        "act_id": act_id,
        "user_id": user_id,
        "act_kind": act_kind,
        "undo_token": undo_token,
        "undo_until": undo_until,
        "snapshot": applied.get("_undo_snapshot"),
        "created_at": _now_iso(),
    }
    _persist_undo(_UNDO[act_id])
    applied.pop("_undo_snapshot", None)

    was_cool = prop.get("policy_version") == POLICY_COOL_OFF or bool(prop.get("cool_off_required"))
    pv_out = POLICY_COOL_OFF if was_cool else POLICY_VERSION

    prop["status"] = "confirmed"
    prop["act_id"] = act_id
    prop["confirmed_at"] = _now_iso()
    if cool_off_advance:
        prop["cool_off_advanced"] = True
    _persist_proposal(prop)

    log_entry = {
        "id": str(uuid.uuid4()),
        "act_id": act_id,
        "user_id": user_id,
        "mode": MODE_C,
        "policy_version": pv_out,
        "persona": get_persona(user_id),
        "rule": POLICY_COOL_OFF if was_cool else decision.rule_id,
        "rule_id": POLICY_COOL_OFF if was_cool else decision.rule_id,
        "tools_called": list(decision.tools_called or []),
        "escalate_flag": False,
        "act_kind": act_kind,
        "proposal_id": proposal_id,
        "guardrail_result": "allow",
        "cool_off": was_cool,
        "timestamp": _now_iso(),
    }
    _ACT_LOGS.append(log_entry)
    _persist_act_log(log_entry)

    return 200, {
        "ok": True,
        "mode": MODE_C,
        "mode_chip": MODE_C_CHIP,
        "disclaimer": MODE_C_DISCLAIMER,
        "policy_version": pv_out,
        "rule": POLICY_COOL_OFF if was_cool else decision.rule_id,
        "rule_id": POLICY_COOL_OFF if was_cool else decision.rule_id,
        "persona": get_persona(user_id),
        "escalate_flag": False,
        "policy_log": decision.to_log(),
        "act_id": act_id,
        "act_kind": act_kind,
        "result": applied,
        "undo": {
            "token": undo_token,
            "until": undo_until,
            "hours": UNDO_HOURS,
        },
        "log": log_entry,
        "cool_off_completed": was_cool,
    }


def _write_envelope(user_id: str, params: dict, act_id: str) -> dict[str, Any]:
    eid = str(uuid.uuid4())
    rec = {
        "envelope_id": eid,
        "user_id": user_id,
        "kind": "envelope",
        "title": str(params.get("title") or "Phong bì tiết kiệm"),
        "target_amount": float(params.get("target_amount") or 0),
        "current_amount": 0.0,
        "locked": bool(params.get("locked")),
        "cross_take_forbidden": bool(params.get("cross_take_forbidden")),
        "status": "active",
        "created_by_act_id": act_id,
        "mode": MODE_C,
        "policy_version": POLICY_VERSION,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    _ENVELOPES[eid] = rec
    _ENVELOPES_BY_USER.setdefault(user_id, []).append(eid)
    _persist_envelope(rec)
    out = dict(rec)
    out["_undo_snapshot"] = {"envelope_id": eid, "action": "delete"}
    return out


def _write_lock(user_id: str, params: dict, act_id: str) -> dict[str, Any]:
    eid = params.get("envelope_id") or _latest_envelope_id(user_id)
    if not eid or eid not in _ENVELOPES:
        # Stub path: create locked placeholder so Act still persists.
        stub = _write_envelope(
            user_id,
            {
                "title": "Phong bì (stub khóa lấy chéo)",
                "target_amount": 0,
                "locked": True,
                "cross_take_forbidden": True,
            },
            act_id,
        )
        stub["lock_stub"] = True
        stub["note"] = CROSS_TAKE_NOTE
        stub["cross_take_supported"] = CROSS_TAKE_SUPPORTED
        return stub

    prev = {
        "locked": _ENVELOPES[eid].get("locked"),
        "cross_take_forbidden": _ENVELOPES[eid].get("cross_take_forbidden"),
    }
    _ENVELOPES[eid]["locked"] = True
    _ENVELOPES[eid]["cross_take_forbidden"] = True
    _ENVELOPES[eid]["updated_at"] = _now_iso()
    _ENVELOPES[eid]["locked_by_act_id"] = act_id
    _persist_envelope(_ENVELOPES[eid])
    out = dict(_ENVELOPES[eid])
    out["note"] = CROSS_TAKE_NOTE
    out["cross_take_supported"] = CROSS_TAKE_SUPPORTED
    out["_undo_snapshot"] = {"envelope_id": eid, "action": "restore_lock", "prev": prev}
    return out


def _write_ceiling(user_id: str, params: dict, act_id: str) -> dict[str, Any]:
    eid = params.get("envelope_id") or _latest_envelope_id(user_id)
    new_ceil = float(params.get("target_amount") or params.get("new_ceiling") or 0)
    if not eid or eid not in _ENVELOPES:
        stub = _write_envelope(
            user_id,
            {
                "title": "Phong bì (stub đổi trần)",
                "target_amount": new_ceil,
                "locked": False,
                "cross_take_forbidden": False,
            },
            act_id,
        )
        stub["ceiling_stub"] = True
        return stub

    prev = {"target_amount": _ENVELOPES[eid].get("target_amount")}
    _ENVELOPES[eid]["target_amount"] = new_ceil
    _ENVELOPES[eid]["updated_at"] = _now_iso()
    _ENVELOPES[eid]["ceiling_by_act_id"] = act_id
    _persist_envelope(_ENVELOPES[eid])
    out = dict(_ENVELOPES[eid])
    out["_undo_snapshot"] = {
        "envelope_id": eid,
        "action": "restore_ceiling",
        "prev": prev,
    }
    return out


def _write_reminder(user_id: str, params: dict, act_id: str) -> dict[str, Any]:
    rid = str(uuid.uuid4())
    rec = {
        "reminder_id": rid,
        "user_id": user_id,
        "kind": "bh_reminder",
        "reminder_kind": params.get("reminder_kind") or "BHYT",
        "schedule_only": True,
        "no_submit_forms": True,
        "no_forge_signature": True,
        "status": "scheduled",
        "created_by_act_id": act_id,
        "mode": MODE_C,
        "policy_version": POLICY_VERSION,
        "created_at": _now_iso(),
    }
    _REMINDERS[rid] = rec
    _REMINDERS_BY_USER.setdefault(user_id, []).append(rid)
    _persist_reminder(rec)
    out = dict(rec)
    out["_undo_snapshot"] = {"reminder_id": rid, "action": "delete"}
    return out


def _write_withdraw_efund(user_id: str, params: dict, act_id: str) -> dict[str, Any]:
    """Apply internal OS withdraw from emergency fund goal. No bank / L2."""
    from welora import goals_api

    amount = float(params.get("amount") or 0)
    if amount <= 0:
        raise ValueError("amount must be > 0")
    goal = goals_api.STORE.get_active_for_user(user_id)
    if not goal:
        # Staging stub: no EF goal — record virtual withdraw on params only.
        return {
            "kind": "withdraw_emergency_fund",
            "user_id": user_id,
            "amount": amount,
            "stub": True,
            "note": "No emergency_fund goal — recorded without balance mutation.",
            "created_by_act_id": act_id,
            "mode": MODE_C,
            "policy_version": POLICY_COOL_OFF,
            "created_at": _now_iso(),
            "_undo_snapshot": {"action": "noop_withdraw"},
        }
    prev_amount = float(goal.current_amount)
    new_amount = max(0.0, prev_amount - amount)
    from welora.goal_emergency_fund import EmergencyFundGoal

    # apply_progress rejects status==completed — soft-reopen before set_amount.
    soft = EmergencyFundGoal(
        goal_id=goal.goal_id,
        user_id=goal.user_id,
        type=goal.type,
        title=goal.title,
        status="active",
        principle_keys=list(goal.principle_keys),
        target_amount=goal.target_amount,
        target_unit=goal.target_unit,
        months_of_expense=goal.months_of_expense,
        target_date=goal.target_date,
        current_amount=goal.current_amount,
        percent=goal.percent,
        last_updated_at=goal.last_updated_at,
        safety_gate_relevant=goal.safety_gate_relevant,
        monthly_contribution=goal.monthly_contribution,
        plan_method=goal.plan_method,
        linked_from_onboarding=goal.linked_from_onboarding,
        essential_expense_monthly=goal.essential_expense_monthly,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )
    goals_api.STORE.save(soft)
    updated = goals_api.STORE.record_progress(goal.goal_id, set_amount=new_amount)

    out = {
        "kind": "withdraw_emergency_fund",
        "user_id": user_id,
        "goal_id": updated.goal_id,
        "amount": amount,
        "previous_amount": prev_amount,
        "current_amount": updated.current_amount,
        "months_covered": updated.months_covered,
        "created_by_act_id": act_id,
        "mode": MODE_C,
        "policy_version": POLICY_COOL_OFF,
        "internal_only": True,
        "created_at": _now_iso(),
        "_undo_snapshot": {
            "action": "restore_efund_amount",
            "goal_id": updated.goal_id,
            "prev_amount": prev_amount,
        },
    }
    return out


def _write_estate(user_id: str, params: dict, act_id: str) -> dict[str, Any]:
    prev = _ESTATE.get(user_id)
    rec = {
        "user_id": user_id,
        "kind": "estate_checklist",
        "checklist_only": True,
        "no_legal_will": True,
        "items": list(params.get("items") or []),
        "status": "open",
        "created_by_act_id": act_id,
        "mode": MODE_C,
        "policy_version": POLICY_VERSION,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    _ESTATE[user_id] = rec
    _persist_estate(user_id, rec)
    out = dict(rec)
    out["_undo_snapshot"] = {"action": "restore_estate", "prev": prev}
    return out


def undo_act(
    *,
    user_id: str,
    act_id: str,
    undo_token: str,
) -> tuple[int, dict[str, Any]]:
    meta = _UNDO.get(act_id)
    if not meta or meta.get("user_id") != user_id:
        return 404, {"error": "act not found"}
    if meta.get("undo_token") != undo_token:
        return 403, {"error": "invalid undo token"}
    until = datetime.fromisoformat(meta["undo_until"])
    if _now() > until:
        return 403, {
            "error": "undo window expired",
            "hint": f"Hoàn tác chỉ trong {UNDO_HOURS} giờ.",
            "undo_until": meta["undo_until"],
        }
    snap = meta.get("snapshot") or {}
    action = snap.get("action")
    if action == "delete" and snap.get("envelope_id"):
        eid = snap["envelope_id"]
        _ENVELOPES.pop(eid, None)
        ids = _ENVELOPES_BY_USER.get(user_id) or []
        _ENVELOPES_BY_USER[user_id] = [x for x in ids if x != eid]
        _persist_delete_envelope(eid, user_id)
    elif action == "restore_lock" and snap.get("envelope_id"):
        eid = snap["envelope_id"]
        if eid in _ENVELOPES:
            prev = snap.get("prev") or {}
            _ENVELOPES[eid]["locked"] = bool(prev.get("locked"))
            _ENVELOPES[eid]["cross_take_forbidden"] = bool(prev.get("cross_take_forbidden"))
            _ENVELOPES[eid]["updated_at"] = _now_iso()
            _persist_envelope(_ENVELOPES[eid])
    elif action == "delete" and snap.get("reminder_id"):
        rid = snap["reminder_id"]
        _REMINDERS.pop(rid, None)
        ids = _REMINDERS_BY_USER.get(user_id) or []
        _REMINDERS_BY_USER[user_id] = [x for x in ids if x != rid]
        _persist_delete_reminder(rid, user_id)
    elif action == "restore_ceiling" and snap.get("envelope_id"):
        eid = snap["envelope_id"]
        if eid in _ENVELOPES:
            prev = snap.get("prev") or {}
            _ENVELOPES[eid]["target_amount"] = float(prev.get("target_amount") or 0)
            _ENVELOPES[eid]["updated_at"] = _now_iso()
            _persist_envelope(_ENVELOPES[eid])
    elif action == "restore_estate":
        prev = snap.get("prev")
        if prev is None:
            _ESTATE.pop(user_id, None)
            _persist_estate(user_id, None)
        else:
            _ESTATE[user_id] = prev
            _persist_estate(user_id, prev)
    elif action == "restore_efund_amount" and snap.get("goal_id"):
        from welora import goals_api
        from welora.goal_emergency_fund import EmergencyFundGoal

        gid = snap["goal_id"]
        prev_amt = float(snap.get("prev_amount") or 0)
        goal = goals_api.STORE.get(gid)
        if goal:
            soft = EmergencyFundGoal(
                goal_id=goal.goal_id,
                user_id=goal.user_id,
                type=goal.type,
                title=goal.title,
                status="active" if prev_amt < goal.target_amount else goal.status,
                principle_keys=list(goal.principle_keys),
                target_amount=goal.target_amount,
                target_unit=goal.target_unit,
                months_of_expense=goal.months_of_expense,
                target_date=goal.target_date,
                current_amount=goal.current_amount,
                percent=goal.percent,
                last_updated_at=goal.last_updated_at,
                safety_gate_relevant=goal.safety_gate_relevant,
                monthly_contribution=goal.monthly_contribution,
                plan_method=goal.plan_method,
                linked_from_onboarding=goal.linked_from_onboarding,
                essential_expense_monthly=goal.essential_expense_monthly,
                created_at=goal.created_at,
                updated_at=goal.updated_at,
            )
            goals_api.STORE.save(soft)
            goals_api.STORE.record_progress(gid, set_amount=prev_amt)
    elif action == "noop_withdraw":
        pass
    else:
        return 400, {
            "error": "undo not supported for this act",
            "note": "Limitation: unknown snapshot.",
        }

    meta["undone_at"] = _now_iso()
    _persist_undo(meta)
    # Mark linked proposal as undone (DoD state) when present.
    for _p in _PROPOSALS.values():
        if _p.get("act_id") == act_id:
            _p["status"] = "undone"
            _p["undone_at"] = meta["undone_at"]
            _persist_proposal(_p)
            break
    undo_log = {
        "id": str(uuid.uuid4()),
        "act_id": act_id,
        "user_id": user_id,
        "mode": MODE_C,
        "policy_version": POLICY_VERSION,
        "event": "undo",
        "timestamp": _now_iso(),
    }
    _ACT_LOGS.append(undo_log)
    _persist_act_log(undo_log)
    return 200, {
        "ok": True,
        "undone": True,
        "act_id": act_id,
        "mode": MODE_C,
        "policy_version": POLICY_VERSION,
        "disclaimer": MODE_C_DISCLAIMER,
    }


def deny_cross_take(
    *,
    user_id: str,
    from_envelope_id: str,
    to_envelope_id: str,
    amount: float = 0,
) -> tuple[int, dict[str, Any]]:
    """If either envelope forbids cross-take, DENY transfer."""
    a = _ENVELOPES.get(from_envelope_id)
    b = _ENVELOPES.get(to_envelope_id)
    if not a or not b or a.get("user_id") != user_id or b.get("user_id") != user_id:
        return 404, {"error": "envelope not found"}
    if a.get("cross_take_forbidden") or a.get("locked") or b.get("cross_take_forbidden") or b.get("locked"):
        return 200, {
            "ok": False,
            "guardrail_result": "deny",
            "rule": "L-ENVELOPE-P4-stub",
            "policy_version": POLICY_VERSION,
            "reply": "Cấm lấy chéo giữa phong bì đã khóa.",
            "note": CROSS_TAKE_NOTE,
            "cross_take_supported": CROSS_TAKE_SUPPORTED,
        }
    # MVP: no silent transfer — even unlocked requires future Act; document as stub allow-path unused.
    return 200, {
        "ok": False,
        "guardrail_result": "deny",
        "rule": "L-ENVELOPE-P4-stub",
        "policy_version": POLICY_VERSION,
        "reply": "Chuyển chéo phong bì chưa mở trong MVP Mode C (chỉ khóa / tạo).",
        "note": CROSS_TAKE_NOTE,
        "amount": amount,
    }


def list_envelopes(user_id: str) -> tuple[int, dict[str, Any]]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    items = [_ENVELOPES[i] for i in (_ENVELOPES_BY_USER.get(user_id) or []) if i in _ENVELOPES]
    return 200, {"items": items, "policy_version": POLICY_VERSION}


def list_reminders(user_id: str) -> tuple[int, dict[str, Any]]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    items = [_REMINDERS[i] for i in (_REMINDERS_BY_USER.get(user_id) or []) if i in _REMINDERS]
    return 200, {"items": items, "policy_version": POLICY_VERSION}


def get_estate_checklist(user_id: str) -> tuple[int, dict[str, Any]]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    return 200, {
        "checklist": _ESTATE.get(user_id),
        "policy_version": POLICY_VERSION,
        "no_legal_will": True,
    }


def _apply_act_write(
    *,
    user_id: str,
    act_kind: str,
    params: dict[str, Any],
    act_id: str,
) -> dict[str, Any]:
    if act_kind == ACT_CREATE_ENVELOPE:
        return _write_envelope(user_id, params, act_id)
    if act_kind == ACT_LOCK_ENVELOPE:
        return _write_lock(user_id, params, act_id)
    if act_kind == ACT_CHANGE_CEILING:
        return _write_ceiling(user_id, params, act_id)
    if act_kind == ACT_BH_REMINDER:
        return _write_reminder(user_id, params, act_id)
    if act_kind == ACT_ESTATE_CHECKLIST:
        return _write_estate(user_id, params, act_id)
    if act_kind == ACT_WITHDRAW_EFUND:
        return _write_withdraw_efund(user_id, params, act_id)
    raise ValueError(f"unsupported act_kind: {act_kind}")


def companion_confirm_act(
    *,
    companion_user_id: str,
    proposal_id: str,
    confirm: bool = True,
) -> tuple[int, dict[str, Any]]:
    """Second-person confirm for pending_dual. Server verifies companion link.

    Never trust client flags (e.g. dual_ok / skip_dual / is_companion).
    """
    if not companion_user_id:
        return 400, {"error": "companion_user_id is required"}
    if not confirm:
        return 400, {
            "error": "confirm required",
            "hint": "Người đồng hành phải xác nhận (G1) trước khi ghi OS.",
            "mode": MODE_C,
            "policy_version": POLICY_DUAL_CONTROL,
        }

    prop = _PROPOSALS.get(proposal_id)
    if not prop:
        return 404, {"error": "proposal not found"}
    if prop.get("status") == "confirmed":
        return 409, {"error": "proposal already confirmed", "act_id": prop.get("act_id")}
    if prop.get("status") == "cancelled":
        return 409, {"error": "proposal cancelled"}
    if prop.get("status") != "pending_dual":
        return 409, {
            "error": "proposal not pending_dual",
            "status": prop.get("status"),
            "policy_version": POLICY_DUAL_CONTROL,
        }

    primary_id = str(prop.get("user_id") or "")
    expected = str(prop.get("companion_user_id") or "")
    link = get_companion(primary_id)
    linked = str((link or {}).get("companion_user_id") or "")

    # Fail-closed anti-spoof: caller must be the linked companion on the proposal
    # AND still linked on the primary's companion store (server-side).
    if (
        not expected
        or companion_user_id != expected
        or not linked
        or companion_user_id != linked
    ):
        return 403, {
            "error": "companion_mismatch",
            "rule": POLICY_DUAL_CONTROL,
            "policy_version": POLICY_DUAL_CONTROL,
            "mode": MODE_C,
            "reply": (
                "Xác nhận đồng kiểm thất bại — user không phải người đồng hành "
                "đã gắn (L-DUAL-CONTROL). Không ghi OS."
            ),
            "guardrail_result": "deny",
        }

    # Re-check primary gate server-side (align #184 fail-closed).
    gate, conf = resolve_server_gate_confidence(primary_id)
    ok, reason = _gate_ok(gate, conf)
    if not ok:
        return 403, {
            "error": reason,
            "mode": MODE_C,
            "policy_version": POLICY_DUAL_CONTROL,
            "rule": POLICY_DUAL_CONTROL,
        }

    act_kind = prop["act_kind"]
    params = dict(prop.get("params") or {})

    # Policy router before OS write (companion path verified)
    decision = run_os_policy(
        user_id=primary_id,
        act=build_policy_act(
            act_kind=act_kind,
            params=params,
            phase="confirm",
            status="pending_dual",
            cool_off=prop.get("cool_off"),
            cool_off_escalated_to_dual=bool(prop.get("cool_off_escalated_to_dual")),
            dual_control_required=True,
        ),
        os_state=build_policy_os_state(
            user_id=primary_id,
            gate_status=gate,
            answer_confidence=conf,
            companion=link,
            proposal_status="pending_dual",
            companion_confirming=True,
            companion_verified=True,
            cool_off=prop.get("cool_off"),
            extra={"phase": "confirm"},
        ),
    )
    _append_policy_log(
        user_id=primary_id,
        decision=decision,
        act_kind=act_kind,
        event="companion_confirm_evaluate",
        extra={
            "proposal_id": proposal_id,
            "companion_user_id": companion_user_id,
        },
    )
    if decision.verdict in ("DENY", "ESCALATE"):
        return 403, {
            "ok": False,
            "error": "policy_blocked",
            "mode": MODE_C,
            "policy_version": decision.policy_version,
            "rule": decision.rule_id,
            "rule_id": decision.rule_id,
            "reply": decision.message_vi,
            "guardrail_result": "deny",
            "escalate_flag": bool(decision.escalate_flag),
            "persona": decision.persona,
            "policy_log": decision.to_log(),
        }

    act_id = str(uuid.uuid4())
    try:
        applied = _apply_act_write(
            user_id=primary_id,
            act_kind=act_kind,
            params=params,
            act_id=act_id,
        )
    except ValueError as e:
        return 400, {"error": str(e)}

    undo_until = (_now() + timedelta(hours=UNDO_HOURS)).isoformat()
    undo_token = str(uuid.uuid4())
    _UNDO[act_id] = {
        "act_id": act_id,
        "user_id": primary_id,
        "companion_user_id": companion_user_id,
        "act_kind": act_kind,
        "undo_token": undo_token,
        "undo_until": undo_until,
        "snapshot": applied.get("_undo_snapshot"),
        "created_at": _now_iso(),
    }
    _persist_undo(_UNDO[act_id])
    applied.pop("_undo_snapshot", None)

    prop["status"] = "confirmed"
    prop["act_id"] = act_id
    prop["confirmed_at"] = _now_iso()
    prop["confirmed_by_companion"] = companion_user_id
    _persist_proposal(prop)

    log_entry = {
        "id": str(uuid.uuid4()),
        "act_id": act_id,
        "user_id": primary_id,
        "companion_user_id": companion_user_id,
        "mode": MODE_C,
        "policy_version": POLICY_DUAL_CONTROL,
        "persona": get_persona(primary_id),
        "rule": POLICY_DUAL_CONTROL,
        "rule_id": POLICY_DUAL_CONTROL,
        "tools_called": list(decision.tools_called or []),
        "escalate_flag": False,
        "act_kind": act_kind,
        "proposal_id": proposal_id,
        "guardrail_result": "allow",
        "dual_control": True,
        "timestamp": _now_iso(),
    }
    _ACT_LOGS.append(log_entry)
    _persist_act_log(log_entry)

    return 200, {
        "ok": True,
        "mode": MODE_C,
        "mode_chip": MODE_C_CHIP,
        "disclaimer": MODE_C_DISCLAIMER,
        "policy_version": POLICY_DUAL_CONTROL,
        "rule": POLICY_DUAL_CONTROL,
        "act_id": act_id,
        "act_kind": act_kind,
        "result": applied,
        "user_id": primary_id,
        "companion_user_id": companion_user_id,
        "undo": {
            "token": undo_token,
            "until": undo_until,
            "hours": UNDO_HOURS,
        },
        "log": log_entry,
        "reply": "Đồng kiểm đủ 2 người — đã ghi vào WeloraOS.",
    }


def cancel_pending_dual(
    *,
    user_id: str,
    proposal_id: str,
) -> tuple[int, dict[str, Any]]:
    """Primary cancels a pending_dual proposal (no OS write)."""
    if not user_id:
        return 400, {"error": "user_id is required"}
    prop = _PROPOSALS.get(proposal_id)
    if not prop or prop.get("user_id") != user_id:
        return 404, {"error": "proposal not found"}
    if prop.get("status") != "pending_dual":
        return 409, {
            "error": "not pending_dual",
            "status": prop.get("status"),
        }
    prop["status"] = "cancelled"
    prop["cancelled_at"] = _now_iso()
    _persist_proposal(prop)
    cancel_log = {
        "id": str(uuid.uuid4()),
        "proposal_id": proposal_id,
        "user_id": user_id,
        "companion_user_id": prop.get("companion_user_id"),
        "mode": MODE_C,
        "policy_version": POLICY_DUAL_CONTROL,
        "event": "cancel_pending_dual",
        "timestamp": _now_iso(),
    }
    _ACT_LOGS.append(cancel_log)
    _persist_act_log(cancel_log)
    return 200, {
        "ok": True,
        "cancelled": True,
        "proposal_id": proposal_id,
        "mode": MODE_C,
        "policy_version": POLICY_DUAL_CONTROL,
        "reply": "Đã hủy đề xuất đồng kiểm — không ghi OS.",
    }


def list_pending_dual(user_id: str) -> tuple[int, dict[str, Any]]:
    """Pending dual proposals where user is primary or companion."""
    if not user_id:
        return 400, {"error": "user_id is required"}
    items = []
    for prop in _PROPOSALS.values():
        if prop.get("status") != "pending_dual":
            continue
        if prop.get("user_id") == user_id or prop.get("companion_user_id") == user_id:
            items.append(dict(prop))
    items.sort(key=lambda x: x.get("created_at") or "")
    return 200, {
        "items": items,
        "policy_version": POLICY_DUAL_CONTROL,
    }


def try_mode_c_from_chat(
    *,
    user_id: str,
    message: str,
    gate_status: str,
    answer_confidence: float,
) -> Optional[dict[str, Any]]:
    """
    Chat hook: if message is Mode C / external-deny intent, return overlay fields.
    None → caller continues normal advisory path.
    """
    if detect_external_deny(message) or detect_mode_c_act(message):
        _code, body = propose_act(
            user_id=user_id,
            message=message,
            gate_status=gate_status,
            answer_confidence=answer_confidence,
        )
        return body
    return None
