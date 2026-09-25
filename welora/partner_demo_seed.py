"""Idempotent rich demo seed for partner@welora.demo (P2) + demo-p4@welora.demo (P4).

CP parity amounts (Welora_Claude os-demo-personas demo_2 / demo_4).
Does not touch Hard Deny, TARGET_MONTHS, logout Hotfix #4, Pre-Rule, Open Banking,
Investments, or Agent product code beyond demo seed data.

P2 on partner: young_family, emergency_fund + debt_payoff (completed so gate can pass),
non-zero accounts, categories, sample txs, safety_gate=passed.
P4 via alias demo-p4@welora.demo: sandwich_3gen, thin EF + active debt, gate not_passed.
"""

from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any, Optional

from welora import goals_api
from welora import onboarding as ob
from welora.auth import (
    DEMO_DISPLAY,
    DEMO_EMAIL,
    DEMO_PASSWORD,
    DEMO_PHONE,
    _hash_password,
    ensure_auth_schema,
    guest_demo_enabled,
)
from welora.db.connection import get_connection
from welora.goal_debt_payoff import create_debt_payoff_goal
from welora.goal_emergency_fund import create_emergency_fund_goal
from welora.goals_api import set_user_flags
from welora.mode_c_act import set_persona
from welora.os_accounts import (
    SOURCE_MANUAL,
    STATUS_ACTIVE,
    Account,
    STORE as ACC_STORE,
)
from welora.os_categories import (
    KIND_FIXED,
    STATUS_ACTIVE as CAT_ACTIVE,
    Category,
    STORE as CAT_STORE,
    service_seed_defaults,
)
from welora.os_transactions import (
    SOURCE_MANUAL as TX_SOURCE_MANUAL,
    STATUS_ACTIVE as TX_ACTIVE,
    Transaction,
    STORE as TX_STORE,
)
from welora.safety_gate import TARGET_MONTHS, compute_safety_gate_from_amounts

PARTNER_USER_ID = "bc25f9aa-9af4-45ea-b981-adbc41133439"

DEMO_P4_EMAIL = "demo-p4@welora.demo"
DEMO_P4_PHONE = "+84900000004"
DEMO_P4_USER_ID = "a4b5c6d7-e8f9-4012-8456-7e8f90112233"
DEMO_P4_DISPLAY = "Demo P4 Sandwich"

DEMO_P2_ESSENTIAL_VND = 10_000_000
DEMO_P2_EF_CURRENT_VND = 32_000_000
DEMO_P2_CHI_TIEU_VND = 8_000_000
DEMO_P2_QUY_DP_VND = 15_000_000
DEMO_P2_DEBT_TARGET_VND = 15_000_000
DEMO_P2_DEBT_CURRENT_VND = 15_000_000  # completed ⇒ progress 100% + gate passed

DEMO_P4_ESSENTIAL_VND = 20_000_000
DEMO_P4_EF_CURRENT_VND = 3_000_000
DEMO_P4_CHI_TIEU_VND = 2_000_000
DEMO_P4_TIET_KIEM_VND = 3_000_000
DEMO_P4_DEBT_VND = 45_000_000
DEMO_P4_DEBT_PAID_VND = 5_000_000

P2_ACC_CHI = "b2000001-0000-4000-8000-000000000001"
P2_ACC_QUY = "b2000001-0000-4000-8000-000000000002"
P2_ACC_NO = "b2000001-0000-4000-8000-000000000003"
P2_GOAL_EF = "b2000001-0000-4000-8000-0000000000ef"
P2_GOAL_DEBT = "b2000001-0000-4000-8000-0000000000d1"
P2_TX_IDS = (
    "b2000001-0000-4000-8000-000000000101",
    "b2000001-0000-4000-8000-000000000102",
    "b2000001-0000-4000-8000-000000000103",
    "b2000001-0000-4000-8000-000000000104",
)

P4_ACC_CHI = "b4000001-0000-4000-8000-000000000001"
P4_ACC_TIET = "b4000001-0000-4000-8000-000000000002"
P4_ACC_NO = "b4000001-0000-4000-8000-000000000003"
P4_GOAL_EF = "b4000001-0000-4000-8000-0000000000ef"
P4_GOAL_DEBT = "b4000001-0000-4000-8000-0000000000d1"
P4_TX_IDS = (
    "b4000001-0000-4000-8000-000000000101",
    "b4000001-0000-4000-8000-000000000102",
    "b4000001-0000-4000-8000-000000000103",
)


def _now() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _clear_user_demo_data(user_id: str, *, url: Optional[str] = None) -> None:
    for sid, s in list(ob.SESSIONS.items()):
        if getattr(s, "user_id", None) == user_id:
            del ob.SESSIONS[sid]
    ob.DNA_BY_USER.pop(user_id, None)
    ob.CONSTITUTION_BY_USER.pop(user_id, None)
    goals_api.USER_FLAGS.pop(user_id, None)

    store = goals_api.STORE
    if hasattr(store, "_by_id"):
        for gid, g in list(store._by_id.items()):
            if getattr(g, "user_id", None) == user_id:
                store._by_id.pop(gid, None)
        if hasattr(store, "_active_by_user"):
            store._active_by_user.pop(user_id, None)
        if hasattr(store, "_debt_by_user"):
            store._debt_by_user.pop(user_id, None)

    try:
        from welora.mode_c_act import _PERSONAS

        _PERSONAS.pop(user_id, None)
    except Exception:
        pass

    for t in list(TX_STORE.list_for_user(user_id, include_hidden=True)):
        if hasattr(TX_STORE, "delete_hard"):
            TX_STORE.delete_hard(t.transaction_id)
        elif hasattr(TX_STORE, "_by_id"):
            TX_STORE._by_id.pop(t.transaction_id, None)
    for a in list(ACC_STORE.list_for_user(user_id, include_hidden=True)):
        if hasattr(ACC_STORE, "delete_hard"):
            ACC_STORE.delete_hard(a.account_id)
        elif hasattr(ACC_STORE, "_by_id"):
            ACC_STORE._by_id.pop(a.account_id, None)
    for c in list(CAT_STORE.list_for_user(user_id, include_disabled=True)):
        if hasattr(CAT_STORE, "delete_hard"):
            CAT_STORE.delete_hard(c.category_id)
        elif hasattr(CAT_STORE, "_by_id"):
            CAT_STORE._by_id.pop(c.category_id, None)

    store_hint = (os.environ.get("WELORA_STORE") or "memory").strip().lower()
    has_db = bool((os.environ.get("WELORA_DB_URL") or "").strip() or url)
    if store_hint in ("sqlite", "postgres", "db") or (has_db and store_hint != "memory"):
        conn = get_connection(url)
        try:
            for sql in (
                "DELETE FROM goal_history WHERE goal_id IN (SELECT goal_id FROM goals WHERE user_id=?)",
                "DELETE FROM goals WHERE user_id=?",
                "DELETE FROM onboarding_sessions WHERE user_id=?",
                "DELETE FROM dna_profiles WHERE user_id=?",
                "DELETE FROM constitutions WHERE user_id=?",
                "DELETE FROM user_flags WHERE user_id=?",
                "DELETE FROM os_transactions WHERE user_id=?",
                "DELETE FROM os_accounts WHERE user_id=?",
                "DELETE FROM os_categories WHERE user_id=?",
            ):
                try:
                    conn.execute(sql, (user_id,))
                except Exception:
                    pass
            conn.commit()
        finally:
            conn.close()


def _upsert_demo_user(
    *,
    user_id: str,
    email: str,
    phone: str,
    display_name: str,
    password: str = DEMO_PASSWORD,
    url: Optional[str] = None,
) -> dict[str, Any]:
    ensure_auth_schema(url)
    conn = get_connection(url)
    try:
        by_email = conn.execute(
            "SELECT user_id, role FROM users WHERE email=?", (email,)
        ).fetchone()
        pw = _hash_password(password)
        device_key = "demo:" + hashlib.sha256(email.encode()).hexdigest()[:16]
        if by_email:
            existing_id = by_email["user_id"]
            conn.execute(
                "UPDATE users SET display_name=?, phone=?, password_hash=?, role=? WHERE user_id=?",
                (display_name, phone, pw, "demo", existing_id),
            )
            conn.commit()
            return {
                "seeded": False,
                "already": True,
                "user_id": existing_id,
                "email": email,
                "role": by_email["role"] or "demo",
            }
        by_id = conn.execute(
            "SELECT user_id FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        if by_id:
            conn.execute(
                "UPDATE users SET display_name=?, device_id=?, email=?, phone=?, "
                "password_hash=?, role=? WHERE user_id=?",
                (display_name, device_key, email, phone, pw, "demo", user_id),
            )
            conn.commit()
            return {
                "seeded": True,
                "updated": True,
                "user_id": user_id,
                "email": email,
                "role": "demo",
            }
        conn.execute(
            "INSERT INTO users(user_id, display_name, device_id, email, phone, password_hash, role) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, display_name, device_key, email, phone, pw, "demo"),
        )
        conn.commit()
        return {
            "seeded": True,
            "user_id": user_id,
            "email": email,
            "phone": phone,
            "role": "demo",
        }
    finally:
        conn.close()


def _run_onboarding(
    user_id: str,
    *,
    essential: float,
    has_dangerous_debt: bool,
    household: str,
    near_term_priority: str = "safety",
) -> dict[str, Any]:
    s = ob.create_session(user_id)
    ob.patch_step(
        s.session_id,
        1,
        {
            "household": household,
            "life_stage": household,
            "income_stability": "stable",
            "family_context": "with_family",
        },
    )
    ob.patch_step(
        s.session_id,
        2,
        {
            "essential_expense_monthly": essential,
            "emergency_fund_months_self": 3 if not has_dangerous_debt else 0.5,
            "has_dangerous_debt_self": has_dangerous_debt,
            "near_term_priority": near_term_priority,
        },
    )
    ob.patch_step(
        s.session_id,
        3,
        {
            "surplus_habit": "hold",
            "risk_tolerance": 3 if has_dangerous_debt else 5,
            "agent_role_preference": "advisor_only",
        },
    )
    ob.patch_step(s.session_id, 4, {})
    return ob.complete_session(s.session_id)


def _save_goal(goal: Any) -> None:
    goals_api.STORE.save(goal)


def _save_account(
    *,
    account_id: str,
    user_id: str,
    name: str,
    type: str,
    balance: float,
) -> Account:
    now = _now()
    acc = Account(
        account_id=account_id,
        user_id=user_id,
        name=name,
        type=type,
        balance=float(balance),
        source=SOURCE_MANUAL,
        consent_ack=True,
        consent_at=now,
        status=STATUS_ACTIVE,
        hidden_at=None,
        created_at=now,
        updated_at=now,
    )
    ACC_STORE.save(acc)
    return acc


def _save_tx(
    *,
    transaction_id: str,
    user_id: str,
    account_id: str,
    amount: float,
    category: str,
    date: str,
    note: str,
    merchant: str | None = None,
) -> Transaction:
    now = _now()
    tx = Transaction(
        transaction_id=transaction_id,
        user_id=user_id,
        account_id=account_id,
        amount=float(amount),
        category=category,
        date=date,
        note=note,
        merchant=merchant,
        source=TX_SOURCE_MANUAL,
        consent_ack=True,
        consent_at=now,
        is_split=False,
        splits=[],
        status=TX_ACTIVE,
        hidden_at=None,
        created_at=now,
        updated_at=now,
    )
    TX_STORE.save(tx)
    return tx


def _seed_categories(user_id: str) -> dict[str, Any]:
    code, out = service_seed_defaults(user_id)
    existing = {
        c.name for c in CAT_STORE.list_for_user(user_id, include_disabled=True)
    }
    name = "Hỗ trợ gia đình"
    if name not in existing:
        now = _now()
        digest = hashlib.sha256(f"{user_id}:{name}".encode()).hexdigest()
        cid = (
            f"{digest[:8]}-{digest[8:12]}-4{digest[13:16]}-"
            f"8{digest[17:20]}-{digest[20:32]}"
        )
        CAT_STORE.save(
            Category(
                category_id=cid,
                user_id=user_id,
                name=name,
                kind=KIND_FIXED,
                tags=["ho-tro-gia-dinh"],
                note="Demo seed",
                status=CAT_ACTIVE,
                disabled_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        out = dict(out or {})
        out["extra_family_support"] = True
    return {"code": code, **(out if isinstance(out, dict) else {"result": out})}


def seed_p2_on_user(user_id: str) -> dict[str, Any]:
    essential = float(DEMO_P2_ESSENTIAL_VND)
    _clear_user_demo_data(user_id)
    completed = _run_onboarding(
        user_id,
        essential=essential,
        has_dangerous_debt=True,
        household="young_family",
        near_term_priority="safety",
    )

    ef = create_emergency_fund_goal(
        user_id=user_id,
        essential_expense_monthly=essential,
        current_amount=float(DEMO_P2_EF_CURRENT_VND),
        linked_from_onboarding=True,
    )
    ef.goal_id = P2_GOAL_EF
    _save_goal(ef)

    debt = create_debt_payoff_goal(
        user_id=user_id,
        target_amount=float(DEMO_P2_DEBT_TARGET_VND),
        current_amount=float(DEMO_P2_DEBT_CURRENT_VND),
        title="Trả nợ thẻ (demo P2)",
        subtype="the_tin_dung",
        monthly_contribution=2_000_000,
        plan_method="avalanche",
    )
    debt.goal_id = P2_GOAL_DEBT
    _save_goal(debt)

    set_user_flags(
        user_id,
        has_dangerous_debt=False,
        debt_on_track=True,
        mastery_no_efund_invest="apply",
    )
    set_persona(user_id=user_id, persona="P2")

    _save_account(
        account_id=P2_ACC_CHI,
        user_id=user_id,
        name="Chi tiêu hộ",
        type="chi_tieu_hang_ngay",
        balance=DEMO_P2_CHI_TIEU_VND,
    )
    _save_account(
        account_id=P2_ACC_QUY,
        user_id=user_id,
        name="Quỹ dự phòng",
        type="tiet_kiem",
        balance=DEMO_P2_QUY_DP_VND,
    )
    _save_account(
        account_id=P2_ACC_NO,
        user_id=user_id,
        name="Nợ thẻ (đã tất toán demo)",
        type="no",
        balance=0.0,
    )

    cats = _seed_categories(user_id)
    _save_tx(
        transaction_id=P2_TX_IDS[0],
        user_id=user_id,
        account_id=P2_ACC_CHI,
        amount=-2_500_000,
        category="Học phí con",
        date="2026-09-01",
        note="Học phí tháng 9",
        merchant="Trường mẫu giáo",
    )
    _save_tx(
        transaction_id=P2_TX_IDS[1],
        user_id=user_id,
        account_id=P2_ACC_CHI,
        amount=-1_200_000,
        category="Siêu thị",
        date="2026-09-05",
        note="Chi tiêu hộ",
        merchant="VinMart",
    )
    _save_tx(
        transaction_id=P2_TX_IDS[2],
        user_id=user_id,
        account_id=P2_ACC_QUY,
        amount=3_000_000,
        category="Quỹ khẩn cấp",
        date="2026-09-10",
        note="Gửi quỹ DP",
    )
    _save_tx(
        transaction_id=P2_TX_IDS[3],
        user_id=user_id,
        account_id=P2_ACC_CHI,
        amount=-2_000_000,
        category="Trả nợ",
        date="2026-08-28",
        note="Tất toán thẻ (demo)",
        merchant="Ngân hàng",
    )

    gate = compute_safety_gate_from_amounts(
        current_efund_amount=float(DEMO_P2_EF_CURRENT_VND),
        essential_expense_monthly=essential,
        has_dangerous_debt=False,
        debt_on_track=True,
        mastery_no_efund_invest="apply",
    )
    return {
        "persona_id": "P2",
        "household": "young_family",
        "user_id": user_id,
        "dna": completed.get("dna"),
        "goals": {
            "emergency_fund": ef.to_dict(),
            "debt_payoff": debt.to_dict(),
        },
        "accounts": [P2_ACC_CHI, P2_ACC_QUY, P2_ACC_NO],
        "transactions": list(P2_TX_IDS),
        "categories": cats,
        "safety_gate": gate.to_dict(),
        "target_months": TARGET_MONTHS,
    }


def seed_p4_on_user(user_id: str) -> dict[str, Any]:
    essential = float(DEMO_P4_ESSENTIAL_VND)
    _clear_user_demo_data(user_id)
    completed = _run_onboarding(
        user_id,
        essential=essential,
        has_dangerous_debt=True,
        household="sandwich_3gen",
        near_term_priority="debt",
    )

    debt = create_debt_payoff_goal(
        user_id=user_id,
        target_amount=float(DEMO_P4_DEBT_VND),
        current_amount=float(DEMO_P4_DEBT_PAID_VND),
        title="Nợ tiêu dùng (demo P4)",
        subtype="tin_dung",
        monthly_contribution=2_500_000,
        plan_method="snowball",
    )
    debt.goal_id = P4_GOAL_DEBT
    _save_goal(debt)

    ef = create_emergency_fund_goal(
        user_id=user_id,
        essential_expense_monthly=essential,
        current_amount=float(DEMO_P4_EF_CURRENT_VND),
        linked_from_onboarding=True,
    )
    ef.goal_id = P4_GOAL_EF
    _save_goal(ef)

    set_user_flags(
        user_id,
        has_dangerous_debt=True,
        debt_on_track=False,
        mastery_no_efund_invest="learning",
    )
    set_persona(user_id=user_id, persona="P4")

    _save_account(
        account_id=P4_ACC_CHI,
        user_id=user_id,
        name="Chi tiêu duy nhất",
        type="chi_tieu_hang_ngay",
        balance=DEMO_P4_CHI_TIEU_VND,
    )
    _save_account(
        account_id=P4_ACC_TIET,
        user_id=user_id,
        name="Quỹ dự phòng mỏng",
        type="tiet_kiem",
        balance=DEMO_P4_TIET_KIEM_VND,
    )
    _save_account(
        account_id=P4_ACC_NO,
        user_id=user_id,
        name="Nợ tiêu dùng",
        type="no",
        balance=float(DEMO_P4_DEBT_VND),
    )

    cats = _seed_categories(user_id)
    _save_tx(
        transaction_id=P4_TX_IDS[0],
        user_id=user_id,
        account_id=P4_ACC_CHI,
        amount=-5_000_000,
        category="Hỗ trợ gia đình",
        date="2026-09-02",
        note="Hỗ trợ ông bà",
    )
    _save_tx(
        transaction_id=P4_TX_IDS[1],
        user_id=user_id,
        account_id=P4_ACC_CHI,
        amount=-4_000_000,
        category="Học phí con",
        date="2026-09-03",
        note="Học phí",
    )
    _save_tx(
        transaction_id=P4_TX_IDS[2],
        user_id=user_id,
        account_id=P4_ACC_CHI,
        amount=-2_500_000,
        category="Trả nợ",
        date="2026-09-05",
        note="Trả góp nợ tiêu dùng",
        merchant="Ngân hàng",
    )

    gate = compute_safety_gate_from_amounts(
        current_efund_amount=float(DEMO_P4_EF_CURRENT_VND),
        essential_expense_monthly=essential,
        has_dangerous_debt=True,
        debt_on_track=False,
        mastery_no_efund_invest="learning",
    )
    return {
        "persona_id": "P4",
        "household": "sandwich_3gen",
        "user_id": user_id,
        "dna": completed.get("dna"),
        "goals": {
            "debt_payoff": debt.to_dict(),
            "emergency_fund": ef.to_dict(),
        },
        "accounts": [P4_ACC_CHI, P4_ACC_TIET, P4_ACC_NO],
        "transactions": list(P4_TX_IDS),
        "categories": cats,
        "safety_gate": gate.to_dict(),
        "target_months": TARGET_MONTHS,
    }


def seed_partner_rich_demo(*, url: Optional[str] = None) -> dict[str, Any]:
    if not guest_demo_enabled():
        return {"seeded": False, "reason": "demo_seed_disabled"}

    partner_auth = _upsert_demo_user(
        user_id=PARTNER_USER_ID,
        email=DEMO_EMAIL,
        phone=DEMO_PHONE,
        display_name=DEMO_DISPLAY,
        password=DEMO_PASSWORD,
        url=url,
    )
    p2 = seed_p2_on_user(partner_auth["user_id"])

    p4_auth = _upsert_demo_user(
        user_id=DEMO_P4_USER_ID,
        email=DEMO_P4_EMAIL,
        phone=DEMO_P4_PHONE,
        display_name=DEMO_P4_DISPLAY,
        password=DEMO_PASSWORD,
        url=url,
    )
    p4 = seed_p4_on_user(p4_auth["user_id"])

    return {
        "seeded": True,
        "partner": {
            **partner_auth,
            "password_hint": DEMO_PASSWORD,
            "persona": p2,
        },
        "demo_p4": {
            **p4_auth,
            "email": DEMO_P4_EMAIL,
            "password_hint": DEMO_PASSWORD,
            "persona": p4,
        },
        "p4_exposure": "alias",
        "p4_login": DEMO_P4_EMAIL,
        "target_months": TARGET_MONTHS,
    }
