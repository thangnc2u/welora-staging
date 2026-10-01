"""Subprocess scenarios for GP P0b (KUAT hardening + persisted Academy progress) on a DB store
(SQLite, or PG17 when the parent passes a postgres WELORA_DB_URL). "Restart" = a second, fresh
process on the same database. Usage: python -m tests._p0b_dbmode <scenario>  → RESULT=<json>.
State between the two processes of one test is passed via P0B_STATE (json).
"""

from __future__ import annotations

import json
import os
import sys
import uuid

ESS = 10_000_000
FORBIDDEN_KEYS = {"correct", "is_correct", "answer", "answers", "perm", "served", "served_json", "detail_per_question"}


def _client():
    from fastapi.testclient import TestClient

    from welora.api.app import create_app

    return TestClient(create_app())


def _h(tok, ip=None):
    h = {"Authorization": "Bearer " + tok}
    if ip:
        h["CF-Connecting-IP"] = ip
    return h


def _guest(c):
    d = c.post("/auth/device", json={"device_id": "web-" + uuid.uuid4().hex[:12]}).json()
    return d["user_id"], d["token"]


def _keys(obj, found=None):
    found = set() if found is None else found
    if isinstance(obj, dict):
        for k, v in obj.items():
            found.add(k)
            _keys(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _keys(v, found)
    return found


def _canonical_ids_in(obj) -> list[str]:
    from welora import academy

    ids = {q["id"] for qs in academy.QUESTIONS.values() for q in qs}
    blob = json.dumps(obj, ensure_ascii=False)
    return sorted(i for i in ids if f'"{i}"' in blob)


def _tree_summary(c, uid, tok):
    t = c.get("/academy/tree", params={"user_id": uid}, headers=_h(tok)).json()
    st = {n["node_id"]: n["status"] for n in t["nodes"] if n["node_id"] in ("N02-01", "N02-02", "N02-03")}
    return {"xp": t["xp"], "status": st, "badges": t["badges"]}


# --------------------------------------------------------------------------- persistence
def scenario_persist_write() -> dict:
    from tests._kuat import pass_kuat_http, solve

    c = _client()
    uid, tok = _guest(c)
    p1 = pass_kuat_http(c, uid, _h(tok), "N02-01")
    fail = pass_kuat_http(c, uid, _h(tok), "N02-02", correct=False)
    # an attempt issued here and submitted by ANOTHER process after the restart
    st = c.post("/academy/kuat/start", json={"user_id": uid, "node_id": "N02-02"}, headers=_h(tok)).json()
    return {"uid": uid, "tok": tok, "p1": [p1[0], p1[1]], "fail": [fail[0], fail[1]],
            "attempt_id": st["attempt_id"], "answers": solve("N02-02", st["questions"]),
            "tree": _tree_summary(c, uid, tok)}


def scenario_persist_read() -> dict:
    from welora.db.connection import get_connection

    s = json.loads(os.environ["P0B_STATE"])
    c = _client()
    uid, tok = s["uid"], s["tok"]
    before = _tree_summary(c, uid, tok)
    node = c.get("/academy/nodes/N02-01", params={"user_id": uid}, headers=_h(tok)).json()
    sub = c.post("/academy/kuat", json={"user_id": uid, "node_id": "N02-02", "attempt_id": s["attempt_id"],
                                        "answers": s["answers"]}, headers=_h(tok))
    again = c.post("/academy/kuat", json={"user_id": uid, "node_id": "N02-02", "attempt_id": s["attempt_id"],
                                          "answers": s["answers"]}, headers=_h(tok))
    gate = c.get(f"/users/{uid}/mastery", headers=_h(tok)).json()
    conn = get_connection(None)
    try:
        prof = conn.execute("SELECT profile_json, rev FROM academy_profiles WHERE user_id=?", (uid,)).fetchone()
        cols = [r[1] if not hasattr(r, "keys") else r["name"] for r in conn.execute(
            "PRAGMA table_info(academy_kuat_attempts)").fetchall()] if os.environ["WELORA_STORE"] == "sqlite" else \
            [r["column_name"] for r in conn.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='academy_kuat_attempts'").fetchall()]
        outcomes = sorted(r["outcome"] or "open" for r in conn.execute(
            "SELECT outcome FROM academy_kuat_attempts WHERE user_id=?", (uid,)).fetchall())
    finally:
        conn.close()
    return {"before": before, "read_kept": "N02-01" in json.loads(prof["profile_json"])["read"],
            "last_kuat_keys": sorted((node.get("last_kuat") or {}).keys()),
            "submit": [sub.status_code, (sub.json().get("kuat_result") or {}).get("passed")],
            "again": [again.status_code, (again.json().get("detail") or {}).get("error_code")],
            "after": _tree_summary(c, uid, tok), "mastery": gate.get("state"),
            "profile_forbidden": sorted(_keys(json.loads(prof["profile_json"])) & FORBIDDEN_KEYS),
            "attempt_columns": sorted(cols), "outcomes": outcomes}


# --------------------------------------------------------------------------- health score
def scenario_health_write() -> dict:
    from tests._kuat import pass_kuat_http

    c = _client()
    uid, tok = _guest(c)
    c.post("/goals", json={"user_id": uid, "type": "emergency_fund", "essential_expense_monthly": ESS,
                           "current_amount": 3 * ESS}, headers=_h(tok))
    pass_kuat_http(c, uid, _h(tok), "N02-01")
    pass_kuat_http(c, uid, _h(tok), "N02-02")
    g = c.get(f"/users/{uid}/safety-gate", headers=_h(tok)).json()
    h = c.get(f"/users/{uid}/health-score", headers=_h(tok)).json()
    return {"uid": uid, "tok": tok, "gate": g["status"], "health_gate": h["safety_gate"]["status"]}


def scenario_health_read() -> dict:
    s = json.loads(os.environ["P0B_STATE"])
    c = _client()
    h = c.get(f"/users/{s['uid']}/health-score", headers=_h(s["tok"])).json()  # health FIRST (cold process)
    g = c.get(f"/users/{s['uid']}/safety-gate", headers=_h(s["tok"])).json()
    return {"gate": g["status"], "health_gate": h["safety_gate"]["status"],
            "health_mastery": h["safety_gate"].get("mastery_no_efund_invest") or h["safety_gate"].get("reasons")}


# --------------------------------------------------------------------------- brute force
def scenario_bruteforce() -> dict:
    """A script that probes the gate KUAT by enumerating answers is locked out after 3 failures,
    never sees per-question verdicts and never passes by guessing within the budget."""
    import itertools

    from tests._kuat import pass_kuat_http

    c = _client()
    uid, tok = _guest(c)
    ip = "198.51.100.%d" % (uuid.uuid4().int % 200 + 1)
    h = _h(tok, ip)
    pass_kuat_http(c, uid, h, "N02-01")
    c.post("/academy/nodes/N02-02/read", json={"user_id": uid, "node_id": "N02-02"}, headers=h)
    log, seen_keys, canon = [], set(), []
    locked = None
    for combo in itertools.product(range(3), repeat=5):
        st = c.post("/academy/kuat/start", json={"user_id": uid, "node_id": "N02-02"}, headers=h)
        if st.status_code == 429:
            locked = {"where": "start", "status": 429, "retry_after_header": st.headers.get("Retry-After"),
                      "detail": st.json()["detail"]}
            break
        a = st.json()
        seen_keys |= _keys(a)
        canon += _canonical_ids_in(a)
        answers = []
        from tests._kuat import solve

        right = solve("N02-02", a["questions"])  # used only to make sure the probe is WRONG
        for i, q in enumerate(a["questions"]):
            ch = combo[i] % len(q["choices"])
            if ch == right[i]["choice"]:
                ch = (ch + 1) % len(q["choices"])
            answers.append({"question_id": q["id"], "choice": ch})
        r = c.post("/academy/kuat", json={"user_id": uid, "node_id": "N02-02", "attempt_id": a["attempt_id"],
                                          "answers": answers}, headers=h)
        if r.status_code == 429:
            locked = {"where": "submit", "status": 429, "detail": r.json()["detail"]}
            break
        body = r.json()
        seen_keys |= _keys(body)
        canon += _canonical_ids_in(body)
        log.append([r.status_code, body["kuat_result"]["passed"]])
    node = c.get("/academy/nodes/N02-02", params={"user_id": uid}, headers=h).json()
    tree = c.get("/academy/tree", params={"user_id": uid}, headers=h).json()
    seen_keys |= _keys(node) | _keys(tree)
    sub = c.post("/academy/kuat", json={"user_id": uid, "node_id": "N02-02", "answers": []}, headers=h)
    # a second account from the same IP keeps its own per-user budget (IP cap is higher)
    uid2, tok2 = _guest(c)
    st2 = pass_kuat_http(c, uid2, _h(tok2, ip), "N02-01")
    return {"log": log, "locked": locked, "node_questions": len(node.get("questions") or []),
            "node_cooldown": (node.get("kuat") or {}).get("cooldown"), "submit_while_locked": sub.status_code,
            "forbidden_keys": sorted(seen_keys & FORBIDDEN_KEYS), "canonical_ids": sorted(set(canon)),
            "mastery": c.get(f"/users/{uid}/mastery", headers=h).json().get("state"),
            "other_user_same_ip": [st2[0], st2[1]]}


# --------------------------------------------------------------------------- guest claim
def scenario_claim_untrusted_account() -> dict:
    from tests._followup2_dbmode import _claim, _register
    from tests._kuat import pass_kuat_http
    from welora.db.connection import get_connection

    c = _client()

    def row(u):
        conn = get_connection(None)
        try:
            r = conn.execute("SELECT mastery_no_efund_invest AS m, mastery_source AS s, has_dangerous_debt AS d "
                             "FROM user_flags WHERE user_id=?", (u,)).fetchone()
            return [r["m"], r["s"], int(r["d"])] if r else None
        finally:
            conn.close()

    def put(u, m, s, d):
        conn = get_connection(None)
        try:
            conn.execute("INSERT INTO user_flags(user_id, has_dangerous_debt, mastery_no_efund_invest, mastery_source) "
                         "VALUES (?,?,?,?)", (u, d, m, s))
            conn.commit()
        finally:
            conn.close()

    out = {}
    # A) account has an OLD untrusted row (no source) → receives the guest's real academy mastery
    gu, gt = _guest(c)
    pass_kuat_http(c, gu, _h(gt), "N02-01")
    pass_kuat_http(c, gu, _h(gt), "N02-02")
    acc = _register(c, "p0b-a@example.test", "192.0.2.201")
    put(acc["user_id"], "apply", None, 1)  # legacy self-set row + the account's own debt flag
    out["a_before"] = c.get(f"/users/{acc['user_id']}/mastery", headers=_h(acc["token"])).json()["state"]
    code, body = _claim(c, acc["token"], gt)
    out["a_claim"] = [code, body.get("moved", {}).get("mastery"), body.get("skipped", {}).get("user_flags")]
    out["a_row"] = row(acc["user_id"])
    out["a_mastery"] = c.get(f"/users/{acc['user_id']}/mastery", headers=_h(acc["token"])).json()["state"]
    out["a_tree"] = _tree_summary(c, acc["user_id"], acc["token"])
    # B) account row with a TRUSTED source wins
    gu, gt = _guest(c)
    pass_kuat_http(c, gu, _h(gt), "N02-01")
    pass_kuat_http(c, gu, _h(gt), "N02-02")
    acc = _register(c, "p0b-b@example.test", "192.0.2.202")
    put(acc["user_id"], "familiar", "academy", 0)
    code, body = _claim(c, acc["token"], gt)
    out["b_claim"] = [code, body.get("moved", {}).get("mastery"), body.get("skipped", {}).get("user_flags")]
    out["b_row"] = row(acc["user_id"])
    # C) the guest's untrusted (self-set, no source) mastery never transfers
    gu, gt = _guest(c)
    put(gu, "apply", None, 0)
    acc = _register(c, "p0b-c@example.test", "192.0.2.203")
    put(acc["user_id"], "not_started", None, 0)
    code, body = _claim(c, acc["token"], gt)
    out["c_claim"] = [code, body.get("moved", {}).get("mastery")]
    out["c_mastery"] = c.get(f"/users/{acc['user_id']}/mastery", headers=_h(acc["token"])).json()["state"]
    # D) account already has Academy progress → merged (account kept + guest's mastered nodes)
    gu, gt = _guest(c)
    pass_kuat_http(c, gu, _h(gt), "N02-01")
    acc = _register(c, "p0b-d@example.test", "192.0.2.204")
    pass_kuat_http(c, acc["user_id"], _h(acc["token"]), "N01-01")
    code, body = _claim(c, acc["token"], gt)
    out["d_claim"] = [code, body.get("moved", {}).get("academy_profiles")]
    t = c.get("/academy/tree", params={"user_id": acc["user_id"]}, headers=_h(acc["token"])).json()
    out["d_tree"] = {"xp": t["xp"], "N01-01": next(n["status"] for n in t["nodes"] if n["node_id"] == "N01-01"),
                     "N02-01": next(n["status"] for n in t["nodes"] if n["node_id"] == "N02-01")}
    return out


if __name__ == "__main__":
    print("RESULT=" + json.dumps(globals()["scenario_" + sys.argv[1]](), default=str))
