"""
Welora — S1-08: CTA helper — Onboarding complete → create Goal

Framework-agnostic. UI calls this after confirm sheet.
"""

from __future__ import annotations

from typing import Any, Optional

from welora.goals_api import service_create_goal


def create_goal_from_onboarding_cta(
    cta: dict[str, Any],
    *,
    current_amount: float = 0.0,
) -> tuple[int, dict]:
    """
    Use complete_session()['cta'] to POST /goals equivalent.

    Returns (status_code, body) same shape as service_create_goal.
    """
    if not cta or cta.get("code") != "create_emergency_fund_goal":
        return 400, {"error": "invalid or missing create_emergency_fund_goal cta"}

    prefill = cta.get("prefill_body")
    if not prefill or not prefill.get("user_id"):
        return 400, {"error": "cta.prefill_body required"}

    if prefill.get("essential_expense_monthly") is None:
        return 400, {"error": "essential_expense_monthly missing in prefill"}

    body = {
        **prefill,
        "current_amount": float(current_amount),
        "linked_from_onboarding": True,
        "type": "emergency_fund",
    }
    return service_create_goal(body)


def format_target_vnd(essential_expense_monthly: float, months: int = 3) -> str:
    target = int(essential_expense_monthly * months)
    return f"{target:,}".replace(",", ".") + " đ"
