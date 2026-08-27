"""Follow-up 2 PR #14: _make_store when WELORA_STORE=postgres (no real PG)."""

from welora.db.repos import SqliteEmergencyFundStore
from welora.goal_emergency_fund import InMemoryEmergencyFundStore
from welora.goals_api import _make_store


def test__make_store_when_WELORA_STORE_postgres(monkeypatch):
    monkeypatch.setenv("WELORA_STORE", "postgres")
    monkeypatch.delenv("WELORA_DB_URL", raising=False)

    def _init(self, url=None):
        self.url = url

    monkeypatch.setattr(SqliteEmergencyFundStore, "__init__", _init)
    store = _make_store()
    assert type(store) is not InMemoryEmergencyFundStore
    assert not isinstance(store, InMemoryEmergencyFundStore)
    assert isinstance(store, SqliteEmergencyFundStore)
