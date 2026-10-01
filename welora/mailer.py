"""Pluggable mail sender — CK-09 receipts, mục 7 renewal reminders, admin email OTP.

Provider resolution (``mail_provider()``), first match wins:

1. ``resend`` — Resend HTTP API (HTTPS 443; works on Render Free, which blocks outbound
   SMTP). Used when ``RESEND_API_KEY`` is set and ``WELORA_MAIL_PROVIDER`` is ``resend``
   or unset/``auto``.
2. ``smtp``  — ``WELORA_SMTP_HOST`` set (STARTTLS when port 587) with
   ``WELORA_SMTP_PORT`` / ``WELORA_SMTP_USER`` / ``WELORA_SMTP_PASSWORD``.
   An explicit ``WELORA_MAIL_PROVIDER=smtp`` skips Resend even if a key is present.
3. ``log``   — log-only (no-op, recipient masked). ``WELORA_MAIL_PROVIDER=log`` forces it.

``WELORA_MAIL_PROVIDER=resend`` without ``RESEND_API_KEY`` falls back to smtp/log (a
startup-visible WARNING is logged on each send so the misconfiguration is obvious).

``WELORA_MAIL_FROM`` is the sender for every provider (Resend default when unset:
``Welora <onboarding@resend.dev>`` — testing sender, delivers only to the Resend account
owner's own address until a domain is verified).

Failures never raise and never leak secrets: the WARNING carries the provider, HTTP status /
Resend error name / exception class and the masked recipient only — never the API key, the
mail body (which may contain an OTP) or the provider's free-text error message.

Sending is dispatched off the request thread (webhook must answer < 5 s) unless
WELORA_MAIL_SYNC=1. Tests may install a capture sender via ``set_sender``.
"""

from __future__ import annotations

import logging
import os
import re
import smtplib
import threading
from email.message import EmailMessage
from typing import Callable, Optional

log = logging.getLogger("welora.mailer")

Sender = Callable[[str, str, str], None]
_custom_sender: Optional[Sender] = None

RESEND_URL = "https://api.resend.com/emails"
RESEND_TIMEOUT_S = 10.0
RESEND_DEFAULT_FROM = "Welora <onboarding@resend.dev>"
PROVIDERS = ("resend", "smtp", "log")


class MailSendError(Exception):
    """Provider rejected the message. Carries only safe, non-secret fields."""

    def __init__(self, provider: str, status: Optional[int] = None, reason: str = "") -> None:
        super().__init__(f"{provider} status={status} reason={reason}")
        self.provider = provider
        self.status = status
        self.reason = reason


def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    return (local[:1] + "***@" + domain) if local else "***@" + domain


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def mail_provider() -> str:
    """Effective provider name from env: ``resend`` | ``smtp`` | ``log`` (no secrets)."""
    choice = _env("WELORA_MAIL_PROVIDER").lower()
    if choice == "log":
        return "log"
    if choice != "smtp" and _env("RESEND_API_KEY"):
        return "resend"
    if _env("WELORA_SMTP_HOST"):
        return "smtp"
    return "log"


def _resend_send(to: str, subject: str, body: str) -> None:
    import httpx  # already a runtime dependency (requirements.txt)

    key = _env("RESEND_API_KEY")
    if not key:
        raise MailSendError("resend", None, "missing_api_key")
    payload = {
        "from": _env("WELORA_MAIL_FROM") or RESEND_DEFAULT_FROM,
        "to": [to],
        "subject": subject,
        "text": body,
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "User-Agent": "welora-mailer/1.0",
    }
    resp = httpx.post(RESEND_URL, json=payload, headers=headers, timeout=RESEND_TIMEOUT_S)
    if 200 <= resp.status_code < 300:
        return
    name = ""
    try:
        data = resp.json()
        if isinstance(data, dict):
            # only the machine-readable error name (e.g. validation_error) — the free-text
            # message may echo addresses, so it is never logged
            name = re.sub(r"[^a-z0-9_]", "", str(data.get("name") or "").lower())[:64]
    except Exception:
        pass
    raise MailSendError("resend", resp.status_code, name)


def _smtp_send(to: str, subject: str, body: str) -> None:
    host = os.environ["WELORA_SMTP_HOST"].strip()
    port = int(os.environ.get("WELORA_SMTP_PORT") or 587)
    user = os.environ.get("WELORA_SMTP_USER") or ""
    password = os.environ.get("WELORA_SMTP_PASSWORD") or ""
    sender = os.environ.get("WELORA_MAIL_FROM") or user or "no-reply@welora.local"
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(host, port, timeout=10) as s:
        if port == 587:
            s.starttls()
        if user:
            s.login(user, password)
        s.send_message(msg)


def _log_send(to: str, subject: str, body: str) -> None:
    log.info("mail (log-only, no mail provider configured) to=%s subject=%s", mask_email(to), subject)


_SENDERS: dict[str, Sender] = {"resend": _resend_send, "smtp": _smtp_send, "log": _log_send}


def set_sender(fn: Optional[Sender]) -> None:
    global _custom_sender
    _custom_sender = fn


def current_sender() -> Sender:
    if _custom_sender is not None:
        return _custom_sender
    return _SENDERS[mail_provider()]


def send(to: str, subject: str, body: str) -> bool:
    """Send now; never raises. Returns True on success, False after a masked WARNING."""
    provider = "custom" if _custom_sender is not None else mail_provider()
    if (
        provider != "resend"
        and _custom_sender is None
        and _env("WELORA_MAIL_PROVIDER").lower() == "resend"
    ):
        log.warning("mail provider=resend selected but RESEND_API_KEY is not set; using provider=%s", provider)
    try:
        current_sender()(to, subject, body)
        return True
    except MailSendError as e:
        log.warning(
            "mail send failed provider=%s status=%s error=%s to=%s",
            e.provider, e.status if e.status is not None else "-", e.reason or "-", mask_email(to),
        )
    except Exception as e:
        log.warning(
            "mail send failed provider=%s status=- error=%s to=%s", provider, type(e).__name__, mask_email(to)
        )
    return False


def enqueue(to: str, subject: str, body: str) -> None:
    if (os.environ.get("WELORA_MAIL_SYNC") or "").strip() in ("1", "true", "yes"):
        send(to, subject, body)
        return
    threading.Thread(target=send, args=(to, subject, body), daemon=True).start()
