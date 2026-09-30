"""Pluggable mail sender — CK-09 receipt email (biên nhận, không phải hoá đơn VAT).

No mail helper existed in the repo, so this is minimal and safe:
- WELORA_SMTP_HOST set → SMTP (STARTTLS when port 587) with
  WELORA_SMTP_PORT / WELORA_SMTP_USER / WELORA_SMTP_PASSWORD / WELORA_MAIL_FROM
- otherwise → log-only sender (no-op, recipient masked, no secrets)
- tests may install a capture sender via ``set_sender``.

Sending is dispatched off the request thread (webhook must answer < 5 s)
unless WELORA_MAIL_SYNC=1.
"""

from __future__ import annotations

import logging
import os
import smtplib
import threading
from email.message import EmailMessage
from typing import Callable, Optional

log = logging.getLogger("welora.mailer")

Sender = Callable[[str, str, str], None]
_custom_sender: Optional[Sender] = None


def mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    return (local[:1] + "***@" + domain) if local else "***@" + domain


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
    log.info("mail (log-only, no SMTP configured) to=%s subject=%s", mask_email(to), subject)


def set_sender(fn: Optional[Sender]) -> None:
    global _custom_sender
    _custom_sender = fn


def current_sender() -> Sender:
    if _custom_sender is not None:
        return _custom_sender
    if (os.environ.get("WELORA_SMTP_HOST") or "").strip():
        return _smtp_send
    return _log_send


def send(to: str, subject: str, body: str) -> None:
    """Send now; never raises (logs a masked warning instead)."""
    try:
        current_sender()(to, subject, body)
    except Exception as e:  # pragma: no cover - network dependent
        log.warning("mail send failed to=%s err=%s", mask_email(to), type(e).__name__)


def enqueue(to: str, subject: str, body: str) -> None:
    if (os.environ.get("WELORA_MAIL_SYNC") or "").strip() in ("1", "true", "yes"):
        send(to, subject, body)
        return
    threading.Thread(target=send, args=(to, subject, body), daemon=True).start()
