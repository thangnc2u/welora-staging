"""Admin bootstrap by email (checkout mục 9/10 prerequisite).

``WELORA_ADMIN_EMAILS`` — comma-separated, case-insensitive, trimmed. Empty/unset
→ nobody is admin (fail-closed).

Why email OTP (and not "any user whose users.email is listed"):
``users.email`` from password sign-up is NOT verified — anyone can register the
founder's address first. So admin is granted only on proof of mailbox ownership:

- ``POST /auth/email-otp/request {email}`` → a 6-digit code is emailed (mailer /
  SMTP) ONLY when the email is listed; the response is identical either way (no
  list disclosure). The code is never echoed, never logged, never fixed
  (``WELORA_OTP_FIXED`` does not apply), stored as a hash, 10 min, 5 attempts,
  max 5 requests / 15 min per email.
- ``POST /auth/email-otp/verify`` → marks ``users.email_verified_at``, issues a
  ``kind='email_otp'`` token and syncs the role:
    listed  → ``admin`` (audit ``admin_role_granted``); every other session of
              that user is revoked (e.g. a squatter's password/device token).
    not listed but admin-role → demoted to ``guest`` (audit ``admin_role_revoked``),
              admin 2FA sessions closed.
- Startup (app lifespan): users with a VERIFIED email in the list are promoted;
  admin-role users not in the list are demoted (both audited). Removing an email
  from the env therefore demotes at the next restart (Render restarts on env
  change) or next login, whichever comes first.
- Password, device and phone-OTP logins into an admin-role account are refused
  (auth.py) — the only way into admin is email OTP (+ TOTP for checkout admin APIs).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

log = logging.getLogger("welora.admin_bootstrap")

ENV = "WELORA_ADMIN_EMAILS"
ACTOR = "env:WELORA_ADMIN_EMAILS"
ADMIN_ROLE = "admin"
DEMOTED_ROLE = "guest"
OTP_TTL_S = 10 * 60
OTP_MAX_ATTEMPTS = 5
OTP_RATE_WINDOW_S = 15 * 60
OTP_RATE_MAX = 5
GENERIC_SENT = "Nếu email này được phép, mã đăng nhập đã được gửi (hiệu lực 10 phút)."


def admin_emails() -> frozenset[str]:
    raw = os.environ.get(ENV) or ""
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip() and "@" in e)


def is_listed(email: Optional[str]) -> bool:
    return bool(email) and str(email).strip().lower() in admin_emails()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _ts(iso: Optional[str]) -> float:
    if not iso:
        return 0.0
    dt = datetime.fromisoformat(str(iso))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _mask(email: Optional[str]) -> str:
    from welora.mailer import mask_email

    return mask_email(email or "")


def _conn(url: Optional[str] = None):
    from welora.auth import ensure_auth_schema
    from welora.db.connection import get_connection

    ensure_auth_schema(url)
    return get_connection(url)


def _roles():
    from welora.auth import ADMIN_ROLES

    return ADMIN_ROLES


def audit(conn: Any, *, user_id: Optional[str], action: str, detail: dict[str, Any], actor: str = ACTOR) -> None:
    conn.execute(
        "INSERT INTO auth_audit(id, user_id, action, actor, detail, created_at) VALUES (?,?,?,?,?,?)",
        (uuid.uuid4().hex, user_id, action, actor, json.dumps(detail, ensure_ascii=False), _iso(time.time())),
    )
    log.info("auth audit action=%s user=%s via=%s", action, (user_id or "")[:8], detail.get("via"))


def _admin_otp_proven(conn: Any, uid: str, email: str) -> bool:
    """The account proved this listed address through the ADMIN e-mail OTP (verify_email_otp sets
    email_otp_challenges.user_id before calling sync_role)."""
    return conn.execute(
        "SELECT 1 FROM email_otp_challenges WHERE user_id=? AND LOWER(email)=? AND consumed=1 LIMIT 1",
        (uid, (email or "").strip().lower()),
    ).fetchone() is not None


def sync_role(conn: Any, row: Any, *, via: str, keep_token: Optional[str] = None) -> str:
    """Apply WELORA_ADMIN_EMAILS to one user row; returns the resulting role. Caller commits."""
    uid = row["user_id"]
    email = (row["email"] or "").strip().lower() if row["email"] else ""
    role = (row["role"] or "guest").strip().lower()
    verified = bool(row["email_verified_at"])
    admins = _roles()
    if verified and is_listed(email) and role not in admins and not _admin_otp_proven(conn, uid, email):
        # PR #244 round 2 (R1): email_verified_at alone (e.g. set by another flow) never grants admin —
        # only a consumed admin e-mail OTP challenge of THIS account for THIS address does.
        return role
    if verified and is_listed(email):
        if role in admins:
            return role
        conn.execute("UPDATE users SET role=? WHERE user_id=?", (ADMIN_ROLE, uid))
        # any pre-existing session (password / device / phone OTP) must not inherit admin
        if keep_token:
            cur = conn.execute(
                "UPDATE auth_tokens SET revoked=1 WHERE user_id=? AND revoked=0 AND token<>?", (uid, keep_token)
            )
        else:
            cur = conn.execute("UPDATE auth_tokens SET revoked=1 WHERE user_id=? AND revoked=0", (uid,))
        audit(conn, user_id=uid, action="admin_role_granted", detail={
            "via": via, "email": _mask(email), "prev_role": role, "revoked_sessions": int(cur.rowcount or 0),
        })
        return ADMIN_ROLE
    if role in admins:
        conn.execute("UPDATE users SET role=? WHERE user_id=?", (DEMOTED_ROLE, uid))
        try:
            conn.execute("DELETE FROM admin_2fa_sessions WHERE user_id=?", (uid,))
        except Exception:  # table from checkout migration 009 — always present after migrate()
            pass
        audit(conn, user_id=uid, action="admin_role_revoked", detail={
            "via": via, "email": _mask(email), "prev_role": role,
            "reason": "email_not_listed" if email else "no_email",
        })
        return DEMOTED_ROLE
    return role


def startup_sync(url: Optional[str] = None) -> dict[str, int]:
    """Promote verified listed users, demote unlisted admin-role users. Never raises."""
    out = {"granted": 0, "revoked": 0}
    try:
        conn = _conn(url)
    except Exception as e:
        log.warning("admin startup sync skipped: %s", type(e).__name__)
        return out
    try:
        admins = sorted(_roles())
        marks = ",".join("?" for _ in admins)
        rows = conn.execute(
            f"SELECT user_id, email, role, email_verified_at FROM users "
            f"WHERE LOWER(COALESCE(role,'')) IN ({marks}) OR (email_verified_at IS NOT NULL AND email IS NOT NULL)",
            tuple(admins),
        ).fetchall()
        for r in rows:
            before = (r["role"] or "guest").strip().lower()
            after = sync_role(conn, r, via="startup")
            if after != before:
                out["granted" if after == ADMIN_ROLE else "revoked"] += 1
        conn.commit()
    except Exception as e:
        conn.rollback()
        log.warning("admin startup sync failed: %s", type(e).__name__)
    finally:
        conn.close()
    return out


# ---------------------------------------------------------------------------
# email OTP (admin bootstrap only — codes go to listed emails only)
# ---------------------------------------------------------------------------


def _code_hash(challenge_id: str, code: str) -> str:
    return hashlib.sha256(f"welora-email-otp:{challenge_id}:{code}".encode("utf-8")).hexdigest()


def request_email_otp(email: str, *, now: Optional[float] = None, url: Optional[str] = None) -> dict[str, Any]:
    from welora import mailer
    from welora.auth import _norm_email

    e = _norm_email(email)  # ValueError on malformed input
    if not e:
        raise ValueError("cần email")
    t = time.time() if now is None else float(now)
    challenge_id = str(uuid.uuid4())
    resp = {"challenge_id": challenge_id, "message": GENERIC_SENT, "expires_at": _iso(t + OTP_TTL_S)}
    if not is_listed(e):
        log.info("email otp request ignored (not listed) to=%s", _mask(e))
        return resp
    conn = _conn(url)
    try:
        recent = [
            r for r in conn.execute("SELECT created_at FROM email_otp_challenges WHERE email=?", (e,)).fetchall()
            if t - _ts(r["created_at"]) < OTP_RATE_WINDOW_S
        ]
        if len(recent) >= OTP_RATE_MAX:
            log.warning("email otp rate-limited to=%s", _mask(e))
            return resp
        code = f"{secrets.randbelow(1_000_000):06d}"
        conn.execute(
            "INSERT INTO email_otp_challenges(challenge_id, email, code_hash, expires_at, attempts, consumed, created_at) "
            "VALUES (?,?,?,?,0,0,?)",
            (challenge_id, e, _code_hash(challenge_id, code), _iso(t + OTP_TTL_S), _iso(t)),
        )
        conn.commit()
    finally:
        conn.close()
    mailer.enqueue(
        e,
        "Welora · Mã đăng nhập quản trị",
        f"Mã đăng nhập quản trị Welora của bạn: {code}\n\nHiệu lực 10 phút. Không chia sẻ mã này.\n"
        "Nếu bạn không yêu cầu, hãy bỏ qua email này.\n",
    )
    return resp


def verify_email_otp(challenge_id: str, code: str, *, now: Optional[float] = None, url: Optional[str] = None) -> dict[str, Any]:
    from welora.auth import _issue_token, _new_user_id

    t = time.time() if now is None else float(now)
    cid = (challenge_id or "").strip()
    c = "".join(ch for ch in str(code or "") if ch.isdigit())
    bad = ValueError("mã không đúng hoặc đã hết hạn")
    conn = _conn(url)
    try:
        ch = conn.execute("SELECT * FROM email_otp_challenges WHERE challenge_id=?", (cid,)).fetchone()
        if not ch or ch["consumed"] or int(ch["attempts"] or 0) >= OTP_MAX_ATTEMPTS or t > _ts(ch["expires_at"]):
            raise bad
        if len(c) != 6 or not hmac.compare_digest(_code_hash(cid, c), ch["code_hash"]):
            conn.execute("UPDATE email_otp_challenges SET attempts=attempts+1 WHERE challenge_id=?", (cid,))
            conn.commit()
            raise bad
        cur = conn.execute("UPDATE email_otp_challenges SET consumed=1 WHERE challenge_id=? AND consumed=0", (cid,))
        if (cur.rowcount or 0) != 1:
            conn.rollback()
            raise bad
        email = ch["email"]
        row = conn.execute("SELECT user_id FROM users WHERE email=?", (email,)).fetchone()
        created = False
        if row:
            uid = row["user_id"]
        else:
            uid = _new_user_id()
            from welora.auth import internal_device_key

            device_key = internal_device_key("email:")  # random internal marker (P0: not derived from email)
            conn.execute(
                "INSERT INTO users(user_id, display_name, device_id, email, role) VALUES (?,?,?,?,?)",
                (uid, email, device_key, email, "guest"),
            )
            created = True
        conn.execute(
            "UPDATE users SET email_verified_at=COALESCE(email_verified_at, ?) WHERE user_id=?", (_iso(t), uid)
        )
        conn.execute("UPDATE email_otp_challenges SET user_id=? WHERE challenge_id=?", (uid, cid))
        token = _issue_token(conn, uid, "email_otp")
        user = conn.execute(
            "SELECT user_id, email, role, email_verified_at FROM users WHERE user_id=?", (uid,)
        ).fetchone()
        role = sync_role(conn, user, via="email_otp", keep_token=token)
        from welora.auth import token_expiry

        expires_at = token_expiry(conn, token)
        conn.commit()
        return {"user_id": uid, "token": token, "expires_at": expires_at, "kind": "email_otp",
                "created": created, "role": role, "admin": role in _roles()}
    finally:
        conn.close()


def verified_email_of(user_id: str, url: Optional[str] = None) -> Optional[str]:
    """Lower-cased email of the user iff proven by email OTP (used by admin 2FA email:BASE32)."""
    try:
        conn = _conn(url)
    except Exception:
        return None
    try:
        r = conn.execute("SELECT email, email_verified_at FROM users WHERE user_id=?", ((user_id or "").strip(),)).fetchone()
        if r and r["email"] and r["email_verified_at"]:
            return str(r["email"]).strip().lower()
        return None
    except Exception:
        return None
    finally:
        conn.close()
