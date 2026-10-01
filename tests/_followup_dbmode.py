"""Subprocess scenarios for P0 follow-up tests that need a DB store from import time.

The OS stores (goals/accounts/transactions/categories) are chosen when their modules are imported
(and partner_demo_seed binds them by name), so DB-mode scenarios run in a fresh interpreter with
WELORA_DB_URL / WELORA_STORE already set. Usage: python -m tests._followup_dbmode <scenario>
Prints one JSON line prefixed with RESULT=.
"""

from __future__ import annotations

import json
import os
import sys
import threading


def _counts() -> dict:
    from welora.db.connection import get_connection

    conn = get_connection(None)
    try:
        out = {}
        for t in ("users", "goals", "os_accounts", "os_transactions", "os_categories",
                  "onboarding_sessions", "user_flags", "dna_profiles"):
            try:
                out[t] = int(conn.execute(f"SELECT COUNT(*) AS n FROM {t}").fetchone()["n"])
            except Exception:
                out[t] = None
        return out
    finally:
        conn.close()


def _gates() -> dict:
    from welora import goals_api
    from welora.partner_demo_seed import DEMO_PERSONA_ALIASES as A

    out = {}
    for pid, m in A.items():
        g = goals_api.service_safety_gate(m["user_id"])[1]
        out[pid] = [g.get("status"), bool(g.get("has_dangerous_debt"))]
    return out


def _forget_process_memory() -> None:
    """Simulate a fresh instance after a deploy: drop every in-process cache."""
    from welora import goals_api, mastery
    from welora import onboarding as ob

    goals_api.USER_FLAGS.clear()
    mastery.reset_mastery_store()
    ob.reset_onboarding_stores()


def scenario_seed_idempotent() -> dict:
    from welora.demo_seed_runner import run_demo_seed

    r1 = run_demo_seed()
    c1 = _counts()
    r2 = run_demo_seed()
    c2 = _counts()
    r3 = run_demo_seed()
    c3 = _counts()
    g_hot = _gates()
    _forget_process_memory()
    g_cold = _gates()
    return {
        "counts": [c1, c2, c3],
        "rich_gates": [(r.get("rich") or {}).get("p2_gate") for r in (r1, r2, r3)]
        + [(r.get("rich") or {}).get("p4_gate") for r in (r1, r2, r3)],
        "fixture_personas": sorted((r3.get("personas") or {}).keys()),
        "email": r3.get("email"),
        "gates_hot": g_hot,
        "gates_cold": g_cold,
    }


def scenario_seed_no_flap() -> dict:
    from welora import goals_api
    from welora.demo_seed_runner import run_demo_seed
    from welora.partner_demo_seed import DEMO_PERSONA_ALIASES as A

    run_demo_seed()
    p2, p4 = A["P2"]["user_id"], A["P4"]["user_id"]
    seen: dict = {"P2": {}, "P4": {}}
    errors: list = []
    stop = threading.Event()
    started = threading.Event()

    def reader():
        while not stop.is_set():
            for k, u in (("P2", p2), ("P4", p4)):
                try:
                    g = goals_api.service_safety_gate(u)[1]
                    key = f"{g.get('status')}|{bool(g.get('has_dangerous_debt'))}"
                    seen[k][key] = seen[k].get(key, 0) + 1
                except Exception as e:  # pragma: no cover
                    errors.append(f"{type(e).__name__}: {e}"[:120])
            started.set()

    t = threading.Thread(target=reader, daemon=True)
    t.start()
    started.wait(30)
    for _ in range(3):
        run_demo_seed()
    stop.set()
    t.join(60)
    return {"seen": seen, "errors": errors}


def scenario_seed_rollback() -> dict:
    """A failure half-way through must leave the previous complete seed untouched."""
    from welora import partner_demo_seed as pds
    from welora.demo_seed_runner import run_demo_seed, startup_seed_once

    run_demo_seed()
    before = _counts()
    g_before = _gates()
    orig = pds.seed_p4_on_user

    def boom(user_id):
        raise RuntimeError("simulated failure after P1-P3 were rewritten")

    pds.seed_p4_on_user = boom
    raised = None
    try:
        run_demo_seed()
    except Exception as e:
        raised = type(e).__name__
    os.environ["WELORA_DEMO_AUTOSEED"] = "1"
    startup = startup_seed_once()  # must not raise
    pds.seed_p4_on_user = orig
    after = _counts()
    _forget_process_memory()
    g_after = _gates()
    return {"raised": raised, "startup": startup, "before": before, "after": after,
            "g_before": g_before, "g_after": g_after}


def scenario_seed_disabled() -> dict:
    from welora.demo_seed_runner import autoseed_wanted, run_demo_seed, startup_seed_once

    out = run_demo_seed()
    return {"run": out, "wanted": list(autoseed_wanted()), "startup": startup_seed_once(), "counts": _counts()}


def scenario_seed_locked() -> dict:
    """Another instance holds the seed lock → startup seed skips (never blocks/crashes)."""
    from welora.db.connection import detect_dialect, get_connection
    from welora.db.migrate import migrate
    from welora import demo_seed_runner as r

    migrate(None)
    holder = get_connection(None)
    if detect_dialect(None) == "postgres":
        holder.execute("SELECT pg_advisory_xact_lock(?)", (r.ADVISORY_LOCK_KEY,))
    else:
        holder.execute("BEGIN IMMEDIATE")
    locked_exc = None
    try:
        r.run_demo_seed(wait=False)
    except r.SeedLocked as e:
        locked_exc = "SeedLocked"
    except Exception as e:  # pragma: no cover
        locked_exc = type(e).__name__ + ":" + str(e)[:80]
    os.environ["WELORA_DEMO_AUTOSEED"] = "1"
    startup = r.startup_seed_once()
    holder.rollback()
    holder.close()
    ok_after = r.run_demo_seed(wait=False)
    return {"locked": locked_exc, "startup": startup, "after_release": (ok_after.get("rich") or {}).get("p2_gate")}


def scenario_lifespan_autoseed() -> dict:
    from fastapi.testclient import TestClient

    from welora import demo_seed_runner as r
    from welora.api.app import create_app

    os.environ["WELORA_DEMO_AUTOSEED"] = "1"
    started = []
    orig = r.start_background_seed

    def spy():
        t = orig()
        started.append(t)
        return t

    r.start_background_seed = spy
    with TestClient(create_app()) as c:
        if started and started[0] is not None:
            started[0].join(120)
        health = c.get("/health").json()
    _forget_process_memory()
    return {"health_demo_seed": health.get("demo_seed"), "gates_cold": _gates()}


def scenario_guest_onboarding() -> dict:
    from fastapi.testclient import TestClient

    from welora.api.app import create_app

    c = TestClient(create_app())
    page = c.get("/app/onboarding")
    import uuid as _uuid
    d = c.post("/auth/device", json={"device_id": "web-" + _uuid.uuid4().hex[:12]})
    tok = d.json()["token"]
    uid = d.json()["user_id"]
    h = {"Authorization": "Bearer " + tok}
    s = c.post("/onboarding/session", json={"user_id": uid}, headers=h)
    sid = s.json()["session_id"]
    steps = [
        (1, {"household": "solo", "life_stage": "solo", "income_stability": "stable", "family_context": "alone"}),
        (2, {"essential_expense_monthly": 12_000_000, "emergency_fund_months_self": 0,
             "has_dangerous_debt_self": False, "near_term_priority": "safety"}),
        (3, {"surplus_habit": "hold", "risk_tolerance": 5, "agent_role_preference": "advisor_only"}),
        (4, {}),
    ]
    codes = []
    for n, body in steps:
        codes.append(c.patch(f"/onboarding/session/{sid}/step/{n}", json=body, headers=h).status_code)
    done = c.post(f"/onboarding/session/{sid}/complete", headers=h)
    goal = c.post("/goals", json={"user_id": uid, "type": "emergency_fund", "essential_expense_monthly": 12_000_000,
                                  "current_amount": 0, "linked_from_onboarding": True}, headers=h)
    again = c.post("/goals", json={"user_id": uid, "type": "emergency_fund", "essential_expense_monthly": 12_000_000,
                                   "current_amount": 0, "linked_from_onboarding": True}, headers=h)
    goals = c.get("/goals", params={"user_id": uid}, headers=h)
    gate = c.get(f"/users/{uid}/safety-gate", headers=h)
    anon_goal = c.post("/goals", json={"user_id": uid, "type": "emergency_fund", "essential_expense_monthly": 1})
    return {
        "page": page.status_code, "page_gate": "/static/auth-gate.js" in page.text,
        "device": d.status_code, "session": s.status_code, "steps": codes, "complete": done.status_code,
        "goal": goal.status_code, "goal_type": (goal.json() or {}).get("type"),
        "goal_essential": (goal.json() or {}).get("essential_expense_monthly"),
        "goal_linked": (goal.json() or {}).get("linked_from_onboarding"),
        "again": again.status_code, "goals_count": len(goals.json().get("items") or []),
        "gate": gate.status_code, "gate_status": gate.json().get("status"), "anon_goal": anon_goal.status_code,
    }


if __name__ == "__main__":
    name = sys.argv[1]
    result = globals()["scenario_" + name]()
    print("RESULT=" + json.dumps(result, default=str))


def run_scenario(name: str, env: dict, timeout: int = 300) -> dict:
    """Run a scenario in a fresh interpreter (helper for the unittest side)."""
    import subprocess
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    full = {k: v for k, v in os.environ.items() if not k.startswith("WELORA_")}
    full.update({"PYTHONPATH": str(root), "WELORA_DEMO_AUTOSEED": "0"})
    full.update(env)
    p = subprocess.run([sys.executable, "-m", "tests._followup_dbmode", name], cwd=str(root), env=full,
                       capture_output=True, text=True, timeout=timeout)
    for line in reversed(p.stdout.splitlines()):
        if line.startswith("RESULT="):
            return json.loads(line[len("RESULT="):])
    raise AssertionError(f"scenario {name} failed rc={p.returncode}\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}")
