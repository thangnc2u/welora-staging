"""Test helper — P0 authz (owner = bearer token user).

Legacy HTTP suites addressed users by arbitrary ids without a token. ``authed(client)``
keeps those tests' requests and assertions unchanged and only attaches the bearer token
of the user each request claims (``user_id`` in JSON body / query / ``/users/{id}/`` path,
``companion_user_id`` for companion-confirm), falling back to the last claimed user for
resource-id routes (/os/accounts/{id}, /goals/{id}, onboarding session steps …).
``/metrics`` (admin + 2FA now) gets a throwaway admin token with a live 2FA session.
Requests that already carry Authorization, and /auth/* · /api/admin/* · /api/checkout/*,
are left untouched. Test-only: tokens are minted straight into auth_tokens.
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from urllib.parse import parse_qs, unquote, urlsplit

from welora import auth as auth_svc
from welora.db.connection import get_connection

_USERS_PATH = re.compile(r"^/users/([^/?]+)/")
_SKIP_PREFIXES = ("/auth/", "/api/admin/", "/api/checkout/", "/static/")
METRICS_ADMIN_PREFIX = "test-metrics-admin-"
SEED_ADMIN_PREFIX = "test-seed-admin-"


def token_for(user_id: str, kind: str = "device", role: str | None = None) -> str:
    auth_svc.ensure_auth_schema(None)
    conn = get_connection(None)
    try:
        conn.execute("INSERT INTO users(user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING", (user_id,))
        if role:
            conn.execute("UPDATE users SET role=? WHERE user_id=?", (role, user_id))
        tok = auth_svc._issue_token(conn, user_id, kind)
        conn.commit()
    finally:
        conn.close()
    return tok


def bearer(user_id: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + token_for(user_id)}


def claimed_user(url, kwargs) -> str | None:
    sp = urlsplit(str(url))
    path = sp.path
    js = kwargs.get("json")
    if isinstance(js, dict):
        if path.endswith("/mode-c/companion-confirm") and js.get("companion_user_id"):
            return str(js["companion_user_id"])
        if js.get("user_id"):
            return str(js["user_id"])
    params = kwargs.get("params")
    if isinstance(params, dict) and params.get("user_id"):
        return str(params["user_id"])
    q = parse_qs(sp.query).get("user_id")
    if q and q[0]:
        return q[0]
    m = _USERS_PATH.match(path)
    if m:
        return unquote(m.group(1))
    return None


def _metrics_request(orig, method, url, args, kw):
    import uuid

    from welora import admin_2fa

    admin_uid = METRICS_ADMIN_PREFIX + uuid.uuid4().hex[:12]  # fresh TOTP state (replay guard)
    secret = admin_2fa.generate_secret()
    key = "WELORA_ADMIN_TOTP_SECRETS"
    prev = os.environ.get(key)
    os.environ[key] = f"{admin_uid}:{secret}"
    try:
        tok = token_for(admin_uid, kind="email_otp", role="admin")
        admin_2fa.open_session(admin_uid, tok, admin_2fa.totp(secret))
        kw["headers"] = {**dict(kw.get("headers") or {}), "Authorization": "Bearer " + tok}
        return orig(method, url, *args, **kw)
    finally:
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev


def authed(client):
    """Patch a TestClient so user-scoped calls carry the claimed user's bearer token."""
    orig = client.request
    state: dict[str, str | None] = {"uid": None}

    def request(method, url, *args, **kw):
        headers = dict(kw.get("headers") or {})
        if any(k.lower() == "authorization" for k in headers):
            return orig(method, url, *args, **kw)
        path = urlsplit(str(url)).path
        if path == "/metrics":
            return _metrics_request(orig, method, url, args, kw)
        if path.startswith(_SKIP_PREFIXES):
            return orig(method, url, *args, **kw)
        uid = claimed_user(url, kw) or state["uid"]
        if uid:
            state["uid"] = uid
            headers["Authorization"] = "Bearer " + token_for(uid)
            kw["headers"] = headers
        return orig(method, url, *args, **kw)

    client.request = request
    return client


@contextmanager
def admin_2fa_headers(prefix: str = SEED_ADMIN_PREFIX):
    """Bearer headers of a throwaway admin with a live 2FA session (TOTP secret set in the env
    for the duration, because _require_admin_2fa re-checks enrolment on every request)."""
    import uuid

    from welora import admin_2fa

    admin_uid = prefix + uuid.uuid4().hex[:12]
    secret = admin_2fa.generate_secret()
    key = "WELORA_ADMIN_TOTP_SECRETS"
    prev = os.environ.get(key)
    os.environ[key] = f"{admin_uid}:{secret}" + (f",{prev}" if prev else "")
    try:
        tok = token_for(admin_uid, kind="email_otp", role="admin")
        admin_2fa.open_session(admin_uid, tok, admin_2fa.totp(secret))
        yield {"Authorization": "Bearer " + tok}
    finally:
        if prev is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = prev


def admin_demo_seed(client):
    """POST /auth/demo/seed as admin+2FA (CoS review of PR #237: the endpoint is admin-only)."""
    with admin_2fa_headers() as h:
        return client.post("/auth/demo/seed", headers=h)
