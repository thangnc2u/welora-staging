"""
Welora — S2-07: POST /agent/chat

Pipeline: Context → Pre-Rule → (Deny template | advisory stub) → Decision Log
Rule-first: Hard Deny never calls LLM in Stage 1 MVP.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Callable, Optional
from urllib.parse import urlparse

from welora.agent import render_deny
from welora.pre_rule_service import (
    context_from_seed,
    context_from_user,
    service_evaluate,
)

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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
    DECISION_LOGS.append(entry)
    uid = entry.get("user_id") or "anonymous"
    LOGS_BY_USER.setdefault(uid, []).append(log_id)
    return log_id


def advisory_stub(message: str, gate_status: str) -> str:
    if gate_status != "passed":
        return (
            "Tôi có thể hỗ trợ trong phạm vi An Toàn và nguyên tắc Welora. "
            "Hiện Cổng An Toàn chưa đạt — ưu tiên quỹ khẩn cấp ≥ 3 tháng và xử lý nợ nguy hiểm trước khi đầu tư. "
            "Bạn muốn xem checklist Cổng An Toàn hay tạo Goal quỹ?"
        )
    return (
        "Cổng An Toàn đã đạt. Tôi có thể giúp phân tích lựa chọn trong phạm vi advisory "
        "(không quyết định thay bạn, không đưa mã cụ thể khi bạn chưa yêu cầu rõ khung rủi ro). "
        "Bạn muốn làm rõ Goal nào tiếp theo?"
    )


def soft_warning_stub() -> str:
    return (
        "Không có khoản đầu tư nào chắc lời với % cố định trong mọi tình huống. "
        "Lợi suất luôn đi kèm rủi ro biến động. Bạn đang xem loại tài sản / khung thời gian nào?"
    )


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

    # Pre-rule first — never call LLM on deny
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

    model_used = "rule_only"
    if guardrail == "deny":
        reply = pre.get("reply") or "Không thể hỗ trợ theo nguyên tắc Welora."
        # Hard rule: never call LLM on deny
        model_used = "rule_only"
    elif guardrail == "soft_warning":
        if call_llm:
            try:
                reply = call_llm("Welora advisory. Không hứa %. An Toàn trước.", message)
                model_used = "llm"
            except Exception:
                reply = soft_warning_stub()
        else:
            reply = soft_warning_stub()
    else:
        if call_llm:
            try:
                reply = call_llm("Welora advisory. An Toàn trước. Không quyết định thay user.", message)
                model_used = "llm"
            except Exception:
                reply = advisory_stub(message, gate_status)
        else:
            reply = advisory_stub(message, gate_status)

    cta = map_cta(cta_codes)
    content_links = []
    try:
        from welora.content_map import resolve_keys
        content_links = resolve_keys(principle_keys)
    except Exception:
        pass

    log_id = write_decision_log({
        "user_id": user_id,
        "user_query_summary": message[:200],
        "guardrail_result": guardrail,
        "rule_hit": rule_hit,
        "principle_keys": principle_keys,
        "model_used": model_used,
        "safety_gate_status": gate_status,
        "cta_offered": cta_codes,
    })

    return 200, {
        "reply": reply,
        "guardrail_result": guardrail,
        "rule_hit": rule_hit,
        "principle_keys": principle_keys,
        "cta": cta,
        "content_links": content_links,
        "decision_log_id": log_id,
        "safety_gate_status": gate_status,
        "months_covered": pre.get("months_covered"),
        "model_used": model_used,
    }


def service_list_logs(user_id: str, limit: int = 20) -> tuple[int, dict]:
    ids = LOGS_BY_USER.get(user_id) or []
    items = [e for e in DECISION_LOGS if e.get("id") in ids][-limit:]
    return 200, {"items": items}


class ChatHandler(BaseHTTPRequestHandler):
    server_version = "WeloraChat/0.1"

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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path in ("/agent/chat", "/chat"):
            body = self._read_json()
            code, out = service_chat(
                user_id=body.get("user_id") or "",
                message=body.get("message") or "",
                context_seed=body.get("context_seed") or body.get("context"),
            )
            self._json(code, out)
            return
        self._json(404, {"error": "not found"})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/users/") and path.endswith("/decision-logs"):
            parts = path.strip("/").split("/")
            if len(parts) >= 3:
                code, out = service_list_logs(parts[1])
                self._json(code, out)
                return
        if path in ("/health", "/"):
            self._json(200, {"ok": True, "service": "welora-chat"})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[chat] {args[0]}")


def run_server(host: str = "127.0.0.1", port: int = 8790) -> None:
    httpd = HTTPServer((host, port), ChatHandler)
    print(f"Welora Chat API on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
