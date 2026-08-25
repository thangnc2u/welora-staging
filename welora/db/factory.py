"""
Store factory — Phase 2.

WELORA_STORE:
  memory   → InMemoryEmergencyFundStore (default tests / demo)
  sqlite   → SqliteEmergencyFundStore (needs WELORA_DB_URL or default path)
  postgres → same Db store against Postgres DSN (P2-E1-05 dialect-aware SQL)
"""

from __future__ import annotations

import os
from typing import Any

from welora.db.connection import detect_dialect


def make_emergency_fund_store(url: str | None = None) -> Any:
    store_hint = (os.environ.get("WELORA_STORE") or "memory").strip().lower()
    dialect = detect_dialect(url)
    has_url = bool(url or (os.environ.get("WELORA_DB_URL") or "").strip())

    if store_hint == "memory" and not has_url:
        from welora.goal_emergency_fund import InMemoryEmergencyFundStore
        return InMemoryEmergencyFundStore()

    if dialect == "postgres" or store_hint in ("sqlite", "postgres", "db") or has_url:
        from welora.db.repos import SqliteEmergencyFundStore
        return SqliteEmergencyFundStore(url)

    from welora.goal_emergency_fund import InMemoryEmergencyFundStore
    return InMemoryEmergencyFundStore()


def make_onboarding_repository(url: str | None = None) -> Any:
    store_hint = (os.environ.get("WELORA_STORE") or "memory").strip().lower()
    has_url = bool(url or (os.environ.get("WELORA_DB_URL") or "").strip())

    if store_hint == "memory" and not has_url:
        import welora.onboarding as ob
        return ob

    from welora.db.repos import SqliteOnboardingRepository
    return SqliteOnboardingRepository(url)
