"""Welora FastAPI app — P1-E5 / P2-E2 / P2-E4 / P2-E8"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from welora import auth as auth_svc
from welora import chat_service as chat_svc
from welora import goals_api as goals_svc
from welora import onboarding_api as ob_svc
from welora import pre_rule_service as pre_svc
from welora import health_score as hs_svc
from welora import csv_parser as csv_svc
from welora import content_map as content_svc


class DeviceLoginBody(BaseModel):
    device_id: str = Field(..., min_length=4)
    display_name: Optional[str] = None

class OtpRequestBody(BaseModel):
    phone: str = Field(..., min_length=8)

class OtpVerifyBody(BaseModel):
    challenge_id: str
    code: str

class GoalCreateBody(BaseModel):
    user_id: str
    type: str = "emergency_fund"
    essential_expense_monthly: float
    current_amount: float = 0
    linked_from_onboarding: bool = False
    monthly_contribution: float = 0
    plan_method: Optional[str] = None

class ProgressBody(BaseModel):
    set_amount: Optional[float] = None
    add_amount: Optional[float] = None

class SessionCreateBody(BaseModel):
    user_id: str

class ChatBody(BaseModel):
    user_id: str
    message: str
    context: Optional[dict[str, Any]] = None

class PreRuleBody(BaseModel):
    user_id: str
    message: str
    context: Optional[dict[str, Any]] = None

class MasteryPatchBody(BaseModel):
    state: str
    node_id: Optional[str] = "no_efund_invest"

class CsvParseBody(BaseModel):
    text: str
    filename: Optional[str] = None


def _respond(code: int, body: dict) -> dict:
    if code >= 400:
        raise HTTPException(status_code=code, detail=body.get("error") or body)
    return body


def create_app() -> FastAPI:
    app = FastAPI(title="Welora API", version="0.2.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/app/onboarding")

    @app.get("/app", include_in_schema=False)
    @app.get("/app/", include_in_schema=False)
    def app_home() -> FileResponse:
        return FileResponse(static_dir / "home.html")

    @app.get("/app/onboarding", include_in_schema=False)
    def onboarding_ui() -> FileResponse:
        return FileResponse(static_dir / "onboarding.html")

    @app.get("/app/demo", include_in_schema=False)
    def demo_ui() -> FileResponse:
        return FileResponse(static_dir / "demo.html")

    @app.get("/app/safety", include_in_schema=False)
    def safety_ui() -> FileResponse:
        return FileResponse(static_dir / "safety.html")

    @app.get("/app/chat", include_in_schema=False)
    def chat_ui() -> FileResponse:
        return FileResponse(static_dir / "chat.html")

    @app.get("/app/parser", include_in_schema=False)
    def parser_ui() -> FileResponse:
        return FileResponse(static_dir / "parser.html")

    @app.get("/app/metrics", include_in_schema=False)
    @app.get("/app/metrics/", include_in_schema=False)
    def metrics_ui() -> FileResponse:
        return FileResponse(static_dir / "metrics.html")

    @app.get("/app/logs", include_in_schema=False)
    @app.get("/app/logs/", include_in_schema=False)
    def logs_ui() -> FileResponse:
        return FileResponse(static_dir / "logs.html")

    @app.get("/app/constitution", include_in_schema=False)
    @app.get("/app/constitution/", include_in_schema=False)
    def constitution_ui() -> FileResponse:
        return FileResponse(static_dir / "constitution.html")

    @app.get("/app/dna", include_in_schema=False)
    @app.get("/app/dna/", include_in_schema=False)
    def dna_ui() -> FileResponse:
        return FileResponse(static_dir / "dna.html")

    @app.get("/app/goals", include_in_schema=False)
    @app.get("/app/goals/", include_in_schema=False)
    def goals_ui() -> FileResponse:
        return FileResponse(static_dir / "goals.html")

    @app.get("/app/otp", include_in_schema=False)
    @app.get("/app/otp/", include_in_schema=False)
    def otp_ui() -> FileResponse:
        return FileResponse(static_dir / "otp.html")

    @app.get("/app/pre-rule", include_in_schema=False)
    @app.get("/app/pre-rule/", include_in_schema=False)
    def prerule_ui() -> FileResponse:
        return FileResponse(static_dir / "prerule.html")

    @app.get("/app/content/{content_id}", include_in_schema=False)
    def content_ui_id(content_id: str) -> FileResponse:
        return FileResponse(static_dir / "content.html")

    @app.get("/app/content/module/{module_id}", include_in_schema=False)
    def content_module_ui(module_id: str) -> FileResponse:
        return FileResponse(static_dir / "content.html")

    @app.get("/app/content", include_in_schema=False)
    def content_ui() -> FileResponse:
        return FileResponse(static_dir / "content.html")

    @app.get("/app/goal", include_in_schema=False)
    def goal_ui_redirect() -> RedirectResponse:
        return RedirectResponse(url="/app/safety")

    @app.get("/health", tags=["system"])
    def health() -> dict:
        import os
        dialect = "unknown"
        try:
            from welora.db.connection import detect_dialect
            dialect = detect_dialect()
        except Exception:
            pass
        return {
            "status": "ok",
            "service": "welora",
            "phase": "2",
            "env": os.environ.get("WELORA_ENV", "local"),
            "store": os.environ.get("WELORA_STORE", "memory"),
            "dialect": dialect,
            "llm": os.environ.get("WELORA_LLM_PROVIDER", "stub"),
            "gate_months": 3,
            "hard_deny": True,
        }

    @app.get("/healthz", tags=["system"], include_in_schema=False)
    def healthz() -> dict:
        return health()

    @app.get("/metrics", tags=["system"], summary="Agent counters (no PII)")
    def metrics() -> dict:
        from welora.metrics import service_get_metrics
        return _respond(*service_get_metrics())

    @app.post("/auth/device", tags=["auth"])
    def auth_device(body: DeviceLoginBody) -> dict:
        return _respond(*auth_svc.service_device_login(body.model_dump()))

    @app.post("/auth/otp/request", tags=["auth"])
    def auth_otp_request(body: OtpRequestBody) -> dict:
        return _respond(*auth_svc.service_otp_request(body.model_dump()))

    @app.post("/auth/otp/verify", tags=["auth"])
    def auth_otp_verify(body: OtpVerifyBody) -> dict:
        return _respond(*auth_svc.service_otp_verify(body.model_dump()))

    @app.get("/auth/me", tags=["auth"])
    def auth_me(authorization: Optional[str] = Header(None)) -> dict:
        token = ""
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        return _respond(*auth_svc.service_me(token))

    @app.post("/onboarding/session", tags=["onboarding"], status_code=201)
    def onboarding_create(body: SessionCreateBody) -> dict:
        code, out = ob_svc.service_create_session(body.model_dump())
        if code == 201:
            return out
        return _respond(code, out)

    @app.patch("/onboarding/session/{session_id}/step/{step}", tags=["onboarding"])
    def onboarding_step(session_id: str, step: int, body: dict[str, Any]) -> dict:
        return _respond(*ob_svc.service_patch_step(session_id, step, body))

    @app.post("/onboarding/session/{session_id}/complete", tags=["onboarding"])
    def onboarding_complete(session_id: str) -> dict:
        return _respond(*ob_svc.service_complete(session_id))

    @app.get("/users/{user_id}/dna", tags=["onboarding"])
    def get_dna(user_id: str) -> dict:
        return _respond(*ob_svc.service_get_dna(user_id))

    @app.get("/users/{user_id}/personal-constitution", tags=["onboarding"])
    def get_constitution(user_id: str) -> dict:
        return _respond(*ob_svc.service_get_constitution(user_id))

    @app.post("/goals", tags=["goals"], status_code=201)
    def goals_create(body: GoalCreateBody) -> dict:
        code, out = goals_svc.service_create_goal(body.model_dump())
        if code == 201:
            return out
        return _respond(code, out)

    @app.get("/goals", tags=["goals"])
    def goals_list(user_id: str = Query(...), type: Optional[str] = Query(None, alias="type")) -> dict:
        return _respond(*goals_svc.service_list_goals(user_id, type))

    @app.get("/goals/{goal_id}", tags=["goals"])
    def goals_get(goal_id: str) -> dict:
        return _respond(*goals_svc.service_get_goal(goal_id))

    @app.patch("/goals/{goal_id}/progress", tags=["goals"])
    def goals_progress(goal_id: str, body: ProgressBody) -> dict:
        return _respond(*goals_svc.service_progress(goal_id, body.model_dump(exclude_none=True)))

    @app.get("/users/{user_id}/safety-gate", tags=["goals", "safety"])
    def safety_gate(user_id: str) -> dict:
        return _respond(*goals_svc.service_safety_gate(user_id))

    @app.get("/users/{user_id}/health-score", tags=["health"])
    def health_score(user_id: str) -> dict:
        return _respond(*hs_svc.service_get_health_score(user_id))

    @app.get("/users/{user_id}/mastery", tags=["mastery"])
    def mastery_get(user_id: str, node_id: str = Query("no_efund_invest")) -> dict:
        from welora.mastery import service_get_mastery
        return _respond(*service_get_mastery(user_id, node_id))

    @app.patch("/users/{user_id}/mastery", tags=["mastery"])
    def mastery_patch(user_id: str, body: MasteryPatchBody) -> dict:
        from welora.mastery import service_patch_mastery
        return _respond(*service_patch_mastery(user_id, body.model_dump()))

    @app.post("/agent/pre-rule", tags=["agent"])
    def agent_pre_rule(body: PreRuleBody) -> dict:
        code, out = pre_svc.service_evaluate(message=body.message, user_id=body.user_id, context_seed=body.context)
        return _respond(code, out)

    @app.post("/agent/chat", tags=["agent"])
    def agent_chat(body: ChatBody) -> dict:
        from welora.llm_adapter import make_llm_callable
        code, out = chat_svc.service_chat(user_id=body.user_id, message=body.message, context_seed=body.context, call_llm=make_llm_callable())
        return _respond(code, out)

    @app.get("/agent/decision-logs", tags=["agent"])
    def agent_logs(user_id: str = Query(...), limit: int = Query(20, ge=1, le=100)) -> dict:
        return _respond(*chat_svc.service_list_logs(user_id, limit))

    @app.post("/parser/csv", tags=["parser"])
    def parse_csv(body: CsvParseBody) -> dict:
        return _respond(*csv_svc.service_parse_csv(text=body.text, filename=body.filename or ""))

    @app.get("/content", tags=["content"])
    def content_index() -> dict:
        return _respond(*content_svc.service_list_content_keys())

    @app.get("/content/{key}", tags=["content"])
    def content_by_key(key: str) -> dict:
        return _respond(*content_svc.service_get_content(key))

    return app


app = create_app()
