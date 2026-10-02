"""Contact verification after register — ticket "Xác minh OTP sau đăng ký + phone OTP gắn tài khoản
có sẵn" (migration 020).

Flow
* ``POST /auth/register`` (e-mail or phone + password) creates the account as before and then calls
  ``issue_after_register`` → a 6-digit verification code bound to THAT ``user_id`` (no second
  account, no lookup by identifier). E-mail goes through the existing mailer (``WELORA_MAIL_PROVIDER``
  — Resend on staging); phone through ``welora.sms`` (disabled today → no code is created, the user
  is told "Kênh SMS chưa bật" and can verify later).
* ``POST /auth/verify/request`` (resend) and ``POST /auth/verify/confirm`` take the BEARER session —
  never an e-mail / phone — so they expose no account-enumeration surface. A ``challenge_id`` that
  belongs to another user behaves exactly like an unknown one.
* Success sets ``users.email_verified_at`` / ``users.phone_verified_at`` (only if the account's
  contact still equals the code's target) → ``auth.has_verified_contact`` is true → KUAT uses the
  verified budget and the account is a valid guest-claim target.

Code at rest: ``hmac256:`` — HMAC with the server key WELORA_OTP_HMAC_KEY of a per-challenge salted
string (welora.otp_hash; codes issued before that deploy as ``sha256:`` verify until they expire) —
never stored or logged in clear, never echoed (not even with WELORA_OTP_ECHO). TTL ``WELORA_VERIFY_OTP_TTL_S`` (600 s). At most
``WELORA_VERIFY_MAX_ATTEMPTS`` (5) code checks per challenge: every check first RESERVES an attempt
with one conditional UPDATE (``attempts < max AND consumed = 0 AND not expired``), so even a
concurrent burst cannot exceed the limit; the correct code then consumes the challenge with
``UPDATE … SET consumed=1 WHERE consumed=0`` (rowcount 1 = the single winner). A new code
supersedes (``consumed=2``) the user's older open codes for the channel. Resend cooldown
``WELORA_VERIFY_RESEND_COOLDOWN_S`` (60 s); request/confirm are also rate-limited per user and per
client IP in ``auth_rate_events`` (``auth_ratelimit`` actions ``verify_request`` / ``verify_confirm``).

Who can verify: registered ``guest``-role accounts with an unverified e-mail or phone. Demo personas
(public password, own KUAT budget) and device-only guests are not offered verification; admin roles
already verify by e-mail OTP. Note: verifying an e-mail listed in WELORA_ADMIN_EMAILS proves the
mailbox exactly like the admin e-mail OTP does, so ``admin_bootstrap.startup_sync`` promotes it on
the next start (same rule as today for a verified listed address).
"""

from __future__ import annotations

import logging
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from welora.db.connection import get_connection, lock_user

log = logging.getLogger("welora.contact_verify")

CHANNELS = ("email", "phone")
OPEN, USED, SUPERSEDED = 0, 1, 2

MSG_INVALID = "Mã xác minh không đúng hoặc đã hết hạn. Vui lòng kiểm tra lại hoặc bấm «Gửi lại mã»."
MSG_TOO_MANY = "Bạn đã nhập sai quá số lần cho phép. Vui lòng bấm «Gửi lại mã» để nhận mã mới."
MSG_NOT_ELIGIBLE = "Tài khoản này không cần xác minh hoặc không có email / số điện thoại để xác minh."
MSG_ALREADY = "Email / số điện thoại của bạn đã được xác minh."
MSG_COOLDOWN = "Vui lòng chờ {s} giây trước khi gửi lại mã."
MSG_SENT_EMAIL = "Chúng tôi đã gửi mã xác minh gồm 6 chữ số tới email {target}. Vui lòng kiểm tra hộp thư (cả mục Spam)."
MSG_SENT_SMS = "Chúng tôi đã gửi mã xác minh gồm 6 chữ số qua SMS tới số {target}."
MSG_SMS_OFF = (
    "Kênh SMS hiện chưa được bật nên Welora chưa thể gửi mã xác minh tới số điện thoại {target}. "
    "Bạn vẫn sử dụng ứng dụng bình thường và có thể xác minh sau."
)
MSG_VERIFIED = "Cảm ơn bạn! Tài khoản đã được xác minh."
MSG_DAILY = "Bạn đã đạt giới hạn xác minh trong 24 giờ. Vui lòng thử lại sau {h} giờ."
ADMIN_NOTICE_SUBJECT = "Welora · Thông báo bảo mật tài khoản"
ADMIN_NOTICE_BODY = (
    "Xin chào,\n\n"
    "Có người vừa đăng ký một tài khoản khách Welora bằng địa chỉ email này. Vì đây là email quản trị, "
    "Welora không gửi mã xác minh cho tài khoản khách đó và tài khoản này sẽ không bao giờ được xác minh "
    "hay cấp quyền quản trị qua luồng đăng ký.\n\n"
    "Bạn vẫn đăng nhập quản trị như bình thường (mã OTP email quản trị + TOTP). Nếu không phải bạn đăng ký, "
    "xin vui lòng báo cho đội vận hành Welora.\n\n"
    "Trân trọng,\nWelora\n"
)
MAIL_SUBJECT = "Welora · Mã xác minh tài khoản"
MAIL_BODY = (
    "Xin chào,\n\n"
    "Mã xác minh tài khoản Welora của bạn là: {code}\n\n"
    "Mã có hiệu lực trong {minutes} phút và chỉ dùng được một lần. Vui lòng không chia sẻ mã này với bất kỳ ai, "
    "kể cả nhân viên Welora.\n\n"
    "Nếu bạn không đăng ký tài khoản Welora, xin vui lòng bỏ qua email này.\n\n"
    "Trân trọng,\nWelora\n"
)
SMS_BODY = "Welora: ma xac minh tai khoan cua ban la {code}. Hieu luc {minutes} phut. Vui long khong chia se ma nay."


class VerifyError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int = 0):
        super().__init__(message)
        self.status, self.code, self.message, self.retry_after = status, code, message, retry_after

    def body(self) -> dict[str, Any]:
        out: dict[str, Any] = {"error_code": self.code, "message": self.message}
        if self.retry_after:
            out["retry_after_s"] = self.retry_after
        return out


# --------------------------------------------------------------------------- config

def _env_int(key: str, default: int, lo: int, hi: int) -> int:
    try:
        v = int(str(os.environ.get(key, "")).strip() or default)
    except ValueError:
        v = default
    return max(lo, min(hi, v))


def ttl_s() -> int:
    return _env_int("WELORA_VERIFY_OTP_TTL_S", 600, 60, 3600)


def max_attempts() -> int:
    return _env_int("WELORA_VERIFY_MAX_ATTEMPTS", 5, 1, 10)


def resend_cooldown_s() -> int:
    return _env_int("WELORA_VERIFY_RESEND_COOLDOWN_S", 60, 0, 900)


DAY_S = 24 * 3600


def daily_send_max() -> int:
    """Codes per user per rolling 24 h (register-issued included). 0 disables."""
    return _env_int("WELORA_VERIFY_DAILY_SEND_MAX", 10, 0, 1000)


def daily_fail_max() -> int:
    """Wrong code checks per user per rolling 24 h, across all its codes. 0 disables."""
    return _env_int("WELORA_VERIFY_DAILY_FAIL_MAX", 30, 0, 10000)


# --------------------------------------------------------------------------- migration 020 (SQLite)

def _has_column(conn: Any, dialect: str, table: str, column: str) -> bool:
    if dialect == "sqlite":
        return any(str(r["name"]) == column for r in conn.execute(f"PRAGMA table_info({table})").fetchall())
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() "
        "AND table_name = ? AND column_name = ?",
        (table, column),
    ).fetchone()
    return row is not None


# Round 2 (R2): at most ONE open code per user + channel. Older duplicates (if any) are superseded
# first so the unique index can always be created; both statements are idempotent.
_DEDUP_OPEN_SQL = (
    "UPDATE contact_verifications SET consumed=2 WHERE consumed=0 AND EXISTS ("
    "SELECT 1 FROM contact_verifications n WHERE n.user_id=contact_verifications.user_id "
    "AND n.channel=contact_verifications.channel AND n.consumed=0 AND (n.created_at>contact_verifications.created_at "
    "OR (n.created_at=contact_verifications.created_at AND n.challenge_id>contact_verifications.challenge_id)))"
)
_OPEN_UNIQUE_SQL = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_contact_verif_open ON contact_verifications(user_id, channel) "
    "WHERE consumed=0"
)


def apply_contact_verification_schema(conn: Any, dialect: str = "sqlite") -> dict[str, Any]:
    """Migration 020 as an idempotent data step (SQLite; PostgreSQL runs the SQL file and records the
    same version, so this step is skipped there — it is safe on both dialects anyway)."""
    added = False
    if not _has_column(conn, dialect, "users", "phone_verified_at"):
        conn.execute("ALTER TABLE users ADD COLUMN phone_verified_at TEXT")
        added = True
    conn.execute(
        "CREATE TABLE IF NOT EXISTS contact_verifications ("
        " challenge_id TEXT PRIMARY KEY,"
        " user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,"
        " channel TEXT NOT NULL CHECK (channel IN ('email', 'phone')),"
        " target TEXT NOT NULL,"
        " code_hash TEXT NOT NULL,"
        " attempts INTEGER NOT NULL DEFAULT 0,"
        " consumed INTEGER NOT NULL DEFAULT 0,"
        " created_at TEXT NOT NULL,"
        " expires_at TEXT NOT NULL)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_contact_verif_user ON contact_verifications(user_id, created_at)")
    conn.execute(_DEDUP_OPEN_SQL)
    conn.execute(_OPEN_UNIQUE_SQL)
    conn.commit()
    return {"phone_verified_at_added": added}


def apply_verify_snooze_schema(conn: Any, dialect: str = "sqlite") -> dict[str, Any]:
    """Migration 021 (follow-up item 2) as an idempotent data step: users.verify_snooze_until."""
    added = False
    if not _has_column(conn, dialect, "users", "verify_snooze_until"):
        conn.execute("ALTER TABLE users ADD COLUMN verify_snooze_until TEXT")
        added = True
    conn.commit()
    return {"verify_snooze_until_added": added}


# --------------------------------------------------------------------------- helpers

def _iso(ts: float) -> str:
    # fixed-width UTC → lexicographic order == time order (used in SQL comparisons)
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def _ts(raw: Any) -> float:
    try:
        d = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return 0.0
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.timestamp()


_DOMAIN = "welora-contact-verify"


def _code_hash(challenge_id: str, code: str) -> str:
    """HMAC with the server key (``hmac256:``, welora.otp_hash — follow-up item 3)."""
    from welora import otp_hash

    return otp_hash.code_hash(_DOMAIN, challenge_id, code)


def _code_matches(challenge_id: str, stored: str, code: str) -> bool:
    """Current ``hmac256:`` codes, and ``sha256:`` codes issued before the HMAC deploy (until they
    expire — TTL ≤ 1 h, same attempt limits)."""
    from welora import otp_hash

    return otp_hash.matches(_DOMAIN, challenge_id, stored, code)


def _clean_code(code: Any) -> str:
    return "".join(ch for ch in str(code or "") if ch.isdigit())[:12]


def _mask(channel: str, target: str) -> str:
    if channel == "email":
        from welora.mailer import mask_email

        return mask_email(target)
    from welora.auth import _mask_phone

    return _mask_phone(target)


def _user(conn, uid: str):
    return conn.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()


def _set(v: Any) -> bool:
    return bool(str(v or "").strip())


def _contacts(row) -> dict[str, Optional[str]]:
    """channel → normalised target the account holds (None when absent)."""
    from welora.phone import try_normalize

    email = str(row["email"] or "").strip().lower() or None
    ph = str(row["phone"] or "").strip()
    return {"email": email, "phone": (try_normalize(ph) or ph or None) if ph else None}


def eligible(conn, row) -> bool:
    """Registered guest-role account with an e-mail or phone (not demo / admin / device guest)."""
    from welora.auth import _is_pure_device_guest

    if row is None:
        return False
    role = str(row["role"] or "guest").strip().lower()
    if role != "guest" or _is_pure_device_guest(conn, row):
        return False
    c = _contacts(row)
    return bool(c["email"] or c["phone"])


def _unverified_channels(row) -> list[str]:
    c = _contacts(row)
    out = []
    if c["email"] and not _set(row["email_verified_at"]):
        out.append("email")
    if c["phone"] and not _set(row["phone_verified_at"]):
        out.append("phone")
    return out


def _admin_listed(channel: str, target: str) -> bool:
    """PR #244 round 2 (R1): an e-mail in WELORA_ADMIN_EMAILS is NEVER verified by this flow —
    admin stays e-mail OTP (admin_bootstrap) + TOTP only. Otherwise registering a not-yet-existing
    admin address and guessing the code would let admin_bootstrap.startup_sync promote it."""
    if channel != "email":
        return False
    from welora import admin_bootstrap

    return admin_bootstrap.is_listed(target)


def _since(t: float) -> str:
    return _iso(t - DAY_S)


def _daily_sends(conn, uid: str, t: float) -> list:
    return conn.execute(
        "SELECT created_at FROM contact_verifications WHERE user_id=? AND created_at>=? ORDER BY created_at",
        (uid, _since(t)),
    ).fetchall()


def _daily_fails(conn, uid: str, t: float) -> tuple[int, float]:
    """(wrong checks in the last 24 h, retry-after seconds). Every check reserves one attempt; the
    successful check of a used code is the only non-wrong one. Codes live ≤ 1 h, so every attempt of
    a row happened within ~1 h of its created_at — counting rows created in the window is exact up
    to that hour."""
    rows = conn.execute(
        "SELECT created_at, attempts, consumed FROM contact_verifications WHERE user_id=? AND created_at>=? "
        "ORDER BY created_at",
        (uid, _since(t)),
    ).fetchall()
    wrong = sum(int(r["attempts"] or 0) - (1 if int(r["consumed"] or 0) == USED else 0) for r in rows)
    oldest = next((_ts(r["created_at"]) for r in rows if int(r["attempts"] or 0) > 0), t)
    return max(0, wrong), max(1.0, oldest + DAY_S - t)


def _daily_error(retry_after: float) -> "VerifyError":
    s = int(retry_after) + 1
    return VerifyError(429, "VERIFY_DAILY_LIMIT", MSG_DAILY.format(h=max(1, (s + 3599) // 3600)), retry_after=s)


def _is_unique_violation(exc: BaseException) -> bool:
    from welora.auth import _is_unique_violation as uv

    return uv(exc)


def _deliverable(channel: str) -> bool:
    if channel == "email":
        return True
    from welora import sms

    return sms.enabled()


# --- follow-up item 2: «Để sau» per user on the server (was localStorage only) -------------------
SNOOZE_S = 24 * 3600


def _snoozed_until(row, t: float) -> Optional[str]:
    try:
        raw = row["verify_snooze_until"]
    except (IndexError, KeyError):  # pragma: no cover - before migration 021
        return None
    return str(raw) if raw and _ts(raw) > t else None


def snooze(uid: str, *, now: Optional[float] = None, url: Optional[str] = None) -> dict[str, Any]:
    """«Để sau»: hide the reminder for 24 h for this ACCOUNT (every device / browser). Only the
    signed-in account's own row; a new press restarts the 24 h."""
    t = time.time() if now is None else float(now)
    until = _iso(t + SNOOZE_S)
    conn = get_connection(url)
    try:
        conn.execute("UPDATE users SET verify_snooze_until=? WHERE user_id=?", (until, uid))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "verify_snoozed": True, "verify_snoozed_until": until, "snooze_s": SNOOZE_S}


def flags(conn, row) -> dict[str, Any]:
    """Verification flags for /auth/me and the FE banner (booleans only, no PII beyond the row)."""
    from welora.auth import has_verified_contact
    from welora import sms

    ok = eligible(conn, row)
    pending = _unverified_channels(row) if ok else []
    until = _snoozed_until(row, time.time()) if row is not None else None
    return {
        "verify_snoozed": bool(until),
        "verify_snoozed_until": until,
        "verified": bool(row is not None and has_verified_contact(conn, row)),
        "email_verified": bool(row is not None and _set(row["email"]) and _set(row["email_verified_at"])),
        "phone_verified": bool(row is not None and _set(row["phone"]) and _set(row["phone_verified_at"])),
        "verify_eligible": ok,
        "verify_channels": pending,
        "can_verify_now": any(_deliverable(ch) for ch in pending),
        "sms_enabled": sms.enabled(),
    }


def _latest_open(conn, uid: str, channel: Optional[str] = None):
    q = "SELECT * FROM contact_verifications WHERE user_id=? AND consumed=0"
    args: list[Any] = [uid]
    if channel:
        q += " AND channel=?"
        args.append(channel)
    q += " ORDER BY created_at DESC, challenge_id DESC LIMIT 1"
    return conn.execute(q, tuple(args)).fetchone()


def _public(ch, *, now: float, delivery: str, message: str) -> dict[str, Any]:
    from welora import sms

    cd = resend_cooldown_s()
    return {
        "challenge_id": ch["challenge_id"],
        "channel": ch["channel"],
        "target_masked": _mask(ch["channel"], ch["target"]),
        "expires_at": ch["expires_at"],
        "delivery": delivery,
        "sms_enabled": sms.enabled(),
        "resend_after_s": max(0, int(round(_ts(ch["created_at"]) + cd - now))),
        "max_attempts": max_attempts(),
        "attempts_left": max(0, max_attempts() - int(ch["attempts"] or 0)),
        "message": message,
    }


def _deliver(channel: str, target: str, code: str) -> str:
    minutes = max(1, ttl_s() // 60)
    if channel == "email":
        from welora import mailer

        mailer.enqueue(target, MAIL_SUBJECT, MAIL_BODY.format(code=code, minutes=minutes))
        return "email"
    from welora import sms

    return "sms" if sms.enqueue(target, SMS_BODY.format(code=code, minutes=minutes)) else "none"


# --------------------------------------------------------------------------- issue / status / confirm

def issue(uid: str, channel: Optional[str] = None, *, now: Optional[float] = None,
          enforce_cooldown: bool = True, url: Optional[str] = None) -> dict[str, Any]:
    """Create (and deliver) a verification code for the signed-in account. Raises VerifyError."""
    t = time.time() if now is None else float(now)
    want = (channel or "").strip().lower() or None
    if want and want not in CHANNELS:
        raise VerifyError(400, "VERIFY_CHANNEL_INVALID", "Kênh xác minh không hợp lệ (email hoặc phone).")
    conn = get_connection(url)
    try:
        row = _user(conn, uid)
        if not eligible(conn, row):
            raise VerifyError(400, "VERIFY_NOT_ELIGIBLE", MSG_NOT_ELIGIBLE)
        pending = _unverified_channels(row)
        if not pending:
            raise VerifyError(409, "ALREADY_VERIFIED", MSG_ALREADY)
        if want and want not in pending:
            raise VerifyError(409, "ALREADY_VERIFIED", MSG_ALREADY) if _contacts(row)[want] else \
                VerifyError(400, "VERIFY_CHANNEL_INVALID", "Tài khoản chưa có " + ("email." if want == "email" else "số điện thoại."))
        ch = want or (pending[0] if "email" not in pending else "email")
        target = _contacts(row)[ch] or ""
        if ch == "phone":
            from welora.phone import phone_conflicted, PHONE_CONFLICT_MSG

            if target.startswith("+") and phone_conflicted(conn, target):
                raise VerifyError(409, "PHONE_CONFLICT_USE_EMAIL", PHONE_CONFLICT_MSG)
            if not _deliverable("phone"):
                from welora import sms

                return {"challenge_id": None, "channel": "phone", "target_masked": _mask("phone", target),
                        "expires_at": None, "delivery": "none", "sms_enabled": sms.enabled(),
                        "resend_after_s": 0, "max_attempts": max_attempts(), "attempts_left": 0,
                        "message": MSG_SMS_OFF.format(target=_mask("phone", target))}
        # per-user lock for the rest of this transaction (follow-up item 8: a real lock — PG advisory
        # xact lock / SQLite BEGIN IMMEDIATE, welora.db.connection.lock_user): concurrent sends for
        # one account run one after another, so the cooldown / daily checks below see the code a
        # parallel request just created. The unique index is the backstop.
        lock_user(conn, uid)
        prev = _latest_open(conn, uid, ch)
        if enforce_cooldown and prev is not None:
            wait = int(round(_ts(prev["created_at"]) + resend_cooldown_s() - t))
            if wait > 0:
                raise VerifyError(429, "VERIFY_RESEND_COOLDOWN", MSG_COOLDOWN.format(s=wait), retry_after=wait)
        if daily_send_max() > 0:
            sends = _daily_sends(conn, uid, t)
            if len(sends) >= daily_send_max():
                raise _daily_error(_ts(sends[0]["created_at"]) + DAY_S - t)
        cid = str(uuid.uuid4())
        code = f"{secrets.randbelow(1_000_000):06d}"
        conn.execute("UPDATE contact_verifications SET consumed=? WHERE user_id=? AND channel=? AND consumed=0",
                     (SUPERSEDED, uid, ch))
        try:
            # uq_contact_verif_open (user_id, channel) WHERE consumed=0 — of two parallel resends only
            # one INSERT succeeds; the other is refused like a cooldown (no second code, no mail)
            conn.execute(
                "INSERT INTO contact_verifications(challenge_id, user_id, channel, target, code_hash, attempts, "
                "consumed, created_at, expires_at) VALUES (?,?,?,?,?,0,0,?,?)",
                (cid, uid, ch, target, _code_hash(cid, code), _iso(t), _iso(t + ttl_s())),
            )
            conn.commit()
        except Exception as e:
            if not _is_unique_violation(e):
                raise
            conn.rollback()
            wait = max(1, resend_cooldown_s())
            raise VerifyError(429, "VERIFY_RESEND_COOLDOWN", MSG_COOLDOWN.format(s=wait), retry_after=wait)
        created = conn.execute("SELECT * FROM contact_verifications WHERE challenge_id=?", (cid,)).fetchone()
    finally:
        conn.close()
    if _admin_listed(ch, target):
        # same response shape / status as any e-mail (no enumeration of the admin list), but the code
        # is never sent and can never verify (confirm refuses it); the mailbox owner gets a notice
        from welora import mailer

        mailer.enqueue(target, ADMIN_NOTICE_SUBJECT, ADMIN_NOTICE_BODY)
        delivery = "email"
        log.warning("verification refused for an admin-listed e-mail user=%s", uid[:8])
    else:
        delivery = _deliver(ch, target, code)
    log.info("verification code issued user=%s channel=%s to=%s", uid[:8], ch, _mask(ch, target))
    msg = (MSG_SENT_EMAIL if ch == "email" else MSG_SENT_SMS).format(target=_mask(ch, target))
    return _public(created, now=t, delivery=delivery, message=msg)


def issue_after_register(uid: str, *, url: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Called right after a successful register. Never raises (registration already succeeded)."""
    try:
        return issue(uid, enforce_cooldown=False, url=url)
    except VerifyError as e:
        return {"challenge_id": None, "delivery": "none", "error_code": e.code, "message": e.message}
    except Exception as e:  # pragma: no cover - never break register
        log.warning("verification issue after register failed: %s", type(e).__name__)
        return None


def status(uid: str, *, now: Optional[float] = None, url: Optional[str] = None) -> dict[str, Any]:
    t = time.time() if now is None else float(now)
    conn = get_connection(url)
    try:
        row = _user(conn, uid)
        out = flags(conn, row)
        c = _contacts(row) if row is not None else {"email": None, "phone": None}
        out["email_masked"] = _mask("email", c["email"]) if c["email"] else None
        out["phone_masked"] = _mask("phone", c["phone"]) if c["phone"] else None
        out["pending"] = None
        if out["verify_eligible"]:
            ch = _latest_open(conn, uid)
            if ch is not None and _ts(ch["expires_at"]) > t and int(ch["attempts"] or 0) < max_attempts() \
                    and ch["channel"] in out["verify_channels"]:
                out["pending"] = _public(ch, now=t, delivery="email" if ch["channel"] == "email" else "sms", message="")
        return out
    finally:
        conn.close()


def confirm(uid: str, code: Any, challenge_id: Optional[str] = None, *, now: Optional[float] = None,
            url: Optional[str] = None) -> dict[str, Any]:
    """Check a verification code of the signed-in account. Raises VerifyError (generic VI message)."""
    t = time.time() if now is None else float(now)
    c = _clean_code(code)
    cid_in = (challenge_id or "").strip()
    bad = VerifyError(400, "VERIFY_CODE_INVALID", MSG_INVALID)
    conn = get_connection(url)
    try:
        if cid_in:
            # a challenge of ANOTHER user is indistinguishable from an unknown one
            ch = conn.execute("SELECT * FROM contact_verifications WHERE challenge_id=? AND user_id=?",
                              (cid_in, uid)).fetchone()
        else:
            ch = _latest_open(conn, uid)
        if ch is None or not c:
            raise bad
        cid = ch["challenge_id"]
        # follow-up item 7: the daily wrong-code cap RESERVES its slot atomically — the per-user lock
        # (item 8) is taken BEFORE the 24 h count and held until the attempt below is reserved and
        # committed, so concurrent checks of one account are counted one after another and a burst
        # can never exceed WELORA_VERIFY_DAILY_FAIL_MAX (every check reserves one attempt; the one
        # successful check of a used code is the only non-wrong one).
        lock_user(conn, uid)
        if daily_fail_max() > 0:
            wrong, retry = _daily_fails(conn, uid, t)
            if wrong >= daily_fail_max():
                conn.rollback()
                raise _daily_error(retry)
        # reserve one attempt atomically: the per-code limit holds even for a concurrent burst
        cur = conn.execute(
            "UPDATE contact_verifications SET attempts=attempts+1 "
            "WHERE challenge_id=? AND consumed=0 AND attempts<? AND expires_at>?",
            (cid, max_attempts(), _iso(t)),
        )
        conn.commit()
        if int(cur.rowcount or 0) != 1:
            again = conn.execute("SELECT consumed, attempts, expires_at FROM contact_verifications WHERE challenge_id=?",
                                 (cid,)).fetchone()
            if again is not None and int(again["consumed"] or 0) == OPEN and _ts(again["expires_at"]) > t \
                    and int(again["attempts"] or 0) >= max_attempts():
                raise VerifyError(429, "VERIFY_TOO_MANY_ATTEMPTS", MSG_TOO_MANY)
            raise bad
        listed = _admin_listed(str(ch["channel"]), str(ch["target"]))  # R1: never verifiable
        if listed or not _code_matches(cid, str(ch["code_hash"] or ""), c):
            left = max(0, max_attempts() - int(ch["attempts"] or 0) - 1)
            if left == 0:
                raise VerifyError(429, "VERIFY_TOO_MANY_ATTEMPTS", MSG_TOO_MANY)
            raise VerifyError(400, "VERIFY_CODE_INVALID", MSG_INVALID + f" (còn {left} lần thử)")
        cur = conn.execute("UPDATE contact_verifications SET consumed=? WHERE challenge_id=? AND consumed=0",
                           (USED, cid))
        if int(cur.rowcount or 0) != 1:
            conn.rollback()
            raise bad  # a concurrent request with the same code won
        stamp = _iso(t)
        if ch["channel"] == "email":
            if _admin_listed("email", str(ch["target"])):  # belt and braces (R1)
                conn.rollback()
                raise bad
            cur = conn.execute(
                "UPDATE users SET email_verified_at=COALESCE(NULLIF(email_verified_at,''), ?) "
                "WHERE user_id=? AND LOWER(email)=?",
                (stamp, uid, str(ch["target"]).lower()),
            )
        else:
            from welora.phone import PHONE_CONFLICT_MSG, lookup_candidates, phone_conflicted

            target = str(ch["target"])
            if target.startswith("+") and phone_conflicted(conn, target):
                conn.rollback()
                raise VerifyError(409, "PHONE_CONFLICT_USE_EMAIL", PHONE_CONFLICT_MSG)
            cands = lookup_candidates(target) if target.startswith("+") else [target]
            cur = conn.execute(
                "UPDATE users SET phone=?, phone_verified_at=COALESCE(NULLIF(phone_verified_at,''), ?) "
                "WHERE user_id=? AND phone IN (" + ",".join("?" * len(cands)) + ")",
                (target, stamp, uid, *cands),
            )
        if int(cur.rowcount or 0) != 1:
            conn.rollback()
            raise bad  # the account's contact changed since the code was sent
        conn.commit()
        row = _user(conn, uid)
        out = {"ok": True, "channel": ch["channel"], "message": MSG_VERIFIED}
        out.update(flags(conn, row))
    finally:
        conn.close()
    log.info("contact verified user=%s channel=%s", uid[:8], ch["channel"])
    return out
