"""GP P0b · DB side of Welorademy: persisted progress, server-held KUAT attempts, KUAT limits.

* ``academy_profiles`` (migration 017): one JSON profile per user + ``rev`` (bumped on every save)
  so another instance / a fresh process reloads it. Written only in DB-store mode
  (WELORA_STORE=sqlite|postgres or a postgres URL — same switch as goals / flags).
* ``academy_kuat_attempts``: every KUAT is an attempt the server issued — which questions (drawn
  from the node's bank) and which option order it showed. Submitting consumes the attempt
  atomically (single-use) before it expires. Only the outcome (passed / failed / superseded) and the
  total score are recorded — never per-question correctness.
* KUAT limits reuse ``auth_rate_events`` (migration 013, same hashing / pruning as the auth limits):
  failed submissions per (user, node) — short window + daily cap — and per client IP (stops
  many guest accounts from one IP), plus attempt starts per (user, node).

Env (all optional; a value ≤ 0 disables that limit):
  WELORA_KUAT_MAX_FAILS (3) failed KUATs per user+node per WELORA_KUAT_COOLDOWN_S (1800 s)
  WELORA_KUAT_DAILY_MAX_FAILS (10) failed KUATs per user+node per 24 h
  WELORA_KUAT_IP_MAX_FAILS (30) failed KUATs per client IP per WELORA_KUAT_COOLDOWN_S
  WELORA_KUAT_MAX_STARTS (30) attempts issued per user+node per WELORA_KUAT_COOLDOWN_S
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
        self.reason = reason  # fails | daily | ip | starts


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
def _keys(user_id: str, node_id: str, ip: Optional[str]) -> list[tuple[str, str, int, int]]:
    """(scope, key_hash, max, window) buckets for failed KUATs."""
    un = f"user:{user_id}|node:{node_id}"
    out = []
    if max_fails() > 0:
        out.append(("kuat_user_node", _key_hash("kuat_user_node", un), max_fails(), cooldown_s()))
    if daily_max_fails() > 0:
        out.append(("kuat_user_node_day", _key_hash("kuat_user_node_day", un), daily_max_fails(), DAY_S))
    real_ip = _valid_ip(ip)  # a real client address only (not e.g. a test client's placeholder)
    if real_ip and ip_max_fails() > 0:
        out.append(("kuat_ip", _key_hash("kuat_ip", ip_bucket(real_ip)), ip_max_fails(), cooldown_s()))
    return out


_REASON = {"kuat_user_node": "fails", "kuat_user_node_day": "daily", "kuat_ip": "ip", "kuat_start": "starts"}


def _check(conn, action: str, buckets, now: float) -> None:
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
                worst = (wait, _REASON[scope])
    if worst:
        raise KuatCooldown(*worst)


def check_kuat_allowed(user_id: str, node_id: str, ip: Optional[str] = None, *, now: Optional[float] = None) -> None:
    """Raise KuatCooldown while the user (or the client IP) has too many failed KUATs."""
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        _check(conn, FAIL_ACTION, _keys(user_id, node_id, ip), t)
    finally:
        conn.close()


def record_kuat_fail(user_id: str, node_id: str, ip: Optional[str] = None, *, now: Optional[float] = None) -> None:
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        stamp = _iso(t)
        for scope, kh, _mx, _win in _keys(user_id, node_id, ip):
            conn.execute(
                "INSERT INTO auth_rate_events(event_id, action, scope, key_hash, created_at) VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), FAIL_ACTION, scope, kh, stamp),
            )
        conn.execute("DELETE FROM auth_rate_events WHERE created_at<?", (_iso(t - max(DAY_S, _PRUNE_AFTER_S)),))
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- attempts
def create_attempt(user_id: str, node_id: str, served: list[dict], *, now: Optional[float] = None) -> dict:
    """Issue a new attempt (start limit per user+node); earlier open attempts are superseded."""
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        if max_starts() > 0:
            kh = _key_hash("kuat_start", f"user:{user_id}|node:{node_id}")
            _check(conn, START_ACTION, [("kuat_start", kh, max_starts(), cooldown_s())], t)
            conn.execute(
                "INSERT INTO auth_rate_events(event_id, action, scope, key_hash, created_at) VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), START_ACTION, "kuat_start", kh, _iso(t)),
            )
        conn.execute(
            "UPDATE academy_kuat_attempts SET used_at=?, outcome='superseded' "
            "WHERE user_id=? AND node_id=? AND used_at IS NULL",
            (_iso(t), user_id, node_id),
        )
        attempt_id = uuid.uuid4().hex
        expires = _iso(t + attempt_ttl_s())
        conn.execute(
            "INSERT INTO academy_kuat_attempts(attempt_id, user_id, node_id, served_json, created_at, expires_at) "
            "VALUES (?,?,?,?,?,?)",
            (attempt_id, user_id, node_id, json.dumps(served), _iso(t), expires),
        )
        conn.execute("DELETE FROM academy_kuat_attempts WHERE created_at<?", (_iso(t - 30 * DAY_S),))
        conn.commit()
        return {"attempt_id": attempt_id, "expires_at": expires}
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


def consume_attempt(attempt_id: str, user_id: str, node_id: str, *, now: Optional[float] = None) -> Optional[list]:
    """Atomically mark the attempt used. Returns what was served, or None (unknown / someone
    else's / other node / expired / already used or superseded)."""
    t = time.time() if now is None else float(now)
    conn = _conn()
    try:
        cur = conn.execute(
            "UPDATE academy_kuat_attempts SET used_at=? WHERE attempt_id=? AND user_id=? AND node_id=? "
            "AND used_at IS NULL AND expires_at>?",
            (_iso(t), str(attempt_id or ""), user_id, node_id, _iso(t)),
        )
        if int(cur.rowcount or 0) != 1:
            return None  # nothing was changed
        r = conn.execute("SELECT served_json FROM academy_kuat_attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
        conn.commit()
        return json.loads(r["served_json"])
    finally:
        conn.close()


def finish_attempt(attempt_id: str, *, passed: bool, score: float) -> None:
    conn = _conn()
    try:
        conn.execute("UPDATE academy_kuat_attempts SET outcome=?, score=? WHERE attempt_id=?",
                     ("passed" if passed else "failed", float(score), attempt_id))
        conn.commit()
    finally:
        conn.close()
