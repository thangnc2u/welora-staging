"""
Mode C SQLite persistence (P2 OS Persist Mode C).

Smallest coherent write-through store for Mode C acts + companion links.
Survives process restart: proposals / pending_cool_off / pending_dual /
confirmed / undone + companion by user_id.

- SQLite only (no new Postgres, no bank aggregator).
- Own schema_version (mode_c_schema); does not touch Hard Deny / TARGET_MONTHS / CORE.
- Enabled when WELORA_MODE_C_DB is set, or WELORA_MODE_C_PERSIST=1, or WELORA_STORE=sqlite.
- Default path: WELORA_MODE_C_DB → sibling of WELORA_DB_URL → /tmp/welora_data/mode_c.db
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 1

DEFAULT_PATH = Path("/tmp/welora_data/mode_c.db")

_PATH: Optional[Path] = None
_ENABLED: bool = False

_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS mode_c_schema (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mode_c_companions (
    user_id            TEXT PRIMARY KEY,
    companion_user_id  TEXT NOT NULL,
    linked_at          TEXT,
    policy_version     TEXT,
    payload_json       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mode_c_proposals (
    proposal_id        TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL,
    companion_user_id  TEXT,
    status             TEXT NOT NULL,
    act_kind           TEXT,
    cool_off_until     TEXT,
    act_id             TEXT,
    payload_json       TEXT NOT NULL,
    updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_mode_c_proposals_user
    ON mode_c_proposals(user_id);
CREATE INDEX IF NOT EXISTS idx_mode_c_proposals_status
    ON mode_c_proposals(status);
CREATE INDEX IF NOT EXISTS idx_mode_c_proposals_act
    ON mode_c_proposals(act_id);

CREATE TABLE IF NOT EXISTS mode_c_undos (
    act_id       TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    undo_token   TEXT NOT NULL,
    undo_until   TEXT NOT NULL,
    undone_at    TEXT,
    act_kind     TEXT,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mode_c_envelopes (
    envelope_id  TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    status       TEXT,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mode_c_envelopes_user
    ON mode_c_envelopes(user_id);

CREATE TABLE IF NOT EXISTS mode_c_envelope_order (
    user_id      TEXT NOT NULL,
    envelope_id  TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    PRIMARY KEY (user_id, envelope_id)
);

CREATE TABLE IF NOT EXISTS mode_c_reminders (
    reminder_id  TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL,
    status       TEXT,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mode_c_reminders_user
    ON mode_c_reminders(user_id);

CREATE TABLE IF NOT EXISTS mode_c_reminder_order (
    user_id      TEXT NOT NULL,
    reminder_id  TEXT NOT NULL,
    seq          INTEGER NOT NULL,
    PRIMARY KEY (user_id, reminder_id)
);

CREATE TABLE IF NOT EXISTS mode_c_estates (
    user_id      TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mode_c_personas (
    user_id  TEXT PRIMARY KEY,
    persona  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mode_c_act_logs (
    id           TEXT PRIMARY KEY,
    user_id      TEXT,
    payload_json TEXT NOT NULL,
    timestamp    TEXT
);
"""


def _resolve_default_path() -> Path:
    explicit = (os.environ.get("WELORA_MODE_C_DB") or "").strip()
    if explicit:
        if explicit.startswith("sqlite:///"):
            explicit = explicit[len("sqlite:///") :]
        return Path(explicit).expanduser().resolve()
    db_url = (os.environ.get("WELORA_DB_URL") or "").strip()
    if db_url and not db_url.startswith("postgres"):
        if db_url.startswith("sqlite:///"):
            db_url = db_url[len("sqlite:///") :]
        base = Path(db_url).expanduser().resolve()
        return base.parent / "mode_c.db"
    return DEFAULT_PATH


def persist_wanted() -> bool:
    """Whether Mode C SQLite persistence should be active."""
    if (os.environ.get("WELORA_MODE_C_DB") or "").strip():
        return True
    flag = (os.environ.get("WELORA_MODE_C_PERSIST") or "").strip().lower()
    if flag in ("1", "true", "yes", "on"):
        return True
    store = (os.environ.get("WELORA_STORE") or "memory").strip().lower()
    return store in ("sqlite", "db")


def is_enabled() -> bool:
    return bool(_ENABLED and _PATH is not None)


def get_path() -> Optional[Path]:
    return _PATH


def schema_version(conn: Optional[sqlite3.Connection] = None) -> int:
    own = False
    if conn is None:
        if not is_enabled():
            return 0
        conn = _connect()
        own = True
    try:
        row = conn.execute(
            "SELECT MAX(version) AS v FROM mode_c_schema"
        ).fetchone()
        if not row or row[0] is None:
            return 0
        return int(row[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        if own:
            conn.close()


def _connect(path: Optional[Path] = None) -> sqlite3.Connection:
    p = path or _PATH
    if p is None:
        raise RuntimeError("Mode C persist path not configured")
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(path: Optional[Path] = None) -> int:
    """Apply Mode C schema. Returns SCHEMA_VERSION after migrate."""
    p = path or _PATH
    if p is None:
        raise RuntimeError("Mode C persist path not configured")
    conn = _connect(p)
    try:
        conn.executescript(_SCHEMA_SQL)
        cur = schema_version(conn)
        if cur < SCHEMA_VERSION:
            conn.execute(
                "INSERT OR REPLACE INTO mode_c_schema(version, applied_at) "
                "VALUES (?, datetime('now'))",
                (SCHEMA_VERSION,),
            )
            conn.commit()
        return SCHEMA_VERSION
    finally:
        conn.close()


def configure(path: Optional[str | Path] = None, *, enable: Optional[bool] = None) -> Path:
    """Enable persist at path (or default). Returns resolved path."""
    global _PATH, _ENABLED
    if path is not None:
        p = Path(str(path)).expanduser().resolve()
    else:
        p = _resolve_default_path()
    _PATH = p
    if enable is None:
        _ENABLED = True
    else:
        _ENABLED = bool(enable)
    if _ENABLED:
        migrate(p)
    return p


def disable() -> None:
    global _ENABLED, _PATH
    _ENABLED = False
    # keep path for tests that re-enable; clear path on full teardown
    _PATH = None


def maybe_autoconfigure() -> bool:
    """Enable from env if wanted. Idempotent."""
    if is_enabled():
        return True
    if not persist_wanted():
        return False
    configure()
    return True


def clear_all() -> None:
    """Wipe Mode C tables (keep schema). No-op if disabled."""
    if not is_enabled():
        return
    conn = _connect()
    try:
        for table in (
            "mode_c_act_logs",
            "mode_c_personas",
            "mode_c_estates",
            "mode_c_reminder_order",
            "mode_c_reminders",
            "mode_c_envelope_order",
            "mode_c_envelopes",
            "mode_c_undos",
            "mode_c_proposals",
            "mode_c_companions",
        ):
            conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()


def _dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


def _loads(s: str) -> Any:
    return json.loads(s)


# --- writers ---

def save_companion(rec: dict[str, Any]) -> None:
    if not is_enabled() or not rec:
        return
    uid = str(rec.get("user_id") or "")
    if not uid:
        return
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO mode_c_companions(
                user_id, companion_user_id, linked_at, policy_version, payload_json
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                companion_user_id = excluded.companion_user_id,
                linked_at = excluded.linked_at,
                policy_version = excluded.policy_version,
                payload_json = excluded.payload_json
            """,
            (
                uid,
                str(rec.get("companion_user_id") or ""),
                rec.get("linked_at"),
                rec.get("policy_version"),
                _dumps(rec),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_proposal(prop: dict[str, Any]) -> None:
    if not is_enabled() or not prop:
        return
    pid = str(prop.get("proposal_id") or "")
    if not pid:
        return
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO mode_c_proposals(
                proposal_id, user_id, companion_user_id, status, act_kind,
                cool_off_until, act_id, payload_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(proposal_id) DO UPDATE SET
                user_id = excluded.user_id,
                companion_user_id = excluded.companion_user_id,
                status = excluded.status,
                act_kind = excluded.act_kind,
                cool_off_until = excluded.cool_off_until,
                act_id = excluded.act_id,
                payload_json = excluded.payload_json,
                updated_at = datetime('now')
            """,
            (
                pid,
                str(prop.get("user_id") or ""),
                prop.get("companion_user_id"),
                str(prop.get("status") or "proposed"),
                prop.get("act_kind"),
                prop.get("cool_off_until"),
                prop.get("act_id"),
                _dumps(prop),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_undo(meta: dict[str, Any]) -> None:
    if not is_enabled() or not meta:
        return
    aid = str(meta.get("act_id") or "")
    if not aid:
        return
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO mode_c_undos(
                act_id, user_id, undo_token, undo_until, undone_at, act_kind, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(act_id) DO UPDATE SET
                user_id = excluded.user_id,
                undo_token = excluded.undo_token,
                undo_until = excluded.undo_until,
                undone_at = excluded.undone_at,
                act_kind = excluded.act_kind,
                payload_json = excluded.payload_json
            """,
            (
                aid,
                str(meta.get("user_id") or ""),
                str(meta.get("undo_token") or ""),
                str(meta.get("undo_until") or ""),
                meta.get("undone_at"),
                meta.get("act_kind"),
                _dumps(meta),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def save_envelope(rec: dict[str, Any]) -> None:
    if not is_enabled() or not rec:
        return
    eid = str(rec.get("envelope_id") or "")
    uid = str(rec.get("user_id") or "")
    if not eid or not uid:
        return
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO mode_c_envelopes(envelope_id, user_id, status, payload_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(envelope_id) DO UPDATE SET
                user_id = excluded.user_id,
                status = excluded.status,
                payload_json = excluded.payload_json
            """,
            (eid, uid, rec.get("status"), _dumps(rec)),
        )
        # preserve order list membership
        row = conn.execute(
            "SELECT MAX(seq) AS m FROM mode_c_envelope_order WHERE user_id = ?",
            (uid,),
        ).fetchone()
        exists = conn.execute(
            "SELECT 1 FROM mode_c_envelope_order WHERE user_id = ? AND envelope_id = ?",
            (uid, eid),
        ).fetchone()
        if not exists:
            seq = int(row["m"] or 0) + 1 if row else 1
            conn.execute(
                "INSERT INTO mode_c_envelope_order(user_id, envelope_id, seq) VALUES (?, ?, ?)",
                (uid, eid, seq),
            )
        conn.commit()
    finally:
        conn.close()


def delete_envelope(envelope_id: str, user_id: str) -> None:
    if not is_enabled() or not envelope_id:
        return
    conn = _connect()
    try:
        conn.execute("DELETE FROM mode_c_envelopes WHERE envelope_id = ?", (envelope_id,))
        conn.execute(
            "DELETE FROM mode_c_envelope_order WHERE user_id = ? AND envelope_id = ?",
            (user_id, envelope_id),
        )
        conn.commit()
    finally:
        conn.close()


def save_reminder(rec: dict[str, Any]) -> None:
    if not is_enabled() or not rec:
        return
    rid = str(rec.get("reminder_id") or "")
    uid = str(rec.get("user_id") or "")
    if not rid or not uid:
        return
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO mode_c_reminders(reminder_id, user_id, status, payload_json)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(reminder_id) DO UPDATE SET
                user_id = excluded.user_id,
                status = excluded.status,
                payload_json = excluded.payload_json
            """,
            (rid, uid, rec.get("status"), _dumps(rec)),
        )
        exists = conn.execute(
            "SELECT 1 FROM mode_c_reminder_order WHERE user_id = ? AND reminder_id = ?",
            (uid, rid),
        ).fetchone()
        if not exists:
            row = conn.execute(
                "SELECT MAX(seq) AS m FROM mode_c_reminder_order WHERE user_id = ?",
                (uid,),
            ).fetchone()
            seq = int(row["m"] or 0) + 1 if row else 1
            conn.execute(
                "INSERT INTO mode_c_reminder_order(user_id, reminder_id, seq) VALUES (?, ?, ?)",
                (uid, rid, seq),
            )
        conn.commit()
    finally:
        conn.close()


def delete_reminder(reminder_id: str, user_id: str) -> None:
    if not is_enabled() or not reminder_id:
        return
    conn = _connect()
    try:
        conn.execute("DELETE FROM mode_c_reminders WHERE reminder_id = ?", (reminder_id,))
        conn.execute(
            "DELETE FROM mode_c_reminder_order WHERE user_id = ? AND reminder_id = ?",
            (user_id, reminder_id),
        )
        conn.commit()
    finally:
        conn.close()


def save_estate(user_id: str, rec: Optional[dict[str, Any]]) -> None:
    if not is_enabled() or not user_id:
        return
    conn = _connect()
    try:
        if rec is None:
            conn.execute("DELETE FROM mode_c_estates WHERE user_id = ?", (user_id,))
        else:
            conn.execute(
                """
                INSERT INTO mode_c_estates(user_id, payload_json)
                VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET payload_json = excluded.payload_json
                """,
                (user_id, _dumps(rec)),
            )
        conn.commit()
    finally:
        conn.close()


def save_persona(user_id: str, persona: str) -> None:
    if not is_enabled() or not user_id:
        return
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO mode_c_personas(user_id, persona)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET persona = excluded.persona
            """,
            (user_id, persona),
        )
        conn.commit()
    finally:
        conn.close()


def append_act_log(entry: dict[str, Any]) -> None:
    if not is_enabled() or not entry:
        return
    eid = str(entry.get("id") or "")
    if not eid:
        return
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT OR REPLACE INTO mode_c_act_logs(id, user_id, payload_json, timestamp)
            VALUES (?, ?, ?, ?)
            """,
            (
                eid,
                entry.get("user_id"),
                _dumps(entry),
                entry.get("timestamp"),
            ),
        )
        conn.commit()
    finally:
        conn.close()


# --- bulk load ---

def load_all() -> dict[str, Any]:
    """Load all Mode C state from SQLite. Empty dicts if disabled / empty DB."""
    empty: dict[str, Any] = {
        "companions": {},
        "proposals": {},
        "undos": {},
        "envelopes": {},
        "envelopes_by_user": {},
        "reminders": {},
        "reminders_by_user": {},
        "estates": {},
        "personas": {},
        "act_logs": [],
    }
    if not is_enabled():
        return empty
    conn = _connect()
    try:
        for row in conn.execute("SELECT payload_json FROM mode_c_companions"):
            rec = _loads(row["payload_json"])
            empty["companions"][str(rec["user_id"])] = rec

        for row in conn.execute("SELECT payload_json FROM mode_c_proposals"):
            prop = _loads(row["payload_json"])
            empty["proposals"][str(prop["proposal_id"])] = prop

        for row in conn.execute("SELECT payload_json FROM mode_c_undos"):
            meta = _loads(row["payload_json"])
            empty["undos"][str(meta["act_id"])] = meta

        for row in conn.execute("SELECT payload_json FROM mode_c_envelopes"):
            rec = _loads(row["payload_json"])
            empty["envelopes"][str(rec["envelope_id"])] = rec

        for row in conn.execute(
            "SELECT user_id, envelope_id FROM mode_c_envelope_order ORDER BY user_id, seq"
        ):
            empty["envelopes_by_user"].setdefault(row["user_id"], []).append(
                row["envelope_id"]
            )

        for row in conn.execute("SELECT payload_json FROM mode_c_reminders"):
            rec = _loads(row["payload_json"])
            empty["reminders"][str(rec["reminder_id"])] = rec

        for row in conn.execute(
            "SELECT user_id, reminder_id FROM mode_c_reminder_order ORDER BY user_id, seq"
        ):
            empty["reminders_by_user"].setdefault(row["user_id"], []).append(
                row["reminder_id"]
            )

        for row in conn.execute("SELECT user_id, payload_json FROM mode_c_estates"):
            empty["estates"][row["user_id"]] = _loads(row["payload_json"])

        for row in conn.execute("SELECT user_id, persona FROM mode_c_personas"):
            empty["personas"][row["user_id"]] = row["persona"]

        for row in conn.execute(
            "SELECT payload_json FROM mode_c_act_logs ORDER BY timestamp"
        ):
            empty["act_logs"].append(_loads(row["payload_json"]))

        return empty
    finally:
        conn.close()
