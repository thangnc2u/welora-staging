"""Migration 019_kuat_open_scope — per-session / per-network open KUAT attempts for demo personas.

PostgreSQL applies ``migrations/postgres/019_kuat_open_scope.sql`` (plain, idempotent SQL). SQLite
has no ``ADD COLUMN IF NOT EXISTS``, so the same change runs here as a data step of
``welora.db.migrate`` (version ``019_kuat_open_scope``; on PostgreSQL the SQL file already recorded
that version, so this step is skipped there). Idempotent on both dialects — it can be run any
number of times:

* ``academy_kuat_attempts.scope_key TEXT NOT NULL DEFAULT ''`` (added only when missing; existing
  rows → '' = the regular per user + node scope);
* unique partial index ``uq_academy_kuat_open_scope (user_id, node_id, scope_key) WHERE used_at IS
  NULL`` — created first;
* 018's ``uq_academy_kuat_open (user_id, node_id) WHERE used_at IS NULL`` dropped afterwards.
"""

from __future__ import annotations

from typing import Any


def _has_column(conn: Any, dialect: str, table: str, column: str) -> bool:
    if dialect == "sqlite":
        return any(str(r["name"]) == column for r in conn.execute(f"PRAGMA table_info({table})").fetchall())
    row = conn.execute(
        "SELECT 1 FROM information_schema.columns WHERE table_schema = current_schema() "
        "AND table_name = ? AND column_name = ?",
        (table, column),
    ).fetchone()
    return row is not None


def apply_kuat_open_scope(conn: Any, dialect: str = "sqlite") -> dict[str, Any]:
    added = False
    if not _has_column(conn, dialect, "academy_kuat_attempts", "scope_key"):
        conn.execute("ALTER TABLE academy_kuat_attempts ADD COLUMN scope_key TEXT NOT NULL DEFAULT ''")
        added = True
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_academy_kuat_open_scope "
        "ON academy_kuat_attempts(user_id, node_id, scope_key) WHERE used_at IS NULL"
    )
    conn.execute("DROP INDEX IF EXISTS uq_academy_kuat_open")
    conn.commit()
    return {"scope_key_added": added}
