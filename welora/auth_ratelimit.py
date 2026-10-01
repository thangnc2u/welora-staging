"""P0 · rate limits for unauthenticated auth endpoints, counted in the shared DB.

Actions: ``otp_request``, ``otp_verify``, ``forgot_password``, ``login``, ``register``. Each allowed attempt records one
row per scope (``target`` = normalised phone/email, ``ip`` = client IP) in ``auth_rate_events``
(migration 013). An attempt is refused (HTTP 429, Vietnamese message) when either scope already
has ``max`` rows inside the sliding window. Shared DB → limits hold across instances and restarts;
count-then-insert is not transactional, so concurrent bursts may overshoot by a request or two.

Env (all optional): WELORA_RL_WINDOW_S (900), WELORA_RL_TARGET_MAX (5), WELORA_RL_IP_MAX (20),
WELORA_RL_VERIFY_TARGET_MAX (10), WELORA_RL_VERIFY_IP_MAX (40). ``register`` uses the TARGET/IP
pair (every attempt counts). A value ≤ 0 disables that limit.

``/auth/login`` is different (CoS review of PR #237): only FAILED attempts (HTTP 401) are recorded
(action ``login_fail``), successful logins never consume quota — partner staff share the P1–P6
demo accounts. Before the password is checked, the attempt is refused when any failure bucket in
the window is full:
  * ``pair``    account + client IP     WELORA_RL_LOGIN_PAIR_MAX     (10)
  * ``target``  account, all IPs        WELORA_RL_LOGIN_ACCOUNT_MAX  (50)
  * ``ip``      client IP, all accounts WELORA_RL_LOGIN_IP_MAX       (30)
So 10 wrong passwords from IP A lock only (account, A); the right password from IP B still works
until the account-wide threshold. A successful login clears that (account, IP) pair bucket.

Client IP (``client_ip``): CF-Connecting-IP → True-Client-IP → first X-Forwarded-For hop → TCP peer,
and the headers are honoured ONLY when the peer is a private/loopback address (the proxy). On Render
every request arrives through Cloudflare + Render's internal proxy, so the peer is always private
and the headers are always read; Cloudflare overwrites CF-Connecting-IP with the address that
connected to it, so a client cannot forge its bucket that way. X-Forwarded-For is only a fallback
(Render appends to a client-supplied XFF, so its first hop is spoofable) and True-Client-IP is
only set by Cloudflare when that zone option is on — both are consulted only when
CF-Connecting-IP is absent. Header values that are not valid IP addresses are skipped.
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
ACTIONS = ("otp_request", "otp_verify", "forgot_password", "register")
LOGIN_FAIL_ACTION = "login_fail"
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


CLIENT_IP_HEADERS = ("cf-connecting-ip", "true-client-ip")


def _valid_ip(value: Optional[str]) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    try:
        return str(ipaddress.ip_address(v))
    except ValueError:
        return ""


def _peer_is_proxy(peer: str) -> bool:
    if not peer:
        return True
    try:
        ip = ipaddress.ip_address(peer)
    except ValueError:
        return True  # e.g. "testclient" / unix socket
    return ip.is_private or ip.is_loopback


def client_ip(peer: Optional[str], forwarded_for: Optional[str] = None, *, headers=None) -> str:
    """Real client IP for rate-limit buckets (see module docstring for the trust rules).

    ``headers``: any mapping with case-insensitive ``.get`` (Starlette ``request.headers``) or a
    plain dict; ``forwarded_for`` is kept for callers that only have X-Forwarded-For."""
    peer = (peer or "").strip()
    if _peer_is_proxy(peer):
        get = None
        if headers is not None:
            low = {str(k).lower(): v for k, v in headers.items()} if isinstance(headers, dict) else None
            get = (lambda k: low.get(k)) if low is not None else (lambda k: headers.get(k))
        if get is not None:
            for name in CLIENT_IP_HEADERS:
                ip = _valid_ip(get(name))
                if ip:
                    return ip
            if forwarded_for is None:
                forwarded_for = get("x-forwarded-for")
        if forwarded_for:
            first = _valid_ip(forwarded_for.split(",")[0])
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


# --- /auth/login: failures only --------------------------------------------------------------

def login_limits() -> dict[str, int]:
    """Failure ceilings per window: {"pair": account+IP, "target": account, "ip": client IP}."""
    return {
        "pair": _env_int("WELORA_RL_LOGIN_PAIR_MAX", 10),
        "target": _env_int("WELORA_RL_LOGIN_ACCOUNT_MAX", 50),
        "ip": _env_int("WELORA_RL_LOGIN_IP_MAX", 30),
    }


def _login_scopes(ip: Optional[str], target: Optional[str]) -> list[tuple[str, str, int]]:
    lim = login_limits()
    tgt = normalise_target(target)
    ipk = (ip or "").strip().lower()
    out: list[tuple[str, str, int]] = []
    if tgt and ipk and lim["pair"] > 0:
        out.append(("pair", _key_hash("pair", tgt + "|" + ipk), lim["pair"]))
    if tgt and lim["target"] > 0:
        out.append(("target", _key_hash("target", tgt), lim["target"]))
    if ipk and lim["ip"] > 0:
        out.append(("ip", _key_hash("ip", ipk), lim["ip"]))
    return out


def login_check(*, ip: Optional[str], target: Optional[str], url: Optional[str] = None,
                now: Optional[float] = None) -> None:
    """Raise RateLimited when a login failure bucket is full. Records nothing."""
    scopes = _login_scopes(ip, target)
    if not scopes:
        return
    from welora.auth import ensure_auth_schema

    ensure_auth_schema(url)
    t = time.time() if now is None else float(now)
    win = window_s()
    since = _iso(t - win)
    conn = get_connection(url)
    try:
        for scope, kh, mx in scopes:
            rows = conn.execute(
                "SELECT created_at FROM auth_rate_events WHERE action=? AND scope=? AND key_hash=? AND created_at>=? "
                "ORDER BY created_at",
                (LOGIN_FAIL_ACTION, scope, kh, since),
            ).fetchall()
            if len(rows) >= mx:
                oldest = datetime.fromisoformat(rows[len(rows) - mx]["created_at"]).timestamp()
                raise RateLimited(oldest + win - t)
    finally:
        conn.close()


def login_record_failure(*, ip: Optional[str], target: Optional[str], url: Optional[str] = None,
                         now: Optional[float] = None) -> None:
    """One row per bucket for a failed (401) login."""
    scopes = _login_scopes(ip, target)
    if not scopes:
        return
    from welora.auth import ensure_auth_schema

    ensure_auth_schema(url)
    t = time.time() if now is None else float(now)
    stamp = _iso(t)
    conn = get_connection(url)
    try:
        for scope, kh, _mx in scopes:
            conn.execute(
                "INSERT INTO auth_rate_events(event_id, action, scope, key_hash, created_at) VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), LOGIN_FAIL_ACTION, scope, kh, stamp),
            )
        conn.execute("DELETE FROM auth_rate_events WHERE created_at<?", (_iso(t - max(window_s(), _PRUNE_AFTER_S)),))
        conn.commit()
    finally:
        conn.close()


def login_clear_pair(*, ip: Optional[str], target: Optional[str], url: Optional[str] = None) -> None:
    """A successful login forgets that (account, IP) pair's failures; account/IP totals stay."""
    tgt = normalise_target(target)
    ipk = (ip or "").strip().lower()
    if not (tgt and ipk):
        return
    conn = get_connection(url)
    try:
        conn.execute(
            "DELETE FROM auth_rate_events WHERE action=? AND scope='pair' AND key_hash=?",
            (LOGIN_FAIL_ACTION, _key_hash("pair", tgt + "|" + ipk)),
        )
        conn.commit()
    finally:
        conn.close()
