"""
Apply SQL migrations — dialect-aware (SQLite | PostgreSQL).

Usage:
  PYTHONPATH=. python -m welora.db.migrate
  WELORA_DB_URL=sqlite:////tmp/t.db PYTHONPATH=. python -m welora.db.migrate
  WELORA_DB_URL=postgresql://user:pass@localhost:5432/welora PYTHONPATH=. python -m welora.db.migrate
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from welora.db.connection import detect_dialect, get_connection, get_db_path

MIGRATIONS_ROOT = Path(__file__).resolve().parent / "migrations"


def _migrations_dir(url: str | None = None) -> Path:
    if detect_dialect(url) == "postgres":
        return MIGRATIONS_ROOT / "postgres"
    return MIGRATIONS_ROOT


def _list_migration_files(url: str | None = None) -> list[Path]:
    d = _migrations_dir(url)
    return sorted(d.glob("*.sql"))


def _version_of(path: Path) -> str:
    return path.stem


def _table_exists(conn: Any, dialect: str, table: str) -> bool:
    if dialect == "sqlite":
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        return row is not None
    row = conn.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name = %s",
        (table,),
    ).fetchone()
    return row is not None


def current_version(conn=None, url: str | None = None) -> list[str]:
    own = False
    dialect = detect_dialect(url)
    if conn is None:
        conn = get_connection(url)
        own = True
    try:
        if not _table_exists(conn, dialect, "schema_migrations"):
            return []
        rows = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        out = []
        for r in rows:
            out.append(r["version"] if not isinstance(r, tuple) else r[0])
        return out
    finally:
        if own:
            conn.close()


def _exec_script(conn: Any, dialect: str, sql: str) -> None:
    if dialect == "sqlite":
        conn.executescript(sql)
        return
    inner = getattr(conn, "_conn", conn)
    with inner.cursor() as cur:
        cur.execute(sql)


def migrate(url: str | None = None) -> list[str]:
    """Apply pending migrations. Returns list of newly applied versions."""
    dialect = detect_dialect(url)
    conn = get_connection(url)
    applied: list[str] = []
    try:
        if dialect == "sqlite":
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )
            conn.commit()
        else:
            inner = getattr(conn, "_conn", conn)
            with inner.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version TEXT PRIMARY KEY,
                        applied_at TEXT NOT NULL DEFAULT (now()::text)
                    )
                    """
                )
            conn.commit()

        done = set(current_version(conn, url=url))
        for path in _list_migration_files(url):
            ver = _version_of(path)
            if ver in done:
                continue
            sql = path.read_text(encoding="utf-8")
            _exec_script(conn, dialect, sql)
            if dialect == "sqlite":
                conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                    (ver,),
                )
            else:
                inner = getattr(conn, "_conn", conn)
                with inner.cursor() as cur:
                    cur.execute(
                        "INSERT INTO schema_migrations(version) VALUES (%s) "
                        "ON CONFLICT (version) DO NOTHING",
                        (ver,),
                    )
            conn.commit()
            applied.append(ver)
        return applied
    finally:
        conn.close()


def main() -> None:
    dialect = detect_dialect()
    if dialect == "sqlite":
        print(f"DB (sqlite): {get_db_path()}")
    else:
        print("DB (postgres): [DSN from WELORA_DB_URL]")
    before = current_version()
    print(f"Already applied: {before or '(none)'}")
    newly = migrate()
    after = current_version()
    print(f"Newly applied: {newly or '(none)'}")
    print(f"Current: {after}")
    print("OK migrate" if newly else "OK up-to-date")


if __name__ == "__main__":
    main()
