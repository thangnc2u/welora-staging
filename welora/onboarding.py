"""
Welora — S1-05: Onboarding session API (service layer)

Flow B0–B5 → DNA Self + Personal Constitution
Aligned with Welora_E1_Onboarding_Spec_v1
"""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from welora.personas import (
    FAMILY_CONTEXT_VALUES,
    HOUSEHOLD_VALUES,
    LEGACY_LIFE_STAGE_TO_HOUSEHOLD,
    apply_debt_priority_lock,
    debt_cta_allowed,
    normalize_emergency_fund_months_self,
    resolve_step1_identity,
    validate_household_family_context,
)

DEFAULT_ARTICLES = [
    {
        "code": "PC-01",
        "source_core": "CORE-01",
        "text": "Tôi chịu trách nhiệm cuối cùng cho quyết định tài chính của mình.",
        "priority": 1,
        "user_confirmed": True,
    },
    {
        "code": "PC-07",
        "source_core": "CORE-07",
        "text": "Tôi ưu tiên An Toàn (quỹ khẩn cấp ≥ 3 tháng) trước khi tăng trưởng.",
        "priority": 2,
        "user_confirmed": True,
    },
    {
        "code": "PC-SAFE-02",
        "source_core": "SAFE-02",
        "text": "Tôi không dùng quỹ khẩn cấp để đầu tư hoặc chi tiêu đã lên kế hoạch.",
        "priority": 3,
        "user_confirmed": True,
    },
    {
        "code": "PC-05",
        "source_core": "CORE-05",
        "text": "Tôi không để FOMO hoặc cảm xúc quyết định thay cho nguyên tắc.",
        "priority": 4,
        "user_confirmed": True,
    },
]


# UI allowlists — must match welora/api/static/onboarding.html <option value=…>
# PRD v2: household enums (P1–P6). Legacy life_stage aliases accepted via personas.normalize_household.
LIFE_STAGE_VALUES = HOUSEHOLD_VALUES | frozenset(LEGACY_LIFE_STAGE_TO_HOUSEHOLD.keys())
INCOME_STABILITY_VALUES = frozenset({"stable", "variable"})
NEAR_TERM_PRIORITY_VALUES = frozenset({"safety", "debt"})
SURPLUS_HABIT_VALUES = frozenset({"hold", "spend"})
AGENT_ROLE_PREFERENCE_VALUES = frozenset({"advisor_only"})
RISK_TOLERANCE_VALUES = frozenset({1, 2, 3, 4, 5})


class OnboardingEnumError(ValueError):
    """Enum outside UI allowlist — HTTP layer maps to 422."""


# GP UAT: every onboarding validation message is Vietnamese (the FE shows ``detail`` verbatim).
FIELD_LABELS_VI = {
    "household": "Hộ gia đình",
    "life_stage": "Hộ gia đình",
    "income_stability": "Mức ổn định thu nhập",
    "family_context": "Hoàn cảnh gia đình",
    "essential_expense_monthly": "Chi tiêu thiết yếu mỗi tháng",
    "emergency_fund_months_self": "Số tháng quỹ dự phòng hiện có",
    "has_dangerous_debt_self": "Nợ nguy hiểm",
    "near_term_priority": "Ưu tiên gần",
    "surplus_habit": "Thói quen với tiền dư",
    "risk_tolerance": "Mức chấp nhận rủi ro",
    "agent_role_preference": "Vai trò của Agent",
}
MSG_USER_ID_REQUIRED = "Thiếu mã người dùng — vui lòng đăng nhập hoặc bắt đầu lại."
MSG_SESSION_NOT_FOUND = "Không tìm thấy phiên onboarding — vui lòng bắt đầu lại."
MSG_SESSION_COMPLETED = "Phiên onboarding này đã hoàn tất."
MSG_STEP_RANGE = "Bước không hợp lệ (chỉ từ 0 đến 5)."
MSG_STEPS_REQUIRED = "Cần hoàn tất bước 1 và 2 trước khi tạo kết quả."


def _enum_msg(field: str) -> str:
    return f"{FIELD_LABELS_VI.get(field, field)}: lựa chọn chưa hợp lệ — vui lòng chọn một mục có sẵn."


def _missing_msg(step: int, field: str) -> str:
    return f"Bước {step}: vui lòng chọn hoặc nhập «{FIELD_LABELS_VI.get(field, field)}»."


def _require_enum(field: str, value: Any, allowed: frozenset) -> Any:
    if value not in allowed:
        raise OnboardingEnumError(_enum_msg(field))
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class OnboardingSession:
    session_id: str
    user_id: str
    current_step: int
    status: str
    steps: dict[int, dict[str, Any]] = field(default_factory=dict)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    completed_at: Optional[str] = None
    dna_id: Optional[str] = None
    constitution_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "current_step": self.current_step,
            "status": self.status,
            "steps": {str(k): v for k, v in self.steps.items()},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "dna_id": self.dna_id,
            "constitution_id": self.constitution_id,
        }


SESSIONS: dict[str, OnboardingSession] = {}
DNA_BY_USER: dict[str, dict[str, Any]] = {}
CONSTITUTION_BY_USER: dict[str, dict[str, Any]] = {}

log = logging.getLogger("welora.onboarding")


# --- Shared-DB persistence (P0: 201-then-404 across instances/restarts) -------
# When the app runs on a DB store (WELORA_STORE=sqlite|postgres or a Postgres
# WELORA_DB_URL — same rule as goals/accounts), onboarding sessions and the
# completed DNA / Personal Constitution are stored in ``onboarding_sessions`` (001_init
# table + 012 columns; step/payload_json = current_step/steps) through the shared connection layer (Postgres on Render). The DB is the source
# of truth; SESSIONS / DNA_BY_USER stay as a per-process cache. Memory-only mode
# (local default, unit tests) is unchanged.
_MIGRATED: set[str] = set()


def _db_mode() -> bool:
    store = (os.environ.get("WELORA_STORE") or "memory").strip().lower()
    url = (os.environ.get("WELORA_DB_URL") or "").strip()
    if store in ("sqlite", "postgres", "db"):
        return True
    return url.startswith("postgresql://") or url.startswith("postgres://")


def _db_url() -> Optional[str]:
    return (os.environ.get("WELORA_DB_URL") or "").strip() or None


def _conn():
    from welora.db.connection import get_connection
    from welora.db.migrate import migrate

    url = _db_url()
    key = url or ""
    if key not in _MIGRATED:
        migrate(url)
        _MIGRATED.add(key)
    return get_connection(url)


def _with_db(fn):
    """Run fn(conn); on a missing-table error (fresh/reset DB) migrate once and retry."""
    for attempt in (0, 1):
        conn = _conn()
        try:
            out = fn(conn)
            conn.commit()
            return out
        except Exception as e:
            if attempt == 0 and ("no such table" in str(e).lower() or "does not exist" in str(e).lower()):
                _MIGRATED.discard(_db_url() or "")
                continue
            raise
        finally:
            conn.close()


def _row_to_session(row: Any) -> OnboardingSession:
    steps_raw = json.loads(row["payload_json"] or "{}")
    return OnboardingSession(
        session_id=row["session_id"],
        user_id=row["user_id"],
        current_step=int(row["step"] or 0),
        status=row["status"] or "draft",
        steps={int(k): v for k, v in steps_raw.items()},
        created_at=row["created_at"] or _now(),
        updated_at=row["updated_at"] or _now(),
        completed_at=row["completed_at"],
        dna_id=row["dna_id"],
        constitution_id=row["constitution_id"],
    )


def _db_save(s: OnboardingSession, dna: Optional[dict] = None, constitution: Optional[dict] = None) -> None:
    steps_json = json.dumps({str(k): v for k, v in s.steps.items()}, ensure_ascii=False)
    dna_json = json.dumps(dna, ensure_ascii=False) if dna is not None else None
    con_json = json.dumps(constitution, ensure_ascii=False) if constitution is not None else None

    def _do(conn):
        # FK users(user_id) is enforced on Postgres — same guard as SqliteOnboardingRepository.
        conn.execute("INSERT INTO users(user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING", (s.user_id,))
        conn.execute(
            "INSERT INTO onboarding_sessions(session_id, user_id, step, status, payload_json, "
            "created_at, updated_at, completed_at, dna_id, constitution_id, dna_json, constitution_json) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(session_id) DO UPDATE SET step=excluded.step, status=excluded.status, "
            "payload_json=excluded.payload_json, updated_at=excluded.updated_at, completed_at=excluded.completed_at, "
            "dna_id=excluded.dna_id, constitution_id=excluded.constitution_id, "
            "dna_json=COALESCE(excluded.dna_json, onboarding_sessions.dna_json), "
            "constitution_json=COALESCE(excluded.constitution_json, onboarding_sessions.constitution_json)",
            (s.session_id, s.user_id, int(s.current_step), s.status, steps_json, s.created_at, s.updated_at,
             s.completed_at, s.dna_id, s.constitution_id, dna_json, con_json),
        )

    _with_db(_do)


def _db_load(session_id: str) -> Optional[OnboardingSession]:
    row = _with_db(lambda conn: conn.execute(
        "SELECT * FROM onboarding_sessions WHERE session_id=?", (session_id,)
    ).fetchone())
    return _row_to_session(row) if row else None


def _db_latest_completed(user_id: str, column: str) -> Optional[dict[str, Any]]:
    assert column in ("dna_json", "constitution_json")
    row = _with_db(lambda conn: conn.execute(
        f"SELECT {column} AS j FROM onboarding_sessions WHERE user_id=? AND status='completed' "
        f"AND {column} IS NOT NULL ORDER BY completed_at DESC LIMIT 1",
        (user_id,),
    ).fetchone())
    if not row or not row["j"]:
        return None
    try:
        return json.loads(row["j"])
    except ValueError:
        return None


def create_session(user_id: str) -> OnboardingSession:
    if not user_id:
        raise ValueError(MSG_USER_ID_REQUIRED)
    s = OnboardingSession(
        session_id=str(uuid4()),
        user_id=str(user_id),
        current_step=0,
        status="draft",
    )
    SESSIONS[s.session_id] = s
    if _db_mode():
        _db_save(s)
    return s


def get_session(session_id: str) -> Optional[OnboardingSession]:
    if _db_mode():
        s = _db_load(session_id)
        if s is not None:
            SESSIONS[session_id] = s
            return s
        return None
    return SESSIONS.get(session_id)


def patch_step(session_id: str, step: int, payload: dict[str, Any]) -> OnboardingSession:
    s = get_session(session_id)
    if not s:
        raise KeyError(MSG_SESSION_NOT_FOUND)
    if s.status == "completed":
        raise ValueError(MSG_SESSION_COMPLETED)
    if step < 0 or step > 5:
        raise ValueError(MSG_STEP_RANGE)

    data = dict(payload or {})
    if step == 1:
        # household (PRD v2) or legacy life_stage — normalize to household + persona_id
        if "income_stability" not in data:
            raise ValueError(_missing_msg(1, "income_stability"))
        if "family_context" not in data:
            raise ValueError(_missing_msg(1, "family_context"))
        if "household" not in data and "life_stage" not in data:
            raise ValueError(_missing_msg(1, "household"))
        try:
            ident = resolve_step1_identity(data)
        except ValueError as e:
            raise OnboardingEnumError(str(e)) from e
        data["household"] = ident["household"]
        data["persona_id"] = ident["persona_id"]
        data["life_stage"] = ident["life_stage"]
        data["income_stability"] = _require_enum(
            "income_stability", data["income_stability"], INCOME_STABILITY_VALUES
        )
        data["family_context"] = _require_enum(
            "family_context", data["family_context"], FAMILY_CONTEXT_VALUES
        )
        # P2 lock: household → family_context (server never trusts client)
        try:
            validate_household_family_context(data["household"], data["family_context"])
        except ValueError as e:
            # ValueError → HTTP 400 with short VI message
            raise ValueError(str(e)) from e
    if step == 2:
        if "essential_expense_monthly" not in data:
            raise ValueError(_missing_msg(2, "essential_expense_monthly"))
        try:
            ess = float(data["essential_expense_monthly"])
        except (TypeError, ValueError) as e:
            raise ValueError("Chi tiêu thiết yếu mỗi tháng phải là một số (đơn vị ₫).") from e
        if not (ess > 0) or ess == float("inf"):
            raise ValueError("Chi tiêu thiết yếu mỗi tháng phải lớn hơn 0 ₫.")
        data["essential_expense_monthly"] = ess
        # P2 form locks: emergency_fund_months_self ∈ [0, 3]; debt × priority
        if "emergency_fund_months_self" in data:
            try:
                data["emergency_fund_months_self"] = normalize_emergency_fund_months_self(
                    data["emergency_fund_months_self"]
                )
            except ValueError as e:
                raise ValueError(str(e)) from e
        try:
            locked = apply_debt_priority_lock(
                has_dangerous_debt_self=data.get("has_dangerous_debt_self", False),
                near_term_priority=data.get("near_term_priority"),
            )
        except ValueError as e:
            # Combo / range locks → HTTP 400 (not 422 enum)
            raise ValueError(str(e)) from e
        data["has_dangerous_debt_self"] = locked["has_dangerous_debt_self"]
        data["near_term_priority"] = locked["near_term_priority"]

    if step == 3:
        if "surplus_habit" in data:
            data["surplus_habit"] = _require_enum(
                "surplus_habit", data["surplus_habit"], SURPLUS_HABIT_VALUES
            )
        if "agent_role_preference" in data:
            data["agent_role_preference"] = _require_enum(
                "agent_role_preference",
                data["agent_role_preference"],
                AGENT_ROLE_PREFERENCE_VALUES,
            )
        if "risk_tolerance" in data:
            try:
                rt = int(data["risk_tolerance"])
            except (TypeError, ValueError) as e:
                raise OnboardingEnumError(
                    "Mức chấp nhận rủi ro phải là một số từ 1 đến 5."
                ) from e
            data["risk_tolerance"] = _require_enum(
                "risk_tolerance", rt, RISK_TOLERANCE_VALUES
            )

    if step == 4:
        articles = data.get("articles")
        if articles is None:
            data["articles"] = deepcopy(DEFAULT_ARTICLES)
        data.setdefault("custom_principles", [])

    s.steps[step] = data
    s.current_step = max(s.current_step, step)
    s.updated_at = _now()
    if _db_mode():
        _db_save(s)
    return s


def propose_constitution(session: OnboardingSession) -> list[dict[str, Any]]:
    return deepcopy(DEFAULT_ARTICLES)


def _build_dna(session: OnboardingSession) -> dict[str, Any]:
    b1 = session.steps.get(1, {})
    b2 = session.steps.get(2, {})
    b3 = session.steps.get(3, {})
    return {
        "dna_id": str(uuid4()),
        "user_id": session.user_id,
        "source": "onboarding_self",
        "confidence": "self_reported",
        "identity_context": {
            "household": b1.get("household"),
            "persona_id": b1.get("persona_id"),
            "life_stage": b1.get("life_stage") or b1.get("household"),
            "income_stability": b1.get("income_stability"),
            "family_context": b1.get("family_context"),
        },
        "financial_snapshot_self": {
            "essential_expense_monthly": b2.get("essential_expense_monthly"),
            "emergency_fund_months_self": b2.get("emergency_fund_months_self"),
            "has_dangerous_debt_self": bool(b2.get("has_dangerous_debt_self")),
            "near_term_priority": b2.get("near_term_priority"),
        },
        "psychological_profile_self": {
            "surplus_habit": b3.get("surplus_habit"),
            "risk_tolerance": b3.get("risk_tolerance"),
            "agent_role_preference": b3.get("agent_role_preference"),
        },
        "created_at": _now(),
    }


def _build_constitution(session: OnboardingSession) -> dict[str, Any]:
    b4 = session.steps.get(4, {})
    articles = b4.get("articles") or deepcopy(DEFAULT_ARTICLES)
    return {
        "constitution_id": str(uuid4()),
        "user_id": session.user_id,
        "version": "1.0",
        "articles": articles,
        "custom_principles": b4.get("custom_principles") or [],
        "created_at": _now(),
    }


def complete_session(session_id: str) -> dict[str, Any]:
    s = get_session(session_id)
    if not s:
        raise KeyError(MSG_SESSION_NOT_FOUND)
    if s.status == "completed":
        raise ValueError(MSG_SESSION_COMPLETED)
    if 1 not in s.steps or 2 not in s.steps:
        raise ValueError(MSG_STEPS_REQUIRED)

    dna = _build_dna(s)
    constitution = _build_constitution(s)
    DNA_BY_USER[s.user_id] = dna
    CONSTITUTION_BY_USER[s.user_id] = constitution

    s.status = "completed"
    s.completed_at = _now()
    s.updated_at = s.completed_at
    s.dna_id = dna["dna_id"]
    s.constitution_id = constitution["constitution_id"]
    s.current_step = 5
    if _db_mode():
        _db_save(s, dna=dna, constitution=constitution)

    snap = dna["financial_snapshot_self"]
    essential = snap.get("essential_expense_monthly") or 0
    has_dangerous_debt_self = bool(snap.get("has_dangerous_debt_self"))
    near_term_priority = snap.get("near_term_priority")
    # CTA/reason only when debt=true for real (priority alone never unlocks copy)
    needs_debt_cta = debt_cta_allowed(has_dangerous_debt_self)
    cta = {
        "code": "create_emergency_fund_goal",
        "prefill_body": {
            "user_id": s.user_id,
            "essential_expense_monthly": essential,
            "months": 3,
            "type": "emergency_fund",
        },
    }
    os_nudge = {
        "kind": "create_goal",
        "goal_type": "emergency_fund",
        "href": "/app/goals",
        "reason": "Hiến pháp Cá nhân đã xác nhận — tạo Goal quỹ khẩn cấp trên WeloraOS.",
        "principle_key": "SAFE-01",
    }
    # Clear VI CTA only — never auto-POST debt_payoff (user enters amount on Goals).
    debt_cta = None
    if needs_debt_cta:
        debt_cta = {
            "code": "open_debt_payoff_form",
            "href": "/app/goals?focus=debt",
            "reason": "Bạn đã khai nợ nguy hiểm — tạo mục tiêu trả nợ",
            "principle_key": "DEBT-01",
        }
    return {
        "session": s.to_dict(),
        "dna": dna,
        "personal_constitution": constitution,
        "cta": cta,
        "cta_goal": {
            "type": "emergency_fund",
            "months_of_expense": 3,
            "essential_expense_monthly": essential,
            "linked_from_onboarding": True,
            "current_amount": 0,
        },
        "os_nudge": os_nudge,
        "debt_cta": debt_cta,
    }


def get_dna(user_id: str) -> Optional[dict[str, Any]]:
    if _db_mode():
        try:
            d = _db_latest_completed(str(user_id), "dna_json")
            if d is not None:
                return d
        except Exception as e:  # pragma: no cover - DB outage → cache fallback
            log.warning("onboarding dna db read failed: %s", type(e).__name__)
    return DNA_BY_USER.get(user_id)


def get_constitution(user_id: str) -> Optional[dict[str, Any]]:
    if _db_mode():
        try:
            c = _db_latest_completed(str(user_id), "constitution_json")
            if c is not None:
                return c
        except Exception as e:  # pragma: no cover
            log.warning("onboarding constitution db read failed: %s", type(e).__name__)
    return CONSTITUTION_BY_USER.get(user_id)


def reset_onboarding_stores() -> None:
    SESSIONS.clear()
    DNA_BY_USER.clear()
    CONSTITUTION_BY_USER.clear()
