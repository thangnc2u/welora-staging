"""
DB connection — SQLite pilot.

WELORA_DB_URL examples:
  sqlite:////tmp/welora_data/welora.db
  sqlite:///./data/welora.db
  (empty → /tmp/welora_data/welora.db)
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# Default under /tmp for reliable I/O in sandbox; override with WELORA_DB_URL
DEFAULT_PATH = Path("/tmp/welora_data/welora.db")


def get_db_path(url: str | None = None) -> Path:
    raw = url if url is not None else os.environ.get("WELORA_DB_URL", "")
    raw = (raw or "").strip()
    if not raw:
        return DEFAULT_PATH
    if raw.startswith("sqlite:///"):
        path = raw[len("sqlite:///") :]
        return Path(path).expanduser().resolve()
    if raw.startswith("postgresql://") or raw.startswith("postgres://"):
        raise NotImplementedError(
            "PostgreSQL driver not in pilot — use SQLite or implement psycopg later"
        )
    return Path(raw).expanduser().resolve()


def get_connection(url: str | None = None) -> sqlite3.Connection:
    path = get_db_path(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn
