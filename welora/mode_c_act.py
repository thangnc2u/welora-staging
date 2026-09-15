"""
Mode C — Act nội bộ OS (MVP).

Founder 15/09: Mode C Act = still G1 (user confirm) ≠ L2 Action Tools.
Source: phụ lục PRD trụ 4 §3.3 Mode C.

- ALLOW: tạo phong bì / quỹ tiết kiệm nội bộ, khóa lấy chéo (stub OK),
  nhắc BHYT/BHTN/đóng bù (schedule only), checklist di sản (no legal will).
- DENY: ticker / ILP mới / chuyển tiền ngân hàng / L2 external money.
- Gate: safety-gate passed + answer_confidence ≥ CONFIDENCE_THRESHOLD (0.80).
- Confirm before write · undo 24h · log mode + policy_version (L-* stub additive).
- Does NOT replace Hard Deny R01–R09 / Pre-Rule order / TARGET_MONTHS / CORE-*.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from welora.agent import CONFIDENCE_THRESHOLD

# Additive L-* stub — never replaces Hard Deny R01–R09.
POLICY_VERSION = "L-stub-1.0"
MODE_C = "C"
MODE_C_CHIP = "Mode C · Hành động"
MODE_C_DISCLAIMER = "Hành động trên OS — có thể hoàn tác trong 24 giờ"
UNDO_HOURS = 24

ACT_CREATE_ENVELOPE = "create_envelope"
ACT_LOCK_ENVELOPE = "lock_envelope"
ACT_BH_REMINDER = "schedule_bh_reminder"
ACT_ESTATE_CHECKLIST = "open_estate_checklist"

ALLOWED_ACTS = frozenset(
    {
        ACT_CREATE_ENVELOPE,
        ACT_LOCK_ENVELOPE,
        ACT_BH_REMINDER,
        ACT_ESTATE_CHECKLIST,
    }
)

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


def reset_mode_c_store() -> None:
    _ENVELOPES.clear()
    _ENVELOPES_BY_USER.clear()
    _REMINDERS.clear()
    _REMINDERS_BY_USER.clear()
    _ESTATE.clear()
    _PROPOSALS.clear()
    _ACT_LOGS.clear()
    _UNDO.clear()


def _now() -> datetime:
    return datetime.now(timezone.utc)


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

    if any(k in n for k in lock_keys):
        return ACT_LOCK_ENVELOPE
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


def _proposal_payload(
    *,
    proposal_id: str,
    user_id: str,
    act_kind: str,
    summary: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    return {
        "proposal_id": proposal_id,
        "user_id": user_id,
        "mode": MODE_C,
        "mode_chip": MODE_C_CHIP,
        "disclaimer": MODE_C_DISCLAIMER,
        "policy_version": POLICY_VERSION,
        "act_kind": act_kind,
        "summary": summary,
        "params": params,
        "needs_confirm": True,
        "confirm_hint": "Xác nhận để ghi vào WeloraOS. Có thể hoàn tác trong 24 giờ.",
        "status": "proposed",
        "created_at": _now_iso(),
    }


def propose_act(
    *,
    user_id: str,
    message: str,
    gate_status: str,
    answer_confidence: float,
    params: Optional[dict[str, Any]] = None,
) -> tuple[int, dict[str, Any]]:
    """Propose a Mode C act (no write). External intents → DENY."""
    if not user_id:
        return 400, {"error": "user_id is required"}

    ext = detect_external_deny(message)
    if ext:
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

    ok, reason = _gate_ok(gate_status, answer_confidence)
    if not ok:
        return 200, {
            "ok": False,
            "mode": MODE_C,
            "mode_chip": MODE_C_CHIP,
            "disclaimer": MODE_C_DISCLAIMER,
            "policy_version": POLICY_VERSION,
            "guardrail_result": "deny",
            "reply": reason,
            "needs_confirm": False,
            "act_proposal": None,
            "gate_blocked": True,
        }

    params = dict(params or {})
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
    elif act_kind == ACT_BH_REMINDER:
        kind = params.get("reminder_kind") or _detect_bh_kind(message)
        params = {
            "reminder_kind": kind,
            "schedule_only": True,
            "no_submit_forms": True,
            "no_forge_signature": True,
        }
        summary = f"Đặt nhắc {kind} (chỉ lịch — không nộp hồ sơ / không giả chữ ký)"
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

    pid = str(uuid.uuid4())
    prop = _proposal_payload(
        proposal_id=pid,
        user_id=user_id,
        act_kind=act_kind,
        summary=summary,
        params=params,
    )
    _PROPOSALS[pid] = prop
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
        "reply": reply,
        "needs_confirm": True,
        "act_proposal": prop,
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


def confirm_act(
    *,
    user_id: str,
    proposal_id: str,
    confirm: bool,
    gate_status: str = "passed",
    answer_confidence: float = 0.90,
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

    ok, reason = _gate_ok(gate_status, answer_confidence)
    if not ok:
        return 403, {
            "error": reason,
            "mode": MODE_C,
            "policy_version": POLICY_VERSION,
        }

    act_kind = prop["act_kind"]
    params = dict(prop.get("params") or {})
    act_id = str(uuid.uuid4())
    applied: dict[str, Any]

    if act_kind == ACT_CREATE_ENVELOPE:
        applied = _write_envelope(user_id, params, act_id)
    elif act_kind == ACT_LOCK_ENVELOPE:
        applied = _write_lock(user_id, params, act_id)
    elif act_kind == ACT_BH_REMINDER:
        applied = _write_reminder(user_id, params, act_id)
    elif act_kind == ACT_ESTATE_CHECKLIST:
        applied = _write_estate(user_id, params, act_id)
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
    applied.pop("_undo_snapshot", None)

    prop["status"] = "confirmed"
    prop["act_id"] = act_id
    prop["confirmed_at"] = _now_iso()

    log_entry = {
        "id": str(uuid.uuid4()),
        "act_id": act_id,
        "user_id": user_id,
        "mode": MODE_C,
        "policy_version": POLICY_VERSION,
        "act_kind": act_kind,
        "proposal_id": proposal_id,
        "guardrail_result": "allow",
        "timestamp": _now_iso(),
    }
    _ACT_LOGS.append(log_entry)

    return 200, {
        "ok": True,
        "mode": MODE_C,
        "mode_chip": MODE_C_CHIP,
        "disclaimer": MODE_C_DISCLAIMER,
        "policy_version": POLICY_VERSION,
        "act_id": act_id,
        "act_kind": act_kind,
        "result": applied,
        "undo": {
            "token": undo_token,
            "until": undo_until,
            "hours": UNDO_HOURS,
        },
        "log": log_entry,
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
    out = dict(_ENVELOPES[eid])
    out["note"] = CROSS_TAKE_NOTE
    out["cross_take_supported"] = CROSS_TAKE_SUPPORTED
    out["_undo_snapshot"] = {"envelope_id": eid, "action": "restore_lock", "prev": prev}
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
    out = dict(rec)
    out["_undo_snapshot"] = {"reminder_id": rid, "action": "delete"}
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
    elif action == "restore_lock" and snap.get("envelope_id"):
        eid = snap["envelope_id"]
        if eid in _ENVELOPES:
            prev = snap.get("prev") or {}
            _ENVELOPES[eid]["locked"] = bool(prev.get("locked"))
            _ENVELOPES[eid]["cross_take_forbidden"] = bool(prev.get("cross_take_forbidden"))
            _ENVELOPES[eid]["updated_at"] = _now_iso()
    elif action == "delete" and snap.get("reminder_id"):
        rid = snap["reminder_id"]
        _REMINDERS.pop(rid, None)
        ids = _REMINDERS_BY_USER.get(user_id) or []
        _REMINDERS_BY_USER[user_id] = [x for x in ids if x != rid]
    elif action == "restore_estate":
        prev = snap.get("prev")
        if prev is None:
            _ESTATE.pop(user_id, None)
        else:
            _ESTATE[user_id] = prev
    else:
        return 400, {
            "error": "undo not supported for this act",
            "note": "Limitation: unknown snapshot.",
        }

    meta["undone_at"] = _now_iso()
    _ACT_LOGS.append(
        {
            "id": str(uuid.uuid4()),
            "act_id": act_id,
            "user_id": user_id,
            "mode": MODE_C,
            "policy_version": POLICY_VERSION,
            "event": "undo",
            "timestamp": _now_iso(),
        }
    )
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
