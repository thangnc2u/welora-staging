"""Test DB target for the checkout suites.

Default: a fresh SQLite file per test (CI). Opt-in real PostgreSQL:
    WELORA_TEST_POSTGRES_URL=postgresql://user:pass@127.0.0.1:5432/welora_test pytest …
→ the ``public`` schema of THAT database is dropped/recreated before every test
(use a throwaway database only). Migrations then run from scratch via the app.
"""

from __future__ import annotations

import os


def pg_url() -> str:
    return (os.environ.get("WELORA_TEST_POSTGRES_URL") or "").strip()


def reset_postgres(url: str) -> None:
    import psycopg

    with psycopg.connect(url, autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS public CASCADE")
        c.execute("CREATE SCHEMA public")


def db_env(tmp: str) -> dict[str, str]:
    url = pg_url()
    if not url:
        return {"WELORA_STORE": "sqlite", "WELORA_DB_URL": f"sqlite:///{tmp}/ck.db"}
    reset_postgres(url)
    return {"WELORA_STORE": "postgres", "WELORA_DB_URL": url}
