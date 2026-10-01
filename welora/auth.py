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
from welora.phone import PHONE_CONFLICT_MSG, PhoneConflictError, candidate_rows as phone_candidate_rows
from welora.phone import find_user_by_phone, normalize_phone_e164, phone_conflicted, phone_taken
from welora.phone import lookup_candidates as phone_lookup_candidates
from welora.phone import try_normalize as try_normalize_phone

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


# --- P0 follow-up: login token expiry -------------------------------------------------------
# Every token row gets expires_at at issue time. WELORA_TOKEN_TTL_DAYS (default 30) covers
# password / phone-OTP / email-OTP (admin) / demo tokens; WELORA_DEVICE_TOKEN_TTL_DAYS (default:
# same as WELORA_TOKEN_TTL_DAYS) covers /auth/device guest tokens (the web FE keeps those in
# memory only and re-mints one per page load, so the TTL mostly bounds a leaked token).
# Legacy rows (expires_at NULL, issued before this change) are NOT logged out abruptly: they get
# expires_at = max(created_at + TTL, first-seen + LEGACY_TOKEN_GRACE_DAYS), written once
# (conditional UPDATE … WHERE expires_at IS NULL) on first use or by the startup backfill.
TOKEN_TTL_DAYS_DEFAULT = 30
LEGACY_TOKEN_GRACE_DAYS = 7
TOKEN_EXPIRED_MSG = "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại."


def _env_days(key: str, default: float) -> float:
    import os as _os

    raw = (_os.environ.get(key) or "").strip()
    try:
        v = float(raw) if raw else float(default)
    except ValueError:
        v = float(default)
    return v if v > 0 else float(default)


def token_ttl_days(kind: str | None = None) -> float:
    base = _env_days("WELORA_TOKEN_TTL_DAYS", TOKEN_TTL_DAYS_DEFAULT)
    if (kind or "") == "device":
        return _env_days("WELORA_DEVICE_TOKEN_TTL_DAYS", base)
    return base


def token_expires_at(kind: str | None = None, *, now: datetime | None = None) -> str:
    return _iso((now or _now()) + timedelta(days=token_ttl_days(kind)))


def _parse_ts(raw: Any) -> Optional[datetime]:
    """created_at/expires_at as written by SQLite (datetime('now')), Postgres (now()::text) or _iso()."""
    if raw is None:
        return None
    if isinstance(raw, datetime):
        dt = raw
    else:
        txt = str(raw).strip()
        if not txt:
            return None
        txt = txt.replace("Z", "+00:00")
        import re as _re

        # Postgres now()::text ends in a bare '+00' offset (time part required, so a date's '-01' is safe)
        txt = _re.sub(r"(\d\d:\d\d(?::\d\d(?:\.\d+)?)?)([+-]\d\d)$", r"\1\2:00", txt)
        try:
            dt = datetime.fromisoformat(txt)
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _legacy_expiry(created_at: Any, kind: str | None, *, now: datetime) -> str:
    created = _parse_ts(created_at) or now
    natural = created + timedelta(days=token_ttl_days(kind))
    floor = now + timedelta(days=LEGACY_TOKEN_GRACE_DAYS)
    return _iso(max(natural, floor))


def backfill_legacy_token_expiry(*, url: str | None = None) -> int:
    """Idempotent: give every expires_at-NULL token its legacy expiry. Returns rows updated."""
    ensure_auth_schema(url)
    conn = get_connection(url)
    try:
        rows = conn.execute(
            "SELECT token, kind, created_at FROM auth_tokens WHERE expires_at IS NULL"
        ).fetchall()
        now = _now()
        n = 0
        for r in rows:
            cur = conn.execute(
                "UPDATE auth_tokens SET expires_at=? WHERE token=? AND expires_at IS NULL",
                (_legacy_expiry(r["created_at"], r["kind"], now=now), r["token"]),
            )
            n += int(cur.rowcount or 0)
        conn.commit()
        return n
    finally:
        conn.close()


def _insert_token(conn, user_id: str, *, kind: str, device_id: str | None = None) -> str:
    token = _token()
    conn.execute(
        "INSERT INTO auth_tokens(token, user_id, device_id, kind, expires_at) VALUES (?,?,?,?,?)",
        (token, user_id, device_id, kind, token_expires_at(kind)),
    )
    return token


def token_expiry(conn, token: str) -> Optional[str]:
    """expires_at of a token (ISO-8601 UTC) — returned by every token-issuing response and /auth/me
    so clients know when the session ends (P0 follow-up 2, item 8). Works before commit on the
    connection that inserted it."""
    row = conn.execute("SELECT expires_at FROM auth_tokens WHERE token=?", (token,)).fetchone() if token else None
    return (row["expires_at"] if row else None) or None


def token_expiry_of(token: str, *, url: str | None = None) -> Optional[str]:
    if not token:
        return None
    conn = get_connection(url)
    try:
        return token_expiry(conn, token)
    finally:
        conn.close()


# --- P0: /auth/device account-takeover guard -------------------------------------------
# Non-device login paths stamp users.device_id with an internal namespace. Those values used
# to be derived from public data (sha256(email|phone)[:16]) so POST /auth/device could replay
# them and receive the victim's token. Now: (1) client device_ids in these namespaces are
# rejected, (2) /auth/device only ever reuses a *pure device-guest* row, (3) new internal
# keys are random and no login path looks a user up by them.
INTERNAL_DEVICE_PREFIXES = ("guest:", "phone:", "email:", "demo:")
DEVICE_RESERVED_MSG = "Mã thiết bị không hợp lệ (tiền tố dành riêng cho hệ thống)."
DEVICE_NOT_GUEST_MSG = (
    "Mã thiết bị này không dùng được cho đăng nhập khách. "
    "Vui lòng đăng nhập bằng email hoặc số điện thoại."
)


class DeviceIdReserved(ValueError):
    pass


class DeviceNotGuest(PermissionError):
    pass


def is_reserved_device_id(device_id: str | None) -> bool:
    return (device_id or "").strip().lower().startswith(INTERNAL_DEVICE_PREFIXES)


def internal_device_key(prefix: str) -> str:
    """Random internal device marker (never derived from email/phone, never looked up)."""
    assert prefix in INTERNAL_DEVICE_PREFIXES
    return prefix + secrets.token_hex(16)


def _is_pure_device_guest(conn, row) -> bool:
    """Only rows created by POST /auth/device: no credentials, no email/phone, guest role,
    no internal namespace (legacy phone-OTP rows keep the phone only in device_id), and no
    history of any other login kind (password / otp / email_otp tokens or OTP challenges) —
    so a row stays protected even if its device_id were ever rewritten."""
    for col in ("password_hash", "email", "phone", "email_verified_at"):
        if str(row[col] or "").strip():
            return False
    if str(row["role"] or "guest").strip().lower() != "guest":
        return False
    if is_reserved_device_id(row["device_id"]):
        return False
    uid = row["user_id"]
    if conn.execute(
        "SELECT 1 FROM auth_tokens WHERE user_id=? AND COALESCE(kind,'device')<>'device' LIMIT 1", (uid,)
    ).fetchone():
        return False
    if conn.execute("SELECT 1 FROM otp_challenges WHERE user_id=? LIMIT 1", (uid,)).fetchone():
        return False
    return True


def device_guest_exists(device_id: str | None, *, url: str | None = None) -> bool:
    """True when a users row already carries this device_id (POST /auth/device would reuse it,
    not create a new guest) — used only to pick the /auth/device rate-limit bucket."""
    d = (device_id or "").strip()
    if not d:
        return False
    ensure_auth_schema(url)
    conn = get_connection(url)
    try:
        return conn.execute("SELECT 1 FROM users WHERE device_id=? LIMIT 1", (d,)).fetchone() is not None
    finally:
        conn.close()


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
    if is_reserved_device_id(device_id):
        raise DeviceIdReserved(DEVICE_RESERVED_MSG)

    ensure_auth_schema(url)
    conn = get_connection(url)
    try:
        row = conn.execute(
            "SELECT user_id, display_name, device_id, email, phone, password_hash, role, email_verified_at "
            "FROM users WHERE device_id=?",
            (device_id,),
        ).fetchone()
        created = False
        if row:
            if not _is_pure_device_guest(conn, row):
                raise DeviceNotGuest(DEVICE_NOT_GUEST_MSG)
            _admin_login_gate(conn, row["user_id"], via="device_login")
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

        token = _insert_token(conn, user_id, kind="device", device_id=device_id)
        expires_at = token_expiry(conn, token)
        conn.commit()
        return {
            "user_id": user_id,
            "token": token,
            "expires_at": expires_at,
            "kind": "device",
            "created": created,
            "display_name": name,
        }
    finally:
        conn.close()


def _otp_code_hash(challenge_id: str, code: str) -> str:
    """Phone-OTP code at rest: salted per challenge like email-OTP (`sha256:` marks hashed rows)."""
    return "sha256:" + hashlib.sha256(f"welora-phone-otp:{challenge_id}:{code}".encode("utf-8")).hexdigest()


def _otp_code_matches(challenge_id: str, stored: str, code: str) -> bool:
    import hmac

    stored = stored or ""
    c = (code or "").strip()
    if stored.startswith("sha256:"):
        return hmac.compare_digest(stored, _otp_code_hash(challenge_id, c))
    return bool(stored) and hmac.compare_digest(stored, c)  # in-flight legacy plaintext rows (10-min TTL)


def otp_challenge_phone(challenge_id: str, *, url: str | None = None) -> Optional[str]:
    """Phone of a challenge (rate-limit key for /auth/otp/verify); None if unknown."""
    if not challenge_id:
        return None
    ensure_auth_schema(url)
    conn = get_connection(url)
    try:
        row = conn.execute("SELECT phone FROM otp_challenges WHERE challenge_id=?", (challenge_id,)).fetchone()
        return row["phone"] if row else None
    finally:
        conn.close()


def otp_echo_enabled() -> bool:
    """P0: the phone-OTP code is echoed in the API response ONLY when WELORA_OTP_ECHO=1
    (staging demo). Unset / any other value → never echoed. Production must not set it."""
    import os

    return (os.environ.get("WELORA_OTP_ECHO") or "").strip() == "1"


def sms_provider_configured() -> bool:
    """No SMS delivery integration exists in this codebase (see renewal/push: no SMS / Zalo).
    Kept explicit so the UI can say 'Kênh SMS chưa bật' instead of pretending a code was sent."""
    return False


def request_otp(
    phone: str,
    *,
    url: str | None = None,
    fixed_code: Optional[str] = None,
) -> dict[str, Any]:
    raw = (phone or "").strip()
    if not raw or len(raw) < 8:
        raise ValueError("phone is required (min 8 chars)")
    phone = normalize_phone_e164(raw)  # stored E.164 (item 9) — ValueError (VI) when invalid

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
            (challenge_id, phone, _otp_code_hash(challenge_id, code), _iso(expires)),
        )
        conn.commit()
        out = {
            "challenge_id": challenge_id,
            "phone_masked": _mask_phone(phone),
            "expires_at": _iso(expires),
            "sms_enabled": sms_provider_configured(),
            "otp_echo": otp_echo_enabled(),
        }
        if out["otp_echo"]:
            out["pilot_code"] = code
            out["pilot_note"] = "Code echoed because WELORA_OTP_ECHO=1 (staging demo only). Never in production."
        return out
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

        if not _otp_code_matches(challenge_id, row["code"], code):
            conn.execute(
                "UPDATE otp_challenges SET attempts=attempts+1 WHERE challenge_id=?",
                (challenge_id,),
            )
            conn.commit()
            raise ValueError("invalid code")

        # CoS review #239: an ambiguous number (migration collision) never signs anyone in by OTP —
        # the caller proved possession of the phone (right code), so telling them is no leak.
        _otp_e164 = try_normalize_phone(row["phone"])
        if _otp_e164 and phone_conflicted(conn, _otp_e164):
            raise PhoneConflictError(PHONE_CONFLICT_MSG)

        # P0 follow-up: consume atomically BEFORE issuing anything — of two concurrent verifies
        # with the right code only the one whose conditional UPDATE hits the row (rowcount 1) wins.
        cur = conn.execute(
            "UPDATE otp_challenges SET consumed=1 WHERE challenge_id=? AND consumed=0",
            (challenge_id,),
        )
        if int(cur.rowcount or 0) != 1:
            conn.rollback()
            raise ValueError("challenge already used")

        phone = row["phone"]
        user_id = row["user_id"]
        if not user_id:
            user_id = str(uuid4())
            # Returning phone-OTP user = owner of an earlier consumed challenge for this phone
            # (challenge.user_id is only ever set here). No lookup by a derived device_id.
            # phone forms: E.164 + legacy local rows not yet migrated (item 9)
            e164 = try_normalize_phone(phone) or phone
            cands = phone_lookup_candidates(e164) if e164.startswith("+") else [phone]
            existing = conn.execute(
                "SELECT c.user_id FROM otp_challenges c JOIN users u ON u.user_id = c.user_id "
                "WHERE c.phone IN (" + ",".join("?" * len(cands)) + ") AND c.consumed=1 "
                "AND c.user_id IS NOT NULL ORDER BY c.created_at, c.challenge_id LIMIT 1",
                tuple(cands),
            ).fetchone()
            device_key = internal_device_key("phone:")
            if existing:
                _admin_login_gate(conn, existing["user_id"], via="phone_otp")
                user_id = existing["user_id"]
            else:
                conn.execute(
                    "INSERT INTO users(user_id, display_name, device_id) VALUES (?,?,?)",
                    (user_id, phone, device_key),
                )

        conn.execute(
            "UPDATE otp_challenges SET user_id=? WHERE challenge_id=?",
            (user_id, challenge_id),
        )
        token = _insert_token(conn, user_id, kind="otp")
        expires_at = token_expiry(conn, token)
        conn.commit()
        return {"user_id": user_id, "token": token, "expires_at": expires_at, "kind": "otp", "created": False}
    finally:
        conn.close()


def _admin_login_gate(conn, user_id: str, *, via: str) -> str:
    """Admin accounts sign in by email OTP only (WELORA_ADMIN_EMAILS) — never device / phone OTP / password.

    An admin-role user whose email is no longer listed is demoted here (audited)
    and continues as a normal user; a still-listed admin is refused on this path.
    """
    row = conn.execute(
        "SELECT user_id, email, role, email_verified_at FROM users WHERE user_id=?", (user_id,)
    ).fetchone()
    role = ((row["role"] if row else None) or "guest").strip().lower()
    if role not in ADMIN_ROLES:
        return role
    from welora import admin_bootstrap

    role = admin_bootstrap.sync_role(conn, row, via=via)
    conn.commit()
    if role in ADMIN_ROLES:
        raise PermissionError("tài khoản quản trị chỉ đăng nhập bằng mã OTP email")
    return role


def token_state(token: str, *, url: str | None = None) -> tuple[str, Optional[str]]:
    """("ok", user_id) | ("expired", user_id) | ("revoked", user_id) | ("unknown", None)."""
    if not token:
        return "unknown", None
    ensure_auth_schema(url)
    conn = get_connection(url)
    try:
        row = conn.execute(
            "SELECT user_id, kind, created_at, expires_at, revoked FROM auth_tokens WHERE token=?",
            (token,),
        ).fetchone()
        if not row:
            return "unknown", None
        if row["revoked"]:
            return "revoked", row["user_id"]
        now = _now()
        exp_raw = row["expires_at"]
        if not exp_raw:
            # legacy token (pre-expiry): fix its expiry once, never shorter than the grace period
            exp_raw = _legacy_expiry(row["created_at"], row["kind"], now=now)
            conn.execute(
                "UPDATE auth_tokens SET expires_at=? WHERE token=? AND expires_at IS NULL",
                (exp_raw, token),
            )
            conn.commit()
            again = conn.execute("SELECT expires_at FROM auth_tokens WHERE token=?", (token,)).fetchone()
            exp_raw = (again["expires_at"] if again else None) or exp_raw
        exp = _parse_ts(exp_raw)
        if exp is None or now > exp:
            return "expired", row["user_id"]
        return "ok", row["user_id"]
    finally:
        conn.close()


def resolve_token(token: str, *, url: str | None = None) -> Optional[str]:
    state, uid = token_state(token, url=url)
    return uid if state == "ok" else None


def _unauthorized_body(token: str) -> dict[str, Any]:
    state, _uid = token_state(token) if token else ("unknown", None)
    if state == "expired":
        return {"error": {"error_code": "TOKEN_EXPIRED", "message": TOKEN_EXPIRED_MSG}}
    return {"error": "invalid or expired token"}


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
    if phone.startswith("+84") and len(phone) > 6:
        phone = "0" + phone[3:]  # mask the familiar local form: 09****95
    return phone[:2] + "****" + phone[-2:]


def service_device_login(body: dict) -> tuple[int, dict]:
    try:
        out = login_or_register_device(
            body.get("device_id") or "",
            display_name=body.get("display_name"),
        )
        return 200 if not out["created"] else 201, out
    except DeviceIdReserved as e:
        return 403, {"error": str(e), "error_code": "DEVICE_ID_RESERVED", "message": str(e)}
    except DeviceNotGuest as e:
        return 403, {"error": str(e), "error_code": "DEVICE_NOT_GUEST", "message": str(e)}
    except PermissionError as e:
        return 403, {"error": str(e), "error_code": "ADMIN_EMAIL_OTP_ONLY"}
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
    except PhoneConflictError as e:
        return 409, {"error_code": "PHONE_CONFLICT_USE_EMAIL", "message": str(e)}
    except PermissionError as e:
        return 403, {"error": str(e), "error_code": "ADMIN_EMAIL_OTP_ONLY"}
    except KeyError:
        return 404, {"error": "challenge not found"}
    except ValueError as e:
        return 400, {"error": str(e)}


def service_me(token: str) -> tuple[int, dict]:
    uid = resolve_token(token)
    if not uid:
        return 401, _unauthorized_body(token)
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
    """E.164 (+84… default) — the stored form since P0 follow-up 2 (welora/phone.py)."""
    return normalize_phone_e164(phone)


_DUMMY_HASH: list[str] = []


def _dummy_password_check(password: str) -> None:
    """Burn one PBKDF2 round for an unknown / password-less account so the response time does not
    reveal whether the account exists (item 10)."""
    if not _DUMMY_HASH:
        _DUMMY_HASH.append(_hash_password(secrets.token_hex(16)))
    _verify_password(password or "", _DUMMY_HASH[0])


def _is_unique_violation(exc: BaseException) -> bool:
    name = type(exc).__name__
    return name in ("IntegrityError", "UniqueViolation") or "unique" in str(exc).lower()


def _require_password(password: str) -> str:
    pw = password or ""
    if len(pw) < MIN_PASSWORD_LEN:
        raise ValueError(f"mật khẩu tối thiểu {MIN_PASSWORD_LEN} ký tự")
    return pw


def _issue_token(conn, user_id: str, kind: str = "password") -> str:
    """password / demo / email_otp tokens — expires_at = now + token_ttl_days(kind)."""
    return _insert_token(conn, user_id, kind=kind)


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
    # internal marker only (random; login is by email/phone + password, never by device_id)
    device_key = internal_device_key("guest:")

    conn = get_connection(url)
    try:
        if email_n:
            hit = conn.execute(
                "SELECT user_id FROM users WHERE email=?", (email_n,)
            ).fetchone()
            if hit:
                raise ValueError("email đã được đăng ký")
        if phone_n and phone_taken(conn, phone_n):  # E.164 or a legacy local-format row
            raise ValueError("số điện thoại đã được đăng ký")

        try:
            conn.execute(
                "INSERT INTO users(user_id, display_name, device_id, email, phone, password_hash, role) "
                "VALUES (?,?,?,?,?,?,?)",
                (user_id, name, device_key, email_n, phone_n, pw_hash, safe_role),
            )
        except Exception as e:  # concurrent register of the same email/phone
            if not _is_unique_violation(e):
                raise
            conn.rollback()
            raise ValueError("email hoặc số điện thoại đã được đăng ký")
        token = _issue_token(conn, user_id, "password")
        expires_at = token_expiry(conn, token)
        conn.commit()
        return {
            "user_id": user_id,
            "token": token,
            "expires_at": expires_at,
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
            if phone_conflicted(conn, phone_n):
                # CoS review #239: an ambiguous number (several accounts) never logs anyone in —
                # no account is preferred. Only a caller who knows the password of one of the
                # accounts learns why (otherwise the same generic 401 as an unknown number).
                hashes = [r["password_hash"] for r in phone_candidate_rows(conn, phone_n, "password_hash")
                          if str(r["password_hash"] or "").strip()]
                if not hashes:
                    _dummy_password_check(pw)
                if any(_verify_password(pw, h) for h in hashes):
                    raise PhoneConflictError(PHONE_CONFLICT_MSG)
                raise ValueError("email/số điện thoại hoặc mật khẩu không đúng")
            row = find_user_by_phone(conn, phone_n)
        if not row or not row["password_hash"]:
            _dummy_password_check(pw)  # same cost as a real check — no timing oracle (item 10)
            raise ValueError("email/số điện thoại hoặc mật khẩu không đúng")
        role = (row["role"] or "guest").strip().lower()
        if role in ADMIN_ROLES:
            # de-listed admin → demoted (audited) and continues as guest; listed admin → refused
            role = _admin_login_gate(conn, row["user_id"], via="password_login")
        if role in ADMIN_ROLES or role not in GUEST_ROLES:
            # Fail-closed: never allow password path into elevated roles
            raise PermissionError("đăng nhập bị từ chối (role)")
        if not _verify_password(pw, row["password_hash"]):
            raise ValueError("email/số điện thoại hoặc mật khẩu không đúng")
        token = _issue_token(conn, row["user_id"], "password")
        expires_at = token_expiry(conn, token)
        conn.commit()
        pub = {**_user_row_public(row), "role": role}  # role after a possible de-list demotion
        return {
            **pub,
            "token": token,
            "expires_at": expires_at,
            "kind": "password",
            "created": False,
        }
    finally:
        conn.close()


def logout_guest(token: str, *, url: str | None = None) -> dict[str, Any]:
    ok = revoke_token(token, url=url)
    return {"revoked": bool(ok)}


RESET_GENERIC_MSG = "Nếu tài khoản tồn tại, yêu cầu đặt lại mật khẩu đã được ghi nhận."
PHONE_RESET_HINT = (
    "Nếu số điện thoại này gắn với nhiều tài khoản (dữ liệu cũ), không thể đặt lại mật khẩu bằng số "
    "điện thoại — vui lòng dùng email của tài khoản."
)


def reset_echo_enabled() -> bool:
    """P0: reset_token is echoed in the API response ONLY when WELORA_RESET_ECHO=1
    (staging demo; there is no reset e-mail/SMS delivery yet). Production must not set it."""
    import os

    return (os.environ.get("WELORA_RESET_ECHO") or "").strip() == "1"


def request_password_reset(
    *,
    email: str | None = None,
    phone: str | None = None,
    url: str | None = None,
) -> dict[str, Any]:
    """
    Forgot-password MVP — token stub (no email/SMS delivery yet).

    The response is identical whether or not the account exists (same status, keys and
    Vietnamese message) — no account enumeration. Only with WELORA_RESET_ECHO=1 (staging)
    is a token minted and echoed for an existing guest/demo account. The token is never logged.
    """
    ensure_auth_schema(url)
    email_n = _norm_email(email) if email else None
    phone_n = _norm_phone(phone) if phone else None
    if not email_n and not phone_n:
        raise ValueError("cần email hoặc số điện thoại")
    echo = reset_echo_enabled()
    base = {
        "ok": True,
        "approach": "token_stub",
        "message": RESET_GENERIC_MSG,
        "note": RESET_GENERIC_MSG,
        "reset_echo": echo,
        "delivery": "none",
    }
    # CoS review #239: identical in every response (email or phone, existing or not — no
    # enumeration). An ambiguous phone number (several accounts) never gets a token.
    base["phone_note"] = PHONE_RESET_HINT
    if not echo:
        return base  # no lookup, no token: nothing to deliver it with

    conn = get_connection(url)
    try:
        row = None
        if email_n:
            row = conn.execute(
                "SELECT user_id, role FROM users WHERE email=?", (email_n,)
            ).fetchone()
        if row is None and phone_n:
            row = find_user_by_phone(conn, phone_n, "user_id, role, phone")
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
        base["pilot_note"] = "Token echoed because WELORA_RESET_ECHO=1 (staging only). Never in production."
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
        # single-use, atomic across instances: only the request that flips consumed 0→1 proceeds
        cur = conn.execute(
            "UPDATE password_reset_tokens SET consumed=1 WHERE token=? AND consumed=0", (tok,)
        )
        if (cur.rowcount or 0) != 1:
            conn.rollback()
            raise ValueError("token đã dùng")
        conn.execute(
            "UPDATE users SET password_hash=?, updated_at=datetime('now') WHERE user_id=?",
            (_hash_password(pw), user["user_id"]),
        )
        # any other outstanding reset token for this user is void once the password changed
        conn.execute(
            "UPDATE password_reset_tokens SET consumed=1 WHERE user_id=? AND consumed=0",
            (user["user_id"],),
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
        device_key = internal_device_key("demo:")
        # Race-safe (item 5): concurrent first logins on an empty DB may all get here. The insert
        # ignores ANY unique conflict (user_id / email / phone); the loser re-reads the winner's row.
        cur = conn.execute(
            "INSERT INTO users(user_id, display_name, device_id, email, phone, password_hash, role) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
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
        if int(cur.rowcount or 0) != 1:
            row = conn.execute("SELECT user_id, role FROM users WHERE email=?", (DEMO_EMAIL,)).fetchone()
            return {
                "seeded": False,
                "already": True,
                "user_id": row["user_id"] if row else user_id,
                "email": DEMO_EMAIL,
                "role": (row["role"] if row else None) or "demo",
                "password_hint": DEMO_PASSWORD,
            }
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


LOGIN_ONE_IDENTIFIER_MSG = "Chỉ nhập email hoặc số điện thoại để đăng nhập, không nhập cả hai."


def login_identifier_conflict(email: str | None, phone: str | None) -> bool:
    """True when a login names both an email and a phone (rejected with 400 — the lookup would
    silently fall back from one to the other, which defeated per-account rate limits)."""
    return bool((email or "").strip()) and bool((phone or "").strip())


def login_rate_key(*, email: str | None = None, phone: str | None = None, url: str | None = None) -> str:
    """Rate-limit account key for /auth/login, resolved exactly like login_guest's lookup.

    Existing account → ``user:<user_id>`` (one budget whether the email or the phone is used).
    Unknown account  → ``email:<normalised>`` / ``phone:<normalised>`` — the identifier the lookup
    used, so failures against non-existent accounts still count per identifier. The caller treats
    both cases identically (same limits, same responses) → nothing reveals whether it exists.
    Call only after login_identifier_conflict() was rejected. "" when no identifier at all."""
    raw_e = (email or "").strip()
    raw_p = (phone or "").strip()
    if raw_e:
        col, raw = "email", raw_e
        try:
            norm = _norm_email(raw_e)
        except ValueError:
            norm = None
    elif raw_p:
        col, raw = "phone", raw_p
        try:
            norm = _norm_phone(raw_p)
        except ValueError:
            norm = None
    else:
        return ""
    if norm:
        ensure_auth_schema(url)
        conn = get_connection(url)
        try:
            if col == "phone":
                row = find_user_by_phone(conn, norm, "user_id, phone")
            else:
                row = conn.execute("SELECT user_id FROM users WHERE email=?", (norm,)).fetchone()
        finally:
            conn.close()
        if row and row["user_id"]:
            return "user:" + str(row["user_id"])
        return f"{col}:{norm}"
    return f"{col}:invalid:{raw.lower()}"


def service_login(body: dict) -> tuple[int, dict]:
    if login_identifier_conflict(body.get("email"), body.get("phone")):
        return 400, {"error": LOGIN_ONE_IDENTIFIER_MSG}
    try:
        out = login_guest(
            email=body.get("email"),
            phone=body.get("phone"),
            password=body.get("password") or "",
        )
        return 200, out
    except PhoneConflictError as e:
        return 409, {"error_code": "PHONE_CONFLICT_USE_EMAIL", "message": str(e)}
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
    """Seed partner auth + rich P1–P6 OS data (idempotent login aliases)."""
    out = seed_partner_demo()
    if not guest_demo_enabled():
        return 200, out
    try:
        from welora.partner_demo_seed import seed_partner_rich_demo

        rich = seed_partner_rich_demo()
        aliases = rich.get("aliases") or {}
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
            "aliases": aliases,
            "persona_emails": {
                pid: (aliases.get(pid) or {}).get("email")
                for pid in ("P1", "P2", "P3", "P4", "P5", "P6")
            },
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
        return 401, _unauthorized_body(token)
    return 200, {**user, "expires_at": token_expiry_of(token)}


# ---------------------------------------------------------------------------
# Admin bootstrap — email OTP (WELORA_ADMIN_EMAILS); see welora/admin_bootstrap.py
# ---------------------------------------------------------------------------


def service_email_otp_request(body: dict) -> tuple[int, dict]:
    from welora import admin_bootstrap

    try:
        return 200, admin_bootstrap.request_email_otp(body.get("email") or "")
    except ValueError as e:
        return 400, {"error": str(e)}


def service_email_otp_verify(body: dict) -> tuple[int, dict]:
    from welora import admin_bootstrap

    try:
        return 200, admin_bootstrap.verify_email_otp(body.get("challenge_id") or "", body.get("code") or "")
    except ValueError as e:
        return 400, {"error": str(e)}
