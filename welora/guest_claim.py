"""Guest → account claim (P0 follow-up 2, item 1).

A guest (pure /auth/device user) finishes onboarding + creates the 3-month fund, then registers or
logs in. ``claim_guest_data`` moves the guest's data onto the account:

PROOF OF OWNERSHIP — the client presents BOTH the account bearer token (live, not a device guest)
and the guest's own device token (``guest_token``, kind=device, live, unrevoked, unexpired). Only
the browser that holds that guest session has the token, so one user cannot claim another's guest
data by knowing a user_id or device_id. The guest must be a *pure device guest* (no credentials,
role guest, never logged in by another method) and must differ from the account.

TARGET — only self-registered accounts (role ``guest`` with email/phone credentials). Shared demo
persona accounts (role ``demo``) and admin roles are refused (403 CLAIM_TARGET_NOT_ALLOWED), so a
partner walkthrough never pollutes P1–P6.

SINGLE WINNER / IDEMPOTENT — inside ONE transaction: lock the account row, then
``UPDATE users SET claimed_by_user_id=… WHERE user_id=<guest> AND claimed_by_user_id IS NULL``.
rowcount 0 → already claimed: by the same account → 200 ``already`` (no-op, even though the guest
token is now revoked); by another account → 409 GUEST_ALREADY_CLAIMED. After the claim the
guest's device tokens are revoked and its device_id is cleared (the browser gets a fresh guest
next time; the old guest row stays as an empty, claimed shell for audit).

CONFLICT POLICY — the account's own data always wins; guest data only fills what is missing:
  * onboarding (onboarding_sessions incl. DNA / constitution JSON, dna_profiles, constitutions):
    moved only if the account has NO completed onboarding session and no DNA profile; otherwise
    every guest onboarding row is skipped (stays on the claimed guest row).
  * goals: an emergency_fund / debt_payoff goal that is active or completed moves only if the
    account has no active/completed goal of that type; other (cancelled/archived) goals move.
    goal_history follows its goal_id.
  * user_flags: moved only if the account has none. mastery_nodes: only node_ids the account lacks.
  * decision_logs: moved (append-only audit of what the agent told this person).
  * OS bundle (os_accounts / os_transactions / os_categories / os_budgets): moved only if the
    account has no rows in any of the four tables (moving part of a ledger would mix two ledgers).
  * NOT moved: Mode C state, checkout / entitlements / push subscriptions, auth tokens, OTP rows.
The response reports what moved and what was skipped (and why).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from welora import auth as auth_svc
from welora.db.connection import ambient_transaction, get_connection

log = logging.getLogger("welora.guest_claim")

CLAIM_MSG_INVALID = "Phiên khách không hợp lệ hoặc đã hết hạn — không thể chuyển dữ liệu."
CLAIM_MSG_TAKEN = "Dữ liệu khách này đã được lưu vào một tài khoản khác."
CLAIM_MSG_TARGET = "Tài khoản này không nhận dữ liệu khách (tài khoản demo/quản trị)."
CLAIM_MSG_SELF = "Cần đăng nhập bằng tài khoản (email/SĐT) để lưu dữ liệu khách."

OS_TABLES = ("os_accounts", "os_transactions", "os_categories", "os_budgets")
_SINGLETON_GOAL_TYPES = ("emergency_fund", "debt_payoff")


class ClaimError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rewrite_uid(raw: Optional[str], account: str) -> Optional[str]:
    if not raw:
        return raw
    try:
        obj = json.loads(raw)
    except ValueError:
        return raw
    if isinstance(obj, dict) and "user_id" in obj:
        obj["user_id"] = account
        return json.dumps(obj, ensure_ascii=False)
    return raw


def _guest_token_row(token: str) -> Optional[Any]:
    conn = get_connection()
    try:
        return conn.execute(
            "SELECT user_id, kind, revoked FROM auth_tokens WHERE token=?", (token,)
        ).fetchone()
    finally:
        conn.close()


def _user_row(conn, uid: str) -> Optional[Any]:
    return conn.execute(
        "SELECT user_id, display_name, device_id, email, phone, password_hash, role, email_verified_at, "
        "claimed_by_user_id, claimed_at FROM users WHERE user_id=?",
        (uid,),
    ).fetchone()


def claim_guest_data(account_uid: str, guest_token: str) -> dict[str, Any]:
    account_uid = str(account_uid or "").strip()
    guest_token = str(guest_token or "").strip()
    if not account_uid or not guest_token:
        raise ClaimError(400, "GUEST_TOKEN_REQUIRED", CLAIM_MSG_INVALID)
    auth_svc.ensure_auth_schema()  # migrations outside the ambient block (executescript commits)

    tok = _guest_token_row(guest_token)
    if not tok or str(tok["kind"] or "device") != "device":
        raise ClaimError(403, "INVALID_GUEST_TOKEN", CLAIM_MSG_INVALID)
    guest_uid = str(tok["user_id"])
    if guest_uid == account_uid:
        raise ClaimError(400, "CLAIM_SELF", CLAIM_MSG_SELF)

    conn = get_connection()
    try:
        g = _user_row(conn, guest_uid)
        acc = _user_row(conn, account_uid)
        if g is None or acc is None:
            raise ClaimError(403, "INVALID_GUEST_TOKEN", CLAIM_MSG_INVALID)
        claimed_by = str(g["claimed_by_user_id"] or "")
        if claimed_by:
            if claimed_by == account_uid:
                return {"ok": True, "already": True, "guest_user_id": guest_uid, "user_id": account_uid,
                        "moved": {}, "skipped": {}}
            raise ClaimError(409, "GUEST_ALREADY_CLAIMED", CLAIM_MSG_TAKEN)
        # unclaimed → the guest token must be a live session and the guest a pure device guest
        state, _ = auth_svc.token_state(guest_token)
        if state != "ok" or not auth_svc._is_pure_device_guest(conn, g):
            raise ClaimError(403, "INVALID_GUEST_TOKEN", CLAIM_MSG_INVALID)
        role = str(acc["role"] or "guest").strip().lower()
        has_creds = bool(str(acc["password_hash"] or "").strip()) and bool(
            str(acc["email"] or "").strip() or str(acc["phone"] or "").strip()
        )
        if role != "guest" or not has_creds:
            if auth_svc._is_pure_device_guest(conn, acc):
                raise ClaimError(400, "CLAIM_SELF", CLAIM_MSG_SELF)
            raise ClaimError(403, "CLAIM_TARGET_NOT_ALLOWED", CLAIM_MSG_TARGET)
    finally:
        conn.close()

    with ambient_transaction() as tx:
        # lock order: account row, then guest row (a guest is never an account → no cycles)
        tx.execute("UPDATE users SET updated_at=updated_at WHERE user_id=?", (account_uid,))
        cur = tx.execute(
            "UPDATE users SET claimed_by_user_id=?, claimed_at=?, device_id=NULL "
            "WHERE user_id=? AND claimed_by_user_id IS NULL",
            (account_uid, _now(), guest_uid),
        )
        if int(cur.rowcount or 0) != 1:
            row = tx.execute("SELECT claimed_by_user_id FROM users WHERE user_id=?", (guest_uid,)).fetchone()
            if row and str(row["claimed_by_user_id"] or "") == account_uid:
                return {"ok": True, "already": True, "guest_user_id": guest_uid, "user_id": account_uid,
                        "moved": {}, "skipped": {}}
            raise ClaimError(409, "GUEST_ALREADY_CLAIMED", CLAIM_MSG_TAKEN)
        tx.execute("UPDATE auth_tokens SET revoked=1 WHERE user_id=? AND revoked=0", (guest_uid,))
        moved, skipped = _move_db(tx, guest_uid, account_uid)
    _move_memory(guest_uid, account_uid, moved, skipped)
    log.info("guest claim: moved=%s skipped=%s", moved, sorted(skipped))
    return {"ok": True, "already": False, "guest_user_id": guest_uid, "user_id": account_uid,
            "moved": moved, "skipped": skipped}


def _count(tx, table: str, where: str, params: tuple) -> int:
    row = tx.execute(f"SELECT COUNT(*) AS n FROM {table} WHERE {where}", params).fetchone()
    return int(row["n"] or 0) if row else 0


def _move_db(tx, guest: str, account: str) -> tuple[dict[str, int], dict[str, str]]:
    moved: dict[str, int] = {}
    skipped: dict[str, str] = {}

    # onboarding: all-or-nothing, only when the account has none of its own
    acc_onb = _count(tx, "onboarding_sessions", "user_id=? AND status='completed'", (account,)) + _count(
        tx, "dna_profiles", "user_id=?", (account,)
    )
    g_onb = _count(tx, "onboarding_sessions", "user_id=?", (guest,))
    if acc_onb:
        if g_onb or _count(tx, "dna_profiles", "user_id=?", (guest,)):
            skipped["onboarding"] = "account_has_onboarding"
    else:
        n = 0
        for r in tx.execute(
            "SELECT session_id, dna_json, constitution_json FROM onboarding_sessions WHERE user_id=?", (guest,)
        ).fetchall():
            tx.execute(
                "UPDATE onboarding_sessions SET user_id=?, dna_json=?, constitution_json=? WHERE session_id=?",
                (account, _rewrite_uid(r["dna_json"], account), _rewrite_uid(r["constitution_json"], account),
                 r["session_id"]),
            )
            n += 1
        moved["onboarding_sessions"] = n
        for table in ("dna_profiles", "constitutions"):
            cur = tx.execute(
                f"UPDATE {table} SET user_id=? WHERE user_id=? AND NOT EXISTS "
                f"(SELECT 1 FROM {table} t2 WHERE t2.user_id=?)",
                (account, guest, account),
            )
            moved[table] = int(cur.rowcount or 0)

    # goals
    n_goals = 0
    for gtype in _SINGLETON_GOAL_TYPES:
        live = tx.execute(
            "SELECT goal_id FROM goals WHERE user_id=? AND type=? AND status IN ('active','completed')",
            (guest, gtype),
        ).fetchall()
        if not live:
            continue
        if _count(tx, "goals", "user_id=? AND type=? AND status IN ('active','completed')", (account, gtype)):
            skipped[f"goal:{gtype}"] = "account_has_goal"
            continue
        for r in live[:1]:  # at most one live goal of a singleton type per user
            tx.execute("UPDATE goals SET user_id=? WHERE goal_id=?", (account, r["goal_id"]))
            n_goals += 1
        if len(live) > 1:
            skipped[f"goal:{gtype}:extra"] = "guest_had_duplicates"
    cur = tx.execute(
        "UPDATE goals SET user_id=? WHERE user_id=? AND NOT (type IN ('emergency_fund','debt_payoff') "
        "AND status IN ('active','completed'))",
        (account, guest),
    )
    n_goals += int(cur.rowcount or 0)
    moved["goals"] = n_goals

    # user_flags / mastery / decision logs
    if _count(tx, "user_flags", "user_id=?", (guest,)):
        cur = tx.execute(
            "UPDATE user_flags SET user_id=? WHERE user_id=? AND NOT EXISTS "
            "(SELECT 1 FROM user_flags f2 WHERE f2.user_id=?)",
            (account, guest, account),
        )
        moved["user_flags"] = int(cur.rowcount or 0)
        if not moved["user_flags"]:
            skipped["user_flags"] = "account_has_flags"
    cur = tx.execute(
        "UPDATE mastery_nodes SET user_id=? WHERE user_id=? AND node_id NOT IN "
        "(SELECT m2.node_id FROM mastery_nodes m2 WHERE m2.user_id=?)",
        (account, guest, account),
    )
    moved["mastery_nodes"] = int(cur.rowcount or 0)
    cur = tx.execute("UPDATE decision_logs SET user_id=? WHERE user_id=?", (account, guest))
    moved["decision_logs"] = int(cur.rowcount or 0)

    # OS ledger bundle
    present = OS_TABLES  # migrations 004–007 (a failed probe would abort the PG transaction)
    g_os = sum(_count(tx, t, "user_id=?", (guest,)) for t in present)
    if g_os:
        if any(_count(tx, t, "user_id=?", (account,)) for t in present):
            skipped["os"] = "account_has_os_data"
        else:
            for t in present:
                cur = tx.execute(f"UPDATE {t} SET user_id=? WHERE user_id=?", (account, guest))
                moved[t] = int(cur.rowcount or 0)
    return moved, skipped


def _move_memory(guest: str, account: str, moved: dict[str, int], skipped: dict[str, str]) -> None:
    """Per-process caches + memory-only stores (local / unit-test mode). DB mode reads the DB."""
    from welora import goals_api, onboarding

    if "onboarding" not in skipped:
        if onboarding.DNA_BY_USER.get(account) is None and guest in onboarding.DNA_BY_USER:
            d = dict(onboarding.DNA_BY_USER.pop(guest))
            d["user_id"] = account
            onboarding.DNA_BY_USER[account] = d
            moved.setdefault("onboarding_memory", 0)
            moved["onboarding_memory"] += 1
        if onboarding.CONSTITUTION_BY_USER.get(account) is None and guest in onboarding.CONSTITUTION_BY_USER:
            c = dict(onboarding.CONSTITUTION_BY_USER.pop(guest))
            c["user_id"] = account
            onboarding.CONSTITUTION_BY_USER[account] = c
        for s in list(onboarding.SESSIONS.values()):
            if s.user_id == guest:
                s.user_id = account
    else:
        onboarding.DNA_BY_USER.pop(guest, None)  # never leak a stale cache to anyone
        onboarding.CONSTITUTION_BY_USER.pop(guest, None)

    store = goals_api.STORE
    if hasattr(store, "_by_id"):  # InMemoryEmergencyFundStore
        n = 0
        for gtype, getter in (("emergency_fund", "get_active_for_user"), ("debt_payoff", "get_debt_for_user")):
            gg = getattr(store, getter)(guest)
            if gg is None:
                continue
            if getattr(store, getter)(account) is not None:
                skipped.setdefault(f"goal:{gtype}", "account_has_goal")
                continue
            gg.user_id = account
            pointer = store._debt_by_user if gtype == "debt_payoff" else store._active_by_user
            pointer.pop(guest, None)
            store.save(gg)
            n += 1
        if n:
            moved["goals"] = moved.get("goals", 0) + n
    if guest in goals_api.USER_FLAGS and account not in goals_api.USER_FLAGS:
        goals_api.USER_FLAGS[account] = goals_api.USER_FLAGS.pop(guest)
