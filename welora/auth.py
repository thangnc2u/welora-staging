"""
Welora P1-E1-04 — Auth pilot

Flows:
  1) Device ID (primary mobile pilot)
  2) OTP mock (phone)
Tokens stored in SQLite auth_tokens. No JWT dependency in pilot.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from welora.db.connection import get_connection
from welora.db.migrate import migrate

OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
FIXED_OTP = "123456"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _token() -> str:
    return secrets.token_urlsafe(32)


def _new_user_id() -> str:
    return str(uuid4())


def ensure_auth_schema(url: str | None = None) -> None:
    migrate(url)


def login_or_register_device(
    device_id: str,
    *,
    display_name: Optional[str] = None,
    url: str | None = None,
) -> dict[str, Any]:
    device_id = (device_id or "").strip()
    if not device_id:
        raise ValueError("device_id is required")
    if len(device_id) < 4:
        raise ValueError("device_id too short")

    ensure_auth_schema(url)
    conn = get_connection(url)
    try:
        row = conn.execute(
            "SELECT user_id, display_name FROM users WHERE device_id=?",
            (device_id,),
        ).fetchone()
        created = False
        if row:
            user_id = row["user_id"]
            name = row["display_name"]
        else:
            user_id = _new_user_id()
            name = display_name
            conn.execute(
                "INSERT INTO users(user_id, display_name, device_id) VALUES (?,?,?)",
                (user_id, name, device_id),
            )
            created = True

        token = _token()
        conn.execute(
            "INSERT INTO auth_tokens(token, user_id, device_id, kind) VALUES (?,?,?,?)",
            (token, user_id, device_id, "device"),
        )
        conn.commit()
        return {
            "user_id": user_id,
            "token": token,
            "kind": "device",
            "created": created,
            "display_name": name,
        }
    finally:
        conn.close()


def request_otp(
    phone: str,
    *,
    url: str | None = None,
    fixed_code: Optional[str] = None,
) -> dict[str, Any]:
    phone = (phone or "").strip()
    if not phone or len(phone) < 8:
        raise ValueError("phone is required (min 8 chars)")

    ensure_auth_schema(url)
    import os

    if fixed_code:
        code = fixed_code
    elif os.environ.get("WELORA_OTP_FIXED") == "1":
        code = FIXED_OTP
    else:
        code = f"{secrets.randbelow(1_000_000):06d}"

    challenge_id = str(uuid4())
    expires = _now() + timedelta(minutes=OTP_TTL_MINUTES)
    conn = get_connection(url)
    try:
        conn.execute(
            "INSERT INTO otp_challenges(challenge_id, phone, code, expires_at) VALUES (?,?,?,?)",
            (challenge_id, phone, code, _iso(expires)),
        )
        conn.commit()
        return {
            "challenge_id": challenge_id,
            "phone_masked": _mask_phone(phone),
            "expires_at": _iso(expires),
            "pilot_code": code,
            "pilot_note": "Code echoed for pilot/tests only. Never in production.",
        }
    finally:
        conn.close()


def verify_otp(
    challenge_id: str,
    code: str,
    *,
    url: str | None = None,
) -> dict[str, Any]:
    ensure_auth_schema(url)
    conn = get_connection(url)
    try:
        row = conn.execute(
            "SELECT * FROM otp_challenges WHERE challenge_id=?",
            (challenge_id,),
        ).fetchone()
        if not row:
            raise KeyError("challenge not found")
        if row["consumed"]:
            raise ValueError("challenge already used")
        if row["attempts"] >= OTP_MAX_ATTEMPTS:
            raise ValueError("too many attempts")

        expires = datetime.fromisoformat(row["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if _now() > expires:
            raise ValueError("OTP expired")

        if (code or "").strip() != row["code"]:
            conn.execute(
                "UPDATE otp_challenges SET attempts=attempts+1 WHERE challenge_id=?",
                (challenge_id,),
            )
            conn.commit()
            raise ValueError("invalid code")

        phone = row["phone"]
        user_id = row["user_id"]
        if not user_id:
            user_id = str(uuid4())
            device_key = "phone:" + hashlib.sha256(phone.encode()).hexdigest()[:16]
            existing = conn.execute(
                "SELECT user_id FROM users WHERE device_id=?", (device_key,)
            ).fetchone()
            if existing:
                user_id = existing["user_id"]
            else:
                conn.execute(
                    "INSERT INTO users(user_id, display_name, device_id) VALUES (?,?,?)",
                    (user_id, phone, device_key),
                )

        token = _token()
        conn.execute(
            "UPDATE otp_challenges SET consumed=1, user_id=? WHERE challenge_id=?",
            (user_id, challenge_id),
        )
        conn.execute(
            "INSERT INTO auth_tokens(token, user_id, device_id, kind) VALUES (?,?,?,?)",
            (token, user_id, None, "otp"),
        )
        conn.commit()
        return {"user_id": user_id, "token": token, "kind": "otp", "created": False}
    finally:
        conn.close()


def resolve_token(token: str, *, url: str | None = None) -> Optional[str]:
    if not token:
        return None
    ensure_auth_schema(url)
    conn = get_connection(url)
    try:
        row = conn.execute(
            "SELECT user_id, expires_at, revoked FROM auth_tokens WHERE token=?",
            (token,),
        ).fetchone()
        if not row or row["revoked"]:
            return None
        if row["expires_at"]:
            exp = datetime.fromisoformat(row["expires_at"])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if _now() > exp:
                return None
        return row["user_id"]
    finally:
        conn.close()


def revoke_token(token: str, *, url: str | None = None) -> bool:
    ensure_auth_schema(url)
    conn = get_connection(url)
    try:
        cur = conn.execute("UPDATE auth_tokens SET revoked=1 WHERE token=?", (token,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


def _mask_phone(phone: str) -> str:
    if len(phone) < 4:
        return "****"
    return phone[:2] + "****" + phone[-2:]


def service_device_login(body: dict) -> tuple[int, dict]:
    try:
        out = login_or_register_device(
            body.get("device_id") or "",
            display_name=body.get("display_name"),
        )
        return 200 if not out["created"] else 201, out
    except ValueError as e:
        return 400, {"error": str(e)}


def service_otp_request(body: dict) -> tuple[int, dict]:
    try:
        out = request_otp(body.get("phone") or "")
        return 200, out
    except ValueError as e:
        return 400, {"error": str(e)}


def service_otp_verify(body: dict) -> tuple[int, dict]:
    try:
        out = verify_otp(body.get("challenge_id") or "", body.get("code") or "")
        return 200, out
    except KeyError:
        return 404, {"error": "challenge not found"}
    except ValueError as e:
        return 400, {"error": str(e)}


def service_me(token: str) -> tuple[int, dict]:
    uid = resolve_token(token)
    if not uid:
        return 401, {"error": "invalid or expired token"}
    return 200, {"user_id": uid}
