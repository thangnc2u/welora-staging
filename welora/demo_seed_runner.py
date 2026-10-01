"""P0 follow-up — demo seed P1–P6 that is atomic, idempotent and runs after every deploy.

``run_demo_seed()`` does exactly what ``POST /auth/demo/seed`` always did (partner auth row +
rich P1–P6 aliases + the P2/P4 fixture personas) but, on a DB store, inside ONE transaction
(``db.connection.ambient_transaction``) guarded by a cross-instance lock:

* Postgres: ``pg_try_advisory_xact_lock`` (startup: skip if another instance holds it) or
  ``pg_advisory_xact_lock`` (explicit endpoint call: wait). Released automatically at COMMIT/ROLLBACK.
* SQLite: ``BEGIN IMMEDIATE`` (the database write lock) — a second seeder waits for the busy
  timeout and then either re-runs idempotently or gives up (startup logs and continues).
* In-process: a ``threading.Lock`` so the startup thread and the endpoint never interleave.

Why the P2/P4 safety gate used to flap: the old seed deleted the personas' goals/DNA/flags and
re-created them across ~15 separate commits (readers on another connection/instance saw "no goal",
"DNA without debt goal" … → has_dangerous_debt and the gate flipped while it ran), and the P2
mastery state lived only in process memory, so after every restart/deploy P2 read
``not_passed (mastery_missing)`` until someone pressed the demo button. Now every write commits
together, and the seed also persists the personas' user_flags (incl. mastery) to the DB.

Startup (``start_background_seed``): only when WELORA_GUEST_DEMO is enabled, WELORA_ENV is not
production and WELORA_DEMO_AUTOSEED is not "0"; runs in a daemon thread, never raises.
"""

from __future__ import annotations

import logging
import os
import threading
import zlib
from typing import Any, Optional

log = logging.getLogger("welora.demo_seed")

ADVISORY_LOCK_KEY = zlib.crc32(b"welora:demo_seed:p1-p6")  # stable 32-bit key
_PROCESS_LOCK = threading.Lock()
LAST_RUN: dict[str, Any] = {}


class SeedLocked(RuntimeError):
    """Another instance/thread is seeding right now."""


def _db_mode() -> bool:
    store = (os.environ.get("WELORA_STORE") or "memory").strip().lower()
    url = (os.environ.get("WELORA_DB_URL") or "").strip()
    if store in ("sqlite", "postgres", "db"):
        return True
    return url.startswith("postgresql://") or url.startswith("postgres://")


def autoseed_wanted() -> tuple[bool, str]:
    from welora.auth import guest_demo_enabled

    if not guest_demo_enabled():
        return False, "WELORA_GUEST_DEMO=0"
    env = (os.environ.get("WELORA_ENV") or "").strip().lower()
    if env in ("production", "prod"):
        return False, "WELORA_ENV=production"
    if (os.environ.get("WELORA_DEMO_AUTOSEED") or "1").strip() == "0":
        return False, "WELORA_DEMO_AUTOSEED=0"
    return True, ""


def _seed_all() -> dict[str, Any]:
    """The full /auth/demo/seed payload (unchanged response shape)."""
    from welora import auth as auth_svc

    code, out = auth_svc.service_demo_seed()
    out = dict(out or {})
    if "rich_error" in out:
        # surfaced in the response before; inside one transaction it must abort the whole seed
        raise RuntimeError(f"rich demo seed failed: {out['rich_error']}")
    out.pop("flag", None)
    from welora.fixtures import seed_priority_demo_personas

    personas = seed_priority_demo_personas()
    out["personas"] = {
        pid: {
            "user_id": fx["user_id"],
            "household": fx.get("household"),
            "persona_id": fx.get("persona_id", pid),
            "os_goals": list(fx.get("os_goals") or []),
            "os_accounts_count": len(fx.get("os_accounts") or []),
            "safety_gate": (fx.get("safety_gate") or {}).get("status"),
        }
        for pid, fx in personas.items()
    }
    return out


def _demo_user_ids() -> list[str]:
    ids: list[str] = []
    try:
        from welora.auth import PARTNER_USER_ID
        from welora.partner_demo_seed import DEMO_PERSONA_ALIASES

        ids.append(PARTNER_USER_ID)
        ids.extend(m["user_id"] for m in DEMO_PERSONA_ALIASES.values())
    except Exception:
        pass
    ids.extend(["user_p2", "user_p4"])
    return ids


def _drop_memory_caches() -> None:
    """After a rolled-back seed, forget in-process copies so readers fall back to the DB."""
    try:
        from welora import goals_api
        from welora import mastery
        from welora import onboarding as ob

        for uid in _demo_user_ids():
            goals_api.USER_FLAGS.pop(uid, None)
            ob.DNA_BY_USER.pop(uid, None)
            ob.CONSTITUTION_BY_USER.pop(uid, None)
            mastery._STORE.pop(uid, None)
            for sid, s in list(ob.SESSIONS.items()):
                if getattr(s, "user_id", None) == uid:
                    ob.SESSIONS.pop(sid, None)
    except Exception:  # pragma: no cover
        pass


def run_demo_seed(*, wait: bool = True, url: Optional[str] = None) -> dict[str, Any]:
    """Seed P1–P6 atomically. Raises SeedLocked when ``wait=False`` and someone else is seeding."""
    from welora.auth import guest_demo_enabled

    if not guest_demo_enabled():
        from welora import auth as auth_svc

        return auth_svc.service_demo_seed()[1]

    if not _PROCESS_LOCK.acquire(blocking=wait):
        raise SeedLocked("demo seed already running in this process")
    try:
        if not _db_mode():
            return _seed_all()

        from welora.db.connection import ambient_transaction, detect_dialect
        from welora.db.migrate import migrate

        dialect = detect_dialect(url)
        try:
            migrate(url)  # DDL outside the seed transaction (SQLite executescript commits)
            with ambient_transaction(url) as conn:
                if dialect == "postgres":
                    if wait:
                        conn.execute("SELECT pg_advisory_xact_lock(?)", (ADVISORY_LOCK_KEY,))
                    else:
                        row = conn.execute(
                            "SELECT pg_try_advisory_xact_lock(?) AS ok", (ADVISORY_LOCK_KEY,)
                        ).fetchone()
                        if not (row and row["ok"]):
                            raise SeedLocked("demo seed already running on another instance")
                return _seed_all()
        except SeedLocked:
            raise
        except Exception as e:
            _drop_memory_caches()
            if dialect == "sqlite" and "locked" in str(e).lower() and not wait:
                raise SeedLocked("demo seed: SQLite database is locked by another writer") from e
            raise
    finally:
        _PROCESS_LOCK.release()


def startup_seed_once() -> dict[str, Any]:
    """Run once at startup. Never raises; records the outcome in LAST_RUN and the log."""
    ok, why = autoseed_wanted()
    if not ok:
        LAST_RUN.clear()
        LAST_RUN.update({"status": "skipped", "reason": why})
        log.info("demo seed skipped: %s", why)
        return dict(LAST_RUN)
    try:
        out = run_demo_seed(wait=False)
        rich = out.get("rich") or {}
        LAST_RUN.clear()
        LAST_RUN.update({"status": "ok", "p2_gate": rich.get("p2_gate"), "p4_gate": rich.get("p4_gate")})
        log.info("demo seed ok (P2 gate=%s, P4 gate=%s)", rich.get("p2_gate"), rich.get("p4_gate"))
    except SeedLocked as e:
        LAST_RUN.clear()
        LAST_RUN.update({"status": "skipped", "reason": str(e)})
        log.info("demo seed skipped: %s", e)
    except Exception as e:  # startup must not crash because of demo data
        LAST_RUN.clear()
        LAST_RUN.update({"status": "failed", "error": type(e).__name__})
        log.exception("demo seed failed (startup continues): %s", e)
    return dict(LAST_RUN)


def start_background_seed() -> Optional[threading.Thread]:
    ok, why = autoseed_wanted()
    if not ok:
        LAST_RUN.clear()
        LAST_RUN.update({"status": "skipped", "reason": why})
        log.info("demo seed skipped: %s", why)
        return None
    t = threading.Thread(target=startup_seed_once, name="welora-demo-seed", daemon=True)
    t.start()
    return t
