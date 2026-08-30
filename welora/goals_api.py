"""Welora Goal API + Safety Gate (P2-OS-01 debt_payoff)."""

from __future__ import annotations

import os
from typing import Any, Optional

from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.safety_gate import compute_safety_gate, compute_safety_gate_from_amounts


def _use_db_store() -> bool:
    store = (os.environ.get("WELORA_STORE") or "memory").strip().lower()
    url = (os.environ.get("WELORA_DB_URL") or "").strip()
    if store in ("sqlite", "postgres", "db"):
        return True
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return True
    return False


def _make_store():
    if _use_db_store():
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


def _sync_debt_flags(user_id: str, debt) -> None:
    from welora.goal_debt_payoff import debt_on_track_from_goal, has_dangerous_debt_from_goal

    flags = get_user_flags(user_id)
    set_user_flags(
        user_id,
        has_dangerous_debt=has_dangerous_debt_from_goal(debt),
        debt_on_track=debt_on_track_from_goal(debt),
        mastery_no_efund_invest=str(flags.get("mastery_no_efund_invest") or "not_started"),
    )
    if _use_db_store():
        try:
            from welora.db.repos import set_user_flags_db
            set_user_flags_db(
                user_id,
                has_dangerous_debt=has_dangerous_debt_from_goal(debt),
                debt_on_track=debt_on_track_from_goal(debt),
                mastery_no_efund_invest=str(flags.get("mastery_no_efund_invest") or "not_started"),
            )
        except Exception:
            pass


def service_create_goal(body: dict) -> tuple[int, dict]:
    user_id = body.get("user_id")
    if not user_id:
        return 400, {"error": "user_id is required"}
    gtype = body.get("type", "emergency_fund")
    if gtype == "debt_payoff":
        target = body.get("target_amount")
        if target is None and isinstance(body.get("target"), dict):
            target = body["target"].get("amount")
        if target is None:
            return 400, {"error": "target_amount is required"}
        try:
            target_f = float(target)
        except (TypeError, ValueError):
            return 400, {"error": "target_amount must be a number"}
        try:
            goal = STORE.create_debt_for_user(
                str(user_id),
                target_amount=target_f,
                current_amount=float(body.get("current_amount") or 0),
                title=body.get("title"),
                subtype=body.get("subtype"),
                monthly_contribution=float(body.get("monthly_contribution") or 0),
                plan_method=body.get("plan_method") or body.get("method"),
            )
        except ValueError as e:
            return 409 if "already has" in str(e) else 400, {"error": str(e)}
        _sync_debt_flags(str(user_id), goal)
        return 201, goal.to_dict()
    if gtype != "emergency_fund":
        return 400, {"error": "Only type=emergency_fund or type=debt_payoff supported"}
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
    if hasattr(STORE, "list_for_user"):
        items = [g.to_dict() for g in STORE.list_for_user(user_id, type)]
        return 200, {"items": items}
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
    if getattr(goal, "type", None) == "debt_payoff":
        _sync_debt_flags(goal.user_id, goal)
    return 200, goal.to_dict()


def _mastery_block(flags: dict) -> dict:
    state = str(flags.get("mastery_no_efund_invest") or "not_started")
    return {
        "node_id": "no_efund_invest",
        "state": state,
        "meets_gate": state in ("apply", "mastered"),
        "gate_min": "apply",
    }


def _apply_debt_goal_flags(user_id: str, flags: dict) -> dict:
    debt = None
    if hasattr(STORE, "get_debt_for_user"):
        try:
            debt = STORE.get_debt_for_user(user_id)
        except Exception:
            debt = None
    if debt:
        from welora.goal_debt_payoff import debt_on_track_from_goal, has_dangerous_debt_from_goal

        flags["has_dangerous_debt"] = has_dangerous_debt_from_goal(debt)
        flags["debt_on_track"] = debt_on_track_from_goal(debt)
        flags["debt_goal_id"] = debt.goal_id
        flags["debt_goal_progress_percent"] = debt.percent
    return flags


def service_safety_gate(user_id: str) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    goal = STORE.get_active_for_user(user_id)
    flags = get_user_flags(user_id)
    if _use_db_store():
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
    flags = _apply_debt_goal_flags(user_id, flags)
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
