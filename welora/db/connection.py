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


def get_connection(url: str | None = None) -> Any:
    """
    Return a DB-API connection.

    - sqlite: sqlite3.Connection with Row factory + FK on
    - postgres: psycopg Connection with dict_row (requires psycopg)
    """
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
