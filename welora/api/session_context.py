"""Follow-up #244/#245 item 14 — per-request login session for the demo-session Safety Gate.

Pure ASGI middleware: for an HTTP request with ``Authorization: Bearer <token>`` it sets
``welora.academy.REQUEST_SESSION`` to (token, client IP) for the duration of the request, so code
that computes the Safety Gate / mastery (goals_api.gate_flags, mastery.service_get_mastery) can show
a demo tester THEIR session's gate. Nothing is looked up here (no DB access per request); the token
is only resolved — and only while WELORA_GUEST_DEMO is on — when a gate is actually computed. The
token is never logged or stored."""

from __future__ import annotations

from typing import Any


class RequestSessionMiddleware:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        token = ""
        for k, v in scope.get("headers") or []:
            if k == b"authorization":
                raw = v.decode("latin-1")
                if raw[:7].lower() == "bearer ":
                    token = raw[7:].strip()
                break
        if not token:
            await self.app(scope, receive, send)
            return
        from starlette.requests import Request

        from welora import academy
        from welora import auth_ratelimit as rl

        req = Request(scope)
        ip = rl.client_ip(req.client.host if req.client else None, headers=req.headers)
        handle = academy.REQUEST_SESSION.set((token, ip))
        try:
            await self.app(scope, receive, send)
        finally:
            academy.REQUEST_SESSION.reset(handle)
