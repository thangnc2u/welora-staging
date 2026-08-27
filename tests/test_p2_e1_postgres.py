"""P2-E1 — Postgres optional. SQLite always; PG skip without WELORA_TEST_PG_URL."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.db.connection import adapt_sql_for_postgres, detect_dialect, ph
from welora.db.migrate import current_version, migrate
from welora.safety_gate import TARGET_MONTHS


def test_ph_and_adapt():
    assert ph("sqlite") == "?"
    assert ph("postgres") == "%s"
    sql = adapt_sql_for_postgres(
        "SELECT * FROM user_flags WHERE user_id=? AND x=datetime('now')"
    )
    assert "%s" in sql
    assert "?" not in sql
    assert "now()::text" in sql


def test_health_default_sqlite(monkeypatch, tmp_path):
    monkeypatch.setenv("WELORA_STORE", "sqlite")
    monkeypatch.setenv("WELORA_DB_URL", str(tmp_path / "health.db"))
    monkeypatch.delenv("WELORA_TEST_PG_URL", raising=False)
    assert TARGET_MONTHS == 3
    r = TestClient(create_app()).get("/health")
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "ok"
    assert b["dialect"] == "sqlite"
    assert b["gate_months"] == 3
    assert b["hard_deny"] is True


def test_sqlite_migrate_always(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'e1.db'}"
    monkeypatch.setenv("WELORA_STORE", "sqlite")
    monkeypatch.setenv("WELORA_DB_URL", url)
    applied = migrate(url)
    assert "001_init" in applied or "001_init" in current_version(url=url)
    assert migrate(url) == []
    vers = current_version(url=url)
    assert "001_init" in vers
    assert "002_auth" in vers


@pytest.mark.skipif(
    not os.environ.get("WELORA_TEST_PG_URL"),
    reason="WELORA_TEST_PG_URL not set",
)
def test_postgres_migrate_when_dsn():
    url = os.environ["WELORA_TEST_PG_URL"]
    assert detect_dialect(url) == "postgres"
    migrate(url)
    vers = current_version(url=url)
    assert "001_init" in vers
