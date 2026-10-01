"""GP P0b · DB side of Welorademy: persisted progress, server-held KUAT attempts, KUAT limits.

* ``academy_profiles`` (migration 017): one JSON profile per user + ``rev`` (bumped on every save)
  so another instance / a fresh process reloads it. Written only in DB-store mode
  (WELORA_STORE=sqlite|postgres or a postgres URL — same switch as goals / flags).
* ``academy_kuat_attempts`` (017 + 018): every KUAT is an attempt the server issued — which questions
  (drawn from the node's bank) and which option order it showed. At most ONE open attempt per
  user + node (unique partial index, migration 018): starting again — another tab, a reload, a
  parallel burst — returns the same open attempt. Submitting consumes it atomically
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
      device id and gate node.
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


def attempt_ttl_s() -> int:
    return max(60, _env_int("WELORA_KUAT_ATTEMPT_TTL_S", 1800))


def use_db_profiles() -> bool:
    from welora.goals_api import _use_db_store

    return _use_db_store()


class KuatCooldown(Exception):
    def __init__(self, retry_after: float, reason: str):
        super().__init__(reason)
        self.retry_after = max(1, int(retry_after + 0.999))
        self.reason = reason  # fails | daily | ip | ip_day | guest_ip | unverified_ip | demo_ip | device | unverified_device | starts


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
           "kuat_guest_ip": "guest_ip", "kuat_guest_device": "device", "kuat_start": "starts"}
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


def open_or_create_attempt(user_id: str, node_id: str, draw, *, now: Optional[float] = None,
                           ip: Optional[str] = None) -> dict:
    """The learner's open attempt for this node if one is still valid (same questions, same option
    order — every tab / reload / parallel request gets the same one); otherwise a NEW attempt from
    ``draw()`` (counts against the start limit). The unique partial index makes a concurrent second
    insert fail → we return the attempt that won. Returns {attempt_id, expires_at, served, created}."""
    t = time.time() if now is None else float(now)
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
                    "WHERE user_id=? AND node_id=? AND used_at IS NULL",
                    (user_id, node_id),
                ).fetchone()
                if r:
                    conn.commit()
                    return {"attempt_id": r["attempt_id"], "expires_at": r["expires_at"],
                            "served": json.loads(r["served_json"]), "created": False}
                if max_starts() > 0:
                    kind, _dev = _identity(conn, user_id)
                    kh = _key_hash("kuat_start", _user_scope(user_id, node_id, kind, _ips(ip)[0]))
                    _check(conn, START_ACTION, [("kuat_start", kh, max_starts(), cooldown_s())], t)
                    conn.execute(
                        "INSERT INTO auth_rate_events(event_id, action, scope, key_hash, created_at) VALUES (?,?,?,?,?)",
                        (str(uuid.uuid4()), START_ACTION, "kuat_start", kh, _iso(t)),
                    )
                served = draw()
                attempt_id = uuid.uuid4().hex
                expires = _iso(t + attempt_ttl_s())
                conn.execute(
                    "INSERT INTO academy_kuat_attempts(attempt_id, user_id, node_id, served_json, created_at, expires_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (attempt_id, user_id, node_id, json.dumps(served), _iso(t), expires),
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


def latest_open_attempt_id(user_id: str, node_id: str, *, now: Optional[float] = None) -> Optional[str]:
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        r = conn.execute(
            "SELECT attempt_id FROM academy_kuat_attempts WHERE user_id=? AND node_id=? AND used_at IS NULL "
            "AND expires_at>? ORDER BY created_at DESC LIMIT 1",
            (user_id, node_id, _iso(t)),
        ).fetchone()
        return r["attempt_id"] if r else None
    finally:
        conn.close()


def peek_attempt(attempt_id: str, user_id: str, node_id: str, *, now: Optional[float] = None) -> Optional[list]:
    """What an OPEN, unexpired attempt of this user + node served (read-only), else None."""
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        r = conn.execute(
            "SELECT served_json FROM academy_kuat_attempts WHERE attempt_id=? AND user_id=? AND node_id=? "
            "AND used_at IS NULL AND expires_at>?",
            (str(attempt_id or ""), user_id, node_id, _iso(t)),
        ).fetchone()
        return json.loads(r["served_json"]) if r else None
    finally:
        conn.close()


def consume_attempt(attempt_id: str, user_id: str, node_id: str, *, now: Optional[float] = None) -> Optional[list]:
    """Atomically mark the attempt used (single UPDATE … WHERE used_at IS NULL … RETURNING): exactly
    one concurrent submit gets what was served; the others (and unknown / someone else's / other
    node / expired / already used) get None."""
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        r = conn.execute(
            "UPDATE academy_kuat_attempts SET used_at=?, outcome='submitted' WHERE attempt_id=? AND user_id=? "
            "AND node_id=? AND used_at IS NULL AND expires_at>? RETURNING served_json",
            (_iso(t), str(attempt_id or ""), user_id, node_id, _iso(t)),
        ).fetchone()
        conn.commit()
        return json.loads(r["served_json"]) if r else None
    finally:
        conn.close()


def reopen_attempt(attempt_id: str, user_id: str, node_id: str) -> None:
    """Undo a consume that was NOT graded (fail slot refused → 429): the learner keeps the attempt.
    If another open attempt appeared meanwhile, the unique index refuses and it stays consumed."""
    conn = _conn()
    try:
        try:
            conn.execute("UPDATE academy_kuat_attempts SET used_at=NULL, outcome=NULL WHERE attempt_id=? "
                         "AND user_id=? AND node_id=? AND outcome='submitted'", (attempt_id, user_id, node_id))
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
