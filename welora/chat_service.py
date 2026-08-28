"""Welora chat — rule-first. Hard Deny never calls LLM. P2-E8 metrics + no PII."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from welora.pre_rule_service import service_evaluate

DECISION_LOGS: list[dict[str, Any]] = []
LOGS_BY_USER: dict[str, list[str]] = {}

CTA_LABELS = {
    "keep_emergency_fund": "Giữ nguyên quỹ khẩn cấp",
    "create_emergency_fund_goal": "Tạo Goal quỹ khẩn cấp 3 tháng",
    "create_invest_goal_surplus_only": "Tạo Goal đầu tư (tiền ngoài quỹ)",
    "view_safety_gate": "Xem checklist Cổng An Toàn",
    "create_debt_payoff_goal": "Tạo plan trả nợ",
    "create_savings_goal": "Tạo Goal tiết kiệm riêng",
    "view_options_framework": "Xem khung lựa chọn",
}

_PII_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)\b(sk-|xai-|ghp_|github_pat_)[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)\bauthorization\s*[:=]\s*\S+"),
    re.compile(r"\b(?:0|\+84)(?:[\s.\-]?\d){8,10}\b"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sanitize_query(text: str, *, limit: int = 120) -> str:
    raw = str(text or "")
    for pat in _PII_PATTERNS:
        raw = pat.sub("[REDACTED]", raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    if len(raw) > limit:
        return raw[:limit] + "…"
    return raw


def sanitize_log_entry(entry: dict[str, Any]) -> dict[str, Any]:
    out = dict(entry)
    out["user_query_summary"] = sanitize_query(out.get("user_query_summary") or "")
    preview = str(out.get("raw_response_preview") or "")
    for pat in _PII_PATTERNS:
        preview = pat.sub("[REDACTED]", preview)
    out["raw_response_preview"] = preview[:300]
    out.pop("phone", None)
    out.pop("token", None)
    out.pop("api_key", None)
    out.pop("authorization", None)
    out.pop("secret", None)
    return out


def map_cta(codes: list[str]) -> list[dict[str, str]]:
    try:
        from welora.content_map import enrich_cta
        return enrich_cta(codes)
    except Exception:
        return [{"code": c, "label": CTA_LABELS.get(c, c)} for c in codes]


def write_decision_log(entry: dict[str, Any]) -> str:
    log_id = entry.get("id") or str(uuid.uuid4())
    entry["id"] = log_id
    entry.setdefault("timestamp", _now())
    entry = sanitize_log_entry(entry)
    DECISION_LOGS.append(entry)
    uid = entry.get("user_id") or "anonymous"
    LOGS_BY_USER.setdefault(uid, []).append(log_id)
    return log_id


def advisory_stub(message: str, gate_status: str) -> str:
    if gate_status != "passed":
        return (
            "Tôi có thể hỗ trợ trong phạm vi An Toàn. "
            "Cổng chưa đạt — ưu tiên quỹ ≥ 3 tháng."
        )
    return "Cổng An Toàn đã đạt. Tôi hỗ trợ advisory, không quyết định thay bạn."


def soft_warning_stub() -> str:
    return "Không có khoản đầu tư nào chắc lời với % cố định. Lợi suất đi kèm rủi ro."


def service_chat(
    *,
    user_id: str,
    message: str,
    context_seed: Optional[dict] = None,
    call_llm: Optional[Callable[[str, str], str]] = None,
) -> tuple[int, dict]:
    if not message or not str(message).strip():
        return 400, {"error": "message is required"}
    if not user_id and not context_seed:
        return 400, {"error": "user_id or context_seed required"}

    code, pre = service_evaluate(
        message=message,
        user_id=user_id,
        context_seed=context_seed,
    )
    if code != 200:
        return code, pre

    guardrail = pre.get("guardrail_result") or "pass"
    gate_status = pre.get("safety_gate_status") or "not_passed"
    cta_codes = list(pre.get("cta") or [])
    principle_keys = list(pre.get("principle_keys") or [])
    rule_hit = pre.get("rule_hit")
    llm_called = False
    model_used = "rule_only"

    if guardrail == "deny":
        reply = pre.get("reply") or "Không thể hỗ trợ theo nguyên tắc Welora."
        model_used = "rule_only"
        llm_called = False
    elif guardrail == "soft_warning":
        from welora.llm_adapter import safe_call_llm
        reply, model_used, llm_called = safe_call_llm(
            call_llm, "CONSTRAINT: Không đưa số % cam kết.", message
        )
        if not llm_called and model_used != "llm_error":
            reply = soft_warning_stub()
            model_used = "rule_only"
    else:
        from welora.llm_adapter import safe_call_llm
        reply, model_used, llm_called = safe_call_llm(
            call_llm, "Welora Agent Stage 1 advisory.", message
        )
        if not llm_called and model_used != "llm_error":
            reply = advisory_stub(message, gate_status)
            model_used = "rule_only"

    try:
        from welora.metrics import record_chat
        record_chat(guardrail_result=guardrail, llm_called=bool(llm_called))
    except Exception:
        pass

    log_id = write_decision_log({
        "user_id": user_id,
        "user_query_summary": sanitize_query(message),
        "guardrail_result": guardrail,
        "rule_hit": rule_hit,
        "principle_keys": principle_keys,
        "model_used": model_used,
        "llm_called": llm_called,
        "safety_gate_status": gate_status,
        "cta_offered": cta_codes,
        "raw_response_preview": str(reply)[:300],
    })

    content_links = []
    try:
        from welora.content_map import resolve_keys
        content_links = resolve_keys(principle_keys)
    except Exception:
        pass

    return 200, {
        "reply": reply,
        "guardrail_result": guardrail,
        "rule_hit": rule_hit,
        "principle_keys": principle_keys,
        "cta": map_cta(cta_codes),
        "content_links": content_links,
        "decision_log_id": log_id,
        "safety_gate_status": gate_status,
        "months_covered": pre.get("months_covered"),
        "should_call_llm": pre.get("should_call_llm"),
        "model_used": model_used,
        "llm_called": llm_called,
    }


def service_list_logs(user_id: str, limit: int = 20) -> tuple[int, dict]:
    ids = list(reversed(LOGS_BY_USER.get(user_id, [])))[:limit]
    by_id = {e["id"]: e for e in DECISION_LOGS}
    items = [sanitize_log_entry(by_id[i]) for i in ids if i in by_id]
    return 200, {"items": items}


def reset_logs() -> None:
    DECISION_LOGS.clear()
    LOGS_BY_USER.clear()
    try:
        from welora.metrics import reset_metrics
        reset_metrics()
    except Exception:
        pass
