"""
Welora — S1-04: Thin HTTP API for Goal emergency_fund

Endpoints (MVP):
  POST /goals
  GET  /goals?user_id=&type=emergency_fund
  GET  /goals/{goal_id}
  PATCH /goals/{goal_id}/progress
  GET  /users/{user_id}/safety-gate
"""

from __future__ import annotations

import json
import os
import re
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.safety_gate import compute_safety_gate_from_amounts


def _make_store():
    if os.environ.get("WELORA_STORE", "memory").lower() == "sqlite":
        from welora.db.repos import SqliteEmergencyFundStore
        return SqliteEmergencyFundStore(os.environ.get("WELORA_DB_URL") or None)
    return InMemoryEmergencyFundStore()


STORE = _make_store()


def use_store(store) -> None:
    global STORE
    STORE = store


USER_FLAGS: dict[str, dict[str, Any]] = {}


def set_user_flags(
    user_id: str,
    *,
    has_dangerous_debt: bool = False,
    debt_on_track: bool = True,
    mastery_no_efund_invest: str = "apply",
) -> None:
    USER_FLAGS[user_id] = {
        "has_dangerous_debt": has_dangerous_debt,
        "debt_on_track": debt_on_track,
        "mastery_no_efund_invest": mastery_no_efund_invest,
    }


def get_user_flags(user_id: str) -> dict[str, Any]:
    return USER_FLAGS.get(
        user_id,
        {
            "has_dangerous_debt": False,
            "debt_on_track": True,
            "mastery_no_efund_invest": "apply",
        },
    )


def service_create_goal(body: dict) -> tuple[int, dict]:
    user_id = body.get("user_id")
    if not user_id:
        return 400, {"error": "user_id is required"}
    goal_type = body.get("type", "emergency_fund")
    if goal_type != "emergency_fund":
        return 400, {"error": "Only type=emergency_fund supported in S1-04"}
    essential = body.get("essential_expense_monthly")
    if essential is None:
        return 400, {"error": "essential_expense_monthly is required for pre-fill"}
    try:
        essential_f = float(essential)
    except (TypeError, ValueError):
        return 400, {"error": "essential_expense_monthly must be a number"}
    if essential_f <= 0:
        return 400, {"error": "essential_expense_monthly must be > 0"}
    current = float(body.get("current_amount") or 0)
    linked = bool(body.get("linked_from_onboarding", False))
    monthly = float(body.get("monthly_contribution") or 0)
    method = body.get("plan_method")
    try:
        goal = STORE.create_for_user(
            str(user_id),
            essential_f,
            current_amount=current,
            linked_from_onboarding=linked,
            monthly_contribution=monthly,
            plan_method=method,
        )
    except ValueError as e:
        return 409, {"error": str(e)}
    return 201, goal.to_dict()


def service_get_goal(goal_id: str) -> tuple[int, dict]:
    goal = STORE.get(goal_id)
    if not goal:
        return 404, {"error": "goal not found"}
    return 200, goal.to_dict()


def service_list_goals(user_id: str, type: Optional[str] = None) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    goal = STORE.get_active_for_user(user_id)
    items = []
    if goal and (type is None or goal.type == type):
        items.append(goal.to_dict())
    return 200, {"items": items}


def service_progress(goal_id: str, body: dict) -> tuple[int, dict]:
    set_amount = body.get("set_amount")
    add_amount = body.get("add_amount")
    try:
        goal = STORE.record_progress(
            goal_id,
            set_amount=float(set_amount) if set_amount is not None else None,
            add_amount=float(add_amount) if add_amount is not None else None,
        )
    except KeyError:
        return 404, {"error": "goal not found"}
    except ValueError as e:
        return 400, {"error": str(e)}
    return 200, goal.to_dict()


def service_safety_gate(user_id: str) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    goal = STORE.get_active_for_user(user_id)
    flags = get_user_flags(user_id)
    # Prefer SQLite flags when available
    if os.environ.get("WELORA_STORE", "memory").lower() == "sqlite":
        try:
            from welora.db.repos import get_user_flags_db
            flags = get_user_flags_db(user_id)
        except Exception:
            pass
    if not goal:
        result = compute_safety_gate_from_amounts(
            current_efund_amount=0.0,
            essential_expense_monthly=0.0,
            has_dangerous_debt=bool(flags.get("has_dangerous_debt")),
            debt_on_track=bool(flags.get("debt_on_track", True)),
            mastery_no_efund_invest=str(flags.get("mastery_no_efund_invest") or "not_started"),
        )
        return 200, result.to_dict()
    result = compute_safety_gate_from_amounts(
        current_efund_amount=goal.current_amount,
        essential_expense_monthly=goal.essential_expense_monthly,
        has_dangerous_debt=bool(flags.get("has_dangerous_debt")),
        debt_on_track=bool(flags.get("debt_on_track", True)),
        mastery_no_efund_invest=str(flags.get("mastery_no_efund_invest") or "not_started"),
    )
    return 200, result.to_dict()


class GoalsHandler(BaseHTTPRequestHandler):
    server_version = "WeloraGoals/0.1"

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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/goals":
            code, body = service_create_goal(self._read_json())
            self._json(code, body)
            return
        self._json(404, {"error": "not found"})

    def do_PATCH(self) -> None:
        path = urlparse(self.path).path
        m = re.fullmatch(r"/goals/([^/]+)/progress", path)
        if m:
            code, body = service_progress(m.group(1), self._read_json())
            self._json(code, body)
            return
        self._json(404, {"error": "not found"})

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)
        if path == "/goals":
            uid = (qs.get("user_id") or [None])[0]
            gtype = (qs.get("type") or [None])[0]
            code, body = service_list_goals(uid or "", gtype)
            self._json(code, body)
            return
        m = re.fullmatch(r"/goals/([^/]+)", path)
        if m:
            code, body = service_get_goal(m.group(1))
            self._json(code, body)
            return
        m = re.fullmatch(r"/users/([^/]+)/safety-gate", path)
        if m:
            code, body = service_safety_gate(m.group(1))
            self._json(code, body)
            return
        if path in ("/health", "/"):
            self._json(200, {"ok": True, "service": "welora-goals"})
            return
        self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[goals_api] {args[0]}")


def run_server(host: str = "127.0.0.1", port: int = 8787) -> None:
    httpd = HTTPServer((host, port), GoalsHandler)
    print(f"Welora Goals API on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    run_server()
