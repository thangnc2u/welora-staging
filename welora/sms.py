"""SMS delivery seam — DISABLED (ticket "Xác minh OTP sau đăng ký", migration 020).

No SMS provider is integrated yet and this module never sends a real SMS. It exists so phone codes
(phone-OTP login and the post-register phone verification) can be switched on later by env without
touching the auth flows:

* ``WELORA_SMS_PROVIDER`` — unset / ``none`` / ``off`` → disabled (default, staging + production
  today). A name is honoured only if it is registered in ``_PROVIDERS`` (empty in this release), so
  setting the env to an unknown value keeps SMS disabled and logs a warning once — it can never
  "pretend" a code was sent.
* Adding a provider later = implement ``fn(phone_e164, body) -> None`` (raise on failure), register
  it in ``_PROVIDERS`` and set the env; ``enabled()`` then turns true and the UI stops saying
  "Kênh SMS chưa bật".
* Tests install a capture sender with ``set_sender(fn)`` (fake provider — tests only).

The message body (it contains the code) is never logged; the number is masked in logs.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional

log = logging.getLogger("welora.sms")

Sender = Callable[[str, str], None]

_PROVIDERS: dict[str, Sender] = {}  # no real provider in this release
_DISABLED = ("", "none", "off", "0", "false", "disabled")
_custom_sender: Optional[Sender] = None
_warned: set[str] = set()


def mask_phone(phone: str) -> str:
    p = (phone or "").strip()
    if len(p) < 5:
        return "****"
    return p[:3] + "****" + p[-2:]


def provider() -> str:
    """Active provider name, or ``none`` (disabled)."""
    if _custom_sender is not None:
        return "test"
    name = (os.environ.get("WELORA_SMS_PROVIDER") or "").strip().lower()
    if name in _DISABLED:
        return "none"
    if name not in _PROVIDERS:
        if name not in _warned:
            _warned.add(name)
            log.warning("WELORA_SMS_PROVIDER=%r is not an implemented provider — SMS stays disabled", name)
        return "none"
    return name


def enabled() -> bool:
    return provider() != "none"


def set_sender(fn: Optional[Sender]) -> None:
    """Tests only: install (or remove with None) a capture sender — enables the SMS channel."""
    global _custom_sender
    _custom_sender = fn


def send(phone: str, body: str) -> bool:
    """Deliver synchronously; never raises. False when disabled or the provider failed."""
    name = provider()
    if name == "none":
        return False
    fn = _custom_sender if name == "test" else _PROVIDERS[name]
    try:
        fn(phone, body)  # type: ignore[misc]
        log.info("sms sent provider=%s to=%s", name, mask_phone(phone))
        return True
    except Exception as e:  # pragma: no cover - provider failure
        log.warning("sms send failed provider=%s to=%s err=%s", name, mask_phone(phone), type(e).__name__)
        return False


def enqueue(phone: str, body: str) -> bool:
    """Fire-and-forget (background thread unless WELORA_MAIL_SYNC=1, shared with the mailer).
    Returns whether a send was scheduled (False when SMS is disabled)."""
    if not enabled():
        return False
    if (os.environ.get("WELORA_MAIL_SYNC") or "").strip() in ("1", "true", "yes"):
        send(phone, body)
        return True
    threading.Thread(target=send, args=(phone, body), daemon=True).start()
    return True
