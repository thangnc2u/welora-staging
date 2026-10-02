"""One-time codes at rest — HMAC with a server key (ticket "GP follow-up sau OTP #244 + Academy #245",
item 3). Used by every OTP the server checks: phone-OTP login (``otp_challenges.code``), the
post-register verification codes (``contact_verifications.code_hash``) and the admin e-mail OTP
(``email_otp_challenges.code_hash``).

Format: ``hmac256:<hex>`` = HMAC-SHA256(key, "<domain>:<challenge_id>:<code>"). A 6-digit code has only
10^6 values, so a plain salted SHA-256 (the previous ``sha256:`` format) can be brute-forced offline
by anyone who reads the table (backup, log of a query, read-only DB access); with the HMAC the key —
which is NOT in the database — is needed as well.

Key — ``WELORA_OTP_HMAC_KEY`` (secret, set in the Render Dashboard, ≥ 32 random characters, e.g.
``python -c "import secrets; print(secrets.token_urlsafe(48))"``). When it is not set:
* derived fallback: HMAC-SHA256 of ``WELORA_DB_URL`` (already a Dashboard secret, never stored in the
  database itself) — so staging keeps working with no new env and the codes in a DB dump still need
  a secret that is not in the dump;
* no DB URL either (local / tests): a fixed development key.
* production (WELORA_ENV=production|prod) REFUSES TO START unless the key comes from the env
  (source ``dev`` or ``derived`` → ``OtpKeyError`` in the app lifespan, so uvicorn exits with a clear
  error naming WELORA_OTP_HMAC_KEY — ticket "GP follow-up sau #246/#247" item 4). Staging / dev stay
  lenient: the derived (or dev) key + a WARNING, and /health reports ``otp_hmac_key`` = the source.
  Changing the key later only invalidates the codes open at that moment (≤ 10–60 min TTL).

Only ``hmac256:`` is accepted (item 3 of the same ticket): the pre-HMAC formats (``sha256:``,
plaintext phone rows, bare-hex admin rows) were accepted only during the #246 transition; the key is
set on staging since 02/10 ~21:59 and every such code has expired (TTL ≤ 1 h). A row still stored in
an old format simply never matches — the caller answers exactly as for a wrong code.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os

log = logging.getLogger("welora.otp_hash")

ENV = "WELORA_OTP_HMAC_KEY"
PREFIX = "hmac256:"
LEGACY_PREFIX = "sha256:"
_DEV_KEY = b"welora-dev-otp-hmac-key (local / tests only)"
MIN_KEY_LEN = 32


def key_source() -> str:
    """'env' | 'derived' (from WELORA_DB_URL) | 'dev' (no secret at all — local / tests)."""
    if (os.environ.get(ENV) or "").strip():
        return "env"
    if (os.environ.get("WELORA_DB_URL") or "").strip():
        return "derived"
    return "dev"


def _key() -> bytes:
    raw = (os.environ.get(ENV) or "").strip()
    if raw:
        return raw.encode("utf-8")
    url = (os.environ.get("WELORA_DB_URL") or "").strip()
    if url:
        return hmac.new(b"welora-otp-hmac-derived-v1", url.encode("utf-8"), hashlib.sha256).digest()
    return _DEV_KEY


class OtpKeyError(RuntimeError):
    """Production started without WELORA_OTP_HMAC_KEY."""


def require_production_key() -> None:
    """Raise ``OtpKeyError`` when WELORA_ENV=production and the key source is not ``env``."""
    from welora.auth import is_production

    src = key_source()
    if is_production() and src != "env":
        raise OtpKeyError(
            f"{ENV} is not set (OTP key source: {src}) — production refuses to start. Set a random "
            f"≥ {MIN_KEY_LEN}-char secret in the Render Dashboard, e.g. "
            "python -c \"import secrets; print(secrets.token_urlsafe(48))\"")


def startup_check() -> list[str]:
    """Problems to log at startup (CRITICAL in production, WARNING elsewhere). Never raises."""
    from welora.auth import is_production

    out: list[str] = []
    src = key_source()
    raw = (os.environ.get(ENV) or "").strip()
    if src != "env":
        out.append(f"{ENV} is not set — OTP codes use the {src} fallback key; set a random ≥ {MIN_KEY_LEN}-char secret")
    elif len(raw) < MIN_KEY_LEN:
        out.append(f"{ENV} is shorter than {MIN_KEY_LEN} characters — use a longer random secret")
    lg = log.critical if is_production() else log.warning
    for msg in out:
        lg("%s", msg)
    return out


def code_hash(domain: str, challenge_id: str, code: str) -> str:
    msg = f"{domain}:{challenge_id}:{code}".encode("utf-8")
    return PREFIX + hmac.new(_key(), msg, hashlib.sha256).hexdigest()


def legacy_hash(domain: str, challenge_id: str, code: str) -> str:
    """The pre-HMAC format (``sha256:`` of the same salted string) — no longer accepted; kept so the
    tests can store an old-format row and check it is refused."""
    return LEGACY_PREFIX + hashlib.sha256(f"{domain}:{challenge_id}:{code}".encode("utf-8")).hexdigest()


def matches(domain: str, challenge_id: str, stored: str, code: str) -> bool:
    """Constant-time check of ``code`` against a stored ``hmac256:`` value. Any other stored format
    (``sha256:``, bare hex, plaintext) → False, like a wrong code."""
    stored = str(stored or "")
    c = str(code or "").strip()
    if not stored or not c or not stored.startswith(PREFIX):
        return False
    return hmac.compare_digest(stored, code_hash(domain, challenge_id, c))
