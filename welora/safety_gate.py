"""
Welora — S1-02: Safety Gate (Cổng An Toàn)

Pure functions aligned with:
- Welora_Cong_An_Toan_Thresholds_v1_LOCKED  (≥ 3 months HARD)
- Welora_E2_Goal_SafetyGate_Spec_v1
- WeloraOS_Schema_Goal_HealthScore_Mastery_v1_LOCKED

No I/O. Deterministic. Unit-testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Literal, Optional

TARGET_MONTHS = 3  # HARD — do not soften in MVP

MasteryState = Literal[
    "not_started", "learning", "familiar", "apply", "mastered"
]
GateStatus = Literal["passed", "not_passed"]

REASON_EFUND = "emergency_fund_below_3_months"
REASON_DEBT = "dangerous_debt_unhandled"
REASON_MASTERY = "mastery_missing"
REASON_VIOLATION = "recent_hard_rule_violation"
REASON_DATA = "data_missing"


@dataclass(frozen=True)
class SafetyGateResult:
    status: GateStatus
    reasons: tuple[str, ...]
    months_covered: float
    target_months: int
    has_dangerous_debt: bool
    debt_on_track: bool
    mastery_no_efund_invest: MasteryState
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reasons": list(self.reasons),
            "months_covered": self.months_covered,
            "target_months": self.target_months,
            "has_dangerous_debt": self.has_dangerous_debt,
            "debt_on_track": self.debt_on_track,
            "mastery_no_efund_invest": self.mastery_no_efund_invest,
            "checked_at": self.checked_at,
        }


def compute_target_amount(essential_expense_monthly: float, months: int = TARGET_MONTHS) -> float:
    if essential_expense_monthly < 0:
        raise ValueError("essential_expense_monthly must be >= 0")
    if months < TARGET_MONTHS:
        months = TARGET_MONTHS
    return months * essential_expense_monthly


def compute_months_covered(current_amount: float, essential_expense_monthly: float) -> float:
    if essential_expense_monthly <= 0:
        return 0.0
    if current_amount < 0:
        current_amount = 0.0
    return current_amount / essential_expense_monthly


def compute_progress_percent(current_amount: float, target_amount: float) -> float:
    if target_amount <= 0:
        return 0.0
    return min(100.0, (max(current_amount, 0.0) / target_amount) * 100.0)


def compute_safety_gate(
    *,
    months_covered: float,
    has_dangerous_debt: bool,
    debt_on_track: bool,
    mastery_no_efund_invest: MasteryState,
    recent_hard_rule_violations: int = 0,
    data_missing: bool = False,
) -> SafetyGateResult:
    reasons: list[str] = []
    if data_missing:
        reasons.append(REASON_DATA)
    if months_covered < TARGET_MONTHS:
        reasons.append(REASON_EFUND)
    if has_dangerous_debt and not debt_on_track:
        reasons.append(REASON_DEBT)
    if mastery_no_efund_invest not in ("apply", "mastered"):
        reasons.append(REASON_MASTERY)
    if recent_hard_rule_violations > 0:
        reasons.append(REASON_VIOLATION)
    status: GateStatus = "passed" if not reasons else "not_passed"
    return SafetyGateResult(
        status=status,
        reasons=tuple(reasons),
        months_covered=float(months_covered),
        target_months=TARGET_MONTHS,
        has_dangerous_debt=has_dangerous_debt,
        debt_on_track=debt_on_track,
        mastery_no_efund_invest=mastery_no_efund_invest,
    )


def compute_safety_gate_from_amounts(
    *,
    current_efund_amount: float,
    essential_expense_monthly: float,
    has_dangerous_debt: bool,
    debt_on_track: bool,
    mastery_no_efund_invest: MasteryState,
    recent_hard_rule_violations: int = 0,
) -> SafetyGateResult:
    data_missing = essential_expense_monthly <= 0 and current_efund_amount <= 0
    months = compute_months_covered(current_efund_amount, essential_expense_monthly)
    return compute_safety_gate(
        months_covered=months,
        has_dangerous_debt=has_dangerous_debt,
        debt_on_track=debt_on_track,
        mastery_no_efund_invest=mastery_no_efund_invest,
        recent_hard_rule_violations=recent_hard_rule_violations,
        data_missing=data_missing,
    )
