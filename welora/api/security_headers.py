"""HTTP security headers (Helmet equivalent for FastAPI/Starlette)."""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# Inline script/style: static HTML pages use <script> and <style> in-file.
# No third-party CDN on current /app pages.
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'"
)

HSTS = "max-age=31536000; includeSubDomains"

# TestClient is HTTP; header is still set so unittest can assert.
# Browsers only honor HSTS on HTTPS (staging Render).
HSTS_NOTE = "HSTS is emitted on every response; browsers apply it only over HTTPS."


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        h = response.headers
        h.setdefault("X-Frame-Options", "DENY")
        h.setdefault("X-Content-Type-Options", "nosniff")
        h.setdefault("Referrer-Policy", "no-referrer")
        h.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        h.setdefault("Content-Security-Policy", CSP)
        h.setdefault("Strict-Transport-Security", HSTS)
        return response
