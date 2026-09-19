"""
Welora — S1-09: User fixtures NOT_PASSED / PASSED

Builds complete in-memory state:
  Onboarding DNA + Constitution + Emergency Fund Goal + Gate flags

Used by Agent Hard Deny suite and E2E smoke tests.

PRD v2: persona fixtures keyed P1–P6 live in welora.personas.
DNA-USER-2026-* 4-persona fixtures are retired (see personas.RETIRED_DNA_USER_2026).
Demo seed prefers P2 + P4.
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
        if hasattr(store, "_debt_by_user"):
            store._debt_by_user.clear()
    elif hasattr(store, "clear"):
        store.clear()
    USER_FLAGS.clear()
    try:
        from welora.mode_c_act import reset_mode_c_store
        reset_mode_c_store()
    except Exception:
        pass


def _run_onboarding(
    user_id: str,
    *,
    essential: float,
    has_dangerous_debt: bool,
    life_stage: str = "solo",
    household: str | None = None,
    family_context: str = "alone",
) -> dict[str, Any]:
    s = ob.create_session(user_id)
    hh = household or life_stage
    ob.patch_step(s.session_id, 1, {
        "household": hh,
        "life_stage": hh,
        "income_stability": "stable",
        "family_context": family_context,
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

    # not_passed ≈ P4 sandwich stress; passed ≈ P2 young family (demo priority)
    completed = _run_onboarding(
        uid, essential=essential, has_dangerous_debt=has_debt,
        household="sandwich_3gen" if kind == "not_passed" else "young_family",
        family_context="with_family",
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


def build_p6_fixture(
    *,
    user_id: Optional[str] = None,
    companion_user_id: Optional[str] = None,
    essential: float = 10_000_000,
    efund_months: float = 12.0,
    goal_store: Optional[InMemoryEmergencyFundStore] = None,
) -> dict[str, Any]:
    """Passed fixture + persona=P6 + child companion (con) for P6 router tests.

    Tops up emergency fund to ``efund_months`` (default 12) so L-EMERGENCY P6
    floors (6–12 / 24 medical) can be exercised without always fail-closing.
    TARGET_MONTHS=3 Safety Gate remains unchanged.
    """
    from welora.mode_c_act import set_companion, set_persona

    store = goal_store or goals_api.STORE
    uid = user_id or "user_p6"
    child_id = companion_user_id or "user_p6_child"
    fx = build_fixture(
        "passed",
        user_id=uid,
        essential=essential,
        goal_store=store,
    )
    goal = store.get_active_for_user(uid)
    if goal is not None:
        target = float(essential) * float(efund_months)
        try:
            topped = store.record_progress(goal.goal_id, set_amount=target)
        except ValueError:
            # Goal may already be completed at 100% of 3mo target — mutate save
            from welora.goal_emergency_fund import apply_progress
            # Force via save of a cloned progress ignoring completed guard
            g2 = store.get(goal.goal_id)
            g2.current_amount = target
            g2.percent = min(100.0, (target / max(g2.target_amount, 1.0)) * 100.0)
            g2.status = "active" if g2.percent < 100 else "completed"
            topped = store.save(g2)
        fx["goal"] = topped.to_dict()
        fx["efund_months"] = float(efund_months)
    set_persona(user_id=uid, persona="P6")
    set_companion(user_id=uid, companion_user_id=child_id, role="child")
    fx["persona"] = "P6"
    fx["companion_user_id"] = child_id
    fx["companion_role"] = "child"
    return fx



def build_persona_fixture(
    persona_id: str,
    *,
    user_id: Optional[str] = None,
    essential: float = 10_000_000,
    goal_store: Optional[InMemoryEmergencyFundStore] = None,
) -> dict[str, Any]:
    """Build fixture from canonical P1–P6 catalog (welora.personas)."""
    from welora.personas import get_persona, os_goal_types
    from welora.mode_c_act import set_persona

    p = get_persona(persona_id)
    store = goal_store or goals_api.STORE
    uid = user_id or f"user_{persona_id.lower()}"
    # P4 sandwich: debt stress / not_passed; others: EF-forward / passed
    if persona_id == "P4":
        has_debt, mastery, debt_on_track = True, "learning", False
        current_amount = essential * 0.5
        kind: FixtureKind = "not_passed"
    else:
        has_debt, mastery, debt_on_track = False, "apply", True
        current_amount = essential * 3.2
        kind = "passed"

    completed = _run_onboarding(
        uid,
        essential=essential,
        has_dangerous_debt=has_debt,
        household=p["household"],
        family_context="alone" if p["household"] == "solo" else "with_family",
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
    set_persona(user_id=uid, persona=persona_id)
    return {
        "kind": kind,
        "persona_id": persona_id,
        "household": p["household"],
        "user_id": uid,
        "dna": completed["dna"],
        "personal_constitution": completed["personal_constitution"],
        "goal": goal.to_dict(),
        "safety_gate": gate.to_dict(),
        "os_goals": list(os_goal_types(persona_id)),
        "dna_answers": dict(p["dna_answers"]),
        "academy_emphasis": list(p["academy_emphasis"]),
        "pillars": dict(p["pillars"]),
        "flags": {
            "has_dangerous_debt": has_debt,
            "debt_on_track": debt_on_track,
            "mastery_no_efund_invest": mastery,
        },
    }


def load_demo_personas(
    *,
    essential: float = 10_000_000,
    priority_only: bool = True,
) -> dict[str, dict[str, Any]]:
    """Demo seed prefers P2 + P4 (Founder lock §13)."""
    from welora.personas import DEMO_SEED_ORDER, demo_seed_personas

    reset_all_stores()
    if priority_only:
        order = [p["persona_id"] for p in demo_seed_personas(only_priority=True)]
    else:
        order = list(DEMO_SEED_ORDER)
    return {pid: build_persona_fixture(pid, essential=essential) for pid in order}



if __name__ == "__main__":
    pair = load_pair()
    for k, fx in pair.items():
        g = fx["safety_gate"]
        print(f"{k}: user={fx['user_id']} gate={g['status']} months={g['months_covered']:.2f} reasons={g['reasons']}")

