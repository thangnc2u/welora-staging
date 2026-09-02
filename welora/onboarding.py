"""
Welora — S1-05: Onboarding session API (service layer)

Flow B0–B5 → DNA Self + Personal Constitution
Aligned with Welora_E1_Onboarding_Spec_v1
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

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


def create_session(user_id: str) -> OnboardingSession:
    if not user_id:
        raise ValueError("user_id is required")
    s = OnboardingSession(
        session_id=str(uuid4()),
        user_id=str(user_id),
        current_step=0,
        status="draft",
    )
    SESSIONS[s.session_id] = s
    return s


def get_session(session_id: str) -> Optional[OnboardingSession]:
    return SESSIONS.get(session_id)


def patch_step(session_id: str, step: int, payload: dict[str, Any]) -> OnboardingSession:
    s = SESSIONS.get(session_id)
    if not s:
        raise KeyError("session not found")
    if s.status == "completed":
        raise ValueError("session already completed")
    if step < 0 or step > 5:
        raise ValueError("step must be 0..5")

    data = dict(payload or {})
    if step == 1:
        for req in ("life_stage", "income_stability", "family_context"):
            if req not in data:
                raise ValueError(f"step 1 requires {req}")
    if step == 2:
        if "essential_expense_monthly" not in data:
            raise ValueError("step 2 requires essential_expense_monthly")
        try:
            ess = float(data["essential_expense_monthly"])
        except (TypeError, ValueError) as e:
            raise ValueError("essential_expense_monthly must be a number") from e
        if ess <= 0:
            raise ValueError("essential_expense_monthly must be > 0")
        data["essential_expense_monthly"] = ess
        if "has_dangerous_debt_self" in data:
            data["has_dangerous_debt_self"] = bool(data["has_dangerous_debt_self"])

    if step == 4:
        articles = data.get("articles")
        if articles is None:
            data["articles"] = deepcopy(DEFAULT_ARTICLES)
        data.setdefault("custom_principles", [])

    s.steps[step] = data
    s.current_step = max(s.current_step, step)
    s.updated_at = _now()
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
            "life_stage": b1.get("life_stage"),
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
    s = SESSIONS.get(session_id)
    if not s:
        raise KeyError("session not found")
    if s.status == "completed":
        raise ValueError("session already completed")
    if 1 not in s.steps or 2 not in s.steps:
        raise ValueError("steps 1 and 2 required before complete")

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

    essential = (dna["financial_snapshot_self"].get("essential_expense_monthly") or 0)
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
    }


def get_dna(user_id: str) -> Optional[dict[str, Any]]:
    return DNA_BY_USER.get(user_id)


def get_constitution(user_id: str) -> Optional[dict[str, Any]]:
    return CONSTITUTION_BY_USER.get(user_id)


def reset_onboarding_stores() -> None:
    SESSIONS.clear()
    DNA_BY_USER.clear()
    CONSTITUTION_BY_USER.clear()
