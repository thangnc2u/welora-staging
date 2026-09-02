"""
Welora P1-E1-03 — SQLite repositories

SqliteEmergencyFundStore + SqliteOnboardingRepository + user flags helpers.
Preserves service API used by goals_api / onboarding.
"""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import uuid4

from welora.db.connection import get_connection
from welora.db.migrate import migrate
from welora.goal_emergency_fund import (
    EmergencyFundGoal,
    apply_progress,
    create_emergency_fund_goal,
)
from welora import onboarding as ob


def get_user_flags_db(user_id: str, *, url: str | None = None) -> dict[str, Any]:
    migrate(url)
    conn = get_connection(url)
    try:
        row = conn.execute(
            "SELECT has_dangerous_debt, debt_on_track, mastery_no_efund_invest, recent_violations "
            "FROM user_flags WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if not row:
            return {
                "has_dangerous_debt": False,
                "debt_on_track": True,
                "mastery_no_efund_invest": "not_started",
                "recent_violations": 0,
            }
        return {
            "has_dangerous_debt": bool(row["has_dangerous_debt"]),
            "debt_on_track": bool(row["debt_on_track"]),
            "mastery_no_efund_invest": row["mastery_no_efund_invest"] or "not_started",
            "recent_violations": int(row["recent_violations"] or 0),
        }
    finally:
        conn.close()


def set_user_flags_db(
    user_id: str,
    *,
    has_dangerous_debt: bool = False,
    debt_on_track: bool = True,
    mastery_no_efund_invest: str = "not_started",
    recent_violations: int = 0,
    url: str | None = None,
) -> None:
    migrate(url)
    conn = get_connection(url)
    try:
        conn.execute(
            "INSERT INTO users(user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
            (user_id,),
        )
        conn.execute(
            """
            INSERT INTO user_flags(user_id, has_dangerous_debt, debt_on_track, mastery_no_efund_invest, recent_violations)
            VALUES (?,?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET
              has_dangerous_debt=excluded.has_dangerous_debt,
              debt_on_track=excluded.debt_on_track,
              mastery_no_efund_invest=excluded.mastery_no_efund_invest,
              recent_violations=excluded.recent_violations,
              updated_at=datetime('now')
            """,
            (user_id, int(has_dangerous_debt), int(debt_on_track), mastery_no_efund_invest, recent_violations),
        )
        conn.commit()
    finally:
        conn.close()


class SqliteEmergencyFundStore:
    def __init__(self, url: str | None = None) -> None:
        self.url = url
        migrate(url)

    def _conn(self):
        return get_connection(self.url)

    def save(self, goal: EmergencyFundGoal) -> EmergencyFundGoal:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO users(user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
                (goal.user_id,),
            )
            conn.execute(
                """
                INSERT INTO goals(
                  goal_id, user_id, type, status, title, target_amount, months_of_expense,
                  target_date, current_amount, essential_expense_monthly, safety_gate_relevant,
                  linked_from_onboarding, plan_json, created_at, updated_at, completed_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(goal_id) DO UPDATE SET
                  status=excluded.status,
                  current_amount=excluded.current_amount,
                  target_amount=excluded.target_amount,
                  essential_expense_monthly=excluded.essential_expense_monthly,
                  plan_json=excluded.plan_json,
                  updated_at=excluded.updated_at,
                  completed_at=excluded.completed_at
                """,
                (
                    goal.goal_id,
                    goal.user_id,
                    goal.type,
                    goal.status,
                    goal.title,
                    goal.target_amount,
                    goal.months_of_expense,
                    goal.target_date,
                    goal.current_amount,
                    goal.essential_expense_monthly,
                    int(goal.safety_gate_relevant),
                    int(goal.linked_from_onboarding),
                    json.dumps({"monthly_contribution": goal.monthly_contribution, "method": goal.plan_method}),
                    goal.created_at,
                    goal.updated_at,
                    goal.updated_at if goal.status == "completed" else None,
                ),
            )
            conn.commit()
            return goal
        finally:
            conn.close()

    def get(self, goal_id: str) -> Optional[EmergencyFundGoal]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM goals WHERE goal_id=?", (goal_id,)).fetchone()
            return self._row_to_goal(row) if row else None
        finally:
            conn.close()

    def get_active_for_user(self, user_id: str) -> Optional[EmergencyFundGoal]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM goals WHERE user_id=? AND type='emergency_fund' "
                "AND status IN ('active','completed') ORDER BY updated_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            return self._row_to_goal(row) if row else None
        finally:
            conn.close()

    def create_for_user(self, user_id: str, essential_expense_monthly: float, **kwargs: Any) -> EmergencyFundGoal:
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

    def get_debt_for_user(self, user_id: str) -> Optional[EmergencyFundGoal]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM goals WHERE user_id=? AND type='debt_payoff' "
                "AND status IN ('active','completed') ORDER BY updated_at DESC LIMIT 1",
                (user_id,),
            ).fetchone()
            return self._row_to_goal(row) if row else None
        finally:
            conn.close()

    def list_for_user(self, user_id: str, type: Optional[str] = None):
        items = []
        ef = self.get_active_for_user(user_id)
        debt = self.get_debt_for_user(user_id)
        for g in (ef, debt):
            if g and (type is None or g.type == type):
                items.append(g)
        return items

    def create_debt_for_user(self, user_id: str, **kwargs: Any) -> EmergencyFundGoal:
        from welora.goal_debt_payoff import create_debt_payoff_goal
        existing = self.get_debt_for_user(user_id)
        if existing and existing.status in ("active", "completed"):
            raise ValueError(
                f"User {user_id} already has debt_payoff goal {existing.goal_id} ({existing.status})"
            )
        goal = create_debt_payoff_goal(user_id=user_id, **kwargs)
        return self.save(goal)

    def _row_to_goal(self, row) -> EmergencyFundGoal:
        plan = {}
        try:
            plan = json.loads(row["plan_json"] or "{}")
        except Exception:
            pass
        from welora.safety_gate import compute_progress_percent

        percent = compute_progress_percent(row["current_amount"] or 0, row["target_amount"] or 1)
        return EmergencyFundGoal(
            goal_id=row["goal_id"],
            user_id=row["user_id"],
            type=row["type"],
            title=row["title"] or "Quỹ khẩn cấp",
            status=row["status"],
            principle_keys=(["DEBT-01", "DEBT-03", "CORE-07"] if row["type"] == "debt_payoff" else ["SAFE-01", "CORE-07"]),
            target_amount=float(row["target_amount"] or 0),
            target_unit="VND",
            months_of_expense=int(row["months_of_expense"] or 3),
            target_date=row["target_date"],
            current_amount=float(row["current_amount"] or 0),
            percent=percent,
            last_updated_at=row["updated_at"] or "",
            safety_gate_relevant=bool(row["safety_gate_relevant"]),
            monthly_contribution=float(plan.get("monthly_contribution") or 0),
            plan_method=plan.get("method"),
            linked_from_onboarding=bool(row["linked_from_onboarding"]),
            essential_expense_monthly=float(row["essential_expense_monthly"] or 0),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )


class SqliteOnboardingRepository:
    """Persists sessions via in-memory onboarding + DNA/constitution tables when completed."""

    def __init__(self, url: str | None = None) -> None:
        self.url = url
        migrate(url)

    def create_session(self, user_id: str):
        return ob.create_session(user_id)

    def patch_step(self, session_id: str, step: int, payload: dict):
        return ob.patch_step(session_id, step, payload)

    def complete_session(self, session_id: str) -> dict:
        result = ob.complete_session(session_id)
        dna = result["dna"]
        constitution = result["personal_constitution"]
        user_id = result["session"]["user_id"]
        conn = get_connection(self.url)
        try:
            conn.execute(
                "INSERT INTO users(user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING",
                (user_id,),
            )
            conn.execute(
                """
                INSERT INTO dna_profiles(user_id, life_stage, income_stability, family_context,
                  essential_expense_monthly, emergency_fund_months_self, has_dangerous_debt_self,
                  near_term_priority, surplus_habit, risk_tolerance, agent_role_preference, raw_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET raw_json=excluded.raw_json, updated_at=datetime('now')
                """,
                (
                    user_id,
                    (dna.get("identity_context") or {}).get("life_stage"),
                    (dna.get("identity_context") or {}).get("income_stability"),
                    (dna.get("identity_context") or {}).get("family_context"),
                    (dna.get("financial_snapshot_self") or {}).get("essential_expense_monthly"),
                    str((dna.get("financial_snapshot_self") or {}).get("emergency_fund_months_self") or ""),
                    int(bool((dna.get("financial_snapshot_self") or {}).get("has_dangerous_debt_self"))),
                    (dna.get("financial_snapshot_self") or {}).get("near_term_priority"),
                    (dna.get("psychological_profile_self") or {}).get("surplus_habit"),
                    (dna.get("psychological_profile_self") or {}).get("risk_tolerance"),
                    (dna.get("psychological_profile_self") or {}).get("agent_role_preference"),
                    json.dumps(dna, ensure_ascii=False),
                ),
            )
            conn.execute(
                """
                INSERT INTO constitutions(user_id, version, articles_json)
                VALUES (?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET articles_json=excluded.articles_json, updated_at=datetime('now')
                """,
                (user_id, constitution.get("version") or "1.0", json.dumps(constitution.get("articles") or [], ensure_ascii=False)),
            )
            conn.commit()
        finally:
            conn.close()
        return result
