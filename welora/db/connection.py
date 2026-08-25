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
            "PostgreSQL requires psycopg. Install: pip install 'psycopg[binary]>=3.2'"
        ) from e

    dsn = get_postgres_dsn(url)
    conn = psycopg.connect(dsn, row_factory=dict_row)
    return conn


def ph(dialect: Dialect | None = None) -> str:
    """Parameter placeholder: ? for sqlite, %s for postgres."""
    d = dialect or detect_dialect()
    return "%s" if d == "postgres" else "?"
