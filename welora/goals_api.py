"""Welora Goal API + Safety Gate (P2-E4 mastery wired)."""

from __future__ import annotations

import os
from typing import Any, Optional

from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.safety_gate import compute_safety_gate, compute_safety_gate_from_amounts


def _make_store():
    if os.environ.get("WELORA_STORE", "memory").lower() == "sqlite":
        from welora.db.repos import SqliteEmergencyFundStore
        return SqliteEmergencyFundStore(os.environ.get("WELORA_DB_URL") or None)
    return InMemoryEmergencyFundStore()


STORE = _make_store()


def use_store(store) -> None:
    global STORE
    STORE = store


USER_FLAGS: dict[str, dict[str, Any]] = {}


def set_user_flags(
    user_id: str,
    *,
    has_dangerous_debt: bool = False,
    debt_on_track: bool = True,
    mastery_no_efund_invest: str = "apply",
) -> None:
    USER_FLAGS[user_id] = {
        "has_dangerous_debt": has_dangerous_debt,
        "debt_on_track": debt_on_track,
        "mastery_no_efund_invest": mastery_no_efund_invest,
    }
    try:
        from welora.mastery import set_state
        set_state(user_id, mastery_no_efund_invest)
    except Exception:
        pass


def get_user_flags(user_id: str) -> dict[str, Any]:
    if user_id in USER_FLAGS:
        return dict(USER_FLAGS[user_id])
    mastery = "not_started"
    try:
        from welora.mastery import get_node
        mastery = get_node(user_id).state
    except Exception:
        pass
    return {
        "has_dangerous_debt": False,
        "debt_on_track": True,
        "mastery_no_efund_invest": mastery,
    }


def service_create_goal(body: dict) -> tuple[int, dict]:
    user_id = body.get("user_id")
    if not user_id:
        return 400, {"error": "user_id is required"}
    if body.get("type", "emergency_fund") != "emergency_fund":
        return 400, {"error": "Only type=emergency_fund supported"}
    essential = body.get("essential_expense_monthly")
    if essential is None:
        return 400, {"error": "essential_expense_monthly is required"}
    try:
        essential_f = float(essential)
    except (TypeError, ValueError):
        return 400, {"error": "essential_expense_monthly must be a number"}
    if essential_f <= 0:
        return 400, {"error": "essential_expense_monthly must be > 0"}
    try:
        goal = STORE.create_for_user(
            str(user_id),
            essential_f,
            current_amount=float(body.get("current_amount") or 0),
            linked_from_onboarding=bool(body.get("linked_from_onboarding", False)),
            monthly_contribution=float(body.get("monthly_contribution") or 0),
            plan_method=body.get("plan_method"),
        )
    except ValueError as e:
        return 409, {"error": str(e)}
    return 201, goal.to_dict()


def service_get_goal(goal_id: str) -> tuple[int, dict]:
    goal = STORE.get(goal_id)
    if not goal:
        return 404, {"error": "goal not found"}
    return 200, goal.to_dict()


def service_list_goals(user_id: str, type: Optional[str] = None) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    goal = STORE.get_active_for_user(user_id)
    items = []
    if goal and (type is None or goal.type == type):
        items.append(goal.to_dict())
    return 200, {"items": items}


def service_progress(goal_id: str, body: dict) -> tuple[int, dict]:
    set_amount = body.get("set_amount")
    add_amount = body.get("add_amount")
    try:
        goal = STORE.record_progress(
            goal_id,
            set_amount=float(set_amount) if set_amount is not None else None,
            add_amount=float(add_amount) if add_amount is not None else None,
        )
    except KeyError:
        return 404, {"error": "goal not found"}
    except ValueError as e:
        return 400, {"error": str(e)}
    return 200, goal.to_dict()


def _mastery_block(flags: dict) -> dict:
    state = str(flags.get("mastery_no_efund_invest") or "not_started")
    return {
        "node_id": "no_efund_invest",
        "state": state,
        "meets_gate": state in ("apply", "mastered"),
        "gate_min": "apply",
    }


def service_safety_gate(user_id: str) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    goal = STORE.get_active_for_user(user_id)
    flags = get_user_flags(user_id)
    if os.environ.get("WELORA_STORE", "memory").lower() == "sqlite":
        try:
            from welora.db.repos import get_user_flags_db
            from welora.mastery import get_node
            db = get_user_flags_db(user_id)
            flags["has_dangerous_debt"] = bool(db.get("has_dangerous_debt"))
            flags["debt_on_track"] = bool(db.get("debt_on_track", True))
            store_state = get_node(user_id).state
            if user_id in USER_FLAGS:
                flags["mastery_no_efund_invest"] = USER_FLAGS[user_id]["mastery_no_efund_invest"]
            elif store_state != "not_started":
                flags["mastery_no_efund_invest"] = store_state
            else:
                flags["mastery_no_efund_invest"] = db.get("mastery_no_efund_invest") or "not_started"
        except Exception:
            pass
    if not goal:
        result = compute_safety_gate(
            months_covered=0.0,
            has_dangerous_debt=bool(flags.get("has_dangerous_debt")),
            debt_on_track=bool(flags.get("debt_on_track", True)),
            mastery_no_efund_invest=str(flags.get("mastery_no_efund_invest") or "not_started"),
            data_missing=True,
        )
        out = result.to_dict()
        out["mastery"] = _mastery_block(flags)
        return 200, out
    result = compute_safety_gate_from_amounts(
        current_efund_amount=goal.current_amount,
        essential_expense_monthly=goal.essential_expense_monthly,
        has_dangerous_debt=bool(flags.get("has_dangerous_debt")),
        debt_on_track=bool(flags.get("debt_on_track", True)),
        mastery_no_efund_invest=str(flags.get("mastery_no_efund_invest") or "not_started"),
    )
    out = result.to_dict()
    out["mastery"] = _mastery_block(flags)
    return 200, out
