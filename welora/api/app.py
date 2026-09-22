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
from welora import budget as budget_svc
from welora import mode_c_act as mode_c_svc
from welora import os_accounts as accounts_svc
from welora import os_transactions as tx_svc
from welora import os_categories as categories_svc
from welora import content_map as content_svc
from welora import academy as academy_svc
from welora import core_constitution as core_const_svc
from welora.api.security_headers import SecurityHeadersMiddleware


class DeviceLoginBody(BaseModel):
    device_id: str = Field(..., min_length=4)
    display_name: Optional[str] = None

class OtpRequestBody(BaseModel):
    phone: str = Field(..., min_length=8)

class OtpVerifyBody(BaseModel):
    challenge_id: str
    code: str

class GuestRegisterBody(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str = Field(..., min_length=8)
    display_name: Optional[str] = None

class GuestLoginBody(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    password: str = Field(..., min_length=1)

class ForgotPasswordBody(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None

class ResetPasswordBody(BaseModel):
    reset_token: str = Field(..., min_length=8)
    new_password: str = Field(..., min_length=8)

class GoalCreateBody(BaseModel):
    user_id: str
    type: str = "emergency_fund"
    essential_expense_monthly: Optional[float] = None
    target_amount: Optional[float] = None
    current_amount: float = 0
    title: Optional[str] = None
    subtype: Optional[str] = None
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

class BudgetApplyBody(BaseModel):
    user_id: str
    confirm: bool = False
    replace_existing: bool = False
    draft: Optional[dict[str, Any]] = None
    lines: Optional[list[dict[str, Any]]] = None
    period: Optional[str] = None
    goal_contrib_lines: Optional[list[dict[str, Any]]] = None


class BudgetDraftFromAvgBody(BaseModel):
    user_id: str
    months: int = 3
    account_id: Optional[str] = None


class BudgetClosePeriodBody(BaseModel):
    user_id: str
    period: str
    confirm: bool = False
    spent_by_category: Optional[dict[str, Any]] = None

class AcademyReadBody(BaseModel):
    user_id: str
    node_id: str


class ModeCProposeBody(BaseModel):
    user_id: str
    message: str
    gate_status: Optional[str] = None
    answer_confidence: Optional[float] = None
    params: Optional[dict[str, Any]] = None
    reason: Optional[str] = None  # required non-empty when L-COOL-OFF triggers
    persona: Optional[str] = None  # staging stub P1–P6 (no full router)

class ModeCConfirmBody(BaseModel):
    user_id: str
    proposal_id: str
    confirm: bool = False
    # Deprecated: ignored — resolved server-side (anti-spoof).
    gate_status: Optional[str] = None
    answer_confidence: Optional[float] = None

class ModeCUndoBody(BaseModel):
    user_id: str
    act_id: str
    undo_token: str

class ModeCCrossTakeBody(BaseModel):
    user_id: str
    from_envelope_id: str
    to_envelope_id: str
    amount: float = 0

class CompanionLinkBody(BaseModel):
    user_id: str
    companion_user_id: str
    role: Optional[str] = None  # P6: child/con
    relation: Optional[str] = None

class ModeCCompanionConfirmBody(BaseModel):
    companion_user_id: str
    proposal_id: str
    confirm: bool = True
    # Spoof / client flags — ignored server-side (anti-bypass).
    dual_ok: Optional[bool] = None
    skip_dual: Optional[bool] = None
    is_companion: Optional[bool] = None
    gate_status: Optional[str] = None
    answer_confidence: Optional[float] = None

class ModeCCancelPendingBody(BaseModel):
    user_id: str
    proposal_id: str

class AccountCreateBody(BaseModel):
    user_id: str
    name: str
    type: str = "chi_tieu_hang_ngay"
    opening_balance: Optional[float] = 0
    balance: Optional[float] = None
    consent_ack: bool = False
    source: str = "manual"

class AccountUpdateBody(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    balance: Optional[float] = None
    opening_balance: Optional[float] = None
    unhide: Optional[bool] = None
    status: Optional[str] = None

class AccountBalanceBody(BaseModel):
    balance: float

class AccountSeedBody(BaseModel):
    user_id: str
    persona_id: str


class TxSplitLineBody(BaseModel):
    amount: float
    category: str
    note: Optional[str] = None
    split_id: Optional[str] = None

class TransactionCreateBody(BaseModel):
    user_id: str
    account_id: str
    amount: float
    category: str
    date: str
    note: Optional[str] = None
    merchant: Optional[str] = None
    consent_ack: Optional[bool] = None
    splits: Optional[list[TxSplitLineBody]] = None

class TransactionUpdateBody(BaseModel):
    account_id: Optional[str] = None
    amount: Optional[float] = None
    category: Optional[str] = None
    date: Optional[str] = None
    note: Optional[str] = None
    merchant: Optional[str] = None
    splits: Optional[list[TxSplitLineBody]] = None
    unhide: Optional[bool] = None
    status: Optional[str] = None

class TransactionSplitBody(BaseModel):
    splits: list[TxSplitLineBody]
    amount: Optional[float] = None
    merchant: Optional[str] = None
    category: Optional[str] = None



class CategoryCreateBody(BaseModel):
    user_id: str
    name: str
    kind: str = "variable"
    tags: Optional[list[str]] = None
    note: Optional[str] = None

class CategoryUpdateBody(BaseModel):
    name: Optional[str] = None
    kind: Optional[str] = None
    tags: Optional[list[str]] = None
    note: Optional[str] = None
    reactivate: Optional[bool] = None
    status: Optional[str] = None

class CategoryDisableBody(BaseModel):
    reassign_to: Optional[str] = None
    target_category_id: Optional[str] = None

class CategoryReassignBody(BaseModel):
    reassign_to: str
    target_category_id: Optional[str] = None

class CategorySeedBody(BaseModel):
    user_id: str



class AcademyKuatBody(BaseModel):
    user_id: str
    node_id: str
    answers: list[dict[str, Any]] = Field(default_factory=list)


def _respond(code: int, body: dict) -> dict:
    if code >= 400:
        raise HTTPException(status_code=code, detail=body.get("error") or body)
    return body



def _short_git_sha() -> str:
    """Short tip SHA for UAT deploy confirmation (Render: RENDER_GIT_COMMIT)."""
    import os
    import subprocess
    for key in (
        "WELORA_GIT_SHA",
        "RENDER_GIT_COMMIT",
        "GIT_SHA",
        "SOURCE_VERSION",
        "GITHUB_SHA",
    ):
        val = (os.environ.get(key) or "").strip()
        if val:
            return val[:7]
    try:
        root = Path(__file__).resolve().parents[2]
        out = subprocess.check_output(
            ["git", "rev-parse", "--short=7", "HEAD"],
            cwd=str(root),
            stderr=subprocess.DEVNULL,
            timeout=1.5,
        )
        sha = out.decode("utf-8", errors="ignore").strip()
        if sha:
            return sha[:7]
    except Exception:
        pass
    return "unknown"

def create_app() -> FastAPI:
    app = FastAPI(title="Welora API", version="0.2.0")
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
    app.add_middleware(SecurityHeadersMiddleware)
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

    @app.get("/app/budget", include_in_schema=False)
    @app.get("/app/budget/", include_in_schema=False)
    def budget_ui() -> FileResponse:
        return FileResponse(static_dir / "budget.html")

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

    @app.get("/app/core-constitution", include_in_schema=False)
    @app.get("/app/core-constitution/", include_in_schema=False)
    def core_constitution_ui() -> FileResponse:
        return FileResponse(static_dir / "core-constitution.html")

    @app.get("/app/academy", include_in_schema=False)
    @app.get("/app/academy/", include_in_schema=False)
    @app.get("/app/learn", include_in_schema=False)
    def academy_ui() -> FileResponse:
        return FileResponse(static_dir / "academy.html")

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

    @app.get("/app/login", include_in_schema=False)
    @app.get("/app/login/", include_in_schema=False)
    def login_ui() -> FileResponse:
        return FileResponse(static_dir / "login.html")

    @app.get("/app/register", include_in_schema=False)
    @app.get("/app/register/", include_in_schema=False)
    def register_ui() -> FileResponse:
        return FileResponse(static_dir / "register.html")

    @app.get("/app/forgot-password", include_in_schema=False)
    @app.get("/app/forgot-password/", include_in_schema=False)
    def forgot_password_ui() -> FileResponse:
        return FileResponse(static_dir / "forgot-password.html")

    @app.get("/app/reset-password", include_in_schema=False)
    @app.get("/app/reset-password/", include_in_schema=False)
    def reset_password_ui() -> FileResponse:
        return FileResponse(static_dir / "reset-password.html")

    @app.get("/app/pre-rule", include_in_schema=False)
    @app.get("/app/pre-rule/", include_in_schema=False)
    def prerule_ui() -> FileResponse:
        """Debug-only UI — off by default (WELORA_DEBUG_PRERULE=1 to enable)."""
        import os
        flag = (os.environ.get("WELORA_DEBUG_PRERULE") or "0").strip().lower()
        if flag not in ("1", "true", "yes", "on"):
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(static_dir / "prerule.html")

    @app.get("/app/health-score", include_in_schema=False)
    @app.get("/app/health-score/", include_in_schema=False)
    def health_score_ui() -> FileResponse:
        return FileResponse(static_dir / "healthscore.html")

    @app.get("/app/dual-control", include_in_schema=False)
    @app.get("/app/dual-control/", include_in_schema=False)
    def dual_control_ui() -> FileResponse:
        return FileResponse(static_dir / "dual-control.html")

    @app.get("/app/accounts", include_in_schema=False)
    @app.get("/app/accounts/", include_in_schema=False)
    def accounts_ui() -> FileResponse:
        return FileResponse(static_dir / "accounts.html")

    @app.get("/app/transactions", include_in_schema=False)
    @app.get("/app/transactions/", include_in_schema=False)
    def transactions_ui() -> FileResponse:
        return FileResponse(static_dir / "transactions.html")


    @app.get("/app/categories", include_in_schema=False)
    @app.get("/app/categories/", include_in_schema=False)
    def categories_ui() -> FileResponse:
        return FileResponse(static_dir / "categories.html")



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

    @app.get("/app/os", include_in_schema=False)
    @app.get("/app/os/", include_in_schema=False)
    def os_ui_redirect() -> RedirectResponse:
        """WeloraOS entry alias — shell lives at /app (+ goals / dual-control /os/*)."""
        return RedirectResponse(url="/app", status_code=302)

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
            "git_sha": _short_git_sha(),
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

    @app.post("/auth/register", tags=["auth"], status_code=201)
    def auth_register(body: GuestRegisterBody) -> dict:
        return _respond(*auth_svc.service_register(body.model_dump()))

    @app.post("/auth/login", tags=["auth"])
    def auth_login(body: GuestLoginBody) -> dict:
        return _respond(*auth_svc.service_login(body.model_dump()))

    @app.post("/auth/logout", tags=["auth"])
    def auth_logout(authorization: Optional[str] = Header(None)) -> dict:
        token = ""
        if authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
        return _respond(*auth_svc.service_logout(token))

    @app.post("/auth/forgot-password", tags=["auth"])
    def auth_forgot_password(body: ForgotPasswordBody) -> dict:
        return _respond(*auth_svc.service_forgot_password(body.model_dump()))

    @app.post("/auth/reset-password", tags=["auth"])
    def auth_reset_password(body: ResetPasswordBody) -> dict:
        return _respond(*auth_svc.service_reset_password(body.model_dump()))

    @app.post("/auth/demo/seed", tags=["auth"])
    def auth_demo_seed() -> dict:
        """Partner walkthrough seed — account + P2/P4 DNA/goals (no gate/Hard Deny bypass)."""
        code, out = auth_svc.service_demo_seed()
        if not auth_svc.guest_demo_enabled():
            return _respond(code, out)
        out.pop("flag", None)
        try:
            from welora.fixtures import seed_priority_demo_personas
            personas = seed_priority_demo_personas()
            out["personas"] = {
                pid: {
                    "user_id": fx["user_id"],
                    "household": fx.get("household"),
                    "persona_id": fx.get("persona_id", pid),
                    "os_goals": list(fx.get("os_goals") or []),
                    "os_accounts_count": len(fx.get("os_accounts") or []),
                    "safety_gate": (fx.get("safety_gate") or {}).get("status"),
                }
                for pid, fx in personas.items()
            }
        except Exception as exc:  # pragma: no cover — surface seed errors without 500 if account ok
            out["personas_error"] = str(exc)
        return _respond(code, out)

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

    @app.get("/constitution/core", tags=["constitution"])
    def get_core_constitution() -> dict:
        return _respond(*core_const_svc.service_get_core_constitution())

    @app.get("/academy/tree", tags=["academy"])
    def academy_tree(user_id: str = Query(...)) -> dict:
        return _respond(*academy_svc.service_get_tree(user_id))

    @app.get("/academy/nodes/{node_id}", tags=["academy"])
    def academy_node(node_id: str, user_id: str = Query(...)) -> dict:
        return _respond(*academy_svc.service_get_node(user_id, node_id))

    @app.post("/academy/nodes/{node_id}/read", tags=["academy"])
    def academy_read(node_id: str, body: AcademyReadBody) -> dict:
        payload = body.model_dump()
        payload["node_id"] = node_id or payload.get("node_id")
        return _respond(*academy_svc.service_mark_read(payload))

    @app.post("/academy/kuat", tags=["academy"])
    def academy_kuat(body: AcademyKuatBody) -> dict:
        return _respond(*academy_svc.service_submit_kuat(body.model_dump()))

    @app.post("/goals", tags=["goals"], status_code=201)
    def goals_create(body: GoalCreateBody) -> dict:
        code, out = goals_svc.service_create_goal(body.model_dump(exclude_none=True))
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

    @app.get("/budget", tags=["budget"])
    def budget_get(user_id: str = Query(...)) -> dict:
        return _respond(*budget_svc.service_get(user_id))

    @app.post("/budget", tags=["budget"])
    def budget_post(body: BudgetApplyBody) -> dict:
        return _respond(*budget_svc.service_apply(body.model_dump()))

    @app.post("/budget/draft-from-avg", tags=["budget"])
    def budget_draft_from_avg(body: BudgetDraftFromAvgBody) -> dict:
        return _respond(*budget_svc.service_draft_from_avg(body.model_dump()))

    @app.post("/budget/close-period", tags=["budget"])
    @app.post("/budget/rollover", tags=["budget"])
    def budget_close_period(body: BudgetClosePeriodBody) -> dict:
        return _respond(*budget_svc.service_close_period(body.model_dump()))

    @app.get("/content", tags=["content"])
    def content_index() -> dict:
        return _respond(*content_svc.service_list_content_keys())

    @app.get("/content/{key}", tags=["content"])
    def content_by_key(key: str) -> dict:
        return _respond(*content_svc.service_get_content(key))


    @app.post("/agent/mode-c/propose", tags=["agent", "mode-c"])
    def mode_c_propose(body: ModeCProposeBody) -> dict:
        # Always resolve gate + confidence server-side; ignore client spoof fields.
        if body.persona:
            mode_c_svc.set_persona(user_id=body.user_id, persona=str(body.persona))
        gate, conf = mode_c_svc.resolve_server_gate_confidence(body.user_id)
        return _respond(*mode_c_svc.propose_act(
            user_id=body.user_id,
            message=body.message,
            gate_status=str(gate),
            answer_confidence=float(conf),
            params=body.params,
            reason=body.reason,
        ))

    @app.post("/agent/mode-c/confirm", tags=["agent", "mode-c"])
    def mode_c_confirm(
        body: ModeCConfirmBody,
        x_test_cool_off_advance: Optional[str] = Header(None, alias="X-Test-Cool-Off-Advance"),
    ) -> dict:
        # Re-check gate + confidence on confirm (client fields ignored).
        gate, conf = mode_c_svc.resolve_server_gate_confidence(body.user_id)
        advance = str(x_test_cool_off_advance or "").strip().lower() in (
            "1", "true", "yes", "y", "on",
        )
        code, out = mode_c_svc.confirm_act(
            user_id=body.user_id,
            proposal_id=body.proposal_id,
            confirm=bool(body.confirm),
            gate_status=str(gate),
            answer_confidence=float(conf),
            cool_off_advance=advance,
        )
        # Early cool-off confirm stays pending (200) — not an HTTP error.
        return _respond(code, out)

    @app.post("/os/persona", tags=["os", "cool-off"])
    def os_persona_set(body: dict[str, Any]) -> dict:
        return _respond(*mode_c_svc.set_persona(
            user_id=str(body.get("user_id") or ""),
            persona=str(body.get("persona") or ""),
        ))

    @app.get("/os/persona", tags=["os", "cool-off"])
    def os_persona_get(user_id: str = Query(...)) -> dict:
        p = mode_c_svc.get_persona(user_id)
        return {
            "user_id": user_id,
            "persona": p,
            "floor_months": mode_c_svc.PERSONA_FLOOR_MONTHS.get(p),
            "policy_version": mode_c_svc.POLICY_COOL_OFF,
        }

    @app.post("/agent/mode-c/undo", tags=["agent", "mode-c"])
    def mode_c_undo(body: ModeCUndoBody) -> dict:
        return _respond(*mode_c_svc.undo_act(
            user_id=body.user_id,
            act_id=body.act_id,
            undo_token=body.undo_token,
        ))

    @app.get("/os/envelopes", tags=["os", "mode-c"])
    def os_envelopes(user_id: str = Query(...)) -> dict:
        return _respond(*mode_c_svc.list_envelopes(user_id))

    @app.get("/os/reminders", tags=["os", "mode-c"])
    def os_reminders(user_id: str = Query(...)) -> dict:
        return _respond(*mode_c_svc.list_reminders(user_id))

    @app.get("/os/estate-checklist", tags=["os", "mode-c"])
    def os_estate(user_id: str = Query(...)) -> dict:
        return _respond(*mode_c_svc.get_estate_checklist(user_id))

    @app.post("/os/envelopes/cross-take", tags=["os", "mode-c"])
    def os_cross_take(body: ModeCCrossTakeBody) -> dict:
        return _respond(*mode_c_svc.deny_cross_take(
            user_id=body.user_id,
            from_envelope_id=body.from_envelope_id,
            to_envelope_id=body.to_envelope_id,
            amount=float(body.amount or 0),
        ))

    @app.post("/os/companion", tags=["os", "dual-control"])
    def os_companion_create(body: CompanionLinkBody) -> dict:
        return _respond(*mode_c_svc.set_companion(
            user_id=body.user_id,
            companion_user_id=body.companion_user_id,
            role=body.role,
            relation=body.relation,
        ))

    @app.get("/os/companion", tags=["os", "dual-control"])
    def os_companion_list(user_id: str = Query(...)) -> dict:
        return _respond(*mode_c_svc.list_companions(user_id))

    @app.get("/os/dual-control/pending", tags=["os", "dual-control"])
    def os_dual_pending(user_id: str = Query(...)) -> dict:
        return _respond(*mode_c_svc.list_pending_dual(user_id))

    @app.post("/agent/mode-c/companion-confirm", tags=["agent", "mode-c", "dual-control"])
    def mode_c_companion_confirm(body: ModeCCompanionConfirmBody) -> dict:
        # Ignore client spoof flags (dual_ok / skip_dual / is_companion / gate).
        return _respond(*mode_c_svc.companion_confirm_act(
            companion_user_id=body.companion_user_id,
            proposal_id=body.proposal_id,
            confirm=bool(body.confirm),
        ))

    @app.post("/agent/mode-c/cancel-pending", tags=["agent", "mode-c", "dual-control"])
    def mode_c_cancel_pending(body: ModeCCancelPendingBody) -> dict:
        return _respond(*mode_c_svc.cancel_pending_dual(
            user_id=body.user_id,
            proposal_id=body.proposal_id,
        ))


    # --- WeloraOS P0 Accounts CRUD (manual + consent + soft-hide) ---
    @app.post("/os/accounts", tags=["os", "accounts"], status_code=201)
    def os_accounts_create(body: AccountCreateBody) -> dict:
        payload = body.model_dump(exclude_none=True)
        code, out = accounts_svc.service_create_account(payload)
        # Preserve consent_required + consent_text for the gate UI / tests.
        if code >= 400 and out.get("consent_required"):
            raise HTTPException(status_code=code, detail=out)
        if code == 201:
            return out
        return _respond(code, out)

    @app.get("/os/accounts", tags=["os", "accounts"])
    def os_accounts_list(
        user_id: str = Query(...),
        include_hidden: bool = Query(False),
    ) -> dict:
        return _respond(*accounts_svc.service_list_accounts(
            user_id, include_hidden=include_hidden,
        ))

    @app.get("/os/accounts/{account_id}", tags=["os", "accounts"])
    def os_accounts_get(account_id: str) -> dict:
        return _respond(*accounts_svc.service_get_account(account_id))

    @app.patch("/os/accounts/{account_id}", tags=["os", "accounts"])
    def os_accounts_patch(account_id: str, body: AccountUpdateBody) -> dict:
        return _respond(*accounts_svc.service_update_account(
            account_id, body.model_dump(exclude_none=True),
        ))

    @app.patch("/os/accounts/{account_id}/balance", tags=["os", "accounts"])
    def os_accounts_balance(account_id: str, body: AccountBalanceBody) -> dict:
        return _respond(*accounts_svc.service_set_balance(
            account_id, body.model_dump(),
        ))

    @app.post("/os/accounts/{account_id}/hide", tags=["os", "accounts"])
    def os_accounts_hide(account_id: str) -> dict:
        return _respond(*accounts_svc.service_hide_account(account_id))

    @app.delete("/os/accounts/{account_id}", tags=["os", "accounts"])
    def os_accounts_soft_delete(account_id: str) -> dict:
        """Soft-delete alias — hide, never hard-delete."""
        return _respond(*accounts_svc.service_hide_account(account_id))

    @app.post("/os/accounts/seed-persona", tags=["os", "accounts"])
    def os_accounts_seed(body: AccountSeedBody) -> dict:
        return _respond(*accounts_svc.service_seed_from_persona(
            body.user_id, body.persona_id,
        ))


    # --- WeloraOS P0 Transactions (manual + split; CSV parser separate) ---
    @app.post("/os/transactions", tags=["os", "transactions"], status_code=201)
    def os_transactions_create(body: TransactionCreateBody) -> dict:
        payload = body.model_dump(exclude_none=True)
        code, out = tx_svc.service_create_transaction(payload)
        if code >= 400 and out.get("consent_required"):
            raise HTTPException(status_code=code, detail=out)
        if code == 201:
            return out
        return _respond(code, out)

    @app.get("/os/transactions", tags=["os", "transactions"])
    def os_transactions_list(
        user_id: str = Query(...),
        account_id: Optional[str] = Query(None),
        include_hidden: bool = Query(False),
    ) -> dict:
        return _respond(*tx_svc.service_list_transactions(
            user_id, account_id=account_id, include_hidden=include_hidden,
        ))

    @app.get("/os/transactions/{tx_id}", tags=["os", "transactions"])
    def os_transactions_get(tx_id: str) -> dict:
        return _respond(*tx_svc.service_get_transaction(tx_id))

    @app.patch("/os/transactions/{tx_id}", tags=["os", "transactions"])
    def os_transactions_patch(tx_id: str, body: TransactionUpdateBody) -> dict:
        return _respond(*tx_svc.service_update_transaction(
            tx_id, body.model_dump(exclude_none=True),
        ))

    @app.post("/os/transactions/{tx_id}/split", tags=["os", "transactions"])
    def os_transactions_split(tx_id: str, body: TransactionSplitBody) -> dict:
        return _respond(*tx_svc.service_split_transaction(
            tx_id, body.model_dump(exclude_none=True),
        ))

    @app.post("/os/transactions/{tx_id}/hide", tags=["os", "transactions"])
    def os_transactions_hide(tx_id: str) -> dict:
        return _respond(*tx_svc.service_hide_transaction(tx_id))

    @app.delete("/os/transactions/{tx_id}", tags=["os", "transactions"])
    def os_transactions_soft_delete(tx_id: str) -> dict:
        """Soft-delete alias — hide, never hard-delete."""
        return _respond(*tx_svc.service_hide_transaction(tx_id))


    # --- WeloraOS P0 Categories (Fixed/Variable/Goals + tags + soft-disable) ---
    @app.get("/os/categories/defaults", tags=["os", "categories"])
    def os_categories_defaults() -> dict:
        return _respond(*categories_svc.service_defaults())

    @app.post("/os/categories/seed-defaults", tags=["os", "categories"])
    def os_categories_seed(body: CategorySeedBody) -> dict:
        return _respond(*categories_svc.service_seed_defaults(body.user_id))

    @app.post("/os/categories", tags=["os", "categories"], status_code=201)
    def os_categories_create(body: CategoryCreateBody) -> dict:
        payload = body.model_dump(exclude_none=True)
        code, out = categories_svc.service_create_category(payload)
        if code == 201:
            return out
        return _respond(code, out)

    @app.get("/os/categories", tags=["os", "categories"])
    def os_categories_list(
        user_id: str = Query(...),
        include_disabled: bool = Query(False),
    ) -> dict:
        return _respond(*categories_svc.service_list_categories(
            user_id, include_disabled=include_disabled,
        ))

    @app.get("/os/categories/{category_id}", tags=["os", "categories"])
    def os_categories_get(category_id: str) -> dict:
        return _respond(*categories_svc.service_get_category(category_id))

    @app.patch("/os/categories/{category_id}", tags=["os", "categories"])
    def os_categories_patch(category_id: str, body: CategoryUpdateBody) -> dict:
        return _respond(*categories_svc.service_update_category(
            category_id, body.model_dump(exclude_none=True),
        ))

    @app.post("/os/categories/{category_id}/reassign", tags=["os", "categories"])
    def os_categories_reassign(category_id: str, body: CategoryReassignBody) -> dict:
        payload = body.model_dump(exclude_none=True)
        return _respond(*categories_svc.service_reassign_category(category_id, payload))

    @app.post("/os/categories/{category_id}/disable", tags=["os", "categories"])
    def os_categories_disable(
        category_id: str, body: Optional[CategoryDisableBody] = None,
    ) -> dict:
        payload = body.model_dump(exclude_none=True) if body else {}
        code, out = categories_svc.service_disable_category(category_id, payload)
        # Preserve reassign_required + counts for the UI / tests.
        if code >= 400 and out.get("reassign_required"):
            raise HTTPException(status_code=code, detail=out)
        return _respond(code, out)


    return app


app = create_app()
