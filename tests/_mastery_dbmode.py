"""Subprocess scenarios for P0 "mastery chỉ từ server" that need a DB store from import time
(SQLite, or PG17 when the parent passes a postgres WELORA_DB_URL).
Usage: python -m tests._mastery_dbmode <scenario>  → prints one RESULT=<json> line.
"""

from __future__ import annotations

import json
import sys
import uuid

ESS = 10_000_000


def _client():
    from fastapi.testclient import TestClient

    from welora.api.app import create_app

    return TestClient(create_app())


def _h(tok):
    return {"Authorization": "Bearer " + tok}


def _guest(c):
    d = c.post("/auth/device", json={"device_id": "web-" + uuid.uuid4().hex[:12]}).json()
    return d["user_id"], d["token"]


def _gate(c, uid, tok):
    g = c.get(f"/users/{uid}/safety-gate", headers=_h(tok)).json()
    return [g.get("status"), sorted(g.get("reasons") or [])]


def _row(uid):
    from welora.db.connection import get_connection

    conn = get_connection(None)
    try:
        r = conn.execute("SELECT mastery_no_efund_invest AS m, mastery_source AS s, has_dangerous_debt AS d "
                         "FROM user_flags WHERE user_id=?", (uid,)).fetchone()
        return [r["m"], r["s"], int(r["d"])] if r else None
    finally:
        conn.close()


def _pass_kuat(c, uid, tok, node_id):
    from welora import academy

    answers = [{"question_id": q["id"], "choice": q["answer"]} for q in academy.QUESTIONS[node_id]]
    c.post(f"/academy/nodes/{node_id}/read", json={"user_id": uid, "node_id": node_id}, headers=_h(tok))
    r = c.post("/academy/kuat", json={"user_id": uid, "node_id": node_id, "answers": answers}, headers=_h(tok))
    return r.status_code, (r.json().get("kuat_result") or {}).get("passed")


def scenario_mastery_server_only() -> dict:
    from tests._followup_dbmode import _forget_process_memory
    from welora import academy
    from welora.db.connection import get_connection

    c = _client()
    out: dict = {}

    # 1) the GP UAT exploit chain: fund self-reported to 3 months + PATCH mastery "apply"
    uid, tok = _guest(c)
    g = c.post("/goals", json={"user_id": uid, "type": "emergency_fund", "essential_expense_monthly": ESS,
                               "current_amount": 0}, headers=_h(tok)).json()
    out["progress"] = c.patch(f"/goals/{g['goal_id']}/progress", json={"set_amount": 3 * ESS},
                              headers=_h(tok)).status_code
    p = c.patch(f"/users/{uid}/mastery", json={"state": "apply", "node_id": "no_efund_invest"}, headers=_h(tok))
    out["patch"] = [p.status_code, (p.json().get("detail") or {}).get("error_code")]
    out["patch_mastered_bad_body"] = c.patch(f"/users/{uid}/mastery", content=b"{not json",
                                             headers={**_h(tok), "Content-Type": "application/json"}).status_code
    out["patch_no_token"] = c.patch(f"/users/{uid}/mastery", json={"state": "apply"}).status_code
    out["gate_after_exploit"] = _gate(c, uid, tok)
    out["mastery_after_exploit"] = c.get(f"/users/{uid}/mastery", headers=_h(tok)).json().get("state")
    out["row_after_exploit"] = _row(uid)

    # 2) legacy row written by the OLD self-service PATCH (no source) → not trusted
    uid2, tok2 = _guest(c)
    c.post("/goals", json={"user_id": uid2, "type": "emergency_fund", "essential_expense_monthly": ESS,
                           "current_amount": 3 * ESS}, headers=_h(tok2))
    conn = get_connection(None)
    try:
        conn.execute("INSERT INTO user_flags(user_id, mastery_no_efund_invest) VALUES (?, 'apply')", (uid2,))
        conn.commit()
    finally:
        conn.close()
    _forget_process_memory()
    out["legacy_gate"] = _gate(c, uid2, tok2)
    out["legacy_mastery"] = c.get(f"/users/{uid2}/mastery", headers=_h(tok2)).json().get("state")

    # 3) the real Academy path (KUAT graded on the server) opens the gate and is persisted
    out["kuat_locked"] = c.post("/academy/kuat", json={"user_id": uid, "node_id": academy.GATE_NODE, "answers": []},
                                headers=_h(tok)).status_code  # prerequisite N02-01 not passed yet
    out["kuat_prereq"] = list(_pass_kuat(c, uid, tok, "N02-01"))
    out["gate_after_prereq"] = _gate(c, uid, tok)
    out["kuat_wrong"] = (lambda r: [r.status_code, (r.json().get("kuat_result") or {}).get("passed")])(
        c.post("/academy/kuat", json={"user_id": uid, "node_id": academy.GATE_NODE,
                                      "answers": [{"question_id": q["id"], "choice": (q["answer"] + 1) % 3}
                                                  for q in academy.QUESTIONS[academy.GATE_NODE]]},
               headers=_h(tok)))
    out["gate_after_wrong"] = _gate(c, uid, tok)
    out["kuat_gate"] = list(_pass_kuat(c, uid, tok, academy.GATE_NODE))
    out["gate_after_kuat"] = _gate(c, uid, tok)
    out["row_after_kuat"] = _row(uid)
    _forget_process_memory()  # another instance / after a restart reads the trusted DB row
    out["gate_after_restart"] = _gate(c, uid, tok)
    out["mastery_after_restart"] = c.get(f"/users/{uid}/mastery", headers=_h(tok)).json()

    # 4) debt-goal progress updates debt flags but never touches mastery
    uid3, tok3 = _guest(c)
    _pass_kuat(c, uid3, tok3, "N02-01")
    _pass_kuat(c, uid3, tok3, academy.GATE_NODE)
    d = c.post("/goals", json={"user_id": uid3, "type": "debt_payoff", "target_amount": 5_000_000,
                               "current_amount": 0}, headers=_h(tok3)).json()
    before = _row(uid3)
    _forget_process_memory()
    c.patch(f"/goals/{d['goal_id']}/progress", json={"set_amount": 1_000_000}, headers=_h(tok3))
    out["debt_sync_row"] = [before, _row(uid3)]
    return out


def scenario_demo_seed_gates() -> dict:
    """Startup demo seed (same runner as boot) → P2 passed, P4 not_passed, rows sourced 'seed',
    also from a fresh process memory (another instance)."""
    from tests._followup_dbmode import _forget_process_memory, _gates
    from welora.demo_seed_runner import run_demo_seed
    from welora.partner_demo_seed import DEMO_PERSONA_ALIASES as A

    run_demo_seed()
    first = _gates()
    _forget_process_memory()
    fresh = _gates()
    rows = {pid: _row(m["user_id"]) for pid, m in A.items()}
    return {"first": first, "fresh": fresh, "sources": sorted({r[1] for r in rows.values() if r}),
            "p2_row": rows.get("P2"), "p4_row": rows.get("P4")}


def scenario_claim_counts() -> dict:
    """GP UAT (b): the claim response counts the DNA / constitution actually transferred."""
    c = _client()
    from tests._followup2_dbmode import _claim, _guest_onboard, _register

    a = _guest_onboard(c, ESS)
    x = _register(c, "count-x@example.test", "192.0.2.180")
    code, body = _claim(c, x["token"], a["token"])
    dna = c.get(f"/users/{x['user_id']}/dna", headers=_h(x["token"]))
    return {"code": code, "moved": body.get("moved"), "dna_status": dna.status_code}


if __name__ == "__main__":
    print("RESULT=" + json.dumps(globals()["scenario_" + sys.argv[1]](), default=str))
