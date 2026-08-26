"""P2-E8 — Agent metrics. Deny must never increment deny_with_llm_calls."""

from __future__ import annotations

from typing import Any

_COUNTERS: dict[str, int] = {
    "chat_total": 0,
    "deny_total": 0,
    "deny_with_llm_calls": 0,
    "llm_calls": 0,
}


def reset_metrics() -> None:
    for k in _COUNTERS:
        _COUNTERS[k] = 0


def record_chat(*, guardrail_result: str, llm_called: bool) -> None:
    _COUNTERS["chat_total"] += 1
    if llm_called:
        _COUNTERS["llm_calls"] += 1
    if guardrail_result == "deny":
        _COUNTERS["deny_total"] += 1
        if llm_called:
            _COUNTERS["deny_with_llm_calls"] += 1


def snapshot() -> dict[str, Any]:
    return {
        "deny_with_llm_calls": int(_COUNTERS["deny_with_llm_calls"]),
        "deny_total": int(_COUNTERS["deny_total"]),
        "chat_total": int(_COUNTERS["chat_total"]),
        "llm_calls": int(_COUNTERS["llm_calls"]),
        "hard_deny": True,
        "gate_months": 3,
    }


def service_get_metrics() -> tuple[int, dict]:
    return 200, snapshot()
