"""
Apply SQL migrations under welora/db/migrations/*.sql

Usage:
  PYTHONPATH=. python -m welora.db.migrate
  WELORA_DB_URL=sqlite:////tmp/t.db PYTHONPATH=. python -m welora.db.migrate
"""

from __future__ import annotations

from pathlib import Path

from welora.db.connection import get_connection, get_db_path

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def _list_migration_files() -> list[Path]:
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    return files


def _version_of(path: Path) -> str:
    return path.stem


def current_version(conn=None) -> list[str]:
    own = False
    if conn is None:
        conn = get_connection()
        own = True
    try:
        cur = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        )
        if not cur.fetchone():
            return []
        rows = conn.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        if own:
            conn.close()


def migrate(url: str | None = None) -> list[str]:
    """Apply pending migrations. Returns list of newly applied versions."""
    conn = get_connection(url)
    applied: list[str] = []
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.commit()
        done = set(current_version(conn))
        for path in _list_migration_files():
            ver = _version_of(path)
            if ver in done:
                continue
            sql = path.read_text(encoding="utf-8")
            conn.executescript(sql)
            conn.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                (ver,),
            )
            conn.commit()
            applied.append(ver)
        return applied
    finally:
        conn.close()


def main() -> None:
    path = get_db_path()
    print(f"DB: {path}")
    before = current_version()
    print(f"Already applied: {before or '(none)'}")
    newly = migrate()
    after = current_version()
    print(f"Newly applied: {newly or '(none)'}")
    print(f"Current: {after}")
    if newly:
        print("OK migrate")
    else:
        print("OK up-to-date")


if __name__ == "__main__":
    main()
