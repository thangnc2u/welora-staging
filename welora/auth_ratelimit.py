"""P0 · rate limits for unauthenticated auth endpoints, counted in the shared DB.

Actions: ``otp_request``, ``otp_verify``, ``forgot_password``, ``register``. Each allowed attempt
records one row per scope (``target`` = normalised phone/email, ``ip`` = client IP) in
``auth_rate_events`` (migration 013). An attempt is refused (HTTP 429, Vietnamese message) when
either scope already has ``max`` rows inside the sliding window. Shared DB → limits hold across
instances and restarts. For these actions the check (count) and the record (insert) are two
statements, not one transaction, so a concurrent burst may overshoot by about the concurrency level;
``/auth/login`` (below) reserves first and does not have that gap.

Env (all optional): WELORA_RL_WINDOW_S (900), WELORA_RL_TARGET_MAX (5), WELORA_RL_IP_MAX (20),
WELORA_RL_VERIFY_TARGET_MAX (10), WELORA_RL_VERIFY_IP_MAX (40). ``register`` uses the TARGET/IP
pair (every attempt counts). A value ≤ 0 disables that limit.

``/auth/device`` (follow-up 2, item 3) is limited per client IP only — never per device_id, so a
returning guest (same device_id, a call on every page load) is never locked out by its own id:
  * ``device``      every call                  WELORA_RL_DEVICE_IP_MAX      (300 / window)
  * ``device_new``  calls creating a new guest  WELORA_RL_DEVICE_NEW_IP_MAX  (30 / window)
Normal use (re-using an existing device_id) only touches the generous ``device`` bucket; minting
many guest users from one IP hits ``device_new``.

Client-IP buckets (CoS review #239): IPv4 per address; IPv6 per /64 (``ip_bucket``), IPv4-mapped
IPv6 counts as the IPv4 address — for every action including login and /auth/device.

``verify_request`` / ``verify_confirm`` (migration 020, POST /auth/verify/request|confirm — bearer
session): per signed-in user (``user:<id>``) + client IP — WELORA_RL_VERIFY_SEND_USER_MAX (5) /
WELORA_RL_VERIFY_SEND_IP_MAX (20) and WELORA_RL_VERIFY_CONFIRM_USER_MAX (10) /
WELORA_RL_VERIFY_CONFIRM_IP_MAX (40) per window.

``event`` (client analytics POST /api/core/v1/entitlements/events): per signed-in user
(``user:<id>``), WELORA_RL_EVENT_USER_MAX (60 / window).

``/auth/login`` counts FAILED attempts only (action ``login_fail``) — partner staff share the P1–P6
demo accounts, so correct logins must never consume quota. Buckets per window:
  * ``pair``    account + client IP     WELORA_RL_LOGIN_PAIR_MAX     (10)
  * ``target``  account, all IPs        WELORA_RL_LOGIN_ACCOUNT_MAX  (50)
  * ``ip``      client IP, all accounts WELORA_RL_LOGIN_IP_MAX       (30)
"account" is the RESOLVED account (``auth.login_rate_key``): ``user:<id>`` for an existing user —
so its email and phone share one budget — else the normalised identifier used for the lookup.
A login naming both email and phone is rejected (400) before any of this.
Reserve-then-count (``login_reserve``): before the password hash runs, one row per bucket is
inserted and committed, then each bucket is counted INCLUDING in-flight reservations; over the
limit → the reservation is deleted and 429. A wrong password keeps the rows (that is the failure
record); a correct login (or a non-guess outcome such as 400/403) deletes them, and a correct login
also clears its (account, IP) pair bucket. A burst therefore cannot exceed the limit; at the exact
boundary concurrent attempts may both be refused (fail-safe), and they can simply retry.
Client IP (``client_ip``) — PR "P0 follow-up 2", item 4. Trust rules, in order:
  1. TCP peer. Unless the peer is a TRUSTED PROXY — ``TRUSTED_PROXY_RANGES`` (RFC 1918, loopback,
     IPv6 ULA, CGNAT ``100.64.0.0/10`` = Render's internal proxies) or an unparseable peer (test
     client / unix socket) — the peer IS the client and every forwarding header is ignored.
  2. Behind a trusted proxy, ``X-Forwarded-For`` is read RIGHT-TO-LEFT: trailing trusted-proxy
     hops are skipped and the first remaining valid hop (``edge``) is the address that connected
     to our proxy layer. Entries left of it were written by the client and are never used. An
     invalid entry stops the scan (everything left of it is untrusted).
  3. ``edge`` inside Cloudflare's published ranges (``CLOUDFLARE_RANGES``, override with
     WELORA_CF_IP_RANGES) → the request came through Cloudflare, which overwrites
     ``CF-Connecting-IP`` → use it, else ``True-Client-IP``, else ``edge``.
  4. ``edge`` outside Cloudflare → the client reached the origin directly (e.g. *.onrender.com):
     ``edge`` is the client; CF-Connecting-IP / True-Client-IP are spoofable there and ignored.
  5. No public hop at all (no XFF, or only trusted hops — local proxy, tests): CF-Connecting-IP →
     True-Client-IP → peer. Reaching this branch requires a peer inside the private network.
  Header values that are not valid IP addresses are skipped.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from welora.db.connection import get_connection

log = logging.getLogger("welora.auth_ratelimit")
RATE_LIMIT_MSG = "Bạn đã thử quá nhiều lần. Vui lòng thử lại sau ít phút."
ACTIONS = ("otp_request", "otp_verify", "forgot_password", "register", "device", "device_new", "event",
           "verify_request", "verify_confirm")
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
    if action == "device":  # every POST /auth/device (guest pages call it on each load) — IP only
        return 0, _env_int("WELORA_RL_DEVICE_IP_MAX", 300)
    if action == "device_new":  # POST /auth/device that would CREATE a new guest user — IP only
        return 0, _env_int("WELORA_RL_DEVICE_NEW_IP_MAX", 30)
    if action == "event":  # POST /api/core/v1/entitlements/events — per signed-in user only
        return _env_int("WELORA_RL_EVENT_USER_MAX", 60), 0
    if action == "verify_request":  # POST /auth/verify/request (send / resend) — per user + IP
        return _env_int("WELORA_RL_VERIFY_SEND_USER_MAX", 5), _env_int("WELORA_RL_VERIFY_SEND_IP_MAX", 20)
    if action == "verify_confirm":  # POST /auth/verify/confirm — per user + IP (+ 5 checks per code)
        return _env_int("WELORA_RL_VERIFY_CONFIRM_USER_MAX", 10), _env_int("WELORA_RL_VERIFY_CONFIRM_IP_MAX", 40)
    return _env_int("WELORA_RL_TARGET_MAX", 5), _env_int("WELORA_RL_IP_MAX", 20)


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")


def normalise_target(value: Optional[str]) -> str:
    raw = (value or "").strip()
    if raw.startswith("user:"):
        return raw  # resolved account / signed-in user id — opaque, case kept, never parsed as phone
    v = raw.lower()
    if not v:
        return ""
    if "@" in v:
        return "email:" + v
    from welora.phone import try_normalize

    e164 = try_normalize(v)
    if e164:
        return "phone:" + e164  # same bucket for 0900…, +84900…, 84900… (item 9)
    digits = re.sub(r"\D", "", v)
    return "phone:" + (digits or v)


def ip_bucket(ip: Optional[str]) -> str:
    """Rate-limit key for a client IP (CoS review #239). IPv4 → the address. IPv6 → its /64
    network (one subscriber / LAN typically owns a whole /64, so rotating the interface id must not
    yield fresh buckets). IPv4-mapped IPv6 (``::ffff:a.b.c.d``) → the IPv4 address. Anything
    unparseable is used verbatim (lower-cased)."""
    v = (ip or "").strip()
    if not v:
        return ""
    try:
        addr = ipaddress.ip_address(v)
    except ValueError:
        return v.lower()
    if addr.version == 6:
        if addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/64", strict=False))
    return str(addr)


def _key_hash(scope: str, key: str) -> str:
    return hashlib.sha256(f"welora-rl:{scope}:{key}".encode("utf-8")).hexdigest()


CLIENT_IP_HEADERS = ("cf-connecting-ip", "true-client-ip")

# https://www.cloudflare.com/ips-v4 + /ips-v6 (fetched 2026-10-01)
CLOUDFLARE_RANGES = (
    "173.245.48.0/20", "103.21.244.0/22", "103.22.200.0/22", "103.31.4.0/22", "141.101.64.0/18",
    "108.162.192.0/18", "190.93.240.0/20", "188.114.96.0/20", "197.234.240.0/22", "198.41.128.0/17",
    "162.158.0.0/15", "104.16.0.0/13", "104.24.0.0/14", "172.64.0.0/13", "131.0.72.0/22",
    "2400:cb00::/32", "2606:4700::/32", "2803:f800::/32", "2405:b500::/32", "2405:8100::/32",
    "2a06:98c0::/29", "2c0f:f248::/32",
)
# Explicit (not ipaddress.is_private, which also covers documentation/benchmark ranges and differs
# between Python versions): RFC 1918, loopback, CGNAT/Render, IPv6 ULA + loopback.
TRUSTED_PROXY_RANGES = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
                        "100.64.0.0/10", "fc00::/7", "::1/128")
_TRUSTED_NETS = tuple(ipaddress.ip_network(n) for n in TRUSTED_PROXY_RANGES)
_CF_CACHE: dict[str, tuple] = {}


def _cloudflare_networks() -> tuple:
    raw = (os.environ.get("WELORA_CF_IP_RANGES") or "").strip()
    if raw not in _CF_CACHE:
        items = [x.strip() for x in raw.split(",") if x.strip()] if raw else list(CLOUDFLARE_RANGES)
        nets = []
        for it in items:
            try:
                nets.append(ipaddress.ip_network(it, strict=False))
            except ValueError:
                continue
        _CF_CACHE[raw] = tuple(nets)
    return _CF_CACHE[raw]


def _valid_ip(value: Optional[str]) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    try:
        return str(ipaddress.ip_address(v))
    except ValueError:
        return ""


def is_trusted_proxy(addr: Optional[str]) -> bool:
    """Private, loopback or CGNAT 100.64.0.0/10 (Render). Unparseable/empty → trusted (tests)."""
    a = (addr or "").strip()
    if not a:
        return True
    try:
        ip = ipaddress.ip_address(a)
    except ValueError:
        return True  # e.g. "testclient" / unix socket
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return any(ip.version == n.version and ip in n for n in _TRUSTED_NETS)


_peer_is_proxy = is_trusted_proxy  # backwards-compatible alias


def is_cloudflare(addr: Optional[str]) -> bool:
    try:
        ip = ipaddress.ip_address((addr or "").strip())
    except ValueError:
        return False
    return any(ip.version == n.version and ip in n for n in _cloudflare_networks())


def _xff_edge(forwarded_for: Optional[str]) -> str:
    """Right-most X-Forwarded-For hop that is not a trusted proxy ("" if none)."""
    for raw in reversed([h.strip() for h in (forwarded_for or "").split(",") if h.strip()]):
        ip = _valid_ip(raw)
        if not ip:
            return ""  # garbage → nothing to its left can be trusted
        if not is_trusted_proxy(ip):
            return ip
    return ""


def client_ip(peer: Optional[str], forwarded_for: Optional[str] = None, *, headers=None) -> str:
    """Real client IP for rate-limit buckets (trust rules: module docstring).

    ``headers``: any mapping with case-insensitive ``.get`` (Starlette ``request.headers``) or a
    plain dict; ``forwarded_for`` is kept for callers that only have X-Forwarded-For."""
    peer = (peer or "").strip()
    if not is_trusted_proxy(peer):
        return peer
    get = lambda _k: None  # noqa: E731
    if headers is not None:
        if isinstance(headers, dict):
            low = {str(k).lower(): v for k, v in headers.items()}
            get = low.get
        else:
            get = headers.get
    if forwarded_for is None:
        forwarded_for = get("x-forwarded-for")
    edge = _xff_edge(forwarded_for)
    if edge and not is_cloudflare(edge):
        return edge  # direct to origin: Cloudflare headers would be client-forged
    for name in CLIENT_IP_HEADERS:
        ip = _valid_ip(get(name))
        if ip:
            return ip
    return edge or peer or "unknown"


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
        scopes.append(("ip", _key_hash("ip", ip_bucket(ip)), imax))
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


# --- /auth/login: failures only, reserve-then-count -------------------------------------------

def login_limits() -> dict[str, int]:
    """Failure ceilings per window: {"pair": account+IP, "target": account, "ip": client IP}."""
    return {
        "pair": _env_int("WELORA_RL_LOGIN_PAIR_MAX", 10),
        "target": _env_int("WELORA_RL_LOGIN_ACCOUNT_MAX", 50),
        "ip": _env_int("WELORA_RL_LOGIN_IP_MAX", 30),
    }


def _login_scopes(ip: Optional[str], account: Optional[str]) -> list[tuple[str, str, int]]:
    lim = login_limits()
    acc = (account or "").strip()
    ipk = ip_bucket(ip)
    out: list[tuple[str, str, int]] = []
    if acc and ipk and lim["pair"] > 0:
        out.append(("pair", _key_hash("pair", acc + "|" + ipk), lim["pair"]))
    if acc and lim["target"] > 0:
        out.append(("target", _key_hash("target", acc), lim["target"]))
    if ipk and lim["ip"] > 0:
        out.append(("ip", _key_hash("ip", ipk), lim["ip"]))
    return out


class LoginAttempt:
    """Rows reserved for one in-flight login (see module docstring)."""

    def __init__(self, event_ids: list[str], url: Optional[str]) -> None:
        self.event_ids = event_ids
        self.url = url


def _delete_events(conn, ids: list[str]) -> None:
    if ids:
        conn.execute(
            "DELETE FROM auth_rate_events WHERE event_id IN (" + ",".join("?" * len(ids)) + ")",
            tuple(ids),
        )


def login_reserve(*, ip: Optional[str], account: Optional[str], url: Optional[str] = None,
                  now: Optional[float] = None) -> LoginAttempt:
    """Insert one failure row per bucket, commit, then count. Raise RateLimited (reservation
    removed) when any bucket now holds more than its max."""
    scopes = _login_scopes(ip, account)
    if not scopes:
        return LoginAttempt([], url)
    from welora.auth import ensure_auth_schema

    ensure_auth_schema(url)
    t = time.time() if now is None else float(now)
    win = window_s()
    since = _iso(t - win)
    stamp = _iso(t)
    ids = [str(uuid.uuid4()) for _ in scopes]
    conn = get_connection(url)
    try:
        for (scope, kh, _mx), eid in zip(scopes, ids):
            conn.execute(
                "INSERT INTO auth_rate_events(event_id, action, scope, key_hash, created_at) VALUES (?,?,?,?,?)",
                (eid, LOGIN_FAIL_ACTION, scope, kh, stamp),
            )
        conn.commit()  # visible to every concurrent attempt before anyone counts
        for scope, kh, mx in scopes:
            rows = conn.execute(
                "SELECT event_id, created_at FROM auth_rate_events "
                "WHERE action=? AND scope=? AND key_hash=? AND created_at>=? ORDER BY created_at, event_id",
                (LOGIN_FAIL_ACTION, scope, kh, since),
            ).fetchall()
            if len(rows) > mx:
                _delete_events(conn, ids)
                conn.commit()
                mine = set(ids)
                others = [r["created_at"] for r in rows if r["event_id"] not in mine]
                pivot = others[len(others) - mx] if len(others) >= mx else (others[0] if others else stamp)
                raise RateLimited(datetime.fromisoformat(pivot).timestamp() + win - t)
        return LoginAttempt(ids, url)
    finally:
        conn.close()


# Post-login bookkeeping never fails the request (follow-up 2, item 10): a DB error while
# releasing / pruning / clearing is logged and swallowed. A reservation that could not be deleted
# simply counts as one failure until it leaves the sliding window (WELORA_RL_WINDOW_S) and is
# pruned later — every count is bounded by ``created_at >= now - window``, so a leaked row can
# never lock anyone out permanently.

def _safe(op: str, fn) -> None:
    try:
        fn()
    except Exception as e:  # noqa: BLE001 — swallow-and-log by design
        log.warning("auth rate-limit %s failed (ignored; row expires with the window): %s", op, type(e).__name__)


def login_commit_failure(attempt: LoginAttempt, *, now: Optional[float] = None) -> None:
    """Wrong password: the reserved rows stay as the failure record (prune old rows)."""
    if not attempt.event_ids:
        return
    t = time.time() if now is None else float(now)

    def _do() -> None:
        conn = get_connection(attempt.url)
        try:
            conn.execute("DELETE FROM auth_rate_events WHERE created_at<?", (_iso(t - max(window_s(), _PRUNE_AFTER_S)),))
            conn.commit()
        finally:
            conn.close()

    _safe("prune", _do)


def login_release(attempt: LoginAttempt) -> None:
    """Correct login / not a password guess: drop the reservation (never consumes quota)."""
    if not attempt.event_ids:
        return

    def _do() -> None:
        conn = get_connection(attempt.url)
        try:
            _delete_events(conn, attempt.event_ids)
            conn.commit()
        finally:
            conn.close()

    _safe("release", _do)
    attempt.event_ids = []


def login_clear_pair(*, ip: Optional[str], account: Optional[str], url: Optional[str] = None) -> None:
    """A successful login forgets that (account, IP) pair's failures; account/IP totals stay."""
    acc = (account or "").strip()
    ipk = ip_bucket(ip)
    if not (acc and ipk):
        return

    def _do() -> None:
        conn = get_connection(url)
        try:
            conn.execute(
                "DELETE FROM auth_rate_events WHERE action=? AND scope='pair' AND key_hash=?",
                (LOGIN_FAIL_ACTION, _key_hash("pair", acc + "|" + ipk)),
            )
            conn.commit()
        finally:
            conn.close()

    _safe("clear_pair", _do)
