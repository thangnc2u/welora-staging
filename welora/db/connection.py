"""
DB connection — SQLite pilot.

WELORA_DB_URL examples:
  sqlite:////tmp/welora.db
  /tmp/welora.db
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Optional


def get_db_url(url: Optional[str] = None) -> str:
    raw = url or os.environ.get("WELORA_DB_URL") or "/tmp/welora.db"
    if raw.startswith("sqlite:///"):
        raw = raw[len("sqlite:///") :]
        if raw.startswith("/") and not raw.startswith("///"):
            pass
        elif raw.startswith("//"):
            raw = raw[1:]
    return raw


def get_connection(url: Optional[str] = None) -> sqlite3.Connection:
    path = get_db_url(url)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
