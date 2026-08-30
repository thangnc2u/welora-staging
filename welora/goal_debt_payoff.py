"""
WeloraOS P2-OS-01 — Goal type debt_payoff (nợ nguy hiểm).

Schema LOCKED:
  type=debt_payoff, principle_keys DEBT-01 + DEBT-03 + CORE-07
  safety_gate_relevant=true
  Cổng: has_dangerous_debt AND NOT debt_on_track → not_passed

Reuse EmergencyFundGoal shape so existing store.save works.
TARGET_MONTHS / emergency_fund rules unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from welora.goal_emergency_fund import EmergencyFundGoal, GoalStatus, PlanMethod
from welora.safety_gate import compute_progress_percent

DEBT_PRINCIPLE_KEYS = ["DEBT-01", "DEBT-03", "CORE-07"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def debt_on_track_from_goal(goal: EmergencyFundGoal) -> bool:
    if goal.status == "completed":
        return True
    if (goal.monthly_contribution or 0) > 0:
        return True
    if (goal.percent or 0) > 0:
        return True
    if goal.plan_method in ("snowball", "avalanche"):
        return True
    return False


def has_dangerous_debt_from_goal(goal: EmergencyFundGoal) -> bool:
    return goal.status != "completed"


def create_debt_payoff_goal(
    *,
    user_id: str,
    target_amount: float,
    current_amount: float = 0.0,
    title: Optional[str] = None,
    subtype: Optional[str] = None,
    monthly_contribution: float = 0.0,
    plan_method: Optional[str] = None,
) -> EmergencyFundGoal:
    target = max(0.0, float(target_amount))
    if target <= 0:
        raise ValueError("target_amount must be > 0")
    current = max(0.0, float(current_amount))
    percent = compute_progress_percent(current, target)
    now = _now()
    status: GoalStatus = "completed" if percent >= 100.0 else "active"
    method: Optional[PlanMethod]
    if plan_method in ("manual", "auto", "snowball", "avalanche"):
        method = plan_method  # type: ignore[assignment]
    else:
        method = "manual" if plan_method is None else None
    return EmergencyFundGoal(
        goal_id=str(uuid4()),
        user_id=user_id,
        type="debt_payoff",
        title=title or ("Trả nợ nguy hiểm" + (f" · {subtype}" if subtype else "")),
        status=status,
        principle_keys=list(DEBT_PRINCIPLE_KEYS),
        target_amount=target,
        target_unit="VND",
        months_of_expense=0,
        target_date=None,
        current_amount=current,
        percent=percent,
        last_updated_at=now,
        safety_gate_relevant=True,
        monthly_contribution=max(0.0, float(monthly_contribution or 0)),
        plan_method=method,
        linked_from_onboarding=False,
        essential_expense_monthly=0.0,
        created_at=now,
        updated_at=now,
    )
