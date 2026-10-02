"""Subprocess scenarios for ticket "GP follow-up sau OTP #244 + Academy #245" (Academy items 9, 10,
13, 14) on a DB store (SQLite, or PG17 when the parent passes a postgres WELORA_DB_URL).
Usage: python -m tests._fu245_dbmode <scenario> → RESULT=<json>."""

from __future__ import annotations

import json
import os
import sys

from tests._acfu_dbmode import _mastery, _session_rows, _tree
from tests._k019_dbmode import _q, _x
from tests._p0b_dbmode import _client, _demo_login, _guest, _h, _phone_otp_account, _rand_ip


def _gate(c, uid, tok):
    g = c.get(f"/users/{uid}/safety-gate", headers=_h(tok)).json()
    return {"m": g.get("mastery_no_efund_invest"), "mastery_reason": "mastery_missing" in (g.get("reasons") or []),
            "block": (g.get("mastery") or {}).get("state")}


def _hs(c, uid, tok):
    r = c.get(f"/users/{uid}/health-score", headers=_h(tok))
    return r.status_code, json.dumps(r.json(), ensure_ascii=False)


# --------------------------------------------------------------------------- item 14
def scenario_session_gate() -> dict:
    """Two testers on P4 (gate not passed in the seed): A passes N02-01 + N02-02 in its session →
    A's Safety Gate / mastery / Health Score / Pre-Rule context see "apply"; B and the persona's
    shared flags stay at the seed state; a regular account is unchanged (shared flags, as before)."""
    from tests._kuat import pass_kuat_http
    from tests._p0b_dbmode import scenario_seed_demo
    from welora import academy, pre_rule_service

    seeded = scenario_seed_demo()
    c = _client()
    a, b = _demo_login(c, "P4"), _demo_login(c, "P4")
    out: dict = {"before": [_gate(c, *a), _gate(c, *b)]}
    out["passes"] = [pass_kuat_http(c, a[0], _h(a[1]), n)[:2] for n in ("N02-01", "N02-02")]
    out["after"] = [_gate(c, *a), _gate(c, *b)]
    out["mastery_api"] = [_mastery(c, *a), _mastery(c, *b)]
    out["flags"] = (_q("SELECT mastery_no_efund_invest AS m, mastery_source AS s FROM user_flags WHERE user_id=?",
                       (a[0],)) or [{}])[0]
    # Pre-Rule context of each session (in-process, with the request session set as the API does)
    ctx = []
    for uid, tok in (a, b):
        h = academy.REQUEST_SESSION.set((tok, ""))
        try:
            ctx.append(pre_rule_service.context_from_user(uid).safety_gate.mastery_no_efund_invest)
        finally:
            academy.REQUEST_SESSION.reset(h)
    out["pre_rule_ctx"] = ctx
    out["no_request_session"] = pre_rule_service.context_from_user(a[0]).safety_gate.mastery_no_efund_invest
    out["hs_status"] = [_hs(c, *a)[0], _hs(c, *b)[0]]
    # another session's token cannot borrow A's gate for B's request (token owner must match)
    h = academy.REQUEST_SESSION.set((a[1], ""))
    try:
        out["foreign_uid"] = academy.session_gate_mastery(seeded.get("P2") or "nobody")
    finally:
        academy.REQUEST_SESSION.reset(h)
    # a regular (verified) account: shared mastery from its own pass, exactly as before
    acc = _phone_otp_account(c)
    hr = _h(acc["token"], _rand_ip("203.0.113."))
    for n in ("N02-01", "N02-02"):
        pass_kuat_http(c, acc["user_id"], hr, n)
    out["regular"] = [_mastery(c, acc["user_id"], acc["token"]),
                      (_q("SELECT mastery_no_efund_invest AS m, mastery_source AS s FROM user_flags WHERE user_id=?",
                          (acc["user_id"],)) or [{}])[0]]
    return out


def scenario_session_gate_flag_off() -> dict:
    """WELORA_GUEST_DEMO=0: no session profiles → nothing overlays the shared gate."""
    from welora import academy

    c = _client()
    from tests._p0b_dbmode import scenario_seed_demo

    os.environ["WELORA_GUEST_DEMO"] = "1"
    scenario_seed_demo()
    os.environ["WELORA_GUEST_DEMO"] = "0"
    a = _demo_login(c, "P4")
    h = academy.REQUEST_SESSION.set((a[1], ""))
    try:
        return {"key": academy.profile_key(a[0], session=a[1]), "uid": a[0],
                "overlay": academy.overlay_session_mastery(a[0], "learning")}
    finally:
        academy.REQUEST_SESSION.reset(h)


# --------------------------------------------------------------------------- item 13
def scenario_demo_reset() -> dict:
    from tests._kuat import pass_kuat_http
    from tests._p0b_dbmode import scenario_seed_demo

    scenario_seed_demo()
    c = _client()
    a, b = _demo_login(c, "P4"), _demo_login(c, "P4")
    p2 = _demo_login(c, "P2")
    c.post("/academy/nodes/N01-01/read", json={"user_id": a[0], "node_id": "N01-01"}, headers=_h(a[1]))
    pass_kuat_http(c, a[0], _h(a[1]), "N02-01")
    c.post("/academy/nodes/N01-01/read", json={"user_id": b[0], "node_id": "N01-01"}, headers=_h(b[1]))
    out: dict = {"flag": [c.get("/academy/tree", params={"user_id": u}, headers=_h(t)).json().get("demo_session")
                          for u, t in (a, b)]}
    out["a_before"], out["b_before"] = _tree(c, *a), _tree(c, *b)
    out["rows_before"] = len(_session_rows(a[0]))
    ev_before = _q("SELECT COUNT(*) AS n FROM academy_kuat_attempts")[0]["n"]
    r = c.post("/academy/demo/reset", json={}, headers=_h(a[1]))
    out["reset"] = [r.status_code, sorted(r.json().keys()), r.json().get("message")]
    out["a_after"], out["b_after"] = _tree(c, *a), _tree(c, *b)
    out["rows_after"] = len(_session_rows(a[0]))
    out["events_unchanged"] = _q("SELECT COUNT(*) AS n FROM academy_kuat_attempts")[0]["n"] == ev_before
    r2 = c.post("/academy/demo/reset", json={}, headers=_h(p2[1]))
    out["p2_after_reset"] = [r2.status_code, _tree(c, *p2)]
    # not a demo session → 403 (regular account, device guest), 401 without a session
    acc = _phone_otp_account(c)
    g, gt = _guest(c)
    out["regular"] = c.post("/academy/demo/reset", json={}, headers=_h(acc["token"])).json()
    out["regular_flag"] = c.get("/academy/tree", params={"user_id": acc["user_id"]},
                                headers=_h(acc["token"])).json().get("demo_session")
    out["guest_status"] = c.post("/academy/demo/reset", json={}, headers=_h(gt)).status_code
    out["anon_status"] = c.post("/academy/demo/reset", json={}).status_code
    return out


# --------------------------------------------------------------------------- item 10
def scenario_cross_worker() -> dict:
    """This process keeps cached profiles; ANOTHER worker (simulated by writing the DB directly, as
    the demo seed / a reset on another instance does) deletes or re-creates the rows. Every read
    checks (rev, updated_at), so this process never serves the stale copy."""
    from tests._kuat import pass_kuat_http
    from tests._p0b_dbmode import scenario_seed_demo
    from welora import academy, academy_store

    scenario_seed_demo()
    c = _client()
    a = _demo_login(c, "P4")
    key = academy.profile_key(a[0], session=a[1])
    pass_kuat_http(c, a[0], _h(a[1]), "N02-01")
    out: dict = {"cached": _tree(c, *a)["status"]["N02-01"], "rev": _q("SELECT rev FROM academy_profiles WHERE user_id=?",
                                                                     (key,))[0]["rev"]}
    # 1) another worker's demo seed deleted the session row → back to the seed state here too
    _x("DELETE FROM academy_profiles WHERE user_id=?", (key,))
    out["after_delete"] = _tree(c, *a)["status"]["N02-01"]
    # 2) progress again (row re-created with rev 1), then another worker rewrites it to a DIFFERENT
    #    profile that also has rev 1 (delete + insert) → this process reloads it
    pass_kuat_http(c, a[0], _h(a[1]), "N02-01")
    rev_now = _q("SELECT rev FROM academy_profiles WHERE user_id=?", (key,))[0]["rev"]
    other = academy._normalise({})
    academy._refresh_locks(other)
    other["xp"] = 7
    _x("DELETE FROM academy_profiles WHERE user_id=?", (key,))
    _x("INSERT INTO academy_profiles(user_id, profile_json, rev, updated_at) VALUES (?,?,?,?)",
       (key, json.dumps(other), rev_now, "2026-10-02T13:00:00.123456+00:00"))
    t = _tree(c, *a)
    out["same_rev_rewrite"] = [rev_now, t["xp"], t["status"]["N02-01"]]
    # 3) the persona's own (non-session) profile rewritten by another worker's seed with rev 1
    base = a[0]
    academy.get_tree(base)  # cache it here
    p = academy._normalise({})
    academy._mark_gate_path_mastered(p)
    _x("DELETE FROM academy_profiles WHERE user_id=?", (base,))
    _x("INSERT INTO academy_profiles(user_id, profile_json, rev, updated_at) VALUES (?,?,1,?)",
       (base, json.dumps(p), "2026-10-02T13:00:01.000001+00:00"))
    out["base_after_rewrite"] = academy.get_tree(base)["xp"]
    out["version_fn"] = list(academy_store.profile_version(base) or [])
    return out


# --------------------------------------------------------------------------- item 9
def scenario_session_lru() -> dict:
    """WELORA_ACADEMY_SESSION_CACHE_MAX=16: 40 demo sessions → at most 16 session profiles in memory;
    an evicted session's progress comes back from the DB; regular profiles are never evicted."""
    from tests._p0b_dbmode import scenario_seed_demo
    from welora import academy

    scenario_seed_demo()
    c = _client()
    sessions = [_demo_login(c, "P4") for _ in range(40)]
    for uid, tok in sessions:
        c.post("/academy/nodes/N01-01/read", json={"user_id": uid, "node_id": "N01-01"}, headers=_h(tok))
    first = sessions[0]
    out = {"max": academy.session_cache_max(), "size": academy.session_cache_size(),
           "lru": len(academy._SESSION_LRU), "first_cached": academy.profile_key(first[0], session=first[1]) in academy._PROFILES}
    out["first_read_back"] = _tree(c, *first)["status"]["N01-01"]
    out["size_after"] = academy.session_cache_size()
    acc = _phone_otp_account(c)
    c.get("/academy/tree", params={"user_id": acc["user_id"]}, headers=_h(acc["token"]))
    for uid, tok in sessions[1:20]:
        _tree(c, uid, tok)
    out["regular_cached"] = acc["user_id"] in academy._PROFILES
    return out


if __name__ == "__main__":
    print("RESULT=" + json.dumps(globals()["scenario_" + sys.argv[1]](), default=str))
