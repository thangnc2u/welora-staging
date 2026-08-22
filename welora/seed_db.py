"""
P1-E1-05 — Seed NOT_PASSED / PASSED fixtures into SQLite

Usage:
  PYTHONPATH=. python -m welora.seed_db
"""

from __future__ import annotations

import json
import os
from typing import Any, Literal, Optional

from welora.db.migrate import migrate
from welora.db.repos import (
    SqliteEmergencyFundStore,
    SqliteOnboardingRepository,
    get_user_flags_db,
    set_user_flags_db,
)
from welora.safety_gate import compute_safety_gate_from_amounts

FixtureKind = Literal["not_passed", "passed"]

DEFAULT_USERS = {
    "not_passed": "user_not_passed",
    "passed": "user_passed",
}


def seed_fixture(
    kind: FixtureKind,
    *,
    url: str | None = None,
    user_id: Optional[str] = None,
    essential: float = 10_000_000,
    clear_user: bool = True,
) -> dict[str, Any]:
    migrate(url)
    goals = SqliteEmergencyFundStore(url)
    ob = SqliteOnboardingRepository(url)
    uid = user_id or DEFAULT_USERS[kind]

    if kind == "not_passed":
        has_debt, mastery, debt_on_track = True, "learning", False
        current_amount = essential * 0.5
    else:
        has_debt, mastery, debt_on_track = False, "apply", True
        current_amount = essential * 3.2

    if clear_user:
        _clear_user(uid, url=url)

    s = ob.create_session(uid)
    ob.patch_step(s.session_id, 1, {
        "life_stage": "young_single" if kind == "not_passed" else "family",
        "income_stability": "stable",
        "family_context": "alone" if kind == "not_passed" else "with_kids",
    })
    ob.patch_step(s.session_id, 2, {
        "essential_expense_monthly": essential,
        "emergency_fund_months_self": "0.5" if kind == "not_passed" else "3+",
        "has_dangerous_debt_self": has_debt,
        "near_term_priority": "safety",
    })
    ob.patch_step(s.session_id, 3, {
        "surplus_habit": "hold",
        "risk_tolerance": 3 if kind == "not_passed" else 5,
        "agent_role_preference": "advisor_only",
    })
    ob.patch_step(s.session_id, 4, {})
    completed = ob.complete_session(s.session_id)

    goal = goals.create_for_user(uid, essential, current_amount=current_amount, linked_from_onboarding=True)
    set_user_flags_db(uid, has_dangerous_debt=has_debt, debt_on_track=debt_on_track, mastery_no_efund_invest=mastery, url=url)

    gate = compute_safety_gate_from_amounts(
        current_efund_amount=goal.current_amount,
        essential_expense_monthly=goal.essential_expense_monthly,
        has_dangerous_debt=has_debt,
        debt_on_track=debt_on_track,
        mastery_no_efund_invest=mastery,
    )
    expected = "not_passed" if kind == "not_passed" else "passed"
    if gate.status != expected:
        raise RuntimeError(f"Seed {kind} expected gate={expected}, got {gate.status}")

    return {
        "kind": kind,
        "user_id": uid,
        "dna": completed["dna"],
        "personal_constitution": completed["personal_constitution"],
        "goal": goal.to_dict(),
        "safety_gate": gate.to_dict(),
        "flags": get_user_flags_db(uid, url=url),
    }


def seed_pair(*, url: str | None = None, essential: float = 10_000_000) -> dict[str, dict[str, Any]]:
    migrate(url)
    return {
        "not_passed": seed_fixture("not_passed", url=url, essential=essential),
        "passed": seed_fixture("passed", url=url, essential=essential),
    }


def _clear_user(user_id: str, *, url: str | None = None) -> None:
    from welora.db.connection import get_connection
    conn = get_connection(url)
    try:
        for sql in (
            "DELETE FROM goal_history WHERE goal_id IN (SELECT goal_id FROM goals WHERE user_id=?)",
            "DELETE FROM goals WHERE user_id=?",
            "DELETE FROM onboarding_sessions WHERE user_id=?",
            "DELETE FROM dna_profiles WHERE user_id=?",
            "DELETE FROM constitutions WHERE user_id=?",
            "DELETE FROM user_flags WHERE user_id=?",
            "DELETE FROM mastery_nodes WHERE user_id=?",
            "DELETE FROM decision_logs WHERE user_id=?",
            "DELETE FROM auth_tokens WHERE user_id=?",
            "DELETE FROM users WHERE user_id=?",
        ):
            conn.execute(sql, (user_id,))
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    url = os.environ.get("WELORA_DB_URL") or None
    pair = seed_pair(url=url)
    for k, fx in pair.items():
        g = fx["safety_gate"]
        print(f"[seed] {k}: user={fx['user_id']} gate={g['status']} months={g['months_covered']:.2f}")
    print(json.dumps({"seeded": list(pair.keys())}, ensure_ascii=False))


if __name__ == "__main__":
    main()
