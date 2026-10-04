"""Production URL / origin config and the production boot guard (ticket «GP · Cutover Production»,
LỆNH Forge 04/10; runbook docs/runbook/cutover-app4.md).

Everything that names the public site comes from env, never from code:

- ``WELORA_PUBLIC_BASE_URL``: the public origin, e.g. ``https://<public host>`` (no path, no trailing
  slash). Absolute links (payOS return / cancel / webhook, renewal magic link) are built from it.
  Dev / tests: unset → relative links (documented fallback; production refuses to start without it).
- ``WELORA_CORS_ORIGINS``: comma-separated origin list. Production: only these + the base URL origin,
  ``*`` is dropped (CRITICAL log). Non-production: unset → ``*`` (unchanged staging behaviour).
- ``WELORA_ALLOWED_HOSTS``: optional comma-separated Host list. Set → other Host headers get 400
  (``/health`` and ``/healthz`` stay open for the platform health check). Unset → no Host check.

``production_boot_errors()`` lists why a ``WELORA_ENV=production`` process must not start; the app
lifespan raises ``ProdConfigError`` with all of them (uvicorn exits, Render keeps the old deploy).
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import urlsplit

log = logging.getLogger("welora.prod_config")

BASE_URL_ENV = "WELORA_PUBLIC_BASE_URL"
CORS_ENV = "WELORA_CORS_ORIGINS"
HOSTS_ENV = "WELORA_ALLOWED_HOSTS"
HOST_CHECK_EXEMPT = ("/health", "/healthz")
# Test-only switches. Production refuses to start when any of them is set (any non-empty value).
TEST_FLAGS = ("WELORA_OTP_FIXED", "WELORA_RESET_ECHO", "WELORA_CHECKOUT_TEST_HOOKS")


class ProdConfigError(RuntimeError):
    """WELORA_ENV=production started without its safety settings (message lists every problem)."""


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def is_production() -> bool:
    from welora.auth import is_production as _p

    return _p()


def _origin(value: str) -> Optional[str]:
    """``scheme://host[:port]`` lower-cased, or None when ``value`` is not a bare http(s) origin."""
    v = (value or "").strip().rstrip("/")
    try:
        u = urlsplit(v)
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not u.hostname or u.path or u.query or u.fragment:
        return None
    if u.username or u.password:
        return None
    host = u.hostname.lower()
    try:
        port = u.port
    except ValueError:
        return None
    return f"{u.scheme}://{host}" + (f":{port}" if port else "")


def public_base_url() -> str:
    """The public origin from WELORA_PUBLIC_BASE_URL (no trailing slash), "" when unset."""
    return _env(BASE_URL_ENV).rstrip("/")


def absolute_url(path: str) -> str:
    """``WELORA_PUBLIC_BASE_URL`` + ``path``. Unset base (dev / tests only) → the relative path."""
    p = path if path.startswith("/") else "/" + path
    return public_base_url() + p


def payos_webhook_url() -> str:
    return absolute_url("/api/checkout/v1/webhook/payos")


def _split(raw: str) -> list[str]:
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def cors_origins() -> list[str]:
    """Origins for CORSMiddleware. Production: env list + base origin, never ``*``."""
    raw = _split(_env(CORS_ENV))
    if not is_production():
        return raw or ["*"]
    out: list[str] = []
    for item in raw + [public_base_url()]:
        if not item:
            continue
        if item == "*":
            log.critical("production: %s contains '*' — wildcard ignored", CORS_ENV)
            continue
        o = _origin(item)
        if o is None:
            log.critical("production: %s entry ignored (not an origin): %r", CORS_ENV, item[:80])
            continue
        if o not in out:
            out.append(o)
    return out


def allowed_hosts() -> list[str]:
    """Host allowlist (lower-case, port stripped); [] = no Host check."""
    out = []
    for h in _split(_env(HOSTS_ENV)):
        h = h.lower().split(":", 1)[0]
        if h and h != "*" and h not in out:
            out.append(h)
    return out


def _rl_disabled() -> list[str]:
    """WELORA_RL_* limits set to ≤ 0 (that switches the limit off — tests only)."""
    bad = []
    for k in sorted(os.environ):
        if not k.startswith("WELORA_RL_"):
            continue
        try:
            if int(_env(k)) <= 0:
                bad.append(k)
        except ValueError:
            continue
    return bad


def production_boot_errors() -> list[str]:
    """Why this WELORA_ENV=production process must not start ([] = OK, and always [] off production)."""
    if not is_production():
        return []
    from welora import admin_2fa, otp_hash

    errs: list[str] = []
    if _env("WELORA_OTP_ECHO"):
        errs.append("WELORA_OTP_ECHO is set — remove it (production never echoes OTP codes)")
    if _env("WELORA_GUEST_DEMO") != "0":
        errs.append("WELORA_GUEST_DEMO must be 0 in production")
    if otp_hash.key_source() != "env":
        errs.append("WELORA_OTP_HMAC_KEY is not set")
    if not admin_2fa._secrets_from_env():
        errs.append("WELORA_ADMIN_TOTP_SECRETS is not set (no key:secret entry)")
    flags = [n for n in TEST_FLAGS if _env(n)] + _rl_disabled()
    if flags:
        errs.append("test-only flags are set: " + ", ".join(flags) + " — remove them")
    from welora import entitlements

    if entitlements.checkout_runtime_enabled():  # same truthy rule as the runtime switch (read only)
        errs.append("WELORA_CHECKOUT_ENABLED is on — checkout stays OFF in production")
    base = public_base_url()
    o = _origin(base)
    if not base:
        errs.append(f"{BASE_URL_ENV} is not set (the public https origin, see docs/runbook/cutover-app4.md)")
    elif o is None or not o.startswith("https://") or o != base.lower():
        errs.append(f"{BASE_URL_ENV} must be a bare https origin without path (https://<public host>)")
    return errs


def require_production_config() -> None:
    errs = production_boot_errors()
    if errs:
        raise ProdConfigError("production refuses to start: " + "; ".join(errs))


class AllowedHostsMiddleware:
    """400 for a Host outside WELORA_ALLOWED_HOSTS (read per request; unset → pass-through)."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        hosts = allowed_hosts()
        if not hosts or scope.get("path") in HOST_CHECK_EXEMPT:
            return await self.app(scope, receive, send)
        host = ""
        for k, v in scope.get("headers") or []:
            if k == b"host":
                host = v.decode("latin-1").strip().lower()
                break
        if host.startswith("["):
            host = host.split("]", 1)[0] + "]"
        else:
            host = host.split(":", 1)[0]
        if host in hosts:
            return await self.app(scope, receive, send)
        if scope["type"] != "http":
            return  # websocket: close without accepting
        from starlette.responses import PlainTextResponse

        await PlainTextResponse("Invalid host header", status_code=400)(scope, receive, send)
