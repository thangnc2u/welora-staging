"""Subprocess scenarios for the "Academy follow-up sau 019" ticket on a DB store (SQLite, or PG17 when
the parent passes a postgres WELORA_DB_URL). Usage: python -m tests._acfu_dbmode <scenario> →
RESULT=<json>. State between processes via ACFU_STATE (json)."""

from __future__ import annotations

import json
import os
import sys
import time
import uuid

from tests._k019_dbmode import _open, _q, _start, _x
from tests._p0b_dbmode import _client, _demo_login, _guest, _h, _phone_otp_account, _rand_ip


def _state() -> dict:
    return json.loads(os.environ.get("ACFU_STATE") or "{}")


def _tree(c, uid, tok, ip=None):
    t = c.get("/academy/tree", params={"user_id": uid}, headers=_h(tok, ip)).json()
    st = {n["node_id"]: n["status"] for n in t["nodes"] if n["node_id"] in ("N01-01", "N02-01", "N02-02", "N02-03")}
    return {"xp": t["xp"], "status": st, "badges": sorted(t["badges"])}


def _session_rows(uid=None):
    rows = _q("SELECT user_id FROM academy_profiles WHERE user_id LIKE ?", ("%#%",))
    return sorted(r["user_id"] for r in rows if uid is None or r["user_id"].startswith(uid + "#"))


def _mastery(c, uid, tok):
    return c.get(f"/users/{uid}/mastery", headers=_h(tok)).json().get("state")


# --------------------------------------------------------------------------- item 1
def scenario_demo_progress() -> dict:
    """Two testers on one demo persona: progress (read / KUAT / XP / badges) is per login session,
    every session starts from the persona's demo seed, the shared gate mastery never moves."""
    from tests._followup2_dbmode import PW, _register
    from tests._k019_dbmode import _login
    from tests._kuat import pass_kuat_http
    from tests._p0b_dbmode import scenario_seed_demo

    seeded = scenario_seed_demo()
    c = _client()
    out: dict = {"uids": seeded}
    a, b = _demo_login(c, "P4"), _demo_login(c, "P4")  # P4: gate not passed (seed: empty tree)
    out["a0"], out["b0"] = _tree(c, *a), _tree(c, *b)
    out["rows_after_views"] = _session_rows()
    c.post("/academy/nodes/N01-01/read", json={"user_id": a[0], "node_id": "N01-01"}, headers=_h(a[1]))
    out["a_pass"] = [pass_kuat_http(c, a[0], _h(a[1]), n)[:2] for n in ("N02-01", "N02-02")]
    out["a1"], out["b1"] = _tree(c, *a), _tree(c, *b)
    out["a_read_node"] = c.get("/academy/nodes/N01-01", params={"user_id": a[0]}, headers=_h(a[1])).json()["status"]
    out["b_read_node"] = c.get("/academy/nodes/N01-01", params={"user_id": b[0]}, headers=_h(b[1])).json()["status"]
    out["p4_mastery_after_a"] = [_mastery(c, *a), _mastery(c, *b)]
    out["p4_gate_after_a"] = c.get(f"/users/{a[0]}/safety-gate", headers=_h(a[1])).json().get("status")
    out["flags_source"] = (_q("SELECT mastery_no_efund_invest AS m, mastery_source AS s FROM user_flags WHERE user_id=?",
                              (a[0],)) or [{}])[0]
    # P2 (gate passed in the seed): every session starts with N02-01 + N02-02 mastered
    p, q = _demo_login(c, "P2"), _demo_login(c, "P2")
    out["p0"] = _tree(c, *p)
    out["p_pass_n0203"] = list(pass_kuat_http(c, p[0], _h(p[1]), "N02-03")[:2])
    out["p1"], out["q1"] = _tree(c, *p), _tree(c, *q)
    out["rows"] = _session_rows()
    out["rows_hold_no_token"] = all(t not in r for r in out["rows"] for t in (a[1], b[1], p[1], q[1]))
    out["base_rows"] = sorted(r["user_id"] for r in _q("SELECT user_id FROM academy_profiles WHERE user_id IN (?,?)",
                                                         (seeded["P2"], seeded["P4"])))
    out["base_p4_profile_xp"] = json.loads(_q("SELECT profile_json FROM academy_profiles WHERE user_id=?",
                                              (seeded["P4"],))[0]["profile_json"])["xp"]
    # a regular account: two logins share ONE profile (unchanged)
    email = f"acfu-{uuid.uuid4().hex[:8]}@example.test"
    acc = _register(c, email, _rand_ip("192.0.2."))
    uid2, tok2 = _login(c, email, PW, _rand_ip("192.0.2."))
    pass_kuat_http(c, acc["user_id"], _h(acc["token"]), "N01-01")
    out["regular_other_login"] = _tree(c, uid2, tok2)["status"]["N01-01"]
    out["regular_rows"] = _session_rows(acc["user_id"])
    out["state"] = {"a": list(a), "b": list(b), "p": list(p)}
    return out


def scenario_demo_progress_read() -> dict:
    """Fresh process (restart / other instance): each session still sees only its own progress."""
    st = _state()
    c = _client()
    return {k: _tree(c, *v) for k, v in st.items()}


def scenario_demo_progress_reseed() -> dict:
    """The demo seed (every deploy) drops the persona's session profiles: same tokens → seed state."""
    from tests._p0b_dbmode import scenario_seed_demo

    st = _state()
    scenario_seed_demo()
    c = _client()
    return {"rows": _session_rows(), **{k: _tree(c, *v) for k, v in st.items()}}


def scenario_demo_progress_flag_off() -> dict:
    """WELORA_GUEST_DEMO=0 (production): no session split — key = user id (as before)."""
    from tests._p0b_dbmode import scenario_seed_demo
    from welora import academy

    seeded = scenario_seed_demo()  # seeded while on …
    c = _client()
    a = _demo_login(c, "P4")
    os.environ["WELORA_GUEST_DEMO"] = "0"  # … then the flag is off
    return {"key": academy.profile_key(a[0], session=a[1], ip="203.0.113.9"), "uid": seeded["P4"]}


# --------------------------------------------------------------------------- items 2 + 4
def scenario_nongate_caps() -> dict:
    """WELORA_KUAT_NONGATE_IP_MAX_STARTS=3, WELORA_KUAT_NONGATE_USER_MAX_STARTS=4."""
    from tests._kuat import solve

    os.environ["WELORA_OTP_ECHO"] = "1"  # test-only: phone-OTP (verified) accounts
    c = _client()
    ip, other = _rand_ip("203.0.113."), _rand_ip("198.51.100.")
    out: dict = {}
    # 5 VERIFIED accounts behind one NAT address: never blocked as a network
    ver = [_phone_otp_account(c) for _ in range(5)]
    out["verified_starts"] = [_start(c, v["user_id"], v["token"], "N01-01", ip)[0] for v in ver]
    out["verified_net_events"] = _net_events(ip)
    # guests / unverified on the same address: the per-network backstop still applies (3)
    gs = [_guest(c) for _ in range(4)]
    res = [_start(c, g, t, "N03-01", ip) for g, t in gs]
    out["guest_starts"] = [[s, (j.get("detail") or {}).get("reason") if s != 200 else None] for s, j in res]
    cap = res[-1][1].get("detail") or {}
    out["guest_cap"] = {k: cap.get(k) for k in ("error_code", "reason", "message", "lesson_href", "lesson_title")}
    out["guest_other_network"] = _start(c, *gs[3], "N03-01", other)[0]
    out["verified_after_guest_cap"] = _start(c, ver[0]["user_id"], ver[0]["token"], "N03-01", ip)[0]
    # per-account cap on a verified account (4 new non-gate attempts / window)
    u, t = ver[1]["user_id"], ver[1]["token"]
    seq = [_start(c, u, t, n, other)[0] for n in ("N03-01", "N04-01", "N05-01")]  # + N01-01 above = 4
    h = _h(t, other)
    att = c.post("/academy/kuat/start", json={"user_id": u, "node_id": "N01-01"}, headers=h).json()
    c.post("/academy/kuat", json={"user_id": u, "node_id": "N01-01", "attempt_id": att["attempt_id"],
                                  "answers": solve("N01-01", att["questions"], correct=False)}, headers=h)
    fifth = c.post("/academy/kuat/start", json={"user_id": u, "node_id": "N01-01"}, headers=h)
    d = fifth.json().get("detail") or {}
    out["user_seq"] = seq + [fifth.status_code]
    out["user_cap"] = {k: d.get(k) for k in ("error_code", "reason", "message", "lesson_href")}
    before = _user_events(u)
    out["user_cap_gate_node"] = _start(c, u, t, "N02-01", other)[0]  # gate nodes keep their own budgets
    out["user_events_before_after_gate"] = [before, _user_events(u)]
    return out


def _net_events(ip):
    from welora import academy_store

    return len(_q("SELECT 1 FROM auth_rate_events WHERE scope='kuat_nongate_ip_start' AND key_hash=?",
                  (academy_store._key_hash("kuat_nongate_ip_start", academy_store.ip_bucket_day(ip)),)))


def _user_events(u):
    from welora import academy_store

    return len(_q("SELECT 1 FROM auth_rate_events WHERE scope='kuat_nongate_user_start' AND key_hash=?",
                  (academy_store._key_hash("kuat_nongate_user_start", f"user:{u}"),)))


def scenario_demo_user_cap() -> dict:
    """Demo personas: the per-account non-gate cap is per (persona, network) like their other budgets."""
    from tests._p0b_dbmode import scenario_seed_demo

    scenario_seed_demo()
    os.environ["WELORA_KUAT_NONGATE_IP_MAX_STARTS"] = "0"  # isolate the per-account bucket
    c = _client()
    ip_a, ip_b = _rand_ip("203.0.113."), _rand_ip("198.51.100.")
    a = _demo_login(c, "P4")
    res = [_start(c, *a, n, ip_a)[0] for n in ("N01-01", "N03-01", "N04-01")]
    b = _demo_login(c, "P4")
    return {"net_a": res + [_start(c, *b, "N05-01", ip_a)[0]], "net_b": _start(c, *b, "N05-01", ip_b)[0]}


# --------------------------------------------------------------------------- item 5
def scenario_stale_bank_attempt() -> dict:
    """An attempt issued from the OLD 3-question bank (ids q101a…) before the deploy: reopening the
    lesson retires it and serves the new bank; submitting it → 409, nothing graded or counted."""
    from welora import academy
    from welora.auth_ratelimit import _iso

    c = _client()
    g, gt = _guest(c)
    ip = _rand_ip("203.0.113.")
    out = {}
    for label in ("start", "submit"):
        uid, tok = _guest(c) if label == "submit" else (g, gt)
        old = uuid.uuid4().hex
        _x("INSERT INTO academy_kuat_attempts(attempt_id, user_id, node_id, served_json, created_at, expires_at, "
           "scope_key) VALUES (?,?,?,?,?,?,?)",
           (old, uid, "N01-01", json.dumps([{"q": "q101a", "perm": [2, 0, 1]}, {"q": "q101b", "perm": [1, 2, 0]},
                                             {"q": "q101c", "perm": [1, 0]}]),
            _iso(time.time() - 60), _iso(time.time() + 1500), ""))  # issued just before the deploy
        if label == "start":
            st, j = _start(c, uid, tok, "N01-01", ip)
            ids = {q["prompt"] for q in academy.QUESTIONS["N01-01"]}
            out["start"] = {"status": st, "new_attempt": j.get("attempt_id") != old,
                            "five_current": len(j.get("questions") or []) == 5
                            and all(q["prompt"] in ids and len(q["choices"]) == 4 for q in j["questions"]),
                            "old_outcome": _q("SELECT outcome FROM academy_kuat_attempts WHERE attempt_id=?",
                                              (old,))[0]["outcome"],
                            "open": len(_open(uid, "N01-01"))}
        else:
            r = c.post("/academy/kuat", json={"user_id": uid, "node_id": "N01-01", "attempt_id": old,
                                              "answers": [{"question_id": f"k{i}", "choice": 0} for i in (1, 2, 3)]},
                       headers=_h(tok, ip))
            out["submit"] = {"status": r.status_code, "code": (r.json().get("detail") or {}).get("error_code"),
                             "fails": len(_q("SELECT 1 FROM auth_rate_events WHERE action='kuat_fail'")),
                             "old_outcome": _q("SELECT outcome FROM academy_kuat_attempts WHERE attempt_id=?",
                                               (old,))[0]["outcome"],
                             "tree_n01": _tree(c, uid, tok)["status"]["N01-01"]}
    return out


def scenario_new_banks_http() -> dict:
    """The three new banks over HTTP: 5 questions × 4 options, no answer / correctness / hard marker;
    a learner who knows the lesson passes, a wrong set fails (pass / fail only)."""
    from tests._kuat import pass_kuat_http

    c = _client()
    out = {}
    for node in ("N01-01", "N03-01", "N04-01"):
        g, gt = _guest(c)
        h = _h(gt, _rand_ip("203.0.113."))
        n = c.get(f"/academy/nodes/{node}", params={"user_id": g}, headers=h).json()
        qs = n["questions"]
        keys = sorted({k for q in qs for k in q})
        fail = pass_kuat_http(c, g, h, node, correct=False)
        ok = pass_kuat_http(c, g, h, node)
        out[node] = {"count": len(qs), "choices": sorted({len(q["choices"]) for q in qs}), "keys": keys,
                     "bank_size": n["kuat"].get("bank_size"), "question_count": n["kuat"].get("question_count"),
                     "fail": fail[:2], "fail_result_keys": sorted((fail[2].get("kuat_result") or {}).keys()),
                     "pass": ok[:2]}
    return out


if __name__ == "__main__":
    print("RESULT=" + json.dumps(globals()["scenario_" + sys.argv[1]](), default=str))
