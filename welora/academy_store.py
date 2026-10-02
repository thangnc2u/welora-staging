"""GP P0b · DB side of Welorademy: persisted progress, server-held KUAT attempts, KUAT limits.

* ``academy_profiles`` (migration 017): one JSON profile per user + ``rev`` (bumped on every save)
  so another instance / a fresh process reloads it. Written only in DB-store mode
  (WELORA_STORE=sqlite|postgres or a postgres URL — same switch as goals / flags).
* ``academy_kuat_attempts`` (017 + 018 + 019): every KUAT is an attempt the server issued — which
  questions (drawn from the node's bank) and which option order it showed. At most ONE open attempt
  per user + node + ``scope_key`` (unique partial index ``uq_academy_kuat_open_scope``, migration
  019; it replaced 018's per user + node index): starting again — another tab, a reload, a parallel
  burst — returns the same open attempt. ``scope_key`` is '' for every regular account (so exactly
  one open attempt per user + node, as before); for the shared demo personas P1–P6 it is the login
  session (a hash of the bearer token, never the token) — or, without one, the client network — so
  two testers on one persona each get their own attempt and never see / consume / overwrite the
  other's (``attempt_scope``). Every read / consume / re-open of an attempt is filtered by it. Submitting consumes it atomically
  (``UPDATE … WHERE used_at IS NULL … RETURNING``; single-use) before it expires. Only the outcome
  (passed / failed / expired / superseded) is recorded — no score, no per-question correctness.
* KUAT limits reuse ``auth_rate_events`` (migration 013, same hashing / pruning as the auth limits).
  A failed-KUAT slot is RESERVED before grading (insert → commit → count, like the login limit of
  #238) and released only when the attempt passes, so parallel submits can never exceed a cap.
  Buckets (round 4: the network-wide ones apply to the GATE KUATs only — ``GATE_KUAT_NODES``,
  N02-01 + N02-02, the only KUATs on the way to the Safety Gate mastery; every other node keeps
  only the per-user limits):
    - every node: per (user, node) short window + daily cap (+ the per (user, node) start limit);
    - gate nodes, every account: per client IP over WELORA_KUAT_COOLDOWN_S and over 24 h, counted
      across both gate nodes together;
    - gate nodes, accounts that are not "verified" (device guests, register-only accounts, demo
      personas): per client IP and per gate node over 24 h (shared by all of them), plus per guest
      device id and gate node;
    - non-gate nodes (migration 019 ticket, item 3): NEW attempts per client network over
      WELORA_KUAT_NONGATE_IP_START_WINDOW_S, all accounts together — so throwaway accounts cannot
      bloat the attempt table. Gate nodes never count against it (their budgets are unchanged).
  "Guest" for these budgets (round 3) = every account WITHOUT a verified contact — device-only
  visitors AND registered accounts that never completed an OTP (see ``_identity`` /
  ``auth.has_verified_contact``). Demo personas P1–P6 (round 4: public password) are identified by
  the server seed (role ``demo`` / the seeded persona ids, never by password): their per-user
  budgets are kept per (persona, client network) so outsiders on one network cannot use up the
  persona for everybody, and they share the guest network bucket.
  The client IP is ``auth_ratelimit.client_ip`` (#239 trust rules, never a raw X-Forwarded-For),
  bucketed with ``ip_bucket`` (IPv6 → /64) for the short windows and per user; the 24 h network
  buckets group IPv6 by WELORA_KUAT_IP6_DAY_PREFIX (/56 by default — one subscriber's allocation).

Env (all optional; a value ≤ 0 disables that limit):
  WELORA_KUAT_MAX_FAILS (3) failed KUATs per user+node per WELORA_KUAT_COOLDOWN_S (1800 s)
  WELORA_KUAT_DAILY_MAX_FAILS (10) failed KUATs per user+node per 24 h
  WELORA_KUAT_IP_MAX_FAILS (30) failed gate KUATs per client IP (any account) per WELORA_KUAT_COOLDOWN_S
  WELORA_KUAT_IP_DAY_MAX_FAILS (60) failed gate KUATs per client network (any account) per 24 h
  WELORA_KUAT_GUEST_IP_MAX_FAILS (6) failed KUATs per gate node of ALL non-verified accounts (guests,
      register-only accounts, demo personas) on one client network per WELORA_KUAT_GUEST_WINDOW_S
  WELORA_KUAT_GUEST_DEVICE_MAX_FAILS (6) failed KUATs per guest device id and gate node per WELORA_KUAT_GUEST_WINDOW_S
  WELORA_KUAT_GUEST_WINDOW_S (86400) window of the two guest limits
  WELORA_KUAT_IP6_DAY_PREFIX (56) IPv6 prefix length of the 24 h network buckets (48–64; 64 = as the short windows)
  WELORA_KUAT_MAX_STARTS (30) NEW attempts issued per user+node per WELORA_KUAT_COOLDOWN_S
  WELORA_KUAT_NONGATE_IP_MAX_STARTS (300) NEW attempts on non-gate nodes per client network (IPv4
      address / IPv6 /WELORA_KUAT_IP6_DAY_PREFIX), any account, per WELORA_KUAT_NONGATE_IP_START_WINDOW_S (3600 s)
  WELORA_KUAT_ATTEMPT_TTL_S (1800) lifetime of an issued attempt
"""

from __future__ import annotations

import ipaddress
import json
import os
import time
import uuid
from datetime import datetime
from typing import Any, Optional

from welora.auth_ratelimit import _PRUNE_AFTER_S, _iso, _key_hash, _valid_ip, ip_bucket
from welora.db.connection import get_connection
from welora.db.migrate import migrate

DAY_S = 24 * 3600
# The KUATs on the way to the Safety Gate: N02-02 grants the gate mastery (academy.GATE_NODE) and
# needs N02-01 mastered first. Only these carry the network-wide (security) budgets (round 4).
GATE_KUAT_NODES = ("N02-01", "N02-02")
FAIL_ACTION = "kuat_fail"
START_ACTION = "kuat_start"


def _env_int(key: str, default: int) -> int:
    try:
        return int(str(os.environ.get(key, "")).strip() or default)
    except ValueError:
        return default


def cooldown_s() -> int:
    return max(1, _env_int("WELORA_KUAT_COOLDOWN_S", 1800))


def max_fails() -> int:
    return _env_int("WELORA_KUAT_MAX_FAILS", 3)


def daily_max_fails() -> int:
    return _env_int("WELORA_KUAT_DAILY_MAX_FAILS", 10)


def ip_max_fails() -> int:
    return _env_int("WELORA_KUAT_IP_MAX_FAILS", 30)


def ip_day_max_fails() -> int:
    return _env_int("WELORA_KUAT_IP_DAY_MAX_FAILS", 60)


def guest_ip_max_fails() -> int:
    return _env_int("WELORA_KUAT_GUEST_IP_MAX_FAILS", 6)


def guest_device_max_fails() -> int:
    return _env_int("WELORA_KUAT_GUEST_DEVICE_MAX_FAILS", 6)


def guest_window_s() -> int:
    return max(60, _env_int("WELORA_KUAT_GUEST_WINDOW_S", DAY_S))


def ip6_day_prefix() -> int:
    return min(64, max(48, _env_int("WELORA_KUAT_IP6_DAY_PREFIX", 56)))


def is_gate_node(node_id: str) -> bool:
    return node_id in GATE_KUAT_NODES


def ip_bucket_day(ip: Optional[str]) -> str:
    """Network key of the 24 h buckets: IPv6 → its /WELORA_KUAT_IP6_DAY_PREFIX (default /56 — a
    subscriber usually gets a /56, so hopping between its /64s yields no fresh day budget); IPv4 and
    IPv4-mapped IPv6 → the address (same as ``ip_bucket``)."""
    b = ip_bucket(ip)
    if "/" not in b:
        return b
    try:
        return str(ipaddress.ip_network(b, strict=False).supernet(new_prefix=ip6_day_prefix()))
    except ValueError:
        return b


def max_starts() -> int:
    return _env_int("WELORA_KUAT_MAX_STARTS", 30)


def nongate_ip_max_starts() -> int:
    return _env_int("WELORA_KUAT_NONGATE_IP_MAX_STARTS", 300)


def nongate_ip_start_window_s() -> int:
    return max(60, _env_int("WELORA_KUAT_NONGATE_IP_START_WINDOW_S", 3600))


def attempt_ttl_s() -> int:
    return max(60, _env_int("WELORA_KUAT_ATTEMPT_TTL_S", 1800))


def use_db_profiles() -> bool:
    from welora.goals_api import _use_db_store

    return _use_db_store()


class KuatCooldown(Exception):
    def __init__(self, retry_after: float, reason: str):
        super().__init__(reason)
        self.retry_after = max(1, int(retry_after + 0.999))
        self.reason = reason  # fails | daily | ip | ip_day | guest_ip | unverified_ip | demo_ip | device | unverified_device | starts | ip_starts


def _ts(iso: str) -> float:
    return datetime.fromisoformat(iso).timestamp()


def _conn():
    migrate(None)
    return get_connection(None)


# --------------------------------------------------------------------------- profiles
def load_profile(user_id: str) -> Optional[tuple[dict, int]]:
    conn = _conn()
    try:
        r = conn.execute("SELECT profile_json, rev FROM academy_profiles WHERE user_id=?", (user_id,)).fetchone()
        if not r:
            return None
        return json.loads(r["profile_json"]), int(r["rev"])
    finally:
        conn.close()


def profile_rev(user_id: str) -> Optional[int]:
    conn = _conn()
    try:
        r = conn.execute("SELECT rev FROM academy_profiles WHERE user_id=?", (user_id,)).fetchone()
        return int(r["rev"]) if r else None
    finally:
        conn.close()


def save_profile(user_id: str, profile: dict) -> int:
    body = json.dumps(profile, ensure_ascii=False, sort_keys=True)
    now = _iso(time.time())
    conn = _conn()
    try:
        conn.execute(
            "INSERT INTO academy_profiles(user_id, profile_json, rev, updated_at) VALUES (?,?,1,?) "
            "ON CONFLICT(user_id) DO UPDATE SET profile_json=excluded.profile_json, "
            "rev=academy_profiles.rev+1, updated_at=excluded.updated_at",
            (user_id, body, now),
        )
        r = conn.execute("SELECT rev FROM academy_profiles WHERE user_id=?", (user_id,)).fetchone()
        conn.commit()
        return int(r["rev"])
    finally:
        conn.close()


def save_profile_if_rev(user_id: str, profile: dict, expected_rev: Optional[int]) -> Optional[int]:
    """Optimistic write: insert when there is no row (``expected_rev`` None) or update only when the
    row still has ``expected_rev``. Returns the new rev, or None when someone else saved first."""
    body = json.dumps(profile, ensure_ascii=False, sort_keys=True)
    now = _iso(time.time())
    conn = _conn()
    try:
        if expected_rev is None:
            cur = conn.execute(
                "INSERT INTO academy_profiles(user_id, profile_json, rev, updated_at) VALUES (?,?,1,?) "
                "ON CONFLICT(user_id) DO NOTHING",
                (user_id, body, now),
            )
        else:
            cur = conn.execute(
                "UPDATE academy_profiles SET profile_json=?, rev=rev+1, updated_at=? WHERE user_id=? AND rev=?",
                (body, now, user_id, int(expected_rev)),
            )
        if not int(cur.rowcount or 0):
            conn.commit()
            return None
        r = conn.execute("SELECT rev FROM academy_profiles WHERE user_id=?", (user_id,)).fetchone()
        conn.commit()
        return int(r["rev"])
    finally:
        conn.close()


# --------------------------------------------------------------------------- limits
GUEST, UNVERIFIED, DEMO, VERIFIED = "guest", "unverified", "demo", "verified"


def demo_persona_ids() -> frozenset:
    """The user ids the server seeds for the partner demo personas P1–P6 (partner_demo_seed)."""
    from welora import partner_demo_seed as seed

    return frozenset({seed.PARTNER_USER_ID, *(a["user_id"] for a in seed.DEMO_PERSONA_ALIASES.values())})


def _identity(conn, user_id: str) -> tuple[str, Optional[str]]:
    """(kind, device_id) for the KUAT budgets:

    * ``guest`` — a device-only account (auth._is_pure_device_guest) or an unknown user id;
    * ``unverified`` — a registered ``guest``-role account WITHOUT a verified contact: no e-mail
      proven by e-mail OTP and no consumed phone-OTP challenge (``auth.has_verified_contact``).
      Register (password + e-mail/phone) alone proves nothing, so throwaway accounts land here;
    * ``demo`` (round 4) — a partner demo persona P1–P6: role ``demo`` (only the server seed sets it;
      /auth/register always creates ``guest``) or one of the seeded persona ids. Its password is
      public, so it is NOT treated as verified;
    * ``verified`` — a verified contact, or another non-``guest`` role (admin roles).
    guest + unverified + demo share the guest network bucket of the gate KUATs."""
    from welora.auth import _is_pure_device_guest, has_verified_contact, is_reserved_device_id

    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return (DEMO, None) if user_id in demo_persona_ids() else (GUEST, None)
    dev = str(row["device_id"] or "").strip() or None
    role = str(row["role"] or "guest").strip().lower()
    if role == "demo" or user_id in demo_persona_ids():
        return DEMO, None  # its device_id is an internal seed marker
    if _is_pure_device_guest(conn, row):
        return GUEST, dev
    if role != "guest" or has_verified_contact(conn, row):
        return VERIFIED, dev
    # registered but unverified: its device_id is a random internal marker (one per account), so
    # a device bucket on it would only duplicate the per-account limits — the shared guest IP
    # bucket is what binds throwaway accounts.
    return UNVERIFIED, (None if is_reserved_device_id(dev) else dev)


def _user_scope(user_id: str, node_id: str, kind: str, ipb: str) -> str:
    """Key of the per-user buckets. Demo personas (shared, public password): per (persona, node,
    client network) — fails / starts from one network never use up the persona elsewhere."""
    un = f"user:{user_id}|node:{node_id}"
    return un + f"|ip:{ipb}" if kind == DEMO and ipb else un


def _ips(ip: Optional[str]) -> tuple[str, str]:
    real_ip = _valid_ip(ip)  # a real client address only (not e.g. a test client's placeholder)
    return (ip_bucket(real_ip), ip_bucket_day(real_ip)) if real_ip else ("", "")


def _keys(conn, user_id: str, node_id: str, ip: Optional[str]) -> tuple[list[tuple[str, str, int, int]], str]:
    """((scope, key_hash, max, window) buckets a failed KUAT counts against, identity kind)."""
    kind, device = _identity(conn, user_id)
    ipb, ipd = _ips(ip)
    un = _user_scope(user_id, node_id, kind, ipb)
    out = []
    if max_fails() > 0:
        out.append(("kuat_user_node", _key_hash("kuat_user_node", un), max_fails(), cooldown_s()))
    if daily_max_fails() > 0:
        out.append(("kuat_user_node_day", _key_hash("kuat_user_node_day", un), daily_max_fails(), DAY_S))
    if not is_gate_node(node_id):
        return out, kind  # round 4: non-gate KUATs keep only the per-user limits
    if ipb and ip_max_fails() > 0:
        out.append(("kuat_ip", _key_hash("kuat_ip", ipb), ip_max_fails(), cooldown_s()))
    if ipd and ip_day_max_fails() > 0:
        out.append(("kuat_ip_day", _key_hash("kuat_ip_day", ipd), ip_day_max_fails(), DAY_S))
    if kind != VERIFIED:
        if ipd and guest_ip_max_fails() > 0:
            out.append(("kuat_guest_ip", _key_hash("kuat_guest_ip", f"{ipd}|node:{node_id}"), guest_ip_max_fails(),
                        guest_window_s()))
        if device and guest_device_max_fails() > 0:
            out.append(("kuat_guest_device", _key_hash("kuat_guest_device", f"{device}|node:{node_id}"),
                        guest_device_max_fails(), guest_window_s()))
    return out, kind


_REASON = {"kuat_user_node": "fails", "kuat_user_node_day": "daily", "kuat_ip": "ip", "kuat_ip_day": "ip_day",
           "kuat_guest_ip": "guest_ip", "kuat_guest_device": "device", "kuat_start": "starts",
           "kuat_nongate_ip_start": "ip_starts"}
_KIND_REASON = {UNVERIFIED: {"guest_ip": "unverified_ip", "device": "unverified_device"},
                DEMO: {"guest_ip": "demo_ip"}}


def _reason(scope: str, kind: str) -> str:
    r = _REASON[scope]
    return _KIND_REASON.get(kind, {}).get(r, r)


def _check(conn, action: str, buckets, now: float, kind: str = VERIFIED) -> None:
    worst = None
    for scope, kh, mx, win in buckets:
        rows = conn.execute(
            "SELECT created_at FROM auth_rate_events WHERE action=? AND scope=? AND key_hash=? AND created_at>=? "
            "ORDER BY created_at DESC",
            (action, scope, kh, _iso(now - win)),
        ).fetchall()
        if len(rows) >= mx:
            # the window frees up when the mx-th most recent event leaves it
            wait = _ts(rows[mx - 1]["created_at"]) + win - now
            if worst is None or wait > worst[0]:
                worst = (wait, _reason(scope, kind))
    if worst:
        raise KuatCooldown(*worst)


def check_kuat_allowed(user_id: str, node_id: str, ip: Optional[str] = None, *, now: Optional[float] = None) -> None:
    """Read-only pre-check (lesson / start): raise KuatCooldown while a fail bucket is full. The
    binding check is the reservation at submit time (reserve_kuat_fail)."""
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        buckets, kind = _keys(conn, user_id, node_id, ip)
        _check(conn, FAIL_ACTION, buckets, t, kind)
    finally:
        conn.close()


class FailReservation:
    """One reserved failed-KUAT slot per bucket. Keep it when the attempt fails; release() on pass
    (or when the attempt turns out to be invalid)."""

    def __init__(self, ids: list[str]) -> None:
        self.ids = ids

    def release(self) -> None:
        if not self.ids:
            return
        conn = _conn()
        try:
            _delete_events(conn, self.ids)
            conn.commit()
        finally:
            conn.close()
        self.ids = []


def _delete_events(conn, ids: list[str]) -> None:
    for eid in ids:
        conn.execute("DELETE FROM auth_rate_events WHERE event_id=?", (eid,))


def reserve_kuat_fail(user_id: str, node_id: str, ip: Optional[str] = None, *,
                      now: Optional[float] = None) -> FailReservation:
    """Atomic check-and-record: insert one fail row per bucket, COMMIT (visible to every concurrent
    submit), then count. Any bucket above its max → remove the reservation and raise KuatCooldown.
    Under concurrency every submit sees at least the reservations committed before its count, so the
    number of kept fails can never exceed a cap (at the boundary both may be refused — fail-safe)."""
    t = time.time() if now is None else float(now)
    stamp = _iso(t)
    conn = _conn()
    try:
        buckets, kind = _keys(conn, user_id, node_id, ip)
        if not buckets:
            return FailReservation([])
        ids = [str(uuid.uuid4()) for _ in buckets]
        for (scope, kh, _mx, _win), eid in zip(buckets, ids):
            conn.execute(
                "INSERT INTO auth_rate_events(event_id, action, scope, key_hash, created_at) VALUES (?,?,?,?,?)",
                (eid, FAIL_ACTION, scope, kh, stamp),
            )
        conn.execute("DELETE FROM auth_rate_events WHERE created_at<?", (_iso(t - max(DAY_S, _PRUNE_AFTER_S)),))
        conn.commit()
        mine = set(ids)
        worst = None
        for scope, kh, mx, win in buckets:
            rows = conn.execute(
                "SELECT event_id, created_at FROM auth_rate_events "
                "WHERE action=? AND scope=? AND key_hash=? AND created_at>=? ORDER BY created_at, event_id",
                (FAIL_ACTION, scope, kh, _iso(t - win)),
            ).fetchall()
            if len(rows) > mx:
                others = [r["created_at"] for r in rows if r["event_id"] not in mine]
                pivot = others[len(others) - mx] if len(others) >= mx else (others[0] if others else stamp)
                wait = _ts(pivot) + win - t
                if worst is None or wait > worst[0]:
                    worst = (wait, _reason(scope, kind))
        if worst:
            _delete_events(conn, ids)
            conn.commit()
            raise KuatCooldown(*worst)
        return FailReservation(ids)
    finally:
        conn.close()


def record_kuat_fail(user_id: str, node_id: str, ip: Optional[str] = None, *, now: Optional[float] = None) -> None:
    """Unconditionally record one failed KUAT (tests / tools). The submit path uses reserve_kuat_fail."""
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        stamp = _iso(t)
        for scope, kh, _mx, _win in _keys(conn, user_id, node_id, ip)[0]:
            conn.execute(
                "INSERT INTO auth_rate_events(event_id, action, scope, key_hash, created_at) VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), FAIL_ACTION, scope, kh, stamp),
            )
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- attempts
def _is_unique_violation(e: Exception) -> bool:
    name = type(e).__name__
    return name in ("IntegrityError", "UniqueViolation") or "unique" in str(e).lower()


def _rollback(conn) -> None:
    from welora.db.connection import in_ambient_transaction

    if not in_ambient_transaction():
        conn.rollback()


def _session_scope(session: Optional[str]) -> str:
    """Scope key of a login session: a hash of the bearer token (the token itself is never stored)."""
    tok = str(session or "").strip()
    return "s:" + _key_hash("kuat_session", tok)[:32] if tok else ""


def attempt_scope(user_id: str, *, session: Optional[str] = None, ip: Optional[str] = None) -> str:
    """``scope_key`` of the learner's open KUAT attempts (migration 019).

    * every regular account (guest, unverified, verified): '' → ONE open attempt per user + node;
    * demo personas P1–P6 (one public login shared by many testers): the login session — the hash
      of the bearer token the request carries — so each tester / browser has its own attempt; with
      no session (in-process callers) the client network (IPv4 / IPv6 /64), else ''.
    The start / fail budgets are NOT per scope: they stay per (persona, node, client network) and
    the gate network buckets (``_keys``), so opening new sessions buys no extra attempts."""
    conn = _conn()
    try:
        kind, _dev = _identity(conn, user_id)
    finally:
        conn.close()
    if kind != DEMO:
        return ""
    sc = _session_scope(session)
    if sc:
        return sc
    ipb = _ips(ip)[0]
    return "n:" + ipb if ipb else ""


def is_device_guest(user_id: str) -> bool:
    """True for a device-only guest (POST /auth/device, no login) or an unknown user id."""
    conn = _conn()
    try:
        return _identity(conn, user_id)[0] == GUEST
    finally:
        conn.close()


def _start_buckets(conn, user_id: str, node_id: str, ip: Optional[str]) -> list[tuple[str, str, int, int]]:
    """Buckets a NEW attempt counts against: per (user, node) [per (persona, node, network) for demo
    personas] and — non-gate nodes only — per client network for all accounts (item 3)."""
    out = []
    ipb, ipd = _ips(ip)
    if max_starts() > 0:
        kind, _dev = _identity(conn, user_id)
        out.append(("kuat_start", _key_hash("kuat_start", _user_scope(user_id, node_id, kind, ipb)), max_starts(),
                    cooldown_s()))
    if not is_gate_node(node_id) and ipd and nongate_ip_max_starts() > 0:
        out.append(("kuat_nongate_ip_start", _key_hash("kuat_nongate_ip_start", ipd), nongate_ip_max_starts(),
                    nongate_ip_start_window_s()))
    return out


def open_or_create_attempt(user_id: str, node_id: str, draw, *, now: Optional[float] = None,
                           ip: Optional[str] = None, scope: str = "") -> dict:
    """The learner's open attempt for this node (and ``scope`` — see ``attempt_scope``) if one is
    still valid (same questions, same option order — every tab / reload / parallel request gets the
    same one); otherwise a NEW attempt from ``draw()`` (counts against the start limits). The unique
    partial index makes a concurrent second insert fail → we return the attempt that won.
    Returns {attempt_id, expires_at, served, created}."""
    t = time.time() if now is None else float(now)
    scope = str(scope or "")
    conn = _conn()
    try:
        for _round in range(4):
            try:
                conn.execute(
                    "UPDATE academy_kuat_attempts SET used_at=?, outcome='expired' "
                    "WHERE user_id=? AND node_id=? AND used_at IS NULL AND expires_at<=?",
                    (_iso(t), user_id, node_id, _iso(t)),
                )
                r = conn.execute(
                    "SELECT attempt_id, served_json, expires_at FROM academy_kuat_attempts "
                    "WHERE user_id=? AND node_id=? AND scope_key=? AND used_at IS NULL",
                    (user_id, node_id, scope),
                ).fetchone()
                if r:
                    conn.commit()
                    return {"attempt_id": r["attempt_id"], "expires_at": r["expires_at"],
                            "served": json.loads(r["served_json"]), "created": False}
                buckets = _start_buckets(conn, user_id, node_id, ip)
                if buckets:
                    _check(conn, START_ACTION, buckets, t)
                    for scope_name, kh, _mx, _win in buckets:
                        conn.execute(
                            "INSERT INTO auth_rate_events(event_id, action, scope, key_hash, created_at) "
                            "VALUES (?,?,?,?,?)",
                            (str(uuid.uuid4()), START_ACTION, scope_name, kh, _iso(t)),
                        )
                served = draw()
                attempt_id = uuid.uuid4().hex
                expires = _iso(t + attempt_ttl_s())
                conn.execute(
                    "INSERT INTO academy_kuat_attempts(attempt_id, user_id, node_id, served_json, created_at, "
                    "expires_at, scope_key) VALUES (?,?,?,?,?,?,?)",
                    (attempt_id, user_id, node_id, json.dumps(served), _iso(t), expires, scope),
                )
                conn.execute("DELETE FROM academy_kuat_attempts WHERE created_at<?", (_iso(t - 30 * DAY_S),))
                conn.commit()
                return {"attempt_id": attempt_id, "expires_at": expires, "served": served, "created": True}
            except KuatCooldown:
                _rollback(conn)
                raise
            except Exception as e:  # a concurrent start won the unique open slot → return that one
                if not _is_unique_violation(e) or _round == 3:
                    raise
                _rollback(conn)
                time.sleep(0.01)
        raise RuntimeError("unreachable")
    finally:
        conn.close()


def latest_open_attempt_id(user_id: str, node_id: str, *, now: Optional[float] = None,
                           scope: str = "") -> Optional[str]:
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        r = conn.execute(
            "SELECT attempt_id FROM academy_kuat_attempts WHERE user_id=? AND node_id=? AND scope_key=? "
            "AND used_at IS NULL AND expires_at>? ORDER BY created_at DESC LIMIT 1",
            (user_id, node_id, str(scope or ""), _iso(t)),
        ).fetchone()
        return r["attempt_id"] if r else None
    finally:
        conn.close()


def peek_attempt(attempt_id: str, user_id: str, node_id: str, *, now: Optional[float] = None,
                 scope: str = "") -> Optional[list]:
    """What an OPEN, unexpired attempt of this user + node + scope served (read-only), else None."""
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        r = conn.execute(
            "SELECT served_json FROM academy_kuat_attempts WHERE attempt_id=? AND user_id=? AND node_id=? "
            "AND scope_key=? AND used_at IS NULL AND expires_at>?",
            (str(attempt_id or ""), user_id, node_id, str(scope or ""), _iso(t)),
        ).fetchone()
        return json.loads(r["served_json"]) if r else None
    finally:
        conn.close()


def consume_attempt(attempt_id: str, user_id: str, node_id: str, *, now: Optional[float] = None,
                    scope: str = "") -> Optional[list]:
    """Atomically mark the attempt used (single UPDATE … WHERE used_at IS NULL … RETURNING): exactly
    one concurrent submit gets what was served; the others (and unknown / someone else's / another
    demo session's / other node / expired / already used) get None."""
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        r = conn.execute(
            "UPDATE academy_kuat_attempts SET used_at=?, outcome='submitted' WHERE attempt_id=? AND user_id=? "
            "AND node_id=? AND scope_key=? AND used_at IS NULL AND expires_at>? RETURNING served_json",
            (_iso(t), str(attempt_id or ""), user_id, node_id, str(scope or ""), _iso(t)),
        ).fetchone()
        conn.commit()
        return json.loads(r["served_json"]) if r else None
    finally:
        conn.close()


def reopen_attempt(attempt_id: str, user_id: str, node_id: str, *, scope: str = "") -> None:
    """Undo a consume that was NOT graded (fail slot refused → 429): the learner keeps the attempt.
    If another open attempt (same scope) appeared meanwhile, the unique index refuses and it stays consumed."""
    conn = _conn()
    try:
        try:
            conn.execute("UPDATE academy_kuat_attempts SET used_at=NULL, outcome=NULL WHERE attempt_id=? "
                         "AND user_id=? AND node_id=? AND scope_key=? AND outcome='submitted'",
                         (attempt_id, user_id, node_id, str(scope or "")))
            conn.commit()
        except Exception as e:
            if not _is_unique_violation(e):
                raise
            _rollback(conn)
    finally:
        conn.close()


def finish_attempt(attempt_id: str, *, passed: bool) -> None:
    """Record the outcome only (pass / fail) — no score, no per-question data."""
    conn = _conn()
    try:
        conn.execute("UPDATE academy_kuat_attempts SET outcome=?, score=NULL WHERE attempt_id=?",
                     ("passed" if passed else "failed", attempt_id))
        conn.commit()
    finally:
        conn.close()
