"""
DB connection — Phase 2 dual-backend.

Dialect from WELORA_DB_URL (or explicit url):

  sqlite (default):
    sqlite:////tmp/welora_data/welora.db
    /tmp/foo.db
    (empty → /tmp/welora_data/welora.db)

  postgres:
    postgresql://user:pass@host:5432/welora
    postgres://user:pass@host:5432/welora

Env:
  WELORA_DB_URL
  WELORA_STORE = memory | sqlite | postgres  (hint; URL wins for dialect)
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Literal

Dialect = Literal["sqlite", "postgres"]

DEFAULT_PATH = Path("/tmp/welora_data/welora.db")


def _raw_url(url: str | None = None) -> str:
    if url is not None:
        return (url or "").strip()
    return (os.environ.get("WELORA_DB_URL") or "").strip()


def detect_dialect(url: str | None = None) -> Dialect:
    raw = _raw_url(url)
    store = (os.environ.get("WELORA_STORE") or "").strip().lower()
    if raw.startswith("postgresql://") or raw.startswith("postgres://"):
        return "postgres"
    if store == "postgres":
        return "postgres"
    return "sqlite"


def get_db_path(url: str | None = None) -> Path:
    """SQLite file path only. Raises if dialect is postgres."""
    if detect_dialect(url) == "postgres":
        raise ValueError("get_db_path() is SQLite-only; dialect is postgres")
    raw = _raw_url(url)
    if not raw:
        return DEFAULT_PATH
    if raw.startswith("sqlite:///"):
        path = raw[len("sqlite:///") :]
        if path.startswith("/"):
            return Path(path).expanduser().resolve()
        return Path(path).expanduser().resolve()
    return Path(raw).expanduser().resolve()


def get_postgres_dsn(url: str | None = None) -> str:
    raw = _raw_url(url)
    if not (raw.startswith("postgresql://") or raw.startswith("postgres://")):
        raise ValueError("Postgres DSN required (postgresql://…)")
    return raw


# --- Ambient transaction (P0 follow-up: demo seed in ONE transaction) -----------------------
# Code paths such as the demo seed go through many repositories, each of which opens its own
# connection and commits. Inside ``ambient_transaction(url)`` every get_connection() for the same
# database on the SAME thread returns one shared connection whose commit()/close() are deferred:
# the block commits once at the end (or rolls back on error), so other connections/instances see
# either the old state or the new state, never a half-written one. Other threads are unaffected.
import threading as _threading
from contextlib import contextmanager as _contextmanager

_AMBIENT = _threading.local()


def _target_key(url: str | None) -> tuple[str, str]:
    dialect = detect_dialect(url)
    if dialect == "sqlite":
        return ("sqlite", str(get_db_path(url)))
    return ("postgres", get_postgres_dsn(url))


class _AmbientConnection:
    """Shared connection handed out inside ambient_transaction(); commit/close are deferred."""

    def __init__(self, conn: Any) -> None:
        self._real = conn

    def execute(self, sql: str, params: Any = ()):
        return self._real.execute(sql, params)

    def executemany(self, sql: str, seq: Any):
        return self._real.executemany(sql, seq)

    def executescript(self, sql: str):  # sqlite: executescript would COMMIT implicitly
        raise RuntimeError("executescript() is not allowed inside ambient_transaction()")

    def cursor(self):
        return self._real.cursor()

    def commit(self) -> None:  # deferred to the end of the ambient block
        return None

    def rollback(self) -> None:
        raise RuntimeError("rollback inside ambient_transaction() — aborting the whole block")

    def close(self) -> None:
        return None

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real, name)


def in_ambient_transaction() -> bool:
    return getattr(_AMBIENT, "conn", None) is not None


@_contextmanager
def ambient_transaction(url: str | None = None, *, sqlite_immediate: bool = True):
    """Yield the shared connection; commit at the end, roll back on any exception.

    SQLite: ``BEGIN IMMEDIATE`` takes the write lock up-front (a second writer waits / gets
    "database is locked"). Postgres: one transaction on one connection (READ COMMITTED readers
    keep seeing the previous committed rows until COMMIT)."""
    if in_ambient_transaction():
        raise RuntimeError("nested ambient_transaction() is not supported")
    key = _target_key(url)
    real = _open_connection(url)
    try:
        if key[0] == "sqlite" and sqlite_immediate:
            real.execute("BEGIN IMMEDIATE")
        _AMBIENT.conn = _AmbientConnection(real)
        _AMBIENT.key = key
        try:
            yield _AMBIENT.conn
        except BaseException:
            try:
                real.rollback()
            finally:
                _AMBIENT.conn = None
                _AMBIENT.key = None
            raise
        _AMBIENT.conn = None
        _AMBIENT.key = None
        real.commit()
    finally:
        _AMBIENT.conn = None
        _AMBIENT.key = None
        try:
            real.close()
        except Exception:
            pass


def get_connection(url: str | None = None) -> Any:
    """
    Return a DB-API connection.

    - sqlite: sqlite3.Connection with Row factory + FK on
    - postgres: psycopg Connection with dict_row (requires psycopg)
    - inside ambient_transaction() on this thread (same database): the shared connection
    """
    amb = getattr(_AMBIENT, "conn", None)
    if amb is not None:
        try:
            if _target_key(url) == getattr(_AMBIENT, "key", None):
                return amb
        except ValueError:
            pass
    return _open_connection(url)


def _open_connection(url: str | None = None) -> Any:
    dialect = detect_dialect(url)
    if dialect == "sqlite":
        path = get_db_path(url)
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as e:
        raise ImportError(
            "PostgreSQL requires psycopg. Install: pip install -r requirements-postgres.txt"
        ) from e

    dsn = get_postgres_dsn(url)
    raw = psycopg.connect(dsn, row_factory=dict_row)
    return PgCompatConnection(raw)


def adapt_sql_for_postgres(sql: str) -> str:
    """Rewrite SQLite-shaped SQL so psycopg can run it."""
    import re

    out = sql
    out = out.replace("datetime('now')", "now()::text")
    out = out.replace("INSERT OR IGNORE INTO", "INSERT INTO")
    out = out.replace("excluded.", "EXCLUDED.")
    out = re.sub(r"ON CONFLICT\(([^)]+)\)", r"ON CONFLICT (\1)", out)
    # literal % (modulo, LIKE 'x%') must be doubled for psycopg; keep explicit %s placeholders
    out = re.sub(r"%(?!s)", "%%", out)
    out = out.replace("?", "%s")
    if (
        "INSERT INTO users(user_id) VALUES" in out
        and "ON CONFLICT" not in out
    ):
        out = out.rstrip().rstrip(";") + " ON CONFLICT (user_id) DO NOTHING"
    return out


class PgCompatConnection:
    """psycopg connection that accepts SQLite '?' placeholders from repos.py."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def execute(self, sql: str, params: Any = ()):
        return self._conn.execute(adapt_sql_for_postgres(sql), params)

    def executemany(self, sql: str, seq: Any):
        return self._conn.executemany(adapt_sql_for_postgres(sql), seq)

    def cursor(self):
        return self._conn.cursor()

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)


def ph(dialect: Dialect | None = None) -> str:
    """Parameter placeholder: ? for sqlite, %s for postgres."""
    d = dialect or detect_dialect()
    return "%s" if d == "postgres" else "?"
