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


# ---------------------------------------------------------------------------
# P2 Auth — Guest / demo password (partner walkthrough on staging)
# Feature flag: WELORA_GUEST_DEMO=1 (default on for staging)
# Allowed roles: guest | demo only — fail-closed away from admin
# Forgot-password: TOKEN STUB (no prod email / magic-link delivery)
# ---------------------------------------------------------------------------

import os
import re

GUEST_ROLES = frozenset({"guest", "demo"})
ADMIN_ROLES = frozenset({"admin", "ops", "staff", "superuser"})
PBKDF2_ITERS = 120_000
RESET_TTL_MINUTES = 30
MIN_PASSWORD_LEN = 8

# Partner demo seed (only when WELORA_GUEST_DEMO=1)
DEMO_EMAIL = "partner@welora.demo"
DEMO_PHONE = "+84900000000"
DEMO_PASSWORD = "WeloraDemo1!"
DEMO_DISPLAY = "Partner Demo"
PARTNER_USER_ID = "bc25f9aa-9af4-45ea-b981-adbc41133439"  # Founder tip stable id


def guest_demo_enabled() -> bool:
    """Feature flag — demo seed / stub reset token echo for partner walkthrough."""
    return os.environ.get("WELORA_GUEST_DEMO", "1").strip() != "0"


def _hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERS
    )
    return f"pbkdf2_sha256${PBKDF2_ITERS}${salt.hex()}${dk.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters_s, salt_hex, hash_hex = (stored or "").split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iters = int(iters_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
        return secrets.compare_digest(dk, expected)
    except Exception:
        return False


def _norm_email(email: str | None) -> str | None:
    if email is None:
        return None
    e = email.strip().lower()
    if not e:
        return None
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", e):
        raise ValueError("email không hợp lệ")
    return e


def _norm_phone(phone: str | None) -> str | None:
    if phone is None:
        return None
    p = re.sub(r"[\s\-()]", "", phone.strip())
    if not p:
        return None
    if len(p) < 8 or not re.match(r"^\+?[0-9]{8,15}$", p):
        raise ValueError("số điện thoại không hợp lệ")
    return p


def _require_password(password: str) -> str:
    pw = password or ""
    if len(pw) < MIN_PASSWORD_LEN:
        raise ValueError(f"mật khẩu tối thiểu {MIN_PASSWORD_LEN} ký tự")
    return pw


def _issue_token(conn, user_id: str, kind: str = "password") -> str:
    token = _token()
    conn.execute(
        "INSERT INTO auth_tokens(token, user_id, device_id, kind) VALUES (?,?,?,?)",
        (token, user_id, None, kind),
    )
    return token


def _user_row_public(row) -> dict[str, Any]:
    role = (row["role"] if "role" in row.keys() else None) or "guest"
    return {
        "user_id": row["user_id"],
        "display_name": row["display_name"],
        "email": row["email"] if "email" in row.keys() else None,
        "phone": row["phone"] if "phone" in row.keys() else None,
        "role": role,
    }


def _assert_guest_role(role: str | None) -> str:
    r = (role or "guest").strip().lower() or "guest"
    if r in ADMIN_ROLES or r not in GUEST_ROLES:
        raise PermissionError("role không được phép (chỉ guest/demo)")
    return r


def register_guest(
    *,
    email: str | None = None,
    phone: str | None = None,
    password: str,
    display_name: str | None = None,
    role: str = "guest",
    url: str | None = None,
) -> dict[str, Any]:
    """Register guest/demo user with email OR phone + password."""
    ensure_auth_schema(url)
    email_n = _norm_email(email)
    phone_n = _norm_phone(phone)
    if not email_n and not phone_n:
        raise ValueError("cần email hoặc số điện thoại")
    pw = _require_password(password)
    # Client cannot self-elevate — always guest unless internal demo seed
    safe_role = _assert_guest_role(role if role == "demo" else "guest")
    if role == "demo":
        safe_role = "demo"
    else:
        safe_role = "guest"

    pw_hash = _hash_password(pw)
    user_id = _new_user_id()
    name = (display_name or "").strip() or email_n or phone_n
    # device_id placeholder keeps unique-ish identity for legacy device flows
    device_key = "guest:" + hashlib.sha256(
        (email_n or phone_n or user_id).encode()
    ).hexdigest()[:16]

    conn = get_connection(url)
    try:
        if email_n:
            hit = conn.execute(
                "SELECT user_id FROM users WHERE email=?", (email_n,)
            ).fetchone()
            if hit:
                raise ValueError("email đã được đăng ký")
        if phone_n:
            hit = conn.execute(
                "SELECT user_id FROM users WHERE phone=?", (phone_n,)
            ).fetchone()
            if hit:
                raise ValueError("số điện thoại đã được đăng ký")

        conn.execute(
            "INSERT INTO users(user_id, display_name, device_id, email, phone, password_hash, role) "
            "VALUES (?,?,?,?,?,?,?)",
            (user_id, name, device_key, email_n, phone_n, pw_hash, safe_role),
        )
        token = _issue_token(conn, user_id, "password")
        conn.commit()
        return {
            "user_id": user_id,
            "token": token,
            "kind": "password",
            "created": True,
            "display_name": name,
            "email": email_n,
            "phone": phone_n,
            "role": safe_role,
        }
    finally:
        conn.close()


def login_guest(
    *,
    email: str | None = None,
    phone: str | None = None,
    password: str,
    url: str | None = None,
) -> dict[str, Any]:
    """Login guest/demo — fail-closed if role not guest/demo or bad password."""
    ensure_auth_schema(url)
    if guest_demo_enabled():
        seed_partner_demo(url=url)
    email_n = _norm_email(email)
    phone_n = _norm_phone(phone)
    if not email_n and not phone_n:
        raise ValueError("cần email hoặc số điện thoại")
    pw = password or ""
    if not pw:
        raise ValueError("cần mật khẩu")

    conn = get_connection(url)
    try:
        row = None
        if email_n:
            row = conn.execute(
                "SELECT * FROM users WHERE email=?", (email_n,)
            ).fetchone()
        if row is None and phone_n:
            row = conn.execute(
                "SELECT * FROM users WHERE phone=?", (phone_n,)
            ).fetchone()
        if not row or not row["password_hash"]:
            raise ValueError("email/số điện thoại hoặc mật khẩu không đúng")
        role = (row["role"] or "guest").strip().lower()
        if role in ADMIN_ROLES or role not in GUEST_ROLES:
            # Fail-closed: never allow password path into elevated roles
            raise PermissionError("đăng nhập bị từ chối (role)")
        if not _verify_password(pw, row["password_hash"]):
            raise ValueError("email/số điện thoại hoặc mật khẩu không đúng")
        token = _issue_token(conn, row["user_id"], "password")
        conn.commit()
        pub = _user_row_public(row)
        return {
            **pub,
            "token": token,
            "kind": "password",
            "created": False,
        }
    finally:
        conn.close()


def logout_guest(token: str, *, url: str | None = None) -> dict[str, Any]:
    ok = revoke_token(token, url=url)
    return {"revoked": bool(ok)}


def request_password_reset(
    *,
    email: str | None = None,
    phone: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """
    Forgot-password MVP — TOKEN STUB (no email/SMS delivery).

    Staging always returns reset_token in the body when the account exists
    so partners can walk through reset without prod mail. When the account
    does not exist, return a generic ok (no user enumeration).
    """
    ensure_auth_schema(url)
    email_n = _norm_email(email) if email else None
    phone_n = _norm_phone(phone) if phone else None
    if not email_n and not phone_n:
        raise ValueError("cần email hoặc số điện thoại")

    conn = get_connection(url)
    try:
        row = None
        if email_n:
            row = conn.execute(
                "SELECT user_id, role FROM users WHERE email=?", (email_n,)
            ).fetchone()
        if row is None and phone_n:
            row = conn.execute(
                "SELECT user_id, role FROM users WHERE phone=?", (phone_n,)
            ).fetchone()
        base = {
            "ok": True,
            "approach": "token_stub",
            "note": "Staging stub — không gửi email/SMS. Dùng reset_token bên dưới (nếu có).",
        }
        if not row:
            return base
        role = (row["role"] or "guest").strip().lower()
        if role not in GUEST_ROLES:
            return base
        token = _token()
        expires = _now() + timedelta(minutes=RESET_TTL_MINUTES)
        conn.execute(
            "INSERT INTO password_reset_tokens(token, user_id, expires_at) VALUES (?,?,?)",
            (token, row["user_id"], _iso(expires)),
        )
        conn.commit()
        base["reset_token"] = token
        base["expires_at"] = _iso(expires)
        base["pilot_note"] = "Token echoed for staging/partner only. Never in production."
        return base
    finally:
        conn.close()


def reset_password_with_token(
    token: str,
    new_password: str,
    *,
    url: str | None = None,
) -> dict[str, Any]:
    ensure_auth_schema(url)
    tok = (token or "").strip()
    if not tok:
        raise ValueError("cần reset_token")
    pw = _require_password(new_password)
    conn = get_connection(url)
    try:
        row = conn.execute(
            "SELECT * FROM password_reset_tokens WHERE token=?", (tok,)
        ).fetchone()
        if not row:
            raise KeyError("token không hợp lệ")
        if row["consumed"]:
            raise ValueError("token đã dùng")
        expires = datetime.fromisoformat(row["expires_at"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if _now() > expires:
            raise ValueError("token hết hạn")
        user = conn.execute(
            "SELECT user_id, role FROM users WHERE user_id=?", (row["user_id"],)
        ).fetchone()
        if not user:
            raise KeyError("user không tồn tại")
        role = (user["role"] or "guest").strip().lower()
        if role not in GUEST_ROLES:
            raise PermissionError("reset bị từ chối (role)")
        conn.execute(
            "UPDATE users SET password_hash=?, updated_at=datetime('now') WHERE user_id=?",
            (_hash_password(pw), user["user_id"]),
        )
        conn.execute(
            "UPDATE password_reset_tokens SET consumed=1 WHERE token=?", (tok,)
        )
        # Revoke outstanding password sessions
        conn.execute(
            "UPDATE auth_tokens SET revoked=1 WHERE user_id=? AND kind='password' AND revoked=0",
            (user["user_id"],),
        )
        conn.commit()
        return {"ok": True, "user_id": user["user_id"]}
    finally:
        conn.close()


def seed_partner_demo(*, url: str | None = None) -> dict[str, Any]:
    """
    Upsert partner demo account when WELORA_GUEST_DEMO=1.
    Separated from Hard Deny / Cổng / Mode C — auth-only seed.
    """
    if not guest_demo_enabled():
        return {"seeded": False, "reason": "demo_seed_disabled"}
    ensure_auth_schema(url)
    conn = get_connection(url)
    try:
        row = conn.execute(
            "SELECT user_id, role FROM users WHERE email=?", (DEMO_EMAIL,)
        ).fetchone()
        if row:
            return {
                "seeded": False,
                "already": True,
                "user_id": row["user_id"],
                "email": DEMO_EMAIL,
                "role": row["role"] or "demo",
                "password_hint": DEMO_PASSWORD,
            }
        user_id = PARTNER_USER_ID
        device_key = "demo:" + hashlib.sha256(DEMO_EMAIL.encode()).hexdigest()[:16]
        conn.execute(
            "INSERT INTO users(user_id, display_name, device_id, email, phone, password_hash, role) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                user_id,
                DEMO_DISPLAY,
                device_key,
                DEMO_EMAIL,
                DEMO_PHONE,
                _hash_password(DEMO_PASSWORD),
                "demo",
            ),
        )
        conn.commit()
        return {
            "seeded": True,
            "user_id": user_id,
            "email": DEMO_EMAIL,
            "phone": DEMO_PHONE,
            "role": "demo",
            "password_hint": DEMO_PASSWORD,
        }
    finally:
        conn.close()


def get_user_for_token(token: str, *, url: str | None = None) -> Optional[dict[str, Any]]:
    uid = resolve_token(token, url=url)
    if not uid:
        return None
    ensure_auth_schema(url)
    conn = get_connection(url)
    try:
        row = conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        if not row:
            return None
        return _user_row_public(row)
    finally:
        conn.close()


def service_register(body: dict) -> tuple[int, dict]:
    try:
        # Ignore client role elevation attempts
        out = register_guest(
            email=body.get("email"),
            phone=body.get("phone"),
            password=body.get("password") or "",
            display_name=body.get("display_name"),
            role="guest",
        )
        return 201, out
    except ValueError as e:
        return 400, {"error": str(e)}
    except PermissionError as e:
        return 403, {"error": str(e)}


def service_login(body: dict) -> tuple[int, dict]:
    try:
        out = login_guest(
            email=body.get("email"),
            phone=body.get("phone"),
            password=body.get("password") or "",
        )
        return 200, out
    except ValueError as e:
        return 401, {"error": str(e)}
    except PermissionError as e:
        return 403, {"error": str(e)}


def service_logout(token: str) -> tuple[int, dict]:
    if not token:
        return 401, {"error": "missing token"}
    return 200, logout_guest(token)


def service_forgot_password(body: dict) -> tuple[int, dict]:
    try:
        out = request_password_reset(
            email=body.get("email"),
            phone=body.get("phone"),
        )
        return 200, out
    except ValueError as e:
        return 400, {"error": str(e)}


def service_reset_password(body: dict) -> tuple[int, dict]:
    try:
        out = reset_password_with_token(
            body.get("reset_token") or body.get("token") or "",
            body.get("new_password") or body.get("password") or "",
        )
        return 200, out
    except KeyError as e:
        return 404, {"error": str(e)}
    except ValueError as e:
        return 400, {"error": str(e)}
    except PermissionError as e:
        return 403, {"error": str(e)}


def service_demo_seed() -> tuple[int, dict]:
    """Seed partner auth + rich P2 OS data; alias demo-p4 for P4 (idempotent)."""
    out = seed_partner_demo()
    if not guest_demo_enabled():
        return 200, out
    try:
        from welora.partner_demo_seed import seed_partner_rich_demo

        rich = seed_partner_rich_demo()
        out["rich"] = {
            "partner_user_id": (rich.get("partner") or {}).get("user_id"),
            "p2_gate": ((rich.get("partner") or {}).get("persona") or {})
            .get("safety_gate", {})
            .get("status"),
            "demo_p4_email": rich.get("p4_login"),
            "demo_p4_user_id": (rich.get("demo_p4") or {}).get("user_id"),
            "p4_gate": ((rich.get("demo_p4") or {}).get("persona") or {})
            .get("safety_gate", {})
            .get("status"),
            "p4_exposure": rich.get("p4_exposure"),
        }
        # Prefer stable partner id from rich seed when available
        if (rich.get("partner") or {}).get("user_id"):
            out["user_id"] = rich["partner"]["user_id"]
    except Exception as exc:  # pragma: no cover
        out["rich_error"] = str(exc)
    return 200, out


# Enhance /auth/me — keep backward compatible user_id, add role when available
_orig_service_me = service_me


def service_me(token: str) -> tuple[int, dict]:  # type: ignore[no-redef]
    user = get_user_for_token(token)
    if not user:
        return 401, {"error": "invalid or expired token"}
    return 200, user
