"""
Welora — S3-03 Mastery node (Phase 0 close-out)

Node: no_efund_invest
States: not_started → learning → familiar → apply → mastered
Gate requires mastery >= apply (LOCKED threshold).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

STATES = ("not_started", "learning", "familiar", "apply", "mastered")
GATE_MIN = "apply"
NODE_NO_EFUND = "no_efund_invest"

_RANK = {s: i for i, s in enumerate(STATES)}


@dataclass
class MasteryNode:
    node_id: str
    state: str = "not_started"
    principle_keys: list[str] = field(default_factory=lambda: ["SAFE-02", "CORE-07", "DEBT-03"])

    def meets_gate(self) -> bool:
        return _RANK.get(self.state, 0) >= _RANK[GATE_MIN]


_STORE: dict[str, dict[str, MasteryNode]] = {}


def reset_mastery_store() -> None:
    _STORE.clear()


def get_node(user_id: str, node_id: str = NODE_NO_EFUND) -> MasteryNode:
    user = _STORE.setdefault(user_id, {})
    if node_id not in user:
        user[node_id] = MasteryNode(node_id=node_id)
    return user[node_id]


def set_state(user_id: str, state: str, node_id: str = NODE_NO_EFUND) -> MasteryNode:
    if state not in STATES:
        raise ValueError(f"invalid mastery state: {state}")
    node = get_node(user_id, node_id)
    node.state = state
    return node


def mastery_ok_for_gate(user_id: str, node_id: str = NODE_NO_EFUND) -> bool:
    return get_node(user_id, node_id).meets_gate()


def to_dict(node: MasteryNode) -> dict:
    return {
        "node_id": node.node_id,
        "state": node.state,
        "meets_gate": node.meets_gate(),
        "gate_min": GATE_MIN,
        "principle_keys": list(node.principle_keys),
    }


def service_get_mastery(user_id: str, node_id: str = NODE_NO_EFUND) -> tuple[int, dict]:
    """Read-only. For the gate node the state is the one the Safety Gate uses (server-written,
    incl. a trusted DB row after a restart)."""
    if not user_id:
        return 400, {"error": "user_id is required"}
    node_id = node_id or NODE_NO_EFUND
    node = get_node(user_id, node_id)
    out = to_dict(node)
    if node_id == NODE_NO_EFUND:
        try:
            from welora.goals_api import effective_mastery_state

            st = effective_mastery_state(user_id)
            from welora.academy import overlay_session_mastery  # item 14: demo session view

            st = overlay_session_mastery(user_id, st)
            out.update({"state": st, "meets_gate": _RANK.get(st, 0) >= _RANK[GATE_MIN]})
        except Exception:  # pragma: no cover
            pass
    out.update({"read_only": True, "updated_by": "academy", "academy_href": "/app/academy"})
    return 200, out


# --- P0 "mastery chỉ từ server" ---------------------------------------------------------------
# Mastery opens the Safety Gate (Cổng an toàn) — together with the 3-month fund — and through it
# dual-control / estate acts. It is therefore written ONLY by server code:
#   * Academy KUAT graded on the server (academy.submit_kuat → grant_from_academy), source "academy";
#   * demo seed / test fixtures (in-process), source "seed" / "internal".
# The user-facing PATCH /users/{id}/mastery is refused for everyone (403, Vietnamese).
# DB rows carry ``user_flags.mastery_source`` (migration 016). Rows written before this fix have no
# source and are NOT trusted (repos.get_user_flags_db reads them as not_started), so a mastery that
# was self-set through the old PATCH cannot keep a gate open after deploy.

TRUSTED_SOURCES = ("academy", "seed", "internal")
MASTERY_SERVER_ONLY_MSG = (
    "Mức hiểu nguyên tắc chỉ được cập nhật tự động từ kết quả bài kiểm tra trên Welorademy — "
    "bạn không thể tự đặt. Hãy học và làm bài kiểm tra tại /app/academy."
)


def record_mastery(user_id: str, state: str, node_id: str = NODE_NO_EFUND, *, source: str) -> MasteryNode:
    """Server-side mastery write (in-process store + flags cache + DB row with its source).
    Never call this with a client-supplied state."""
    if source not in TRUSTED_SOURCES:
        raise ValueError(f"untrusted mastery source: {source}")
    node = set_state(user_id, str(state), node_id)
    if node_id != NODE_NO_EFUND:
        return node
    try:
        from welora.goals_api import USER_FLAGS, get_user_flags

        prev = get_user_flags(user_id)
        flags = USER_FLAGS.setdefault(
            user_id,
            {
                "has_dangerous_debt": bool(prev.get("has_dangerous_debt")),
                "debt_on_track": bool(prev.get("debt_on_track", True)),
                "mastery_no_efund_invest": node.state,
            },
        )
        flags["mastery_no_efund_invest"] = node.state
    except Exception:  # pragma: no cover
        pass
    from welora.goals_api import _use_db_store

    if _use_db_store():
        from welora.db.repos import set_user_mastery_db

        set_user_mastery_db(user_id, node.state, source=source)
    return node


def grant_from_academy(user_id: str) -> MasteryNode:
    """Academy KUAT for the gate node passed (graded on the server) → mastery ≥ apply."""
    cur = get_node(user_id, NODE_NO_EFUND)
    if cur.meets_gate():
        return cur
    return record_mastery(user_id, GATE_MIN, NODE_NO_EFUND, source="academy")


def service_patch_mastery(user_id: str, body: dict) -> tuple[int, dict]:
    """Former self-service write (it let a user set "apply" and open the gate). Refused for every
    caller — there is no client path that may write mastery (see module notes above)."""
    return 403, {"error_code": "MASTERY_SERVER_ONLY", "message": MASTERY_SERVER_ONLY_MSG}
