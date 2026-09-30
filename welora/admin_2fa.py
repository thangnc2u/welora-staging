"""Admin 2FA (Phụ lục Checkout mục 9 — "Trang quản trị có 2FA, phân quyền").

Method: TOTP (RFC 6238, SHA-1, 6 digits, 30 s) — works with any authenticator app.
- Secrets live ONLY in env ``WELORA_ADMIN_TOTP_SECRETS`` — comma-separated
  ``email:BASE32`` (preferred: survives a DB reset / new user_id) or
  ``user_id:BASE32`` — set on Render; never committed, never logged, never stored
  in the DB. An ``email:`` entry matches only the user's email VERIFIED by the
  email-OTP admin login (``users.email_verified_at``); ``user_id`` wins if both exist.
- ``POST /api/admin/v1/2fa/verify`` with a valid code opens a 2FA session bound
  to the caller's bearer token (sha256 only stored), TTL ``WELORA_ADMIN_2FA_TTL_S``
  (default 12 h). Every admin checkout API requires admin role + live session.
- Replay protection (a code step is accepted once) and lockout after 5 failures
  for 15 minutes.
- Fail closed: an admin with no configured secret cannot pass 2FA.

Generate a secret locally (prints to your terminal only):
    PYTHONPATH=. python -m welora.admin_2fa gen <admin_email>     # preferred
    PYTHONPATH=. python -m welora.admin_2fa gen <admin_user_id>
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

STEP_S = 30
DIGITS = 6
WINDOW = 1  # accept previous/next step for clock drift
MAX_FAILED = 5
LOCK_S = 15 * 60
DEFAULT_TTL_S = 12 * 3600


class TwoFactorError(Exception):
    def __init__(self, status: int, error_code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.error_code = error_code
        self.message = message

    def body(self) -> dict[str, Any]:
        return {"error_code": self.error_code, "message": self.message}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="seconds")


def _ts(iso: Optional[str]) -> float:
    if not iso:
        return 0.0
    dt = datetime.fromisoformat(str(iso))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _b32decode(secret: str) -> bytes:
    s = "".join(str(secret).split()).upper()
    s += "=" * (-len(s) % 8)
    return base64.b32decode(s)


def generate_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp(secret: str, *, at: Optional[float] = None, step: int = STEP_S, digits: int = DIGITS) -> str:
    counter = int((time.time() if at is None else at) // step)
    return _hotp(secret, counter, digits)


def _hotp(secret: str, counter: int, digits: int = DIGITS) -> str:
    mac = hmac.new(_b32decode(secret), struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off : off + 4])[0] & 0x7FFFFFFF) % (10**digits)
    return str(code).zfill(digits)


def provisioning_uri(secret: str, account: str, issuer: str = "Welora Admin") -> str:
    return (
        f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}"
        f"&issuer={quote(issuer)}&algorithm=SHA1&digits={DIGITS}&period={STEP_S}"
    )


def _norm_key(key: str) -> str:
    k = (key or "").strip()
    return k.lower() if "@" in k else k


def _secrets_from_env() -> dict[str, str]:
    raw = (os.environ.get("WELORA_ADMIN_TOTP_SECRETS") or "").strip()
    out: dict[str, str] = {}
    for part in raw.split(","):
        key, sep, sec = part.strip().partition(":")
        if sep and key.strip() and sec.strip():
            out[_norm_key(key)] = sec.strip()
    return out


def _secret_for(user_id: str) -> Optional[str]:
    """TOTP secret by user_id, else by the user's verified email (email:BASE32)."""
    uid = (user_id or "").strip()
    if not uid:
        return None
    table = _secrets_from_env()
    if uid in table:
        return table[uid]
    if not any("@" in k for k in table):
        return None
    from welora import admin_bootstrap

    email = admin_bootstrap.verified_email_of(uid)
    return table.get(email) if email else None


def is_enrolled(user_id: str) -> bool:
    return bool(_secret_for(user_id))


def _ttl() -> int:
    try:
        return max(300, int(os.environ.get("WELORA_ADMIN_2FA_TTL_S") or DEFAULT_TTL_S))
    except ValueError:
        return DEFAULT_TTL_S


def _conn():
    from welora import checkout as co

    return co._conn()


def _token_hash(token: str) -> str:
    return hashlib.sha256(("welora-admin-2fa:" + token).encode("utf-8")).hexdigest()


def verify_code(user_id: str, code: str, *, now: Optional[float] = None) -> None:
    """Raise TwoFactorError unless code is a fresh valid TOTP for user_id."""
    uid = (user_id or "").strip()
    t = time.time() if now is None else float(now)
    secret = _secret_for(uid)
    if not secret:
        raise TwoFactorError(403, "ADMIN_2FA_NOT_ENROLLED", "Tài khoản quản trị chưa cấu hình 2FA")
    c = "".join(ch for ch in str(code or "") if ch.isdigit())
    conn = _conn()
    try:
        row = conn.execute("SELECT * FROM admin_totp_state WHERE user_id=?", (uid,)).fetchone()
        if row is None:
            conn.execute(
                "INSERT INTO admin_totp_state(user_id, last_step, failed, locked_until) VALUES (?,?,?,?)",
                (uid, 0, 0, None),
            )
            conn.commit()
            last_step, failed, locked_until = 0, 0, 0.0
        else:
            last_step, failed = int(row["last_step"] or 0), int(row["failed"] or 0)
            locked_until = _ts(row["locked_until"])
        if locked_until and t < locked_until:
            raise TwoFactorError(429, "ADMIN_2FA_LOCKED", "Nhập sai quá nhiều lần — thử lại sau 15 phút")
        cur = int(t // STEP_S)
        matched: Optional[int] = None
        if len(c) == DIGITS:
            for s in range(cur - WINDOW, cur + WINDOW + 1):
                if hmac.compare_digest(_hotp(secret, s), c):
                    matched = s
                    break
        if matched is None or matched <= last_step:
            failed += 1
            lock = _iso(t + LOCK_S) if failed >= MAX_FAILED else None
            conn.execute(
                "UPDATE admin_totp_state SET failed=?, locked_until=? WHERE user_id=?",
                (0 if lock else failed, lock, uid),
            )
            conn.commit()
            reused = matched is not None
            raise TwoFactorError(
                401,
                "ADMIN_2FA_REPLAY" if reused else "ADMIN_2FA_INVALID",
                "Mã đã được dùng" if reused else "Mã 2FA không đúng",
            )
        conn.execute(
            "UPDATE admin_totp_state SET last_step=?, failed=0, locked_until=NULL WHERE user_id=?",
            (matched, uid),
        )
        conn.commit()
    finally:
        conn.close()


def open_session(user_id: str, token: str, code: str, *, now: Optional[float] = None) -> dict[str, Any]:
    t = time.time() if now is None else float(now)
    verify_code(user_id, code, now=t)
    exp = t + _ttl()
    th = _token_hash(token)
    conn = _conn()
    try:
        conn.execute("DELETE FROM admin_2fa_sessions WHERE token_hash=?", (th,))
        conn.execute(
            "INSERT INTO admin_2fa_sessions(token_hash, user_id, expires_at, created_at) VALUES (?,?,?,?)",
            (th, user_id, _iso(exp), _iso(t)),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "expires_at": _iso(exp)}


def session_valid(user_id: str, token: str, *, now: Optional[float] = None) -> bool:
    if not token or not is_enrolled(user_id):
        return False
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT user_id, expires_at FROM admin_2fa_sessions WHERE token_hash=?", (_token_hash(token),)
        ).fetchone()
    finally:
        conn.close()
    return bool(row) and row["user_id"] == user_id and _ts(row["expires_at"]) > t


def close_session(token: str) -> None:
    conn = _conn()
    try:
        conn.execute("DELETE FROM admin_2fa_sessions WHERE token_hash=?", (_token_hash(token),))
        conn.commit()
    finally:
        conn.close()


def _main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "gen":
        who = _norm_key(argv[1])
        if not who or ":" in who or "," in who:
            print("usage: python -m welora.admin_2fa gen <admin_email|admin_user_id>")
            return 2
        sec = generate_secret()
        kind = "email" if "@" in who else "user_id"
        print(f"# Add to Render env WELORA_ADMIN_TOTP_SECRETS (comma-separated {kind}:secret):")
        print(f"{who}:{sec}")
        print("# Scan in an authenticator app:")
        print(provisioning_uri(sec, who))
        return 0
    print("usage: python -m welora.admin_2fa gen <admin_email|admin_user_id>")
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
