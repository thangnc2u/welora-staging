"""
Welora — S1-03: Goal model `emergency_fund`

Aligned with:
- Welora_E2_Goal_SafetyGate_Spec_v1
- WeloraOS_Schema_Goal_HealthScore_Mastery_v1_LOCKED
- safety_gate.py helpers (TARGET_MONTHS = 3 hard)

In-memory store for MVP / tests. Swap repository for DB later.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from welora.safety_gate import (
    TARGET_MONTHS,
    compute_months_covered,
    compute_progress_percent,
    compute_target_amount,
)

GoalStatus = Literal["active", "completed", "paused", "cancelled"]
PlanMethod = Literal["manual", "auto"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class EmergencyFundGoal:
    goal_id: str
    user_id: str
    type: str
    title: str
    status: GoalStatus
    principle_keys: list[str]
    target_amount: float
    target_unit: str
    months_of_expense: int
    target_date: Optional[str]
    current_amount: float
    percent: float
    last_updated_at: str
    safety_gate_relevant: bool
    monthly_contribution: float
    plan_method: Optional[PlanMethod]
    linked_from_onboarding: bool
    essential_expense_monthly: float
    created_at: str
    updated_at: str

    @property
    def months_covered(self) -> float:
        return compute_months_covered(self.current_amount, self.essential_expense_monthly)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal_id": self.goal_id,
            "user_id": self.user_id,
            "type": self.type,
            "title": self.title,
            "status": self.status,
            "principle_keys": list(self.principle_keys),
            "target": {
                "amount": self.target_amount,
                "unit": self.target_unit,
                "months_of_expense": self.months_of_expense,
                "target_date": self.target_date,
            },
            "current": {
                "amount": self.current_amount,
                "percent": self.percent,
                "months_covered": self.months_covered,
                "last_updated_at": self.last_updated_at,
            },
            "safety_gate_relevant": self.safety_gate_relevant,
            "plan": {
                "monthly_contribution": self.monthly_contribution,
                "method": self.plan_method,
            },
            "linked_from_onboarding": self.linked_from_onboarding,
            "essential_expense_monthly": self.essential_expense_monthly,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


def create_emergency_fund_goal(
    *,
    user_id: str,
    essential_expense_monthly: float,
    current_amount: float = 0.0,
    months_of_expense: int = TARGET_MONTHS,
    title: Optional[str] = None,
    target_date: Optional[str] = None,
    monthly_contribution: float = 0.0,
    plan_method: Optional[PlanMethod] = None,
    linked_from_onboarding: bool = False,
) -> EmergencyFundGoal:
    if months_of_expense < TARGET_MONTHS:
        months_of_expense = TARGET_MONTHS
    target = compute_target_amount(essential_expense_monthly, months_of_expense)
    current = max(0.0, float(current_amount))
    percent = compute_progress_percent(current, target)
    now = _now()
    status: GoalStatus = "completed" if percent >= 100.0 else "active"
    return EmergencyFundGoal(
        goal_id=str(uuid4()),
        user_id=user_id,
        type="emergency_fund",
        title=title or f"Quỹ khẩn cấp {months_of_expense} tháng",
        status=status,
        principle_keys=["SAFE-01", "CORE-07"],
        target_amount=target,
        target_unit="VND",
        months_of_expense=months_of_expense,
        target_date=target_date,
        current_amount=current,
        percent=percent,
        last_updated_at=now,
        safety_gate_relevant=True,
        monthly_contribution=max(0.0, monthly_contribution),
        plan_method=plan_method,
        linked_from_onboarding=linked_from_onboarding,
        essential_expense_monthly=float(essential_expense_monthly),
        created_at=now,
        updated_at=now,
    )


def apply_progress(
    goal: EmergencyFundGoal,
    *,
    set_amount: Optional[float] = None,
    add_amount: Optional[float] = None,
) -> EmergencyFundGoal:
    if set_amount is not None and add_amount is not None:
        raise ValueError("Provide either set_amount or add_amount, not both")
    if set_amount is None and add_amount is None:
        raise ValueError("Provide set_amount or add_amount")
    if set_amount is not None:
        new_current = max(0.0, float(set_amount))
    else:
        new_current = max(0.0, goal.current_amount + float(add_amount or 0))
    percent = compute_progress_percent(new_current, goal.target_amount)
    now = _now()
    status: GoalStatus = goal.status
    if percent >= 100.0 and status == "active":
        status = "completed"
    elif percent < 100.0 and status == "completed":
        status = "active"
    return EmergencyFundGoal(
        goal_id=goal.goal_id,
        user_id=goal.user_id,
        type=goal.type,
        title=goal.title,
        status=status,
        principle_keys=list(goal.principle_keys),
        target_amount=goal.target_amount,
        target_unit=goal.target_unit,
        months_of_expense=goal.months_of_expense,
        target_date=goal.target_date,
        current_amount=new_current,
        percent=percent,
        last_updated_at=now,
        safety_gate_relevant=goal.safety_gate_relevant,
        monthly_contribution=goal.monthly_contribution,
        plan_method=goal.plan_method,
        linked_from_onboarding=goal.linked_from_onboarding,
        essential_expense_monthly=goal.essential_expense_monthly,
        created_at=goal.created_at,
        updated_at=now,
    )


class InMemoryEmergencyFundStore:
    def __init__(self) -> None:
        self._by_id: dict[str, EmergencyFundGoal] = {}
        self._active_by_user: dict[str, str] = {}

    def save(self, goal: EmergencyFundGoal) -> EmergencyFundGoal:
        self._by_id[goal.goal_id] = goal
        if goal.status in ("active", "completed"):
            self._active_by_user[goal.user_id] = goal.goal_id
        elif self._active_by_user.get(goal.user_id) == goal.goal_id:
            del self._active_by_user[goal.user_id]
        return goal

    def get(self, goal_id: str) -> Optional[EmergencyFundGoal]:
        return self._by_id.get(goal_id)

    def get_active_for_user(self, user_id: str) -> Optional[EmergencyFundGoal]:
        gid = self._active_by_user.get(user_id)
        return self._by_id.get(gid) if gid else None

    def create_for_user(
        self,
        user_id: str,
        essential_expense_monthly: float,
        **kwargs: Any,
    ) -> EmergencyFundGoal:
        existing = self.get_active_for_user(user_id)
        if existing and existing.status in ("active", "completed"):
            raise ValueError(
                f"User {user_id} already has emergency_fund goal {existing.goal_id} ({existing.status})"
            )
        goal = create_emergency_fund_goal(
            user_id=user_id,
            essential_expense_monthly=essential_expense_monthly,
            **kwargs,
        )
        return self.save(goal)

    def record_progress(
        self,
        goal_id: str,
        *,
        set_amount: Optional[float] = None,
        add_amount: Optional[float] = None,
    ) -> EmergencyFundGoal:
        goal = self.get(goal_id)
        if not goal:
            raise KeyError(f"Goal not found: {goal_id}")
        updated = apply_progress(goal, set_amount=set_amount, add_amount=add_amount)
        return self.save(updated)
