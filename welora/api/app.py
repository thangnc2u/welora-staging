"""Welora FastAPI app — P1-E5 / P2-E2 / P2-E4 / P2-E8"""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Optional

from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
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
from welora import entitlements as entitlements_svc
from welora import checkout as checkout_svc
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

class EmailOtpRequestBody(BaseModel):
    email: str = Field(..., min_length=5, max_length=254)

class EmailOtpVerifyBody(BaseModel):
    challenge_id: str = Field(..., min_length=8, max_length=64)
    code: str = Field(..., min_length=4, max_length=12)

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


def _shell_js_src() -> str:
    """Cache-bust query for shell.js — one shared ver for every /app* HTML."""
    return f"/static/shell.js?v={_short_git_sha()}"


_SHELL_JS_SRC_RE = re.compile(r'src=(["\'])/static/shell\.js(?:\?[^"\']*)?\1')


def _cache_bust_shell_js(html: str) -> str:
    """Rewrite shell.js script tags to include ?v=<git_sha|asset_ver>."""
    src = _shell_js_src()

    def _repl(m: re.Match[str]) -> str:
        q = m.group(1)
        return f"src={q}{src}{q}"

    return _SHELL_JS_SRC_RE.sub(_repl, html)


def _serve_app_html(static_dir: Path, name: str) -> HTMLResponse:
    """Serve /app* HTML with consistent shell.js cache-bust query."""
    html = (static_dir / name).read_text(encoding="utf-8")
    return HTMLResponse(content=_cache_bust_shell_js(html))



class EntitlementTrialStartBody(BaseModel):
    phone: str = Field(..., min_length=8)
    otp_code: Optional[str] = None
    user_id: Optional[str] = None


class EntitlementEventBody(BaseModel):
    event: str = Field(..., min_length=1)
    payload: Optional[dict] = None


class CheckoutQuoteBody(BaseModel):
    plan_id: str = Field(..., min_length=1)
    billing_cycle: str = "month"
    coupon_code: Optional[str] = Field(None, max_length=40)


class CheckoutOrderBody(BaseModel):
    plan_id: str = Field(..., min_length=1)
    billing_cycle: str = "month"
    agree_terms: bool = False
    # CK-04: accepted only so we can prove it is IGNORED — server prices only.
    amount: Optional[Any] = None
    coupon_code: Optional[str] = Field(None, max_length=40)


class AdminReasonBody(BaseModel):
    reason: str = ""


class AdminRefundBody(BaseModel):
    reason: str = ""
    stage: str = "request"
    override: bool = False
    bank_ref: Optional[str] = Field(None, max_length=120)
    amount: Optional[int] = None


class UserRefundBody(BaseModel):
    reason: str = ""


class RenewMagicBody(BaseModel):
    token: str = Field(..., min_length=20, max_length=200)


class Admin2FABody(BaseModel):
    code: str = Field(..., min_length=6, max_length=10)


class AdminCouponBody(BaseModel):
    code: str = Field(..., min_length=3, max_length=32)
    kind: str
    value: int
    plans: list[str] = []
    cycles: list[str] = []
    starts_at: Optional[str] = None
    ends_at: Optional[str] = None
    max_redemptions: Optional[int] = None
    per_user_limit: int = 1
    reason: str = ""


class AdminCouponActiveBody(BaseModel):
    active: bool
    reason: str = ""


class AdminShiftBody(BaseModel):
    order_code: int
    days: float
    reason: str = ""


class AdminRenewalRunBody(BaseModel):
    # non-prod only (WELORA_CHECKOUT_TEST_HOOKS=1): run the job as if N days later
    now_offset_days: Optional[float] = None


class PushSubscriptionBody(BaseModel):
    """W3C PushSubscription.toJSON() — endpoint + keys{p256dh, auth} (public keys)."""

    endpoint: str = Field(..., min_length=12, max_length=1000)
    keys: dict[str, str] = Field(default_factory=dict)


class PushUnsubscribeBody(BaseModel):
    endpoint: str = Field(..., min_length=12, max_length=1000)


class AdminConfirmWebhookBody(BaseModel):
    webhook_url: str = Field(..., min_length=8)


def _bearer_uid(authorization: Optional[str]) -> Optional[str]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization[7:].strip()
    if not token:
        return None
    try:
        return auth_svc.resolve_token(token)
    except Exception:
        return None


def _require_login(authorization: Optional[str]) -> str:
    uid = _bearer_uid(authorization)
    if not uid:
        raise HTTPException(
            status_code=401,
            detail={"error_code": "LOGIN_REQUIRED", "message": "Cần đăng nhập trước khi thanh toán"},
        )
    return uid


def _require_admin(authorization: Optional[str]) -> str:
    """CK-10 guard — bearer token whose users.role ∈ auth.ADMIN_ROLES (fail-closed)."""
    uid = _bearer_uid(authorization)
    if not uid:
        raise HTTPException(status_code=401, detail={"error_code": "ADMIN_LOGIN_REQUIRED"})
    role = ""
    try:
        from welora.db.connection import get_connection

        conn = get_connection(None)
        try:
            row = conn.execute("SELECT role FROM users WHERE user_id=?", (uid,)).fetchone()
            role = ((row["role"] if row else "") or "").strip().lower()
        finally:
            conn.close()
    except Exception:
        role = ""
    if role not in auth_svc.ADMIN_ROLES:
        raise HTTPException(status_code=403, detail={"error_code": "ADMIN_ONLY"})
    return uid


def _bearer_token(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        return ""
    return authorization[7:].strip()


def _require_admin_2fa(authorization: Optional[str]) -> str:
    """Mục 9 — admin role AND a live TOTP session bound to this bearer token."""
    uid = _require_admin(authorization)
    from welora import admin_2fa

    if not admin_2fa.is_enrolled(uid):
        raise HTTPException(
            status_code=403,
            detail={"error_code": "ADMIN_2FA_NOT_ENROLLED", "message": "Tài khoản quản trị chưa cấu hình 2FA"},
        )
    if not admin_2fa.session_valid(uid, _bearer_token(authorization)):
        raise HTTPException(
            status_code=401,
            detail={"error_code": "ADMIN_2FA_REQUIRED", "message": "Nhập mã 2FA để tiếp tục"},
        )
    return uid


def _checkout_call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except checkout_svc.CheckoutError as e:
        raise HTTPException(status_code=e.status, detail=e.body())


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # Reconcile job (every 5 min) runs in THIS process — no extra Render service.
    from welora import admin_bootstrap
    from welora import renewal as renewal_svc

    # WELORA_ADMIN_EMAILS: promote verified listed users / demote unlisted admins (audited, never raises)
    admin_bootstrap.startup_sync()
    if checkout_svc.checkout_enabled():
        checkout_svc.start_reconcile_loop()
        renewal_svc.start_loop()  # mục 7 reminders + grace/downgrade, same process
    try:
        yield
    finally:
        checkout_svc.stop_reconcile_loop()
        renewal_svc.stop_loop()


class EntitlementStudentStartBody(BaseModel):
    student_id: str = Field(..., min_length=4)
    verification_method: str = "edu_vn_email_otp"
    email: Optional[str] = None
    user_id: Optional[str] = None


class EntitlementPlanChangePreviewBody(BaseModel):
    from_plan: str = Field(..., min_length=1)
    to_plan: str = Field(..., min_length=1)
    interval: str = "month"
    days_remaining: int = 15
    days_in_period: int = 30
    user_id: Optional[str] = None


def create_app() -> FastAPI:
    app = FastAPI(title="Welora API", version="0.2.0", lifespan=_lifespan)
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
        return _serve_app_html(static_dir, "home.html")

    @app.get("/app/onboarding", include_in_schema=False)
    def onboarding_ui() -> FileResponse:
        return _serve_app_html(static_dir, "onboarding.html")

    @app.get("/app/demo", include_in_schema=False)
    def demo_ui() -> FileResponse:
        return _serve_app_html(static_dir, "demo.html")

    @app.get("/app/safety", include_in_schema=False)
    def safety_ui() -> FileResponse:
        return _serve_app_html(static_dir, "safety.html")

    @app.get("/app/chat", include_in_schema=False)
    def chat_ui() -> FileResponse:
        return _serve_app_html(static_dir, "chat.html")

    @app.get("/app/parser", include_in_schema=False)
    def parser_ui() -> FileResponse:
        return _serve_app_html(static_dir, "parser.html")

    @app.get("/app/budget", include_in_schema=False)
    @app.get("/app/budget/", include_in_schema=False)
    def budget_ui() -> FileResponse:
        return _serve_app_html(static_dir, "budget.html")

    @app.get("/app/metrics", include_in_schema=False)
    @app.get("/app/metrics/", include_in_schema=False)
    def metrics_ui() -> FileResponse:
        return _serve_app_html(static_dir, "metrics.html")

    @app.get("/app/logs", include_in_schema=False)
    @app.get("/app/logs/", include_in_schema=False)
    def logs_ui() -> FileResponse:
        return _serve_app_html(static_dir, "logs.html")

    @app.get("/app/constitution", include_in_schema=False)
    @app.get("/app/constitution/", include_in_schema=False)
    def constitution_ui() -> FileResponse:
        return _serve_app_html(static_dir, "constitution.html")

    @app.get("/app/core-constitution", include_in_schema=False)
    @app.get("/app/core-constitution/", include_in_schema=False)
    def core_constitution_ui() -> FileResponse:
        return _serve_app_html(static_dir, "core-constitution.html")

    @app.get("/app/academy", include_in_schema=False)
    @app.get("/app/academy/", include_in_schema=False)
    @app.get("/app/learn", include_in_schema=False)
    def academy_ui() -> FileResponse:
        return _serve_app_html(static_dir, "academy.html")

    @app.get("/app/dna", include_in_schema=False)
    @app.get("/app/dna/", include_in_schema=False)
    def dna_ui() -> FileResponse:
        return _serve_app_html(static_dir, "dna.html")

    @app.get("/app/goals", include_in_schema=False)
    @app.get("/app/goals/", include_in_schema=False)
    def goals_ui() -> FileResponse:
        return _serve_app_html(static_dir, "goals.html")

    @app.get("/app/otp", include_in_schema=False)
    @app.get("/app/otp/", include_in_schema=False)
    def otp_ui() -> FileResponse:
        return _serve_app_html(static_dir, "otp.html")

    @app.get("/app/login", include_in_schema=False)
    @app.get("/app/login/", include_in_schema=False)
    def login_ui() -> FileResponse:
        return _serve_app_html(static_dir, "login.html")

    @app.get("/app/register", include_in_schema=False)
    @app.get("/app/register/", include_in_schema=False)
    def register_ui() -> FileResponse:
        return _serve_app_html(static_dir, "register.html")

    @app.get("/app/forgot-password", include_in_schema=False)
    @app.get("/app/forgot-password/", include_in_schema=False)
    def forgot_password_ui() -> FileResponse:
        return _serve_app_html(static_dir, "forgot-password.html")

    @app.get("/app/reset-password", include_in_schema=False)
    @app.get("/app/reset-password/", include_in_schema=False)
    def reset_password_ui() -> FileResponse:
        return _serve_app_html(static_dir, "reset-password.html")

    @app.get("/app/pre-rule", include_in_schema=False)
    @app.get("/app/pre-rule/", include_in_schema=False)
    def prerule_ui() -> FileResponse:
        """Debug-only UI — off by default (WELORA_DEBUG_PRERULE=1 to enable)."""
        import os
        flag = (os.environ.get("WELORA_DEBUG_PRERULE") or "0").strip().lower()
        if flag not in ("1", "true", "yes", "on"):
            raise HTTPException(status_code=404, detail="Not Found")
        return _serve_app_html(static_dir, "prerule.html")

    @app.get("/app/health-score", include_in_schema=False)
    @app.get("/app/health-score/", include_in_schema=False)
    def health_score_ui() -> FileResponse:
        return _serve_app_html(static_dir, "healthscore.html")

    @app.get("/app/dual-control", include_in_schema=False)
    @app.get("/app/dual-control/", include_in_schema=False)
    def dual_control_ui() -> FileResponse:
        return _serve_app_html(static_dir, "dual-control.html")

    @app.get("/app/accounts", include_in_schema=False)
    @app.get("/app/accounts/", include_in_schema=False)
    def accounts_ui() -> FileResponse:
        return _serve_app_html(static_dir, "accounts.html")

    @app.get("/app/transactions", include_in_schema=False)
    @app.get("/app/transactions/", include_in_schema=False)
    def transactions_ui() -> FileResponse:
        return _serve_app_html(static_dir, "transactions.html")


    @app.get("/app/categories", include_in_schema=False)
    @app.get("/app/categories/", include_in_schema=False)
    def categories_ui() -> FileResponse:
        return _serve_app_html(static_dir, "categories.html")



    @app.get("/app/content/{content_id}", include_in_schema=False)
    def content_ui_id(content_id: str) -> FileResponse:
        return _serve_app_html(static_dir, "content.html")

    @app.get("/app/content/module/{module_id}", include_in_schema=False)
    def content_module_ui(module_id: str) -> FileResponse:
        return _serve_app_html(static_dir, "content.html")

    @app.get("/app/content", include_in_schema=False)
    def content_ui() -> FileResponse:
        return _serve_app_html(static_dir, "content.html")

    @app.get("/app/goal", include_in_schema=False)
    def goal_ui_redirect() -> RedirectResponse:
        return RedirectResponse(url="/app/safety")

    @app.get("/app/os", include_in_schema=False)
    @app.get("/app/os/", include_in_schema=False)
    def os_ui_redirect() -> RedirectResponse:
        """WeloraOS entry alias — shell lives at /app (+ goals / dual-control /os/*)."""
        return RedirectResponse(url="/app", status_code=302)


    @app.get("/pricing", include_in_schema=False)
    @app.get("/pricing/", include_in_schema=False)
    def pricing_ui() -> FileResponse:
        """P9 public pricing page — deep-link friendly (not under /app auth gate)."""
        return _serve_app_html(static_dir, "pricing.html")

    @app.get("/app/pricing", include_in_schema=False)
    @app.get("/app/pricing/", include_in_schema=False)
    def app_pricing_ui() -> FileResponse:
        return _serve_app_html(static_dir, "pricing.html")

    # --- Checkout VietQR P0 pages (CK-01/03/05/06) · returnUrl only redirects ---
    @app.get("/app/checkout", include_in_schema=False)
    @app.get("/app/checkout/", include_in_schema=False)
    @app.get("/app/checkout/return", include_in_schema=False)
    @app.get("/app/checkout/cancel", include_in_schema=False)
    def checkout_ui() -> HTMLResponse:
        """Static page only — never grants (CK-08). Status comes from server polling."""
        return _serve_app_html(static_dir, "checkout.html")

    @app.get("/app/admin/login", include_in_schema=False)
    def admin_login_ui() -> HTMLResponse:
        # Email OTP sign-in for WELORA_ADMIN_EMAILS (no password path into admin).
        return _serve_app_html(static_dir, "admin-login.html")

    @app.get("/app/admin/checkout", include_in_schema=False)
    def admin_checkout_ui() -> HTMLResponse:
        # Static shell only — every data call needs admin role + TOTP session (mục 9).
        return _serve_app_html(static_dir, "admin-checkout.html")

    @app.get("/app/checkout/renew", include_in_schema=False)
    def checkout_renew_ui() -> HTMLResponse:
        return _serve_app_html(static_dir, "checkout-renew.html")

    @app.get("/app/sw.js", include_in_schema=False)
    def app_service_worker() -> Response:
        # Served under /app/ so its default scope is /app/ (renewal push → /app/checkout/renew).
        js = (static_dir / "sw.js").read_text(encoding="utf-8")
        return Response(
            content=js,
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/app/"},
        )

    @app.get("/app/my-plan", include_in_schema=False)
    @app.get("/app/my-plan/", include_in_schema=False)
    def my_plan_ui() -> HTMLResponse:
        return _serve_app_html(static_dir, "my-plan.html")

    def _mail_provider_name() -> str:
        try:
            from welora.mailer import mail_provider
            return mail_provider()
        except Exception:
            return "log"

    @app.get("/health", tags=["system"])
    def health() -> dict:
        import os
        dialect = "unknown"
        try:
            from welora.db.connection import detect_dialect
            dialect = detect_dialect()
        except Exception:
            pass
        body = {
            "status": "ok",
            "service": "welora",
            "phase": "2",
            "env": os.environ.get("WELORA_ENV", "local"),
            "store": os.environ.get("WELORA_STORE", "memory"),
            "dialect": dialect,
            "llm": os.environ.get("WELORA_LLM_PROVIDER", "stub"),
            "mail_provider": _mail_provider_name(),
            "gate_months": 3,
            "hard_deny": True,
            "git_sha": _short_git_sha(),
        }
        try:
            body["entitlements"] = entitlements_svc.health_fields()
        except Exception:
            body["entitlements"] = {"checkout_enabled": False, "pricing_module": False}
        return body

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

    # Admin bootstrap (WELORA_ADMIN_EMAILS) — code emailed to listed addresses only, never echoed
    @app.post("/auth/email-otp/request", tags=["auth"])
    def auth_email_otp_request(body: EmailOtpRequestBody) -> dict:
        return _respond(*auth_svc.service_email_otp_request(body.model_dump()))

    @app.post("/auth/email-otp/verify", tags=["auth"])
    def auth_email_otp_verify(body: EmailOtpVerifyBody) -> dict:
        return _respond(*auth_svc.service_email_otp_verify(body.model_dump()))

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
        """Partner walkthrough seed — P1–P6 login aliases + OS fixtures (no gate/Hard Deny bypass)."""
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



    # --- Pricing & Entitlements (P1–P9 · P4–P7) ---
    @app.get("/api/core/v1/entitlements/pricing", tags=["entitlements"])
    def entitlements_pricing(authorization: Optional[str] = Header(None)) -> dict:
        # Optional bearer: A/B price for the viewer's sticky group when the
        # experiment is on (default OFF → config price, identical payload).
        from welora import checkout_pricing as _cp

        uid = _bearer_uid(authorization) if _cp.experiment().get("active") else None
        return _cp.pricing_public_for(uid)

    @app.get("/api/core/v1/entitlements/checkout/config", tags=["entitlements"])
    def entitlements_checkout_config() -> dict:
        return entitlements_svc.get_checkout_config()

    @app.get("/api/core/v1/entitlements/me", tags=["entitlements"])
    def entitlements_me(
        user_id: Optional[str] = Query(None),
        authorization: Optional[str] = Header(None),
    ) -> dict:
        uid = (user_id or "").strip() or None
        if not uid and authorization and authorization.lower().startswith("bearer "):
            token = authorization[7:].strip()
            try:
                me = auth_svc.service_me(token)
                if isinstance(me, tuple):
                    _code, payload = me
                    if isinstance(payload, dict):
                        uid = payload.get("user_id") or payload.get("id")
                elif isinstance(me, dict):
                    uid = me.get("user_id") or me.get("id")
            except Exception:
                uid = None
        return entitlements_svc.get_me(uid)

    @app.get("/api/core/v1/entitlements/has", tags=["entitlements"])
    def entitlements_has(
        key: str = Query(..., min_length=1),
        user_id: Optional[str] = Query(None),
    ) -> dict:
        ok = entitlements_svc.has_entitlement(user_id, key)
        return {"key": key, "allowed": ok, "user_id": user_id or "anonymous"}

    @app.post("/api/core/v1/entitlements/trial/aca/start", tags=["entitlements"])
    def entitlements_trial_aca_start(body: EntitlementTrialStartBody) -> dict:
        return _respond(*entitlements_svc.start_aca_trial(
            user_id=body.user_id,
            phone=body.phone,
            otp_code=body.otp_code,
        ))

    @app.post("/api/core/v1/entitlements/student/start", tags=["entitlements"])
    def entitlements_student_start(body: EntitlementStudentStartBody) -> dict:
        """P4 — student verify → 12 months free then ACA_SV; blocks OS sell."""
        return _respond(*entitlements_svc.start_student_path(
            user_id=body.user_id,
            student_id=body.student_id,
            verification_method=body.verification_method,
            email=body.email,
        ))

    @app.get("/api/core/v1/entitlements/seats/quote", tags=["entitlements"])
    def entitlements_seats_quote(
        extra_seats: int = Query(1, ge=0, le=50),
        plan_code: Optional[str] = Query(None),
    ) -> dict:
        """P5 — household seat add-on quote from config (no charge)."""
        return entitlements_svc.quote_seat_addon(
            extra_seats=extra_seats, plan_code=plan_code,
        )

    @app.get("/api/core/v1/entitlements/founding-family", tags=["entitlements"])
    def entitlements_founding_family(
        plan_code: Optional[str] = Query(None),
    ) -> dict:
        """P5 — Founding Family pre-order flag until OS 3.10."""
        return entitlements_svc.founding_family_status(plan_code)

    @app.post("/api/core/v1/entitlements/plan-change/preview", tags=["entitlements"])
    def entitlements_plan_change_preview(body: EntitlementPlanChangePreviewBody) -> dict:
        """P6 — upgrade/downgrade + prorate preview (checkout remains off)."""
        return _respond(*entitlements_svc.preview_plan_change(
            from_plan=body.from_plan,
            to_plan=body.to_plan,
            interval=body.interval,
            days_remaining=body.days_remaining,
            days_in_period=body.days_in_period,
            user_id=body.user_id,
        ))

    @app.get("/api/core/v1/entitlements/lifetime", tags=["entitlements"])
    def entitlements_lifetime() -> dict:
        """P7 — Founding Lifetime status (flag OFF — not for sale)."""
        return entitlements_svc.lifetime_purchase_blocked()

    # --- Checkout VietQR P0 API (CK-01…CK-10) ---
    @app.get("/api/checkout/v1/config", tags=["checkout"])
    def checkout_config() -> dict:
        return checkout_svc.checkout_config()

    @app.post("/api/checkout/v1/quote", tags=["checkout"])
    def checkout_quote(body: CheckoutQuoteBody, authorization: Optional[str] = Header(None)) -> dict:
        _checkout_call(checkout_svc._require_enabled)
        uid = _require_login(authorization)
        return _checkout_call(
            checkout_svc.quote, body.plan_id, body.billing_cycle, user_id=uid, coupon_code=body.coupon_code,
        )

    @app.post("/api/checkout/v1/orders", tags=["checkout"])
    def checkout_create_order(body: CheckoutOrderBody, authorization: Optional[str] = Header(None)) -> dict:
        _checkout_call(checkout_svc._require_enabled)
        uid = _require_login(authorization)
        if not body.agree_terms:
            raise HTTPException(
                status_code=400,
                detail={"error_code": "TERMS_REQUIRED", "message": "Cần đồng ý Điều khoản và Chính sách hoàn tiền"},
            )
        return _checkout_call(
            checkout_svc.create_order,
            user_id=uid, plan_id=body.plan_id, billing_cycle=body.billing_cycle, client_amount=body.amount,
            coupon_code=body.coupon_code,
        )

    @app.get("/api/checkout/v1/orders/{order_code}", tags=["checkout"])
    def checkout_get_order(order_code: int, authorization: Optional[str] = Header(None)) -> dict:
        _checkout_call(checkout_svc._require_enabled)
        uid = _require_login(authorization)
        return _checkout_call(checkout_svc.get_order_for_user, uid, order_code)

    @app.get("/api/checkout/v1/orders/{order_code}/qr.svg", tags=["checkout"])
    def checkout_order_qr(order_code: int, authorization: Optional[str] = Header(None)) -> Response:
        _checkout_call(checkout_svc._require_enabled)
        uid = _require_login(authorization)
        svg = _checkout_call(checkout_svc.qr_svg, uid, order_code)
        return Response(content=svg, media_type="image/svg+xml")

    @app.post("/api/checkout/v1/orders/{order_code}/cancel", tags=["checkout"])
    def checkout_cancel_order(order_code: int, authorization: Optional[str] = Header(None)) -> dict:
        _checkout_call(checkout_svc._require_enabled)
        uid = _require_login(authorization)
        return _checkout_call(checkout_svc.cancel_order_for_user, uid, order_code)

    @app.post("/api/checkout/v1/webhook/payos", tags=["checkout"])
    async def checkout_webhook(request: Request) -> JSONResponse:
        """payOS webhook — verify signature → payment_events → idempotent → PAID/UNDERPAID."""
        if not checkout_svc.checkout_enabled():
            return JSONResponse(status_code=403, content={"error_code": "CHECKOUT_DISABLED"})
        try:
            payload = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"ok": False, "error_code": "INVALID_JSON"})
        try:
            code, out = checkout_svc.handle_webhook(payload)
        except checkout_svc.CheckoutError as e:
            return JSONResponse(status_code=e.status, content=e.body())
        return JSONResponse(status_code=code, content=out)

    # --- Admin CK-10 (role ∈ ADMIN_ROLES + TOTP 2FA session; every manual action audit-logged) ---
    @app.get("/api/admin/v1/checkout/orders", tags=["admin"])
    def admin_checkout_search(q: str = Query("", max_length=120), authorization: Optional[str] = Header(None)) -> dict:
        _require_admin_2fa(authorization)
        return {"orders": _checkout_call(checkout_svc.admin_search, q)}

    @app.get("/api/admin/v1/checkout/orders/{order_code}", tags=["admin"])
    def admin_checkout_detail(order_code: int, authorization: Optional[str] = Header(None)) -> dict:
        _require_admin_2fa(authorization)
        return _checkout_call(checkout_svc.admin_order_detail, order_code)

    @app.post("/api/admin/v1/checkout/orders/{order_code}/grant", tags=["admin"])
    def admin_checkout_grant(order_code: int, body: AdminReasonBody, authorization: Optional[str] = Header(None)) -> dict:
        admin_uid = _require_admin_2fa(authorization)
        return _checkout_call(
            checkout_svc.admin_manual_grant, admin_uid=admin_uid, order_code=order_code, reason=body.reason,
        )

    @app.post("/api/admin/v1/checkout/orders/{order_code}/refund", tags=["admin"])
    def admin_checkout_refund(order_code: int, body: AdminRefundBody, authorization: Optional[str] = Header(None)) -> dict:
        admin_uid = _require_admin_2fa(authorization)
        return _checkout_call(
            checkout_svc.admin_refund, admin_uid=admin_uid, order_code=order_code,
            reason=body.reason, stage=body.stage, override=body.override, bank_ref=body.bank_ref, amount=body.amount,
        )

    @app.post("/api/admin/v1/checkout/reconcile", tags=["admin"])
    def admin_checkout_reconcile(authorization: Optional[str] = Header(None)) -> dict:
        _require_admin_2fa(authorization)
        return checkout_svc.reconcile_once()

    @app.post("/api/admin/v1/checkout/confirm-webhook", tags=["admin"])
    def admin_checkout_confirm_webhook(body: AdminConfirmWebhookBody, authorization: Optional[str] = Header(None)) -> dict:
        """Run once per environment/channel: registers webhook URL with payOS."""
        _require_admin_2fa(authorization)
        from welora.payments import ProviderError, get_provider

        try:
            return get_provider().confirm_webhook(body.webhook_url)
        except (ProviderError, NotImplementedError) as e:
            raise HTTPException(status_code=502, detail={"error_code": "CONFIRM_WEBHOOK_FAILED", "message": str(e)})

    # --- Checkout P1 user API (CK-12 / CK-13 / mục 7 / mục 8) ---
    @app.get("/api/checkout/v1/prices", tags=["checkout"])
    def checkout_prices(authorization: Optional[str] = Header(None)) -> dict:
        _checkout_call(checkout_svc._require_enabled)
        uid = _require_login(authorization)
        return _checkout_call(checkout_svc.prices_for_user, uid)

    # --- PAY-05 renewal push (Web Push / VAPID) — safe no-op until env keys are set ---
    @app.get("/api/push/v1/vapid-public-key", tags=["push"])
    def push_vapid_public_key() -> dict:
        from welora import webpush

        key = webpush.public_key()
        return {"enabled": bool(key), "public_key": key}

    @app.post("/api/push/v1/subscriptions", tags=["push"])
    def push_subscribe(
        body: PushSubscriptionBody,
        authorization: Optional[str] = Header(None),
        user_agent: Optional[str] = Header(None),
    ) -> dict:
        from welora import webpush

        uid = _require_login(authorization)
        if not webpush.enabled():
            raise HTTPException(status_code=503, detail={"error_code": "PUSH_DISABLED", "message": "Thông báo đẩy chưa bật"})
        try:
            return webpush.save_subscription(uid, body.model_dump(), user_agent=user_agent or "")
        except ValueError as e:
            raise HTTPException(status_code=400, detail={"error_code": str(e), "message": "Đăng ký thông báo không hợp lệ"})

    @app.delete("/api/push/v1/subscriptions", tags=["push"])
    def push_unsubscribe(body: PushUnsubscribeBody, authorization: Optional[str] = Header(None)) -> dict:
        from welora import webpush

        uid = _require_login(authorization)
        return {"ok": True, "removed": webpush.delete_subscription(uid, body.endpoint)}

    @app.get("/api/checkout/v1/my-plan", tags=["checkout"])
    def checkout_my_plan(authorization: Optional[str] = Header(None)) -> dict:
        _checkout_call(checkout_svc._require_enabled)
        uid = _require_login(authorization)
        return _checkout_call(checkout_svc.my_plan, uid)

    @app.get("/api/checkout/v1/orders/{order_code}/refund-eligibility", tags=["checkout"])
    def checkout_refund_eligibility(order_code: int, authorization: Optional[str] = Header(None)) -> dict:
        _checkout_call(checkout_svc._require_enabled)
        uid = _require_login(authorization)
        return _checkout_call(checkout_svc.refund_eligibility_for_user, uid, order_code)

    @app.post("/api/checkout/v1/orders/{order_code}/refund-request", tags=["checkout"])
    def checkout_refund_request(order_code: int, body: UserRefundBody, authorization: Optional[str] = Header(None)) -> dict:
        _checkout_call(checkout_svc._require_enabled)
        uid = _require_login(authorization)
        return _checkout_call(checkout_svc.request_refund_for_user, uid, order_code, body.reason)

    @app.post("/api/checkout/v1/renew/magic", tags=["checkout"])
    def checkout_renew_magic(body: RenewMagicBody) -> dict:
        _checkout_call(checkout_svc._require_enabled)
        return _checkout_call(checkout_svc.consume_renewal_link, body.token)

    # --- Admin 2FA (mục 9) ---
    @app.get("/api/admin/v1/2fa/status", tags=["admin"])
    def admin_2fa_status(authorization: Optional[str] = Header(None)) -> dict:
        from welora import admin_2fa

        uid = _require_admin(authorization)
        return {
            "enrolled": admin_2fa.is_enrolled(uid),
            "session": admin_2fa.session_valid(uid, _bearer_token(authorization)),
        }

    @app.post("/api/admin/v1/2fa/verify", tags=["admin"])
    def admin_2fa_verify(body: Admin2FABody, authorization: Optional[str] = Header(None)) -> dict:
        from welora import admin_2fa

        uid = _require_admin(authorization)
        try:
            return admin_2fa.open_session(uid, _bearer_token(authorization), body.code)
        except admin_2fa.TwoFactorError as e:
            raise HTTPException(status_code=e.status, detail=e.body())

    @app.post("/api/admin/v1/2fa/logout", tags=["admin"])
    def admin_2fa_logout(authorization: Optional[str] = Header(None)) -> dict:
        from welora import admin_2fa

        _require_admin(authorization)
        admin_2fa.close_session(_bearer_token(authorization))
        return {"ok": True}

    # --- Admin P1 (2FA): coupons · A/B stats · renewal job · non-prod test hooks ---
    @app.get("/api/admin/v1/checkout/coupons", tags=["admin"])
    def admin_coupons_list(authorization: Optional[str] = Header(None)) -> dict:
        _require_admin_2fa(authorization)
        return {"coupons": _checkout_call(checkout_svc.admin_list_coupons)}

    @app.post("/api/admin/v1/checkout/coupons", tags=["admin"])
    def admin_coupons_create(body: AdminCouponBody, authorization: Optional[str] = Header(None)) -> dict:
        admin_uid = _require_admin_2fa(authorization)
        return _checkout_call(checkout_svc.admin_create_coupon, admin_uid=admin_uid, body=body.model_dump())

    @app.post("/api/admin/v1/checkout/coupons/{code}/active", tags=["admin"])
    def admin_coupons_active(code: str, body: AdminCouponActiveBody, authorization: Optional[str] = Header(None)) -> dict:
        admin_uid = _require_admin_2fa(authorization)
        return _checkout_call(
            checkout_svc.admin_set_coupon_active, admin_uid=admin_uid, code=code, active=body.active, reason=body.reason,
        )

    @app.get("/api/admin/v1/checkout/unmatched-payments", tags=["admin"])
    def admin_unmatched_payments(authorization: Optional[str] = Header(None)) -> dict:
        _require_admin_2fa(authorization)
        return {"items": _checkout_call(checkout_svc.admin_unmatched_payments)}

    @app.get("/api/admin/v1/checkout/experiments/aca_price_ab", tags=["admin"])
    def admin_experiment_stats(authorization: Optional[str] = Header(None)) -> dict:
        _require_admin_2fa(authorization)
        return _checkout_call(checkout_svc.admin_experiment_stats)

    @app.post("/api/admin/v1/checkout/renewal/run", tags=["admin"])
    def admin_renewal_run(body: Optional[AdminRenewalRunBody] = None, authorization: Optional[str] = Header(None)) -> dict:
        import time as _time

        from welora import renewal as renewal_svc

        _require_admin_2fa(authorization)
        now = None
        if body and body.now_offset_days:
            _checkout_call(checkout_svc._require_test_hooks)
            now = _time.time() + float(body.now_offset_days) * 86400
        return renewal_svc.run_once(now=now)

    @app.post("/api/admin/v1/checkout/test/shift-subscription", tags=["admin"])
    def admin_test_shift(body: AdminShiftBody, authorization: Optional[str] = Header(None)) -> dict:
        admin_uid = _require_admin_2fa(authorization)
        return _checkout_call(
            checkout_svc.admin_test_shift_subscription, admin_uid=admin_uid, order_code=body.order_code,
            days=body.days, reason=body.reason,
        )

    @app.post("/api/core/v1/entitlements/events", tags=["entitlements"])
    def entitlements_events(body: EntitlementEventBody) -> dict:
        return entitlements_svc.emit_event(body.event, body.payload)

    @app.get("/api/core/v1/entitlements/experiments/aca_price_ab", tags=["entitlements"])
    def entitlements_experiment_aca() -> dict:
        return entitlements_svc.assign_experiment("aca_price_ab")



    return app


app = create_app()
