"""Pluggable push sender (PAY-05: renewal reminders via email + push only).

Sender resolution (first match wins):
1. explicit ``set_sender(fn)`` (tests / future FCM) — ``fn(user_id, title, body, data)``;
2. Web Push (``welora.webpush``) when ``WELORA_PUSH_PROVIDER=webpush`` and the
   VAPID env keys are set — encrypted per subscription, sent to the browser's
   push service;
3. log-only with the user id masked — the safe default (no env → no network).
No SMS / Zalo ZNS (PAY-05).
"""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable, Optional

log = logging.getLogger("welora.push")

PushSender = Callable[[str, str, str, dict[str, Any]], None]
_lock = threading.Lock()
_sender: Optional[PushSender] = None


def set_sender(fn: Optional[PushSender]) -> None:
    global _sender
    with _lock:
        _sender = fn


def _mask(uid: str) -> str:
    u = str(uid or "")
    return (u[:4] + "…") if len(u) > 4 else "…"


def send(user_id: str, title: str, body: str, data: Optional[dict[str, Any]] = None) -> bool:
    """Send one push. Returns True when handed to a real sender."""
    with _lock:
        fn = _sender
    if fn is None:
        from welora import webpush

        if webpush.enabled():
            try:
                return webpush.send_to_user(user_id, title, body, dict(data or {})) > 0
            except Exception as e:  # never break the renewal job on push errors
                log.warning("webpush failed user=%s err=%s", _mask(user_id), type(e).__name__)
                return False
        log.info("push (log-only, no transport) user=%s title=%s", _mask(user_id), title)
        return False
    try:
        fn(user_id, title, body, dict(data or {}))
        return True
    except Exception as e:  # never break the renewal job on push errors
        log.warning("push send failed user=%s err=%s", _mask(user_id), type(e).__name__)
        return False
