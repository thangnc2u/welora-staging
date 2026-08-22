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


# In-memory store: user_id -> node_id -> MasteryNode
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
