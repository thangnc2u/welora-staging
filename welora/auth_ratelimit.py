"""P0 · rate limits for unauthenticated auth endpoints, counted in the shared DB.

Actions: ``otp_request``, ``otp_verify``, ``forgot_password``. Each allowed attempt records one
row per scope (``target`` = normalised phone/email, ``ip`` = client IP) in ``auth_rate_events``
(migration 013). An attempt is refused (HTTP 429, Vietnamese message) when either scope already
has ``max`` rows inside the sliding window. Shared DB → limits hold across instances and restarts;
count-then-insert is not transactional, so concurrent bursts may overshoot by a request or two.

Env (all optional): WELORA_RL_WINDOW_S (900), WELORA_RL_TARGET_MAX (5), WELORA_RL_IP_MAX (20),
WELORA_RL_VERIFY_TARGET_MAX (10), WELORA_RL_VERIFY_IP_MAX (40). A value ≤ 0 disables that limit.
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from welora.db.connection import get_connection

RATE_LIMIT_MSG = "Bạn đã thử quá nhiều lần. Vui lòng thử lại sau ít phút."
ACTIONS = ("otp_request", "otp_verify", "forgot_password")
_PRUNE_AFTER_S = 24 * 3600


class RateLimited(Exception):
    def __init__(self, retry_after: int):
        super().__init__(RATE_LIMIT_MSG)
        self.retry_after = max(1, int(retry_after))


def _env_int(key: str, default: int) -> int:
    try:
        return int(str(os.environ.get(key, "")).strip() or default)
    except ValueError:
        return default


def window_s() -> int:
    return max(1, _env_int("WELORA_RL_WINDOW_S", 900))


def limits(action: str) -> tuple[int, int]:
    """(per-target max, per-IP max) for an action."""
    if action == "otp_verify":
        return _env_int("WELORA_RL_VERIFY_TARGET_MAX", 10), _env_int("WELORA_RL_VERIFY_IP_MAX", 40)
    return _env_int("WELORA_RL_TARGET_MAX", 5), _env_int("WELORA_RL_IP_MAX", 20)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def normalise_target(value: Optional[str]) -> str:
    v = (value or "").strip().lower()
    if not v:
        return ""
    if "@" in v:
        return "email:" + v
    digits = re.sub(r"\D", "", v)
    if digits.startswith("84") and len(digits) >= 11:
        digits = "0" + digits[2:]
    return "phone:" + (digits or v)


def _key_hash(scope: str, key: str) -> str:
    return hashlib.sha256(f"welora-rl:{scope}:{key}".encode("utf-8")).hexdigest()


def client_ip(peer: Optional[str], forwarded_for: Optional[str]) -> str:
    """Peer address, or — only when the peer is a private/loopback proxy (Render's edge) — the
    first X-Forwarded-For hop. A public client therefore cannot spoof its IP bucket; behind the
    proxy a forged XFF only weakens the per-IP limit (per-target limits still apply)."""
    peer = (peer or "").strip()
    try:
        behind_proxy = not peer or ipaddress.ip_address(peer).is_private or ipaddress.ip_address(peer).is_loopback
    except ValueError:
        behind_proxy = True  # e.g. "testclient"
    if behind_proxy and forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    return peer or "unknown"


def check_and_record(action: str, *, ip: Optional[str], target: Optional[str], url: Optional[str] = None,
                     now: Optional[float] = None) -> None:
    """Raise RateLimited if over the limit; otherwise record this attempt."""
    assert action in ACTIONS, action
    from welora.auth import ensure_auth_schema

    ensure_auth_schema(url)
    t = time.time() if now is None else float(now)
    win = window_s()
    since = _iso(t - win)
    tmax, imax = limits(action)
    scopes = []
    tgt = normalise_target(target)
    if tgt and tmax > 0:
        scopes.append(("target", _key_hash("target", tgt), tmax))
    if ip and imax > 0:
        scopes.append(("ip", _key_hash("ip", ip.strip().lower()), imax))
    if not scopes:
        return
    conn = get_connection(url)
    try:
        for scope, kh, mx in scopes:
            rows = conn.execute(
                "SELECT created_at FROM auth_rate_events WHERE action=? AND scope=? AND key_hash=? AND created_at>=? "
                "ORDER BY created_at",
                (action, scope, kh, since),
            ).fetchall()
            if len(rows) >= mx:
                oldest = datetime.fromisoformat(rows[0]["created_at"]).timestamp()
                raise RateLimited(oldest + win - t)
        stamp = _iso(t)
        for scope, kh, _mx in scopes:
            conn.execute(
                "INSERT INTO auth_rate_events(event_id, action, scope, key_hash, created_at) VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), action, scope, kh, stamp),
            )
        conn.execute("DELETE FROM auth_rate_events WHERE created_at<?", (_iso(t - max(win, _PRUNE_AFTER_S)),))
        conn.commit()
    finally:
        conn.close()
