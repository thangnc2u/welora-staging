"""
P2 OS — Full L-* policy router (OS-scope).

evaluate(act, persona, os_state) → ALLOW | DENY | ESCALATE
plus rule_id, policy_version, Vietnamese message.

Fixed registration order (first DENY/ESCALATE wins; ALLOW falls through):
  L-EMERGENCY, L-PILLAR-ORDER, L-PROTECT-CAP, L-PROTECT-COVER, L-RETIRE-FLOOR,
  L-ENVELOPE-P3, L-ENVELOPE-P4, L-NO-ILP-NEW, L-ILP-AUDIT, L-BHXH-TOPUP,
  L-ESTATE, L-NO-TICKER, L-NO-SPEC, L-COOL-OFF, L-DUAL-CONTROL, L-FIDUCIARY

Does NOT replace Hard Deny R01–R09 / TARGET_MONTHS / CORE-* / Pre-Rule.
No bank/securities L2 Action Tools · no persist DB.
Persona floors: P1–P5 stub in Mode C; P6 specialized in L-EMERGENCY /
L-DUAL-CONTROL / L-ESTATE / L-NO-ILP-NEW / L-COOL-OFF (child companion, no self cool-off).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional

Verdict = Literal["ALLOW", "DENY", "ESCALATE"]

POLICY_VERSION = "L-router-1.0"

RULE_ORDER: tuple[str, ...] = (
    "L-EMERGENCY",
    "L-PILLAR-ORDER",
    "L-PROTECT-CAP",
    "L-PROTECT-COVER",
    "L-RETIRE-FLOOR",
    "L-ENVELOPE-P3",
    "L-ENVELOPE-P4",
    "L-NO-ILP-NEW",
    "L-ILP-AUDIT",
    "L-BHXH-TOPUP",
    "L-ESTATE",
    "L-NO-TICKER",
    "L-NO-SPEC",
    "L-COOL-OFF",
    "L-DUAL-CONTROL",
    "L-FIDUCIARY",
)

# Messages (VI) — surface rule code on DENY/ESCALATE.
MSG: dict[str, str] = {
    "L-EMERGENCY": (
        "L-EMERGENCY: Cấm dùng quỹ khẩn cấp để đầu tư / đầu cơ. "
        "Quỹ KH chỉ cho rủi ro bất ngờ — không ghi OS."
    ),
    "L-EMERGENCY-P6": (
        "L-EMERGENCY (P6): Sàn quỹ KH 6–12 tháng (24 tháng nếu y tế). "
        "Thiếu số dư — từ chối an toàn (fail-closed) — không ghi OS."
    ),
    "L-PILLAR-ORDER": (
        "L-PILLAR-ORDER: Sai thứ tự trụ — An Toàn trước Tăng trưởng/Tự do. "
        "Không bỏ qua trụ khi Cổng chưa đạt — không ghi OS."
    ),
    "L-PROTECT-CAP": (
        "L-PROTECT-CAP: Phí bảo vệ vượt trần cho phép theo hồ sơ. "
        "Giảm mức / tách lớp trước khi ghi OS."
    ),
    "L-PROTECT-COVER": (
        "L-PROTECT-COVER: Cấm hủy lớp bảo vệ bắt buộc khi chưa có lớp thay thế. "
        "Không ghi OS."
    ),
    "L-RETIRE-FLOOR": (
        "L-RETIRE-FLOOR: Cấm rút dưới sàn hưu trí (persona floor stub). "
        "Không ghi OS."
    ),
    "L-ENVELOPE-P3": (
        "L-ENVELOPE-P3: Vi phạm ràng buộc phong bì P3 (trần / mục đích). "
        "Không ghi OS."
    ),
    "L-ENVELOPE-P4": (
        "L-ENVELOPE-P4: Cấm lấy chéo giữa phong bì đã khóa. Không ghi OS."
    ),
    "L-NO-ILP-NEW": (
        "L-NO-ILP-NEW: Cấm đề xuất / tạo lead ILP mới. Agent không nộp hồ sơ BH."
    ),
    "L-ILP-AUDIT": (
        "L-ILP-AUDIT: Chỉ cho phép rà soát ILP hiện có — cấm nộp hồ sơ / giả chữ ký."
    ),
    "L-BHXH-TOPUP": (
        "L-BHXH-TOPUP: Chỉ đặt lịch nhắc đóng bù — cấm nộp hồ sơ / giả chữ ký BHXH."
    ),
    "L-ESTATE": (
        "L-ESTATE: Chỉ checklist di sản — cấm soạn di chúc pháp lý / giả chữ ký."
    ),
    "L-NO-TICKER": (
        "L-NO-TICKER: Cấm đặt lệnh / khuyến nghị mua mã CK cụ thể (Mode C ≠ L2)."
    ),
    "L-NO-SPEC": (
        "L-NO-SPEC: Cấm khuyến nghị đầu cơ / all-in / đòn bẩy ngoài OS. Không ghi OS."
    ),
    "L-COOL-OFF": (
        "L-COOL-OFF: Chạm quỹ KH (dưới sàn persona hoặc ≥20%) — "
        "cần lý do + chờ 24 giờ (pending_cool_off). Không ghi OS ngay."
    ),
    "L-DUAL-CONTROL": (
        "L-DUAL-CONTROL: Cần người đồng hành xác nhận (đồng kiểm 2 người). "
        "Thiếu companion hoặc chưa dual-confirm — không ghi OS."
    ),
    "L-FIDUCIARY": (
        "L-FIDUCIARY: Cấm chuyển tiền ra ngân hàng / đối tác ngoài OS "
        "(không phải L2 Action Tools)."
    ),
}

PROTECT_CAP_MAX_PCT = 0.15  # stub: premium / income
DUAL_CONTROL_ACTS = frozenset(
    {
        "lock_envelope",
        "change_envelope_ceiling",
        "open_estate_checklist",
    }
)

# P6: money + estate + create_envelope always dual (Mode C routes via L-DUAL-CONTROL).
P6_DUAL_CONTROL_ACTS = frozenset(
    {
        "create_envelope",
        "lock_envelope",
        "change_envelope_ceiling",
        "open_estate_checklist",
        "withdraw_emergency_fund",
    }
)
# Dual-bound money/estate acts for P6 (create + withdraw included).
# "Large act missing checklist" gate uses lock/ceiling + explicit large_act flag
# so cool-off/withdraw dual paths (#187) stay coherent.
P6_LARGE_ACTS = frozenset(
    {
        "lock_envelope",
        "change_envelope_ceiling",
    }
)

# P6 L-EMERGENCY floors (TARGET_MONTHS=3 stays Safety Gate HARD — separate).
P6_EMERGENCY_FLOOR_MONTHS_MIN = 6   # band 6–12 months
P6_EMERGENCY_FLOOR_MONTHS_MAX = 12
P6_MEDICAL_FLOOR_MONTHS = 24

CHILD_COMPANION_ROLES = frozenset({"child", "con", "son", "daughter", "con_ruot"})

SIDE_PENDING_COOL_OFF = "pending_cool_off"
SIDE_PENDING_DUAL = "pending_dual"


@dataclass
class PolicyDecision:
    verdict: Verdict
    rule_id: Optional[str]
    policy_version: str
    message_vi: str
    escalate_flag: bool = False
    side_effect: Optional[str] = None
    tools_called: list[str] = field(default_factory=list)
    persona: Optional[str] = None
    mode: str = "C"
    meta: dict[str, Any] = field(default_factory=dict)

    def to_log(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "policy_version": self.policy_version,
            "persona": self.persona,
            "rule_id": self.rule_id,
            "tools_called": list(self.tools_called),
            "escalate_flag": bool(self.escalate_flag),
            "verdict": self.verdict,
            "side_effect": self.side_effect,
        }


def _decision(
    verdict: Verdict,
    rule_id: Optional[str],
    *,
    persona: Optional[str] = None,
    message_vi: Optional[str] = None,
    side_effect: Optional[str] = None,
    tools_called: Optional[list[str]] = None,
    meta: Optional[dict[str, Any]] = None,
    mode: str = "C",
) -> PolicyDecision:
    escalate = verdict == "ESCALATE"
    msg = message_vi
    if msg is None and rule_id:
        msg = MSG.get(rule_id, f"{rule_id}: từ chối theo policy OS.")
    if msg is None:
        msg = "ALLOW — không có rule L-* chặn."
    # policy_version: specific rule code when blocking/escalating; else router version
    if verdict in ("DENY", "ESCALATE") and rule_id:
        pv = rule_id
    else:
        pv = POLICY_VERSION
    return PolicyDecision(
        verdict=verdict,
        rule_id=rule_id,
        policy_version=pv,
        message_vi=msg,
        escalate_flag=escalate,
        side_effect=side_effect,
        tools_called=list(tools_called or []),
        persona=persona,
        mode=mode,
        meta=dict(meta or {}),
    )


def _norm(s: str) -> str:
    return (s or "").lower().strip()


def _act_dict(act: Any) -> dict[str, Any]:
    if isinstance(act, dict):
        return act
    if hasattr(act, "__dict__"):
        return dict(vars(act))
    return {"kind": str(act)}


def _os_dict(os_state: Any) -> dict[str, Any]:
    if isinstance(os_state, dict):
        return os_state
    if hasattr(os_state, "__dict__"):
        return dict(vars(os_state))
    return {}


def _persona(persona: Any, os_state: dict[str, Any]) -> str:
    if persona:
        return str(persona).upper().strip()
    p = os_state.get("persona") or "P1"
    return str(p).upper().strip()


def _intent(act: dict[str, Any], os_state: dict[str, Any]) -> Optional[str]:
    """Normalize external / shape intent for deny rules."""
    for key in ("intent", "external_intent", "deny_intent"):
        v = act.get(key) or os_state.get(key)
        if v:
            return str(v)
    kind = str(act.get("kind") or act.get("act_kind") or "")
    if kind in ("buy_ticker", "ilp_new", "bank_transfer", "speculate"):
        return kind
    msg = _norm(str(act.get("message") or os_state.get("message") or ""))
    if not msg:
        return None
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
    spec_keys = [
        "all-in",
        "all in",
        "đầu cơ",
        "margin",
        "đòn bẩy",
        "short bán",
        "phóng đại lợi nhuận",
        "chắc lời mã",
    ]
    if any(k in msg for k in ticker_keys):
        return "buy_ticker"
    if any(k in msg for k in ilp_keys):
        return "ilp_new"
    if any(k in msg for k in bank_keys):
        return "bank_transfer"
    if any(k in msg for k in spec_keys):
        return "speculate"
    return None



def _companion_record(act: dict[str, Any], os_state: dict[str, Any]) -> Any:
    return os_state.get("companion") or act.get("companion")


def _has_any_companion(act: dict[str, Any], os_state: dict[str, Any]) -> bool:
    companion = _companion_record(act, os_state)
    if not companion:
        return False
    if isinstance(companion, dict):
        return bool(companion.get("companion_user_id"))
    return bool(str(companion).strip())


def _has_child_companion(act: dict[str, Any], os_state: dict[str, Any]) -> bool:
    """P6 requires ≥1 child companion (role/relation = child/con)."""
    companion = _companion_record(act, os_state)
    if not isinstance(companion, dict) or not companion.get("companion_user_id"):
        return False
    role = str(
        companion.get("role")
        or companion.get("relation")
        or companion.get("companion_role")
        or ""
    ).lower().strip()
    return role in CHILD_COMPANION_ROLES


def _is_medical_purpose(act: dict[str, Any], os_state: dict[str, Any]) -> bool:
    params = dict(act.get("params") or {})
    purpose = str(
        params.get("purpose")
        or act.get("purpose")
        or os_state.get("purpose")
        or ""
    ).lower()
    if purpose in ("medical", "y_te", "y tế", "healthcare", "health"):
        return True
    if bool(params.get("medical") or act.get("medical") or os_state.get("medical")):
        return True
    msg = _norm(str(act.get("message") or os_state.get("message") or ""))
    medical_keys = (
        "y tế",
        "yte",
        "viện phí",
        "chữa bệnh",
        "khám bệnh",
        "medical",
        "hospital",
        "bệnh viện",
    )
    return any(k in msg for k in medical_keys)


def _months_covered_value(act: dict[str, Any], os_state: dict[str, Any]) -> Optional[float]:
    """Prefer post-act months; fall back to current EF coverage in os_state/params."""
    params = dict(act.get("params") or {})
    for key in ("months_covered_after", "efund_months_after"):
        v = params.get(key)
        if v is None:
            v = act.get(key)
        if v is None:
            v = os_state.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    for key in ("efund_months_covered", "months_covered"):
        v = os_state.get(key)
        if v is None:
            v = params.get(key)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    remaining = params.get("remaining")
    if remaining is None:
        remaining = os_state.get("efund_remaining") or os_state.get("remaining")
    essential = params.get("essential_expense_monthly")
    if essential is None:
        essential = os_state.get("efund_essential") or os_state.get("essential_expense_monthly")
    if remaining is not None and essential is not None:
        try:
            ess = float(essential)
            if ess > 0:
                return float(remaining) / ess
        except (TypeError, ValueError):
            pass
    return None


def _p6_required_efund_floor_months(act: dict[str, Any], os_state: dict[str, Any]) -> int:
    if _is_medical_purpose(act, os_state):
        return P6_MEDICAL_FLOOR_MONTHS
    return P6_EMERGENCY_FLOOR_MONTHS_MIN


def _estate_checklist_present(act: dict[str, Any], os_state: dict[str, Any]) -> bool:
    if os_state.get("estate_checklist") or os_state.get("estate"):
        return True
    params = dict(act.get("params") or {})
    if params.get("estate_checklist_present") or act.get("estate_checklist_present"):
        return True
    return False


# --- Individual rules (return None = fall through / no opinion) ---

RuleFn = Callable[[dict[str, Any], str, dict[str, Any]], Optional[PolicyDecision]]


def rule_l_emergency(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    """DENY invest/speculate from EF; P6 also enforces 6–12mo / 24mo medical floors."""
    params = dict(act.get("params") or {})
    flags = (
        bool(params.get("invest_from_efund"))
        or bool(act.get("invest_from_efund"))
        or bool(os_state.get("invest_from_efund"))
        or str(act.get("purpose") or "").lower() in ("invest", "speculate", "đầu tư")
    )
    msg = _norm(str(act.get("message") or ""))
    if flags or ("quỹ kh" in msg and ("đầu tư" in msg or "mua ck" in msg or "all-in" in msg)):
        return _decision("DENY", "L-EMERGENCY", persona=persona, tools_called=["rule_l_emergency"])

    # P6: fail-closed when EF coverage would fall below persona floor.
    if persona == "P6":
        kind = str(act.get("kind") or act.get("act_kind") or "")
        touches_ef = (
            kind == "withdraw_emergency_fund"
            or bool(act.get("touch_efund") or params.get("touch_efund"))
            or bool(params.get("amount") and kind == "withdraw_emergency_fund")
        )
        if touches_ef or bool(act.get("check_p6_efund_floor") or params.get("check_p6_efund_floor")):
            floor_m = _p6_required_efund_floor_months(act, os_state)
            months = _months_covered_value(act, os_state)
            if months is None:
                return _decision(
                    "DENY",
                    "L-EMERGENCY",
                    persona=persona,
                    tools_called=["rule_l_emergency"],
                    message_vi=MSG["L-EMERGENCY-P6"]
                    + " Thiếu số liệu số dư/sàn để đánh giá.",
                    meta={
                        "p6_floor_months": floor_m,
                        "medical": _is_medical_purpose(act, os_state),
                        "fail_closed": True,
                        "reason": "insufficient_balance_data",
                    },
                )
            if float(months) < float(floor_m):
                return _decision(
                    "DENY",
                    "L-EMERGENCY",
                    persona=persona,
                    tools_called=["rule_l_emergency"],
                    message_vi=(
                        f"{MSG['L-EMERGENCY-P6']} "
                        f"Còn ~{months:.1f} tháng < sàn {floor_m} tháng"
                        f"{' (y tế)' if floor_m == P6_MEDICAL_FLOOR_MONTHS else ''}."
                    ),
                    meta={
                        "p6_floor_months": floor_m,
                        "months_covered": months,
                        "medical": _is_medical_purpose(act, os_state),
                        "fail_closed": True,
                        "reason": "below_p6_efund_floor",
                    },
                )
    return None


def rule_l_pillar_order(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    """DENY growth/freedom acts when safety pillar not satisfied (stub)."""
    params = dict(act.get("params") or {})
    skip = bool(
        act.get("skip_pillar_order")
        or params.get("skip_pillar_order")
        or os_state.get("skip_pillar_order")
    )
    gate = str(os_state.get("gate_status") or act.get("gate_status") or "passed")
    kind = str(act.get("kind") or act.get("act_kind") or "")
    growthish = kind in ("buy_ticker", "speculate") or bool(act.get("growth_act"))
    if skip or (growthish and gate != "passed"):
        return _decision(
            "DENY", "L-PILLAR-ORDER", persona=persona, tools_called=["rule_l_pillar_order"]
        )
    return None


def rule_l_protect_cap(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    """DENY when protection premium ratio exceeds stub cap. TODO: full income model."""
    params = dict(act.get("params") or {})
    pct = params.get("protect_premium_pct")
    if pct is None:
        pct = act.get("protect_premium_pct") or os_state.get("protect_premium_pct")
    if pct is None:
        return None  # TODO: need income + premium in os_state
    try:
        p = float(pct)
    except (TypeError, ValueError):
        return None
    if p > PROTECT_CAP_MAX_PCT:
        return _decision(
            "DENY",
            "L-PROTECT-CAP",
            persona=persona,
            tools_called=["rule_l_protect_cap"],
            meta={"protect_premium_pct": p, "cap": PROTECT_CAP_MAX_PCT},
        )
    return None


def rule_l_protect_cover(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    """DENY canceling required cover without replacement."""
    params = dict(act.get("params") or {})
    if (
        bool(act.get("cancel_insurance_cover"))
        or bool(params.get("cancel_insurance_cover"))
        or bool(os_state.get("cancel_insurance_cover"))
        or str(act.get("kind") or "") == "cancel_insurance_cover"
    ):
        return _decision(
            "DENY", "L-PROTECT-COVER", persona=persona, tools_called=["rule_l_protect_cover"]
        )
    return None


def rule_l_retire_floor(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    """DENY retire withdraw below persona floor stub. TODO: full retire balance."""
    params = dict(act.get("params") or {})
    if str(act.get("kind") or act.get("act_kind") or "") not in (
        "withdraw_retire",
        "retire_withdraw",
    ) and not bool(act.get("withdraw_retire") or params.get("withdraw_retire")):
        return None
    remaining = params.get("retire_remaining")
    floor = params.get("retire_floor")
    if remaining is None:
        remaining = os_state.get("retire_remaining")
    if floor is None:
        floor = os_state.get("retire_floor")
    if remaining is not None and floor is not None:
        try:
            if float(remaining) < float(floor):
                return _decision(
                    "DENY",
                    "L-RETIRE-FLOOR",
                    persona=persona,
                    tools_called=["rule_l_retire_floor"],
                )
        except (TypeError, ValueError):
            pass
    # Shape detected without balances → DENY fail-closed for retire withdraw
    return _decision(
        "DENY",
        "L-RETIRE-FLOOR",
        persona=persona,
        tools_called=["rule_l_retire_floor"],
        message_vi=(
            "L-RETIRE-FLOOR: Phát hiện rút hưu trí — thiếu số dư/sàn để đánh giá đủ. "
            "Từ chối an toàn (stub) — không ghi OS."
        ),
    )


def rule_l_envelope_p3(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    """P3 envelope constraint stub — DENY when violation flag set."""
    params = dict(act.get("params") or {})
    if bool(
        act.get("envelope_p3_violation")
        or params.get("envelope_p3_violation")
        or os_state.get("envelope_p3_violation")
    ):
        return _decision(
            "DENY", "L-ENVELOPE-P3", persona=persona, tools_called=["rule_l_envelope_p3"]
        )
    return None  # TODO: full P3 envelope matrix when OS data exists


def rule_l_envelope_p4(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    """DENY cross-take from/to locked envelopes."""
    params = dict(act.get("params") or {})
    cross = bool(
        act.get("cross_take")
        or params.get("cross_take")
        or os_state.get("cross_take")
        or str(act.get("kind") or "") == "cross_take"
    )
    if not cross:
        return None
    locked = bool(
        act.get("from_locked")
        or act.get("to_locked")
        or params.get("from_locked")
        or params.get("to_locked")
        or params.get("cross_take_forbidden")
        or os_state.get("from_locked")
        or os_state.get("to_locked")
        or os_state.get("cross_take_forbidden")
    )
    # MVP: any cross_take is denied (align Mode C deny_cross_take stub)
    return _decision(
        "DENY",
        "L-ENVELOPE-P4",
        persona=persona,
        tools_called=["rule_l_envelope_p4"],
        meta={"locked": locked},
    )


def rule_l_no_ilp_new(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    if _intent(act, os_state) == "ilp_new" or str(act.get("kind") or "") == "ilp_new":
        msg = MSG["L-NO-ILP-NEW"]
        if persona == "P6":
            msg = (
                "L-NO-ILP-NEW (P6 tuyệt đối): Cấm đề xuất / tạo lead ILP mới. "
                "Agent không nộp hồ sơ BH — không ghi OS."
            )
        return _decision(
            "DENY",
            "L-NO-ILP-NEW",
            persona=persona,
            tools_called=["rule_l_no_ilp_new"],
            message_vi=msg,
            meta={"absolute_p6": persona == "P6"},
        )
    return None


def rule_l_ilp_audit(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    """Existing ILP: allow audit/schedule; DENY submit forms / forge signature."""
    params = dict(act.get("params") or {})
    kind = str(act.get("kind") or act.get("act_kind") or "")
    is_ilp = (
        kind in ("ilp_audit", "ilp_existing")
        or bool(act.get("ilp_audit"))
        or bool(params.get("ilp_audit"))
        or bool(os_state.get("ilp_audit"))
    )
    if not is_ilp:
        return None
    if (
        bool(params.get("submit_forms"))
        or bool(params.get("forge_signature"))
        or bool(act.get("submit_forms"))
        or bool(act.get("forge_signature"))
        or params.get("no_submit_forms") is False
    ):
        return _decision(
            "DENY", "L-ILP-AUDIT", persona=persona, tools_called=["rule_l_ilp_audit"]
        )
    return None  # audit-only → fall through ALLOW


def rule_l_bhxh_topup(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    """BHXH/BHYT/BHTN schedule OK; DENY submit / forge."""
    params = dict(act.get("params") or {})
    kind = str(act.get("kind") or act.get("act_kind") or "")
    rk = str(params.get("reminder_kind") or act.get("reminder_kind") or "")
    is_bh = kind == "schedule_bh_reminder" or rk.upper().startswith("BH") or "bhxh" in rk.lower()
    if not is_bh and not bool(act.get("bhxh_topup") or params.get("bhxh_topup")):
        return None
    if (
        bool(params.get("submit_forms"))
        or bool(params.get("forge_signature"))
        or bool(act.get("submit_forms"))
        or params.get("no_submit_forms") is False
        or params.get("no_forge_signature") is False
    ):
        return _decision(
            "DENY", "L-BHXH-TOPUP", persona=persona, tools_called=["rule_l_bhxh_topup"]
        )
    return None


def rule_l_estate(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    """Checklist OK; legal will DENY (P1–P5) / ESCALATE (P6); P6 large missing checklist."""
    params = dict(act.get("params") or {})
    kind = str(act.get("kind") or act.get("act_kind") or "")
    msg = _norm(str(act.get("message") or ""))
    legal = bool(
        act.get("legal_will")
        or params.get("legal_will")
        or params.get("no_legal_will") is False
        or "soạn di chúc" in msg
        or "di chúc pháp lý" in msg
    )
    if legal:
        if persona == "P6":
            return _decision(
                "ESCALATE",
                "L-ESTATE",
                persona=persona,
                tools_called=["rule_l_estate"],
                message_vi=(
                    "L-ESTATE (P6): Soạn di chúc pháp lý — escalate (không tự soạn / "
                    "không giả chữ ký). Checklist di sản thì ALLOW qua Mode C."
                ),
                meta={"legal_will": True, "p6_escalate": True},
            )
        return _decision("DENY", "L-ESTATE", persona=persona, tools_called=["rule_l_estate"])

    # P6: estate checklist act itself is ALLOW (fall through → dual may still escalate).
    if persona == "P6" and kind == "open_estate_checklist":
        return None

    # P6: large Act without estate checklist → DENY with L-ESTATE rule code.
    if persona == "P6":
        large_flag = bool(
            act.get("large_act")
            or params.get("large_act")
            or kind in P6_LARGE_ACTS
        )
        if large_flag and kind != "open_estate_checklist" and not _estate_checklist_present(
            act, os_state
        ):
            return _decision(
                "DENY",
                "L-ESTATE",
                persona=persona,
                tools_called=["rule_l_estate"],
                message_vi=(
                    "L-ESTATE (P6): Act lớn thiếu checklist di sản — "
                    "mở checklist trước (ALLOW) hoặc escalate. Không ghi OS."
                ),
                meta={"missing_estate_checklist": True, "large_act": True},
            )
    return None


def rule_l_no_ticker(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    if _intent(act, os_state) == "buy_ticker" or str(act.get("kind") or "") == "buy_ticker":
        return _decision(
            "DENY", "L-NO-TICKER", persona=persona, tools_called=["rule_l_no_ticker"]
        )
    return None


def rule_l_no_spec(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    if _intent(act, os_state) == "speculate" or str(act.get("kind") or "") == "speculate":
        return _decision(
            "DENY", "L-NO-SPEC", persona=persona, tools_called=["rule_l_no_spec"]
        )
    return None


def rule_l_cool_off(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    """ESCALATE to pending_cool_off (P1–P5) or pending_dual (P6). Preserve #187 flows."""
    kind = str(act.get("kind") or act.get("act_kind") or "")
    phase = str(act.get("phase") or os_state.get("phase") or "propose")
    cool_meta = act.get("cool_off") or os_state.get("cool_off") or {}
    triggered = bool(cool_meta.get("triggered")) if isinstance(cool_meta, dict) else False
    status = str(act.get("status") or os_state.get("proposal_status") or "")

    # Already in dual pipeline (P6 cool-off escalate) — do not re-fire cool-off
    if status == "pending_dual" or os_state.get("companion_confirming"):
        return None

    # Confirm phase: still waiting → ESCALATE (block write); ready → fall through
    if phase == "confirm" and status == "pending_cool_off":
        ready = bool(os_state.get("cool_off_ready") or act.get("cool_off_ready"))
        if not ready:
            return _decision(
                "ESCALATE",
                "L-COOL-OFF",
                persona=persona,
                side_effect=SIDE_PENDING_COOL_OFF,
                tools_called=["rule_l_cool_off"],
                meta={"still_pending": True},
            )
        return None

    if kind != "withdraw_emergency_fund" and not triggered:
        return None
    if not triggered:
        return None

    # P6: never self L-COOL-OFF — annotate act and fall through to L-DUAL-CONTROL
    # so child-companion DENY/ESCALATE is enforced in one place.
    if persona == "P6":
        act["cool_off_escalated_to_dual"] = True
        act["dual_control_required"] = True
        if isinstance(cool_meta, dict):
            act["cool_off"] = cool_meta
        return None

    return _decision(
        "ESCALATE",
        "L-COOL-OFF",
        persona=persona,
        side_effect=SIDE_PENDING_COOL_OFF,
        tools_called=["rule_l_cool_off"],
        meta={"cool_off": cool_meta},
    )


def rule_l_dual_control(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    """DENY missing companion; ESCALATE pending_dual when companion present. Preserve #186.

    P6: money + estate + create_envelope → dual; companion must be child (con).
    """
    kind = str(act.get("kind") or act.get("act_kind") or "")
    phase = str(act.get("phase") or os_state.get("phase") or "propose")
    status = str(act.get("status") or os_state.get("proposal_status") or "")
    if persona == "P6":
        has_companion = _has_child_companion(act, os_state)
    else:
        has_companion = _has_any_companion(act, os_state)
    force_dual = bool(
        act.get("cool_off_escalated_to_dual")
        or os_state.get("cool_off_escalated_to_dual")
        or status == "pending_dual"
    )
    needs = kind in DUAL_CONTROL_ACTS or force_dual or bool(act.get("dual_control_required"))
    if persona == "P6" and kind in P6_DUAL_CONTROL_ACTS:
        needs = True

    cool_meta = act.get("cool_off") or os_state.get("cool_off") or {}
    escalated_from_cool = bool(
        act.get("cool_off_escalated_to_dual") or os_state.get("cool_off_escalated_to_dual")
    )

    if phase == "confirm":
        if status == "pending_dual" or (needs and status != "pending_cool_off"):
            if os_state.get("companion_confirming"):
                if persona == "P6":
                    if has_companion or (
                        os_state.get("companion_verified")
                        and _has_child_companion(act, os_state)
                    ):
                        return None
                    return _decision(
                        "DENY",
                        "L-DUAL-CONTROL",
                        persona=persona,
                        tools_called=["rule_l_dual_control"],
                        meta={"child_companion_required": True},
                        message_vi=(
                            "L-DUAL-CONTROL (P6): Cần ≥1 người đồng hành là con. "
                            "Thiếu companion con — không ghi OS."
                        ),
                    )
                if not has_companion and not os_state.get("companion_verified"):
                    return _decision(
                        "DENY",
                        "L-DUAL-CONTROL",
                        persona=persona,
                        tools_called=["rule_l_dual_control"],
                    )
                return None
            return _decision(
                "DENY",
                "L-DUAL-CONTROL",
                persona=persona,
                tools_called=["rule_l_dual_control"],
                meta={"needs_companion_confirm": True},
            )
        return None

    if not needs:
        return None
    if not has_companion:
        meta: dict[str, Any] = {"companion_missing": True}
        msg = None
        if persona == "P6":
            meta["child_companion_required"] = True
            if _has_any_companion(act, os_state):
                meta["companion_missing"] = False
                meta["companion_not_child"] = True
            msg = (
                "L-DUAL-CONTROL (P6): Cần ≥1 người đồng hành là con (child). "
                "Thiếu companion con — không ghi OS. Không dùng self L-COOL-OFF."
            )
        if escalated_from_cool:
            meta["cool_off_escalated_to_dual"] = True
            meta["cool_off"] = cool_meta
            meta["no_self_cool_off"] = True
        return _decision(
            "DENY",
            "L-DUAL-CONTROL",
            persona=persona,
            tools_called=["rule_l_dual_control"],
            meta=meta,
            message_vi=msg,
        )
    meta_ok: dict[str, Any] = {"child_companion": persona == "P6"}
    if escalated_from_cool:
        meta_ok["cool_off_escalated_to_dual"] = True
        meta_ok["cool_off"] = cool_meta
        meta_ok["no_self_cool_off"] = True
    return _decision(
        "ESCALATE",
        "L-DUAL-CONTROL",
        persona=persona,
        side_effect=SIDE_PENDING_DUAL,
        tools_called=["rule_l_dual_control"],
        meta=meta_ok,
        message_vi=(
            (
                "P6 — không cho tự override bằng cooling-off một mình. "
                + MSG["L-DUAL-CONTROL"]
            )
            if escalated_from_cool
            else None
        ),
    )



def rule_l_fiduciary(
    act: dict[str, Any], persona: str, os_state: dict[str, Any]
) -> Optional[PolicyDecision]:
    if _intent(act, os_state) == "bank_transfer" or str(act.get("kind") or "") == "bank_transfer":
        return _decision(
            "DENY", "L-FIDUCIARY", persona=persona, tools_called=["rule_l_fiduciary"]
        )
    params = dict(act.get("params") or {})
    if params.get("no_bank_transfer") is False or bool(params.get("bank_transfer")):
        return _decision(
            "DENY", "L-FIDUCIARY", persona=persona, tools_called=["rule_l_fiduciary"]
        )
    return None


RULE_REGISTRY: list[tuple[str, RuleFn]] = [
    ("L-EMERGENCY", rule_l_emergency),
    ("L-PILLAR-ORDER", rule_l_pillar_order),
    ("L-PROTECT-CAP", rule_l_protect_cap),
    ("L-PROTECT-COVER", rule_l_protect_cover),
    ("L-RETIRE-FLOOR", rule_l_retire_floor),
    ("L-ENVELOPE-P3", rule_l_envelope_p3),
    ("L-ENVELOPE-P4", rule_l_envelope_p4),
    ("L-NO-ILP-NEW", rule_l_no_ilp_new),
    ("L-ILP-AUDIT", rule_l_ilp_audit),
    ("L-BHXH-TOPUP", rule_l_bhxh_topup),
    ("L-ESTATE", rule_l_estate),
    ("L-NO-TICKER", rule_l_no_ticker),
    ("L-NO-SPEC", rule_l_no_spec),
    ("L-COOL-OFF", rule_l_cool_off),
    ("L-DUAL-CONTROL", rule_l_dual_control),
    ("L-FIDUCIARY", rule_l_fiduciary),
]


def registered_rule_ids() -> tuple[str, ...]:
    return tuple(code for code, _ in RULE_REGISTRY)


def evaluate(
    act: Any,
    persona: Any = None,
    os_state: Any = None,
) -> PolicyDecision:
    """Run OS-scope L-* rules in fixed order.

    First DENY or ESCALATE wins. ALLOW from a rule falls through.
    If no rule blocks → ALLOW with policy_version=L-router-1.0.
    """
    a = _act_dict(act)
    o = _os_dict(os_state)
    p = _persona(persona, o)
    tools: list[str] = ["evaluate"]
    mode = str(a.get("mode") or o.get("mode") or "C")

    assert registered_rule_ids() == RULE_ORDER, "RULE_REGISTRY order must match RULE_ORDER"

    for code, fn in RULE_REGISTRY:
        tools.append(code)
        result = fn(a, p, o)
        if result is None:
            continue
        if result.verdict == "ALLOW":
            # fall through — keep tools trail
            tools.extend(result.tools_called)
            continue
        # DENY / ESCALATE — stop
        result.tools_called = tools + [t for t in result.tools_called if t not in tools]
        result.persona = p
        result.mode = mode
        return result

    return _decision(
        "ALLOW",
        None,
        persona=p,
        mode=mode,
        tools_called=tools,
        message_vi="ALLOW — không có rule L-* chặn.",
    )


__all__ = [
    "POLICY_VERSION",
    "RULE_ORDER",
    "MSG",
    "PolicyDecision",
    "SIDE_PENDING_COOL_OFF",
    "SIDE_PENDING_DUAL",
    "DUAL_CONTROL_ACTS",
    "P6_DUAL_CONTROL_ACTS",
    "P6_LARGE_ACTS",
    "P6_EMERGENCY_FLOOR_MONTHS_MIN",
    "P6_EMERGENCY_FLOOR_MONTHS_MAX",
    "P6_MEDICAL_FLOOR_MONTHS",
    "CHILD_COMPANION_ROLES",
    "evaluate",
    "registered_rule_ids",
    "RULE_REGISTRY",
]
