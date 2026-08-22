"""
Welora — S1-09: User fixtures NOT_PASSED / PASSED

Builds complete in-memory state:
  Onboarding DNA + Constitution + Emergency Fund Goal + Gate flags

Used by Agent Hard Deny suite and E2E smoke tests.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

import welora.onboarding as ob
from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora import goals_api
from welora.goals_api import USER_FLAGS, set_user_flags
from welora.safety_gate import compute_safety_gate_from_amounts

FixtureKind = Literal["not_passed", "passed"]


def reset_all_stores(goal_store: Optional[InMemoryEmergencyFundStore] = None) -> None:
    ob.reset_onboarding_stores()
    store = goal_store or goals_api.STORE
    if hasattr(store, "_by_id"):
        store._by_id.clear()
        store._active_by_user.clear()
    elif hasattr(store, "clear"):
        store.clear()
    USER_FLAGS.clear()


def _run_onboarding(
    user_id: str,
    *,
    essential: float,
    has_dangerous_debt: bool,
    life_stage: str = "young_single",
) -> dict[str, Any]:
    s = ob.create_session(user_id)
    ob.patch_step(s.session_id, 1, {
        "life_stage": life_stage,
        "income_stability": "stable",
        "family_context": "alone",
    })
    ob.patch_step(s.session_id, 2, {
        "essential_expense_monthly": essential,
        "emergency_fund_months_self": 0 if essential else 0,
        "has_dangerous_debt_self": has_dangerous_debt,
        "near_term_priority": "safety",
    })
    ob.patch_step(s.session_id, 3, {
        "surplus_habit": "hold",
        "risk_tolerance": 3,
        "agent_role_preference": "advisor_only",
    })
    ob.patch_step(s.session_id, 4, {})
    return ob.complete_session(s.session_id)


def build_fixture(
    kind: FixtureKind,
    *,
    user_id: Optional[str] = None,
    essential: float = 10_000_000,
    goal_store: Optional[InMemoryEmergencyFundStore] = None,
) -> dict[str, Any]:
    store = goal_store or goals_api.STORE
    uid = user_id or ("user_not_passed" if kind == "not_passed" else "user_passed")

    if kind == "not_passed":
        has_debt = True
        mastery = "learning"
        debt_on_track = False
        current_amount = essential * 0.5
    else:
        has_debt = False
        mastery = "apply"
        debt_on_track = True
        current_amount = essential * 3.2

    completed = _run_onboarding(
        uid, essential=essential, has_dangerous_debt=has_debt,
        life_stage="young_single" if kind == "not_passed" else "family",
    )
    goal = store.create_for_user(
        uid, essential, current_amount=current_amount, linked_from_onboarding=True,
    )
    set_user_flags(
        uid,
        has_dangerous_debt=has_debt,
        debt_on_track=debt_on_track,
        mastery_no_efund_invest=mastery,
    )
    gate = compute_safety_gate_from_amounts(
        current_efund_amount=goal.current_amount,
        essential_expense_monthly=goal.essential_expense_monthly,
        has_dangerous_debt=has_debt,
        debt_on_track=debt_on_track,
        mastery_no_efund_invest=mastery,
    )
    return {
        "kind": kind,
        "user_id": uid,
        "dna": completed["dna"],
        "personal_constitution": completed["personal_constitution"],
        "goal": goal.to_dict(),
        "safety_gate": gate.to_dict(),
        "flags": {
            "has_dangerous_debt": has_debt,
            "debt_on_track": debt_on_track,
            "mastery_no_efund_invest": mastery,
        },
        "agent_context_seed": {
            "user_id": uid,
            "safety_gate": gate.to_dict(),
            "goals": {
                "emergency_fund": {
                    "exists": True,
                    "months_target": goal.months_of_expense,
                    "months_covered": goal.months_covered,
                    "percent": goal.percent,
                    "current_amount": goal.current_amount,
                    "target_amount": goal.target_amount,
                },
                "debt_payoff": ({"exists": True, "on_track": debt_on_track} if has_debt else None),
            },
            "dna_summary": {
                "life_stage": completed["dna"]["identity_context"].get("life_stage"),
                "near_term_priority": completed["dna"]["financial_snapshot_self"].get("near_term_priority"),
                "risk_tolerance_self": completed["dna"]["psychological_profile_self"].get("risk_tolerance"),
                "essential_expense_monthly": goal.essential_expense_monthly,
            },
            "personal_constitution_codes": [
                a["code"] for a in completed["personal_constitution"]["articles"]
            ],
            "stage_agent": "advisory_only",
            "data_confidence": "full",
        },
    }


def fixture_not_passed(**kwargs: Any) -> dict[str, Any]:
    return build_fixture("not_passed", **kwargs)


def fixture_passed(**kwargs: Any) -> dict[str, Any]:
    return build_fixture("passed", **kwargs)


def load_pair(essential: float = 10_000_000) -> dict[str, dict[str, Any]]:
    reset_all_stores()
    return {
        "not_passed": fixture_not_passed(essential=essential),
        "passed": fixture_passed(essential=essential),
    }


if __name__ == "__main__":
    pair = load_pair()
    for k, fx in pair.items():
        g = fx["safety_gate"]
        print(f"{k}: user={fx['user_id']} gate={g['status']} months={g['months_covered']:.2f} reasons={g['reasons']}")
