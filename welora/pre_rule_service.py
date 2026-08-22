"""
Welora — S2-03: Pre-Rule service

Wraps evaluate_pre_rules with Context from Goal + Gate + fixtures.
HTTP: POST /agent/pre-rule  (evaluate only, no LLM)

Hard Deny → should_call_llm=False + deny template.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional
from urllib.parse import urlparse

from welora.agent import (
    AgentContext,
    SafetyGateSnapshot,
    evaluate_pre_rules,
    render_deny,
)
from welora import goals_api
from welora.goals_api import get_user_flags, service_safety_gate
from welora.onboarding import get_constitution, get_dna


def context_from_user(user_id: str) -> AgentContext:
    code, gate_dict = service_safety_gate(user_id)
    gate = SafetyGateSnapshot(
        status=gate_dict["status"],
        reasons=list(gate_dict.get("reasons") or []),
        months_covered=float(gate_dict.get("months_covered") or 0),
        target_months=int(gate_dict.get("target_months") or 3),
        has_dangerous_debt=bool(gate_dict.get("has_dangerous_debt")),
        debt_on_track=bool(gate_dict.get("debt_on_track")),
        mastery_no_efund_invest=gate_dict.get("mastery_no_efund_invest") or "not_started",
        checked_at=gate_dict.get("checked_at") or "",
    )

    goal = goals_api.STORE.get_active_for_user(user_id)
    ef = None
    if goal:
        ef = {
            "exists": True,
            "months_target": goal.months_of_expense,
            "months_covered": goal.months_covered,
            "percent": goal.percent,
            "current_amount": goal.current_amount,
            "target_amount": goal.target_amount,
        }

    flags = get_user_flags(user_id)
    debt = None
    if flags.get("has_dangerous_debt"):
        debt = {"exists": True, "on_track": bool(flags.get("debt_on_track"))}

    dna = get_dna(user_id) or {}
    constitution = get_constitution(user_id) or {}
    codes = [a.get("code") for a in (constitution.get("articles") or []) if a.get("code")]

    confidence = "full"
    if "data_missing" in gate.reasons or not dna:
        confidence = "missing"
    elif not goal:
        confidence = "partial"

    return AgentContext(
        user_id=user_id,
        safety_gate=gate,
        goals={"emergency_fund": ef, "debt_payoff": debt},
        dna_summary={
            "life_stage": (dna.get("identity_context") or {}).get("life_stage"),
            "near_term_priority": (dna.get("financial_snapshot_self") or {}).get("near_term_priority"),
            "risk_tolerance_self": (dna.get("psychological_profile_self") or {}).get("risk_tolerance"),
            "essential_expense_monthly": (dna.get("financial_snapshot_self") or {}).get("essential_expense_monthly"),
        },
        personal_constitution_codes=codes,
        data_confidence=confidence,
    )


def context_from_seed(seed: dict[str, Any]) -> AgentContext:
    sg = seed["safety_gate"]
    return AgentContext(
        user_id=seed["user_id"],
        safety_gate=SafetyGateSnapshot(
            status=sg["status"],
            reasons=list(sg.get("reasons") or []),
            months_covered=float(sg.get("months_covered") or 0),
            target_months=int(sg.get("target_months") or 3),
            has_dangerous_debt=bool(sg.get("has_dangerous_debt")),
            debt_on_track=bool(sg.get("debt_on_track")),
            mastery_no_efund_invest=sg.get("mastery_no_efund_invest") or "not_started",
        ),
        goals=seed.get("goals") or {},
        dna_summary=seed.get("dna_summary") or {},
        personal_constitution_codes=seed.get("personal_constitution_codes") or [],
        data_confidence=seed.get("data_confidence") or "full",
    )


def service_evaluate(
    *,
    message: str,
    user_id: Optional[str] = None,
    context_seed: Optional[dict] = None,
) -> tuple[int, dict]:
    if not message or not str(message).strip():
        return 400, {"error": "message is required"}

    if context_seed:
        ctx = context_from_seed(context_seed)
    elif user_id:
        ctx = context_from_user(str(user_id))
    else:
        return 400, {"error": "user_id or context_seed required"}

    pre = evaluate_pre_rules(str(message), ctx)

    reply = None
    if pre.result == "deny" and pre.primary_hit:
        reply = render_deny(pre.primary_hit)

    return 200, {
        "guardrail_result": pre.result,
        "should_call_llm": pre.should_call_llm,
        "rule_hit": pre.primary_hit.rule_id if pre.primary_hit else None,
        "principle_keys": list(pre.primary_hit.principle_keys) if pre.primary_hit else [],
        "reason": pre.primary_hit.reason if pre.primary_hit else "",
        "cta": list(pre.primary_hit.cta) if pre.primary_hit else [],
        "reply": reply,
        "safety_gate_status": ctx.safety_gate.status,
        "months_covered": ctx.safety_gate.months_covered,
        "hits": [
            {"rule_id": h.rule_id, "principle_keys": list(h.principle_keys), "reason": h.reason}
            for h in pre.hits
        ],
    }


class PreRuleHandler(BaseHTTPRequestHandler):
    server_version = "WeloraPreRule/0.1"

    def _json(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(raw)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        try:
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path in ("/agent/pre-rule", "/pre-rule"):
            body = self._read_json()
            code, out = service_evaluate(
                message=body.get("message") or "",
                user_id=body.get("user_id"),
                context_seed=body.get("context_seed"),
            )
            self._json(code, out)
            return
        self._json(404, {"error": "not found"})

    def do_GET(self) -> None:
        if urlparse(self.path).path in ("/health", "/"):
            self._json(200, {"ok": True, "service": "welora-pre-rule"})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[pre_rule] {args[0]}")


def run_server(host: str = "127.0.0.1", port: int = 8789) -> None:
    httpd = HTTPServer((host, port), PreRuleHandler)
    print(f"Welora Pre-Rule API on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
