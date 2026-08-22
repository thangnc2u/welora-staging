"""
Welora P1-E6 — Health Score read path (0–1000)

Aligned with WeloraOS_Schema_Goal_HealthScore_Mastery_v1_LOCKED.

Hard rule: score MUST NOT bypass Safety Gate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from welora import goals_api
from welora.safety_gate import TARGET_MONTHS, compute_safety_gate_from_amounts


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _level(score: float) -> str:
    if score < 200:
        return "critical"
    if score < 400:
        return "low"
    if score < 600:
        return "moderate"
    if score < 800:
        return "good"
    return "strong"


def score_emergency_fund(months_covered: float, target_months: int = TARGET_MONTHS) -> tuple[float, dict]:
    m = max(0.0, float(months_covered))
    if m <= 0:
        s = 0.0
    elif m < 1:
        s = 80.0 * m
    elif m < 2:
        s = 80.0 + 80.0 * (m - 1)
    elif m < 3:
        s = 160.0 + 90.0 * (m - 2)
    else:
        s = 250.0
    s = min(250.0, s)
    return s, {
        "months_covered": round(m, 2),
        "target_months": target_months,
        "percent_to_target": round(min(100.0, (m / target_months) * 100), 1) if target_months else 0.0,
    }


def score_debt(* , has_dangerous_debt: bool, debt_on_track: bool, debt_goal_progress_percent: float = 0.0) -> tuple[float, dict]:
    if not has_dangerous_debt:
        s = 250.0
    elif debt_on_track:
        s = 100.0 + min(80.0, max(0.0, debt_goal_progress_percent) * 0.8)
    else:
        s = 30.0
    return s, {
        "has_dangerous_debt": has_dangerous_debt,
        "dangerous_debt_amount": None,
        "debt_goal_progress_percent": debt_goal_progress_percent,
        "on_track": debt_on_track if has_dangerous_debt else True,
    }


def score_cashflow(* , essential: float, monthly_contribution: float = 0.0, income_estimate: Optional[float] = None) -> tuple[float, dict]:
    ess = max(0.0, float(essential or 0))
    contrib = max(0.0, float(monthly_contribution or 0))
    income = income_estimate
    surplus = None
    if income and income > 0:
        surplus = income - ess
        ratio = surplus / income
        s = max(0.0, min(200.0, 100.0 + ratio * 200.0))
    elif ess > 0 and contrib > 0:
        s = min(200.0, 40.0 + min(160.0, (contrib / ess) * 200.0))
    elif ess > 0:
        s = 60.0
    else:
        s = 20.0
    return s, {
        "monthly_income": income,
        "monthly_essential_expense": ess or None,
        "surplus": surplus,
        "positive_months_last_3": None,
        "monthly_contribution_to_ef": contrib,
    }


def score_savings_invest_rate(monthly_contrib: float, essential: float) -> tuple[float, dict]:
    ess = max(essential, 1.0)
    pct = max(0.0, monthly_contrib) / ess * 100.0
    s = min(150.0, pct * 3.0)
    return s, {"monthly_save_invest_percent": round(pct, 1)}


def score_behavior(* , mastery: str, recent_violations: int = 0, goals_on_track: int = 0) -> tuple[float, dict]:
    mastery_pts = {"not_started": 10, "learning": 40, "familiar": 70, "apply": 120, "mastered": 140}.get(mastery, 10)
    s = float(mastery_pts)
    s -= min(80.0, recent_violations * 40.0)
    s += min(10.0, goals_on_track * 5.0)
    s = max(0.0, min(150.0, s))
    return s, {
        "streak_days": 0,
        "goals_on_track": goals_on_track,
        "recent_hard_rule_violations": recent_violations,
        "mastery_no_efund_invest": mastery,
    }


def compute_health_score(
    *,
    user_id: str,
    months_covered: float = 0.0,
    essential_expense_monthly: float = 0.0,
    current_efund_amount: float = 0.0,
    target_efund_amount: float = 0.0,
    goal_id: Optional[str] = None,
    monthly_contribution: float = 0.0,
    has_dangerous_debt: bool = False,
    debt_on_track: bool = True,
    mastery_no_efund_invest: str = "not_started",
    recent_violations: int = 0,
) -> dict[str, Any]:
    ef_s, ef_d = score_emergency_fund(months_covered)
    ef_d["goal_id"] = goal_id
    ef_d["current_amount"] = current_efund_amount
    ef_d["target_amount"] = target_efund_amount

    debt_s, debt_d = score_debt(has_dangerous_debt=has_dangerous_debt, debt_on_track=debt_on_track)
    cf_s, cf_d = score_cashflow(essential=essential_expense_monthly, monthly_contribution=monthly_contribution)
    sav_s, sav_d = score_savings_invest_rate(monthly_contribution, essential_expense_monthly)
    beh_s, beh_d = score_behavior(
        mastery=mastery_no_efund_invest,
        recent_violations=recent_violations,
        goals_on_track=1 if months_covered >= TARGET_MONTHS else 0,
    )

    total = max(0.0, min(1000.0, ef_s + debt_s + cf_s + sav_s + beh_s))

    gate = compute_safety_gate_from_amounts(
        current_efund_amount=current_efund_amount if essential_expense_monthly > 0 else 0.0,
        essential_expense_monthly=essential_expense_monthly if essential_expense_monthly > 0 else 1.0,
        has_dangerous_debt=has_dangerous_debt,
        debt_on_track=debt_on_track,
        mastery_no_efund_invest=mastery_no_efund_invest,
    )

    return {
        "user_id": user_id,
        "score": int(round(total)),
        "level": _level(total),
        "components": {
            "cashflow": {"score": int(round(cf_s)), "weight": 0.20, "details": cf_d},
            "emergency_fund": {"score": int(round(ef_s)), "weight": 0.25, "details": ef_d},
            "debt": {"score": int(round(debt_s)), "weight": 0.25, "details": debt_d},
            "savings_invest_rate": {"score": int(round(sav_s)), "weight": 0.15, "details": sav_d},
            "behavior_consistency": {"score": int(round(beh_s)), "weight": 0.15, "details": beh_d},
        },
        "safety_gate": gate.to_dict(),
        "can_bypass_gate_with_score": False,
        "note": "Health Score không thay thế Cổng An Toàn. Đầu tư chỉ khi safety_gate.status=passed.",
        "calculated_at": _now(),
        "version": "1.0",
    }


def health_score_for_user(user_id: str) -> dict[str, Any]:
    goal = goals_api.STORE.get_active_for_user(user_id)
    flags = goals_api.get_user_flags(user_id)
    if not goal:
        return compute_health_score(
            user_id=user_id,
            has_dangerous_debt=bool(flags.get("has_dangerous_debt")),
            debt_on_track=bool(flags.get("debt_on_track", True)),
            mastery_no_efund_invest=str(flags.get("mastery_no_efund_invest") or "not_started"),
        )
    return compute_health_score(
        user_id=user_id,
        months_covered=goal.months_covered,
        essential_expense_monthly=goal.essential_expense_monthly,
        current_efund_amount=goal.current_amount,
        target_efund_amount=goal.target_amount,
        goal_id=goal.goal_id,
        monthly_contribution=goal.monthly_contribution,
        has_dangerous_debt=bool(flags.get("has_dangerous_debt")),
        debt_on_track=bool(flags.get("debt_on_track", True)),
        mastery_no_efund_invest=str(flags.get("mastery_no_efund_invest") or "not_started"),
    )


def service_get_health_score(user_id: str) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    return 200, health_score_for_user(user_id)
