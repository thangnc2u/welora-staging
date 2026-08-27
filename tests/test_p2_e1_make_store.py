"""P2-E1 follow-up: _make_store uses DB store when WELORA_STORE=postgres."""

from __future__ import annotations

import os

import pytest

from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.db.repos import SqliteEmergencyFundStore


def test_make_store_postgres_not_memory(monkeypatch):
    monkeypatch.setenv("WELORA_STORE", "postgres")
    monkeypatch.setenv("WELORA_DB_URL", "postgresql://u:p@localhost/welora")

    def _init(self, url=None):
        self.url = url

    monkeypatch.setattr(SqliteEmergencyFundStore, "__init__", _init)
    from welora.goals_api import _make_store

    store = _make_store()
    assert not isinstance(store, InMemoryEmergencyFundStore)
    assert isinstance(store, SqliteEmergencyFundStore)


def test_make_store_memory_default(monkeypatch):
    monkeypatch.setenv("WELORA_STORE", "memory")
    monkeypatch.delenv("WELORA_DB_URL", raising=False)
    from welora.goals_api import _make_store

    store = _make_store()
    assert isinstance(store, InMemoryEmergencyFundStore)


@pytest.mark.skipif(not os.environ.get("WELORA_TEST_PG_URL"), reason="WELORA_TEST_PG_URL not set")
def test_postgres_create_goal_when_dsn(monkeypatch):
    url = os.environ["WELORA_TEST_PG_URL"]
    monkeypatch.setenv("WELORA_STORE", "postgres")
    monkeypatch.setenv("WELORA_DB_URL", url)
    from welora.goals_api import _make_store

    store = _make_store()
    assert isinstance(store, SqliteEmergencyFundStore)
    goal = store.create_for_user("u_pg_e1", 10_000_000, current_amount=0)
    assert goal.months_of_expense == 3
