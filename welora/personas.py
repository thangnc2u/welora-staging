"""
Welora — PRD Chân dung P1–P6 v2 (canonical).

Replaces 4-persona / DNA-USER-2026-* fixtures (8/2026).
Chrome / onboarding schema only — does not touch Hard Deny, TARGET_MONTHS, CORE, Cổng.

Product law:
  - 3 trụ: Welorapedia · Welorademy · WeloraOS. Agent ≠ trụ 4.
  - DNA skeleton ≤7 answers; no real money numbers; no KUAT hard lock.
  - OS goals MVP only: emergency_fund | debt_payoff.
  - Demo seed prioritizes P2 + P4.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Optional

# --- Enums / constants -------------------------------------------------------

PERSONA_IDS = ("P1", "P2", "P3", "P4", "P5", "P6")

HOUSEHOLD_VALUES = frozenset({
    "solo",
    "young_family",
    "couple_no_kids",
    "sandwich_3gen",
    "pre_retire",
    "retire_companion",
})

# Legacy life_stage (Founder 04/09) → household (PRD v2). Retained for API compat.
LEGACY_LIFE_STAGE_TO_HOUSEHOLD: dict[str, str] = {
    "young_single": "solo",
    "established_single": "solo",
    "young_couple": "couple_no_kids",
    "family": "young_family",
    "pre_retire": "pre_retire",
    "retired": "retire_companion",
}

HOUSEHOLD_TO_PERSONA: dict[str, str] = {
    "solo": "P1",
    "young_family": "P2",
    "couple_no_kids": "P3",
    "sandwich_3gen": "P4",
    "pre_retire": "P5",
    "retire_companion": "P6",
}

OS_GOAL_TYPES_MVP = frozenset({"emergency_fund", "debt_payoff"})

# Forbidden as OS goal.type (narrative primary_goals only)
OS_GOAL_TYPES_FORBIDDEN = frozenset({
    "education",
    "retirement",
    "net_worth",
    "investment",
    "investments",
    "nw",
})

PRODUCT_PILLARS = ("Welorapedia", "Welorademy", "WeloraOS")
# Agent is Advisory + Guardrail on 3 pillars — never pillar 4
AGENT_IS_PILLAR = False

# Demo seed order — Founder lock: prioritize P2 + P4 first
DEMO_SEED_ORDER = ("P2", "P4", "P1", "P3", "P5", "P6")

# DNA answer ids (≤7) — voice/examples only; no money numbers
DNA_SKELETON_IDS = ("A1", "A2", "A3", "B1", "B2", "B3", "B4")

# Retired 4-persona / DNA-USER-2026-* (8/2026) — do not revive in seeds/onboarding
RETIRED_DNA_USER_2026: dict[str, Any] = {
    "status": "retired",
    "retired_at": "2026-09-19",
    "replaced_by": "P1-P6",
    "fixture_ids": (
        "DNA-USER-2026-01",
        "DNA-USER-2026-02",
        "DNA-USER-2026-03",
        "DNA-USER-2026-04",
    ),
    "note": (
        "4 persona mẫu 8/2026 (Welora_Financial_DNA_va_4_Persona) retired. "
        "Canonical is personas.PERSONAS P1–P6."
    ),
}


def _dna(a1: str, a2: str, a3: str, b1: str, b2: str, b3: str, b4: str) -> dict[str, str]:
    return {
        "A1": a1,
        "A2": a2,
        "A3": a3,
        "B1": b1,
        "B2": b2,
        "B3": b3,
        "B4": b4,
    }


# --- Canonical catalog -------------------------------------------------------

PERSONAS: dict[str, dict[str, Any]] = {
    "P1": {
        "persona_id": "P1",
        "label_vi": "Độc thân đô thị 18+",
        "age_band": "18–29",
        "household": "solo",
        "income_band_vnd_mo": "12–20tr net",  # [Inf] band — not in DNA
        "primary_goals": [
            "Quỹ dự phòng",
            "Bảo vệ (BH)",
            "Bắt đầu hưu/dài hạn",  # narrative only — not OS goal
        ],
        "os_accounts": [
            {"name": "Chi tiêu hàng ngày", "type": "chi_tieu_hang_ngay", "opening_balance": None},
            {"name": "Quỹ dự phòng", "type": "tiet_kiem", "opening_balance": None},
            {"name": "Thẻ tín dụng (optional)", "type": "no", "opening_balance": None},
        ],
        "os_goals": [
            {"type": "emergency_fund", "priority": 1},
            {"type": "debt_payoff", "priority": 2, "optional": True},
        ],
        "budget_tags": ["an_uong", "di_chuyen", "giai_tri", "pyf"],
        "academy_emphasis": ["02.2", "02.1", "02.3", "02.6", "02.7"],
        "kuat_hint": (1, 2),
        "risk_soft": "Cao",
        "pillars": {
            "Welorapedia": "SAFE-01/02; DEBT nếu có thẻ",
            "Welorademy": "02.2 → 02.1 → 02.3 → 02.6 → 02.7",
            "WeloraOS": "EF 3 tháng; optional nợ thẻ",
        },
        "dna_answers": _dna(
            "Dựng quỹ 3 tháng chi thiết yếu",
            "Chi hết lương mỗi tháng",
            "Có lưới an toàn rõ ràng",
            "Mất việc / mất thu nhập",
            "Cắt chi không cần thiết",
            "Không có ngân sách",
            "Hối tiếc mua sắm xung động",
        ),
    },
    "P2": {
        "persona_id": "P2",
        "label_vi": "25–34 Gia đình trẻ khởi đầu",
        "age_band": "25–34",
        "household": "young_family",
        "income_band_vnd_mo": "hộ 20–35tr",
        "primary_goals": [
            "Quỹ DP 6 tháng",  # life goal narrative; gate still 3
            "BH trụ cột",
            "Quỹ giáo dục",  # narrative ≠ OS goal
            "Ngân sách hộ",
        ],
        "os_accounts": [
            {"name": "Chi tiêu hộ", "type": "chi_tieu_hang_ngay", "opening_balance": None},
            {"name": "Quỹ dự phòng", "type": "tiet_kiem", "opening_balance": None},
            {"name": "Nợ (optional)", "type": "no", "opening_balance": None},
        ],
        "os_goals": [
            {"type": "emergency_fund", "priority": 1},
            {"type": "debt_payoff", "priority": 2, "optional": True},
        ],
        "budget_tags": ["hoc_phi_con", "bao_hiem", "nha_o", "an_uong"],
        "academy_emphasis": ["02.1", "02.2", "02.3", "02.4", "02.8"],
        "kuat_hint": (2, 2),
        "risk_soft": "Cao",
        "pillars": {
            "Welorapedia": "SAFE + BH narrative; DEBT nếu thẻ",
            "Welorademy": "02.1 → 02.2 → 02.3 → 02.4 → 02.8",
            "WeloraOS": "EF; gate hard 3 tháng dù life-goal 6–12",
        },
        "dna_answers": _dna(
            "An toàn 12 tháng cho con",
            "Chi tăng khi có con",
            "Gia đình có lưới",
            "Ốm / mất thu nhập",
            "Ưu tiên BH và quỹ",
            "Hai người cùng chi",
            "Nợ tiêu dùng",
        ),
        "demo_priority": 1,
    },
    "P3": {
        "persona_id": "P3",
        "label_vi": "35–59 Nâng đỡ hai đầu (không con nhỏ)",
        "age_band": "35–59",
        "household": "couple_no_kids",
        "income_band_vnd_mo": "hộ 25–45tr",
        "primary_goals": [
            "Ngân sách hỗ trợ gia đình",
            "Quỹ dự phòng",
            "Nợ xấu nếu có",
            "Tỷ lệ tiết kiệm",
        ],
        "os_accounts": [
            {"name": "Chi tiêu", "type": "chi_tieu_hang_ngay", "opening_balance": None},
            {"name": "Tiết kiệm hỗ trợ GM", "type": "tiet_kiem", "opening_balance": None},
            {"name": "Quỹ dự phòng", "type": "tiet_kiem", "opening_balance": None},
        ],
        "os_goals": [
            {"type": "emergency_fund", "priority": 1},
            {"type": "debt_payoff", "priority": 2, "optional": True},
        ],
        "budget_tags": ["ho-tro-gia-dinh", "bao_hiem", "nha_o"],
        "academy_emphasis": ["02.1", "02.6", "02.2", "02.4", "02.5"],
        "kuat_hint": (2, 3),
        "risk_soft": "Cao",
        "pillars": {
            "Welorapedia": "SAFE + hỗ trợ GM; DEBT nếu có",
            "Welorademy": "02.1 → 02.6 → 02.2 → 02.4 → 02.5",
            "WeloraOS": "EF; tag ho-tro-gia-dinh",
        },
        "dna_answers": _dna(
            "Cân bằng hỗ trợ cha mẹ vs bản thân",
            "Xung đột ưu tiên",
            "Có quỹ riêng",
            "Cha mẹ bệnh",
            "Cắt mong muốn",
            "Áp lực gia đình",
            "Cho mượn quá nhiều",
        ),
        "narrative_note": "couple_no_kids + hỗ trợ cha mẹ",
    },
    "P4": {
        "persona_id": "P4",
        "label_vi": "35–59 Ba đời trên một take-home",
        "age_band": "35–59",
        "household": "sandwich_3gen",
        "income_band_vnd_mo": "1 take-home 18–30tr nuôi hộ",
        "primary_goals": [
            "Dòng tiền sống sót",
            "Cắt nợ xấu",
            "Quỹ DP tối thiểu 3 tháng",
            "BH trụ cột",
        ],
        "os_accounts": [
            {"name": "Chi tiêu duy nhất", "type": "chi_tieu_hang_ngay", "opening_balance": None},
            {"name": "Quỹ dự phòng mỏng", "type": "tiet_kiem", "opening_balance": None},
            {"name": "Nợ", "type": "no", "opening_balance": None},
        ],
        "os_goals": [
            {"type": "debt_payoff", "priority": 1},
            {"type": "emergency_fund", "priority": 2},
        ],
        "budget_tags": ["hoc_phi", "ho-tro-gia-dinh", "tra_no"],
        "academy_emphasis": ["02.4", "02.1", "02.2", "02.3", "02.8"],
        "kuat_hint": (1, 2),
        "risk_soft": "Cao",
        "pillars": {
            "Welorapedia": "DEBT-01/02/03 trước; SAFE tối thiểu",
            "Welorademy": "02.4 → 02.1 → 02.2 → 02.3 → 02.8",
            "WeloraOS": "debt_payoff first + EF 3×",
        },
        "dna_answers": _dna(
            "Hết nợ lãi cao",
            "Một lương nuôi ba đời",
            "Không cháy túi",
            "Mất việc",
            "Ưu tiên nhu cầu",
            "Nhiều miệng ăn",
            "Vay tiêu dùng",
        ),
        "demo_priority": 2,
    },
    "P5": {
        "persona_id": "P5",
        "label_vi": "55–64 Cửa sổ 10 năm trước hưu",
        "age_band": "55–64",
        "household": "pre_retire",
        "income_band_vnd_mo": "20–40tr",
        "primary_goals": [
            "Catch-up tiết kiệm hưu",  # narrative ≠ OS goal
            "Quỹ dự phòng",
            "Giảm nợ trước hưu",
            "Net Worth",  # narrative ≠ OS goal
        ],
        "os_accounts": [
            {"name": "Chi tiêu", "type": "chi_tieu_hang_ngay", "opening_balance": None},
            {"name": "Tiết kiệm hưu", "type": "tiet_kiem", "opening_balance": None},
            {"name": "Nợ (optional)", "type": "no", "opening_balance": None},
        ],
        "os_goals": [
            {"type": "emergency_fund", "priority": 1},
            {"type": "debt_payoff", "priority": 2, "optional": True},
        ],
        "budget_tags": ["pyf", "bao_hiem", "nha_o"],
        "academy_emphasis": ["02.6", "02.5", "02.2", "02.7", "02.8"],
        "kuat_hint": (2, 3),
        "risk_soft": "Cao",
        "pillars": {
            "Welorapedia": "SAFE dày; không nhảy M03 đầu tư",
            "Welorademy": "02.6 → 02.5 → 02.2 → 02.7 → 02.8",
            "WeloraOS": "EF; debt_payoff trước hưu — không Investments UI",
        },
        "dna_answers": _dna(
            "Đủ đệm trước hưu",
            "Sợ trễ",
            "Kế hoạch 10 năm",
            "Lạm phát / y tế",
            "Thận trọng",
            "Không biết bắt đầu",
            "Đầu tư theo cảm xúc",
        ),
    },
    "P6": {
        "persona_id": "P6",
        "label_vi": "65+ Tuổi vàng và hộ đồng hành",
        "age_band": "65+",
        "household": "retire_companion",
        "income_band_vnd_mo": "lương hưu / tiền gửi 8–20tr",
        "primary_goals": [
            "Dòng tiền ổn định",
            "Y tế / BH",
            "Di sản",  # Pedia CORE-10 narrative
            "Sống bền",
        ],
        "os_accounts": [
            {"name": "Chi tiêu", "type": "chi_tieu_hang_ngay", "opening_balance": None},
            {"name": "Tiết kiệm thanh khoản", "type": "tiet_kiem", "opening_balance": None},
        ],
        "os_goals": [
            {"type": "emergency_fund", "priority": 1},
        ],
        "budget_tags": ["bao_hiem", "nha_o", "an_uong", "giai_tri"],
        "academy_emphasis": ["02.2", "02.3", "02.5", "02.1", "02.8"],
        "kuat_hint": (1, 2),
        "risk_soft": "Cao",
        "pillars": {
            "Welorapedia": "SAFE + bền vững/di sản narrative",
            "Welorademy": "02.2 → 02.3 → 02.5 → 02.1 → 02.8 (giọng chậm)",
            "WeloraOS": "EF y tế; hiếm nợ",
        },
        "dna_answers": _dna(
            "Yên tâm chi tiêu",
            "Sợ tốn y tế",
            "Con không phải gánh",
            "Bệnh dài ngày",
            "Giữ tiền mặt",
            "Phụ thuộc con",
            "Quyết định vội",
        ),
        # Life pillars (narrative) map into 3 product pillars only — Agent ≠ pillar 4
        "life_pillars_narrative": (
            "dòng tiền ổn định",
            "y tế/BH",
            "di sản / hộ đồng hành",
            "chất lượng sống",
        ),
    },
}


HOUSEHOLD_LABEL_VI: dict[str, str] = {
    p["household"]: p["label_vi"] for p in PERSONAS.values()
}


def get_persona(persona_id: str) -> dict[str, Any]:
    pid = (persona_id or "").upper().strip()
    if pid not in PERSONAS:
        raise KeyError(f"unknown persona_id: {persona_id}")
    return deepcopy(PERSONAS[pid])


def persona_for_household(household: str) -> dict[str, Any]:
    h = normalize_household(household)
    return get_persona(HOUSEHOLD_TO_PERSONA[h])


def normalize_household(value: str) -> str:
    """Accept household or legacy life_stage; return canonical household."""
    v = (value or "").strip()
    if v in HOUSEHOLD_VALUES:
        return v
    if v in LEGACY_LIFE_STAGE_TO_HOUSEHOLD:
        return LEGACY_LIFE_STAGE_TO_HOUSEHOLD[v]
    raise ValueError(
        f"household must be one of: {', '.join(sorted(HOUSEHOLD_VALUES))} "
        f"(or legacy life_stage)"
    )


def resolve_step1_identity(payload: dict[str, Any]) -> dict[str, str]:
    """
    Normalize onboarding step-1 identity fields.

    Accepts ``household`` and/or legacy ``life_stage``.
    Returns household, persona_id, life_stage (= household for DNA chrome).
    """
    raw = payload.get("household")
    if raw is None or raw == "":
        raw = payload.get("life_stage")
    if raw is None or raw == "":
        raise ValueError("step 1 requires household (or legacy life_stage)")
    household = normalize_household(str(raw))
    persona_id = HOUSEHOLD_TO_PERSONA[household]
    return {
        "household": household,
        "persona_id": persona_id,
        "life_stage": household,  # DNA/chrome: life_stage key carries household enum
    }


def os_goal_types(persona_id: str) -> list[str]:
    p = get_persona(persona_id)
    return [g["type"] for g in p["os_goals"]]


def dna_skeleton(persona_id: str) -> dict[str, str]:
    return dict(get_persona(persona_id)["dna_answers"])


def assert_dna_skeleton_clean(answers: dict[str, str]) -> None:
    """DoD: ≤7 answers, no money-like numbers, keys A1–A3+B1–B4."""
    if len(answers) > 7:
        raise AssertionError(f"DNA skeleton has {len(answers)} answers; max 7")
    for k in DNA_SKELETON_IDS:
        if k not in answers:
            raise AssertionError(f"DNA skeleton missing {k}")
    # No digits that look like money amounts (allow "3 tháng", "12 tháng", "10 năm")
    import re
    moneyish = re.compile(
        r"(?:\d{1,3}(?:[.,]\d{3})+|\d+\s*(?:tr|triệu|đ|vnd|vnđ))",
        re.IGNORECASE,
    )
    for k, v in answers.items():
        if moneyish.search(str(v)):
            raise AssertionError(f"DNA {k} contains money-like number: {v!r}")


def assert_os_goals_mvp(persona_id: str) -> None:
    for t in os_goal_types(persona_id):
        if t not in OS_GOAL_TYPES_MVP:
            raise AssertionError(f"{persona_id} os_goal type {t!r} not in MVP")
        if t in OS_GOAL_TYPES_FORBIDDEN:
            raise AssertionError(f"{persona_id} os_goal type {t!r} is forbidden")


def demo_seed_personas(*, only_priority: bool = True) -> list[dict[str, Any]]:
    """Return persona dicts for demo seed — P2 then P4 first."""
    order = DEMO_SEED_ORDER
    if only_priority:
        order = tuple(pid for pid in order if PERSONAS[pid].get("demo_priority"))
    return [get_persona(pid) for pid in order]


def is_retired_dna_user_fixture(fixture_id: str) -> bool:
    return str(fixture_id) in RETIRED_DNA_USER_2026["fixture_ids"] or str(
        fixture_id
    ).startswith("DNA-USER-2026-")


def list_active_fixture_ids() -> list[str]:
    """Active demo/onboarding fixture ids — never DNA-USER-2026-*."""
    return list(DEMO_SEED_ORDER)


def pillars_for(persona_id: str) -> dict[str, str]:
    p = get_persona(persona_id)
    out = dict(p["pillars"])
    # Enforce product law: only 3 pillars
    for k in list(out.keys()):
        if k not in PRODUCT_PILLARS:
            del out[k]
    assert "Agent" not in out
    return out
