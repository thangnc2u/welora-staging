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
  Buckets: per (user, node) short window + daily cap; per client IP (all accounts — shared NAT)
  over WELORA_KUAT_COOLDOWN_S AND over 24 h (round 3: throwaway accounts); for guests additionally
  per IP across ALL guests and per device id, over 24 h. "Guest" for these budgets (round 3) =
  every account WITHOUT a verified contact — device-only visitors AND registered accounts that
  never completed an OTP (see ``_identity`` / ``auth.has_verified_contact``).
  The client IP is ``auth_ratelimit.client_ip`` (#239 trust rules, never a raw X-Forwarded-For),
  bucketed with ``ip_bucket`` (IPv6 → /64).

Env (all optional; a value ≤ 0 disables that limit):
  WELORA_KUAT_MAX_FAILS (3) failed KUATs per user+node per WELORA_KUAT_COOLDOWN_S (1800 s)
  WELORA_KUAT_DAILY_MAX_FAILS (10) failed KUATs per user+node per 24 h
  WELORA_KUAT_IP_MAX_FAILS (30) failed KUATs per client IP (any account) per WELORA_KUAT_COOLDOWN_S
  WELORA_KUAT_IP_DAY_MAX_FAILS (60) failed KUATs per client IP (any account, verified or not) per 24 h
  WELORA_KUAT_GUEST_IP_MAX_FAILS (6) failed KUATs of ALL guests on one client IP per WELORA_KUAT_GUEST_WINDOW_S
  WELORA_KUAT_GUEST_DEVICE_MAX_FAILS (6) failed KUATs per guest device id per WELORA_KUAT_GUEST_WINDOW_S
  WELORA_KUAT_GUEST_WINDOW_S (86400) window of the two guest limits
  WELORA_KUAT_MAX_STARTS (30) NEW attempts issued per user+node per WELORA_KUAT_COOLDOWN_S
  WELORA_KUAT_ATTEMPT_TTL_S (1800) lifetime of an issued attempt
"""

from __future__ import annotations

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
        self.reason = reason  # fails | daily | ip | ip_day | guest_ip | unverified_ip | device | unverified_device | starts


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
GUEST, UNVERIFIED, VERIFIED = "guest", "unverified", "verified"


def _identity(conn, user_id: str) -> tuple[str, Optional[str]]:
    """(kind, device_id) for the KUAT budgets (round 3):

    * ``guest`` — a device-only account (auth._is_pure_device_guest) or an unknown user id;
    * ``unverified`` — a registered ``guest``-role account WITHOUT a verified contact: no e-mail
      proven by e-mail OTP and no consumed phone-OTP challenge (``auth.has_verified_contact``).
      Register (password + e-mail/phone) alone proves nothing, so throwaway accounts land here;
    * ``verified`` — a verified contact, or a non-``guest`` role (``demo`` personas P1–P6 seeded by
      the server, admin roles).
    guest + unverified share the guest IP / device buckets."""
    from welora.auth import _is_pure_device_guest, has_verified_contact, is_reserved_device_id

    row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    if not row:
        return GUEST, None
    dev = str(row["device_id"] or "").strip() or None
    if _is_pure_device_guest(conn, row):
        return GUEST, dev
    role = str(row["role"] or "guest").strip().lower()
    if role != "guest" or has_verified_contact(conn, row):
        return VERIFIED, dev
    # registered but unverified: its device_id is a random internal marker (one per account), so
    # a device bucket on it would only duplicate the per-account limits — the shared guest IP
    # bucket is what binds throwaway accounts.
    return UNVERIFIED, (None if is_reserved_device_id(dev) else dev)


def _keys(conn, user_id: str, node_id: str, ip: Optional[str]) -> tuple[list[tuple[str, str, int, int]], str]:
    """((scope, key_hash, max, window) buckets a failed KUAT counts against, identity kind)."""
    un = f"user:{user_id}|node:{node_id}"
    out = []
    if max_fails() > 0:
        out.append(("kuat_user_node", _key_hash("kuat_user_node", un), max_fails(), cooldown_s()))
    if daily_max_fails() > 0:
        out.append(("kuat_user_node_day", _key_hash("kuat_user_node_day", un), daily_max_fails(), DAY_S))
    real_ip = _valid_ip(ip)  # a real client address only (not e.g. a test client's placeholder)
    ipb = ip_bucket(real_ip) if real_ip else ""
    if ipb and ip_max_fails() > 0:
        out.append(("kuat_ip", _key_hash("kuat_ip", ipb), ip_max_fails(), cooldown_s()))
    if ipb and ip_day_max_fails() > 0:
        out.append(("kuat_ip_day", _key_hash("kuat_ip_day", ipb), ip_day_max_fails(), DAY_S))
    kind, device = _identity(conn, user_id)
    if kind != VERIFIED:
        if ipb and guest_ip_max_fails() > 0:
            out.append(("kuat_guest_ip", _key_hash("kuat_guest_ip", ipb), guest_ip_max_fails(), guest_window_s()))
        if device and guest_device_max_fails() > 0:
            out.append(("kuat_guest_device", _key_hash("kuat_guest_device", device), guest_device_max_fails(),
                        guest_window_s()))
    return out, kind


_REASON = {"kuat_user_node": "fails", "kuat_user_node_day": "daily", "kuat_ip": "ip", "kuat_ip_day": "ip_day",
           "kuat_guest_ip": "guest_ip", "kuat_guest_device": "device", "kuat_start": "starts"}
_UNVERIFIED_REASON = {"guest_ip": "unverified_ip", "device": "unverified_device"}


def _reason(scope: str, kind: str) -> str:
    r = _REASON[scope]
    return _UNVERIFIED_REASON.get(r, r) if kind == UNVERIFIED else r


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


def open_or_create_attempt(user_id: str, node_id: str, draw, *, now: Optional[float] = None) -> dict:
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
                    kh = _key_hash("kuat_start", f"user:{user_id}|node:{node_id}")
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
