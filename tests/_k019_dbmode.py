"""Subprocess scenarios for the "KUAT demo persona (migration 019)" ticket on a DB store (SQLite, or
PG17 when the parent passes a postgres WELORA_DB_URL). Usage:
python -m tests._k019_dbmode <scenario> → RESULT=<json>. State between processes via K019_STATE (json).
"""

from __future__ import annotations

import json
import os
import sys
import uuid

from tests._p0b_dbmode import _client, _demo_login, _guest, _h, _rand_ip, _tree_summary


def _state() -> dict:
    return json.loads(os.environ.get("K019_STATE") or "{}")


def _q(sql, params=()):
    from welora.db.connection import get_connection

    conn = get_connection(None)
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _x(sql, params=()):
    from welora.db.connection import get_connection

    conn = get_connection(None)
    try:
        conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _open(uid, node):
    return _q("SELECT attempt_id, scope_key FROM academy_kuat_attempts WHERE user_id=? AND node_id=? "
              "AND used_at IS NULL ORDER BY created_at", (uid, node))


def _start(c, uid, tok, node, ip):
    h = _h(tok, ip)
    c.post(f"/academy/nodes/{node}/read", json={"user_id": uid, "node_id": node}, headers=h)
    r = c.post("/academy/kuat/start", json={"user_id": uid, "node_id": node}, headers=h)
    return r.status_code, r.json()


def _submit(c, uid, tok, node, att, ip, *, correct=False, attempt_id=None, omit_id=False):
    from tests._kuat import solve

    body = {"user_id": uid, "node_id": node, "answers": solve(node, att["questions"], correct=correct)}
    if not omit_id:
        body["attempt_id"] = attempt_id or att["attempt_id"]
    r = c.post("/academy/kuat", json=body, headers=_h(tok, ip))
    j = r.json()
    return [r.status_code, (j.get("kuat_result") or {}).get("passed") if r.status_code == 200
            else (j.get("detail") or j).get("error_code") or (j.get("detail") or {}).get("reason")]


def _login(c, email, pw, ip):
    r = c.post("/auth/login", json={"email": email, "password": pw}, headers={"CF-Connecting-IP": ip})
    assert r.status_code == 200, r.text
    return r.json()["user_id"], r.json()["token"]


# --------------------------------------------------------------------------- item 1
def scenario_demo_sessions() -> dict:
    """Two testers on ONE demo persona (two logins = two sessions, two networks) each get their own
    open attempt; neither can see / consume the other's; regular accounts keep exactly one."""
    from tests._followup2_dbmode import PW, _register
    from tests._p0b_dbmode import scenario_seed_demo
    from welora import academy, academy_store

    scenario_seed_demo()
    c = _client()
    out: dict = {}
    ip_a, ip_b = _rand_ip("203.0.113."), _rand_ip("198.51.100.")
    a = _demo_login(c, "P4")  # P4: gate not passed → N02-01 open, nothing mastered
    b = _demo_login(c, "P4")
    out["same_user"] = a[0] == b[0]
    sa, att_a = _start(c, *a, "N02-01", ip_a)
    sb, att_b = _start(c, *b, "N02-01", ip_b)
    out["starts"] = [sa, sb]
    out["distinct_attempts"] = att_a["attempt_id"] != att_b["attempt_id"]
    # each session keeps its own attempt on reload / another tab / GET node
    out["a_again"] = _start(c, *a, "N02-01", ip_a)[1]["attempt_id"] == att_a["attempt_id"]
    node_b = c.get("/academy/nodes/N02-01", params={"user_id": b[0]}, headers=_h(b[1], ip_b)).json()
    out["b_node_same"] = (node_b.get("kuat") or {}).get("attempt_id") == att_b["attempt_id"]
    # tester A on tester B's network still has A's attempt (scope = login session, not the network)
    out["a_on_ip_b"] = _start(c, *a, "N02-01", ip_b)[1]["attempt_id"] == att_a["attempt_id"]
    opened = _open(a[0], "N02-01")
    out["open_count"] = len(opened)
    out["open_scopes_distinct"] = len({o["scope_key"] for o in opened}) == 2
    out["scope_prefixes"] = sorted({o["scope_key"][:2] for o in opened})
    out["token_not_stored"] = all(a[1] not in o["scope_key"] and b[1] not in o["scope_key"] for o in opened)
    # A cannot consume B's attempt (409, nothing counted); B's attempt still open afterwards
    out["a_submits_b_attempt"] = _submit(c, *a, "N02-01", att_b, ip_a, attempt_id=att_b["attempt_id"])
    out["b_still_open"] = any(o["attempt_id"] == att_b["attempt_id"] for o in _open(a[0], "N02-01"))
    # A submits without attempt_id → A's own open attempt is used (never B's)
    out["a_submit_no_id"] = _submit(c, *a, "N02-01", att_a, ip_a, omit_id=True)
    out["a_consumed"] = _q("SELECT outcome FROM academy_kuat_attempts WHERE attempt_id=?", (att_a["attempt_id"],))[0]["outcome"]
    out["b_after_a"] = _q("SELECT used_at FROM academy_kuat_attempts WHERE attempt_id=?", (att_b["attempt_id"],))[0]["used_at"]
    out["b_pass"] = _submit(c, *b, "N02-01", att_b, ip_b, correct=True)
    # in-process callers without a session: per client network
    n1 = academy.start_attempt(a[0], "N04-01", ip=ip_a)["attempt_id"]
    n2 = academy.start_attempt(a[0], "N04-01", ip=ip_b)["attempt_id"]
    n3 = academy.start_attempt(a[0], "N04-01", ip=ip_a)["attempt_id"]
    out["network_scope"] = [n1 != n2, n1 == n3]
    out["network_scopes"] = sorted({o["scope_key"][:2] for o in _open(a[0], "N04-01")})
    # regular accounts: two logins (two tokens) of ONE account → the SAME single open attempt
    email = f"k019-{uuid.uuid4().hex[:8]}@example.test"
    acc = _register(c, email, _rand_ip("192.0.2."))
    out["regular"] = {}
    tok1 = acc["token"]
    uid2, tok2 = _login(c, email, PW, _rand_ip("192.0.2."))
    out["regular"]["two_tokens_same_user"] = [uid2 == acc["user_id"], tok2 != tok1]
    r1 = _start(c, acc["user_id"], tok1, "N02-01", ip_a)[1]
    r2 = _start(c, uid2, tok2, "N02-01", ip_b)[1]
    out["regular"]["same_attempt"] = r1["attempt_id"] == r2["attempt_id"]
    out["regular"]["open"] = [o["scope_key"] for o in _open(acc["user_id"], "N02-01")]
    g, gt = _guest(c)
    gr = [_start(c, g, gt, "N02-01", ip)[1]["attempt_id"] for ip in (ip_a, ip_b)]
    out["guest_same_attempt"] = gr[0] == gr[1]
    out["guest_open"] = [o["scope_key"] for o in _open(g, "N02-01")]
    out["scope_regular"] = [academy_store.attempt_scope(acc["user_id"], session=tok1, ip=ip_a),
                            academy_store.attempt_scope(g, session=gt, ip=ip_a)]
    # DB: a second open attempt in the regular scope is refused by the unique index
    try:
        _x("INSERT INTO academy_kuat_attempts(attempt_id, user_id, node_id, served_json, created_at, expires_at) "
           "VALUES (?,?,?,?,?,?)", (uuid.uuid4().hex, acc["user_id"], "N02-01", "[]", "2026-01-01T00:00:00+00:00",
                                    "2099-01-01T00:00:00+00:00"))
        out["db_second_open_regular"] = "inserted"
    except Exception as e:  # noqa: BLE001
        out["db_second_open_regular"] = type(e).__name__
    return out


def scenario_demo_session_budget() -> dict:
    """New sessions buy no extra attempts: the start budget stays per (persona, node, network)."""
    from tests._p0b_dbmode import scenario_seed_demo

    scenario_seed_demo()
    c = _client()
    ip = _rand_ip("203.0.113.")
    res = []
    for _ in range(4):  # WELORA_KUAT_MAX_STARTS=3 for this scenario
        s = _demo_login(c, "P5")
        st, j = _start(c, *s, "N04-01", ip)
        res.append([st, (j.get("detail") or {}).get("reason") if st != 200 else None])
    other_net = _start(c, *_demo_login(c, "P5"), "N04-01", _rand_ip("198.51.100."))[0]
    return {"starts": res, "other_network": other_net}


# --------------------------------------------------------------------------- migration
def scenario_migrate_twice() -> dict:
    """Pre-019 database (up to 018) with open attempts → 019 → run again (also with its version row
    removed, and the PG SQL file executed twice by hand) → no error, same schema, rows kept."""
    import importlib

    from welora.academy_migration import apply_kuat_open_scope
    from welora.db.connection import detect_dialect, get_connection

    m = importlib.import_module("welora.db.migrate")  # the module (welora.db re-exports the function)

    dialect = detect_dialect(None)
    real_files, real_steps = m._list_migration_files, m._data_steps
    m._list_migration_files = lambda url=None: [p for p in real_files(url) if not p.stem.startswith("019")]
    m._data_steps = lambda: [s for s in real_steps() if not s[0].startswith("019")]
    try:
        pre = m.migrate(None)
    finally:
        m._list_migration_files, m._data_steps = real_files, real_steps

    def cols():
        if dialect == "sqlite":
            return sorted(r["name"] for r in _q("PRAGMA table_info(academy_kuat_attempts)"))
        return sorted(r["column_name"] for r in _q(
            "SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() "
            "AND table_name='academy_kuat_attempts'"))

    def idx():
        if dialect == "sqlite":
            return sorted(r["name"] for r in _q("SELECT name FROM sqlite_master WHERE type='index' "
                                                "AND tbl_name='academy_kuat_attempts' AND name LIKE 'uq_%'"))
        return sorted(r["indexname"] for r in _q("SELECT indexname FROM pg_indexes WHERE tablename='academy_kuat_attempts' "
                                                 "AND indexname LIKE 'uq_%'"))

    out = {"dialect": dialect, "pre_has_019": any(v.startswith("019") for v in pre),
           "pre_cols_scope": "scope_key" in cols(), "pre_idx": idx()}
    _x("INSERT INTO academy_kuat_attempts(attempt_id, user_id, node_id, served_json, created_at, expires_at) "
       "VALUES (?,?,?,?,?,?)", ("pre019", "u-pre", "N02-01", "[]", "2026-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"))
    out["first"] = m.migrate(None)
    out["second"] = m.migrate(None)
    out["cols_scope"] = "scope_key" in cols()
    out["idx"] = idx()
    out["pre_row_scope"] = _q("SELECT scope_key FROM academy_kuat_attempts WHERE attempt_id='pre019'")[0]["scope_key"]
    # forget the version row → the change is re-applied without error
    _x("DELETE FROM schema_migrations WHERE version='019_kuat_open_scope'")
    out["third"] = m.migrate(None)
    conn = get_connection(None)
    try:
        apply_kuat_open_scope(conn, dialect)
        apply_kuat_open_scope(conn, dialect)
        out["step_twice"] = "ok"
    finally:
        conn.close()
    if dialect == "postgres":
        import psycopg

        sql = (m.MIGRATIONS_ROOT / "postgres" / "019_kuat_open_scope.sql").read_text(encoding="utf-8")
        with psycopg.connect(os.environ["WELORA_DB_URL"]) as pc:
            pc.execute(sql)
            pc.execute(sql)
        out["sql_file_twice"] = "ok"
    out["idx_after"] = idx()
    out["cols_after"] = cols().count("scope_key")
    out["versions_019"] = [v for v in m.current_version() if v.startswith("019")]
    # uniqueness: regular scope '' → one open per user + node; another scope may open its own
    for scope, label in (("", "dup_regular"), ("s:x", "other_scope"), ("s:x", "dup_other_scope")):
        try:
            _x("INSERT INTO academy_kuat_attempts(attempt_id, user_id, node_id, served_json, created_at, expires_at, "
               "scope_key) VALUES (?,?,?,?,?,?,?)", (uuid.uuid4().hex, "u-pre", "N02-01", "[]",
                                                       "2026-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00", scope))
            out[label] = "inserted"
        except Exception as e:  # noqa: BLE001
            out[label] = "refused" if "unique" in str(e).lower() or "Integrity" in type(e).__name__ else repr(e)
    return out


# --------------------------------------------------------------------------- item 3
def scenario_nongate_starts() -> dict:
    """WELORA_KUAT_NONGATE_IP_MAX_STARTS=5: new attempts on non-gate nodes from one network are
    capped (all accounts); reloads are free; other networks and the gate nodes are unaffected."""
    from welora import academy_store

    c = _client()
    ip, other = _rand_ip("203.0.113."), _rand_ip("198.51.100.")
    guests = [_guest(c) for _ in range(6)]
    res = []
    for i, (u, t) in enumerate(guests):
        st, j = _start(c, u, t, "N04-01" if i % 2 else "N01-01", ip)
        res.append([st, (j.get("detail") or {}).get("reason") if st != 200 else None])
    cap = _start(c, *guests[5], "N04-01", ip)[1].get("detail") or {}
    reload_ = _start(c, *guests[0], "N01-01", ip)[0]  # open attempt reused → no new start
    gate = [_start(c, u, t, "N02-01", ip)[0] for u, t in guests[:3]]
    return {
        "starts": res, "cap": {k: cap.get(k) for k in ("error_code", "reason", "message", "retry_after", "lesson_href")},
        "reload": reload_, "other_network": _start(c, *guests[5], "N04-01", other)[0], "gate": gate,
        "nongate_events": len(_q("SELECT 1 FROM auth_rate_events WHERE scope='kuat_nongate_ip_start' AND key_hash=?",
                                 (academy_store._key_hash("kuat_nongate_ip_start", academy_store.ip_bucket_day(ip)),))),
        "gate_fail_events": len(_q("SELECT 1 FROM auth_rate_events WHERE action='kuat_fail'")),
    }


# --------------------------------------------------------------------------- item 4
def scenario_seed_profiles() -> dict:
    from tests._p0b_dbmode import scenario_seed_demo
    from welora.db.connection import get_connection

    seeded = scenario_seed_demo()
    c = _client()

    def tree(pid):
        uid, tok = _demo_login(c, pid)
        return _tree_summary(c, uid, tok)

    out = {"first": {pid: tree(pid) for pid in ("P1", "P2", "P3", "P4", "P5", "P6")}}
    out["gate_p2"] = c.get(f"/users/{seeded['P2']}/safety-gate", headers=_h(_demo_login(c, "P2")[1])).json().get("status")
    out["mastery_p2"] = c.get(f"/users/{seeded['P2']}/mastery", headers=_h(_demo_login(c, "P2")[1])).json().get("state")
    conn = get_connection(None)
    try:
        out["rows"] = int(conn.execute("SELECT COUNT(*) AS n FROM academy_profiles").fetchone()["n"])
    finally:
        conn.close()
    scenario_seed_demo()  # again → same result
    out["second"] = {pid: tree(pid) for pid in ("P2", "P4")}
    return {**out, "uids": seeded}


def scenario_seed_profiles_read() -> dict:
    """Fresh process (= restart / other instance) reads the seeded progress."""
    c = _client()
    out = {}
    for pid in ("P2", "P4"):
        uid, tok = _demo_login(c, pid)
        out[pid] = _tree_summary(c, uid, tok)
    return out


def scenario_seed_rollback() -> dict:
    """The profile is written in the seed's transaction: a seed that fails later leaves no profile."""
    from welora import demo_seed_runner, partner_demo_seed

    def boom(_uid):
        raise RuntimeError("simulated failure after P2's profile")

    partner_demo_seed.seed_p6_on_user = boom
    try:
        demo_seed_runner.run_demo_seed()
        failed = False
    except Exception:
        failed = True
    return {"failed": failed, "profiles": _q("SELECT user_id FROM academy_profiles")}


# --------------------------------------------------------------------------- item 6
def _put_mastery(uid, state, source):
    from welora.db.connection import get_connection

    conn = get_connection(None)
    try:
        conn.execute("INSERT INTO users(user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING", (uid,))
        conn.execute("DELETE FROM user_flags WHERE user_id=?", (uid,))
        conn.execute("INSERT INTO user_flags(user_id, mastery_no_efund_invest, mastery_source) VALUES (?,?,?)",
                     (uid, state, source))
        conn.commit()
    finally:
        conn.close()


def _rev(uid):
    r = _q("SELECT rev FROM academy_profiles WHERE user_id=?", (uid,))
    return r[0]["rev"] if r else None


def scenario_backfill_write() -> dict:
    """Users who passed the gate before 017 (mastery apply, source academy) / the demo seed (source
    seed) but have no Academy profile; plus controls that must NOT be backfilled."""
    from tests._kuat import pass_kuat_http
    from tests._followup2_dbmode import _register

    c = _client()
    out: dict = {}
    users = {}
    for label, state, source in (("academy_apply", "apply", "academy"), ("seed_apply", "apply", "seed"),
                                 ("untrusted_apply", "apply", None), ("academy_familiar", "familiar", "academy"),
                                 ("with_row", "apply", "academy"), ("already", "apply", "academy")):
        acc = _register(c, f"k019-{label.replace('_', '-')}-{uuid.uuid4().hex[:6]}@example.test", _rand_ip("192.0.2."))
        users[label] = (acc["user_id"], acc["token"])
    # with_row: a profile row from after 017 (read a lesson, passed N01-01) → kept + gate path added
    u, t = users["with_row"]
    pass_kuat_http(c, u, _h(t), "N01-01")
    c.post("/academy/nodes/N02-01/read", json={"user_id": u, "node_id": "N02-01"}, headers=_h(t))
    # already: passed both gate KUATs through the Academy (profile has them) → untouched, no double XP
    u, t = users["already"]
    pass_kuat_http(c, u, _h(t), "N02-01")
    pass_kuat_http(c, u, _h(t), "N02-02")
    out["already_rev_before"] = _rev(u)
    for label, (state, source) in {"academy_apply": ("apply", "academy"), "seed_apply": ("apply", "seed"),
                                   "untrusted_apply": ("apply", None), "academy_familiar": ("familiar", "academy"),
                                   "with_row": ("apply", "academy")}.items():
        _put_mastery(users[label][0], state, source)
    from welora import academy

    academy.reset_academy_store()  # = the deploy / restart after which the backfill first runs
    out["rows_before"] = {k: _rev(u) for k, (u, _t) in users.items()}
    out["trees"] = {k: _tree_summary(c, u, t) for k, (u, t) in users.items()}
    out["rev_after_first_read"] = {k: _rev(u) for k, (u, _t) in users.items()}
    out["trees_again"] = {k: _tree_summary(c, u, t) for k, (u, t) in users.items()}
    out["rev_after_second_read"] = {k: _rev(u) for k, (u, _t) in users.items()}
    out["mastery_after"] = {k: c.get(f"/users/{u}/mastery", headers=_h(t)).json().get("state") for k, (u, t) in users.items()}
    out["sources_after"] = {k: (_q("SELECT mastery_source AS s FROM user_flags WHERE user_id=?", (u,)) or [{"s": None}])[0]["s"]
                            for k, (u, _t) in users.items()}
    wr = c.get("/academy/tree", params={"user_id": users["with_row"][0]}, headers=_h(users["with_row"][1])).json()
    out["with_row_n01"] = next(n["status"] for n in wr["nodes"] if n["node_id"] == "N01-01")
    prof = json.loads(_q("SELECT profile_json FROM academy_profiles WHERE user_id=?", (users["with_row"][0],))[0]["profile_json"])
    out["with_row_read"] = sorted(prof.get("read") or [])
    # the gate KUAT still works after a backfill (N02-03 open)
    u, t = users["academy_apply"]
    out["n02_03_after"] = list(pass_kuat_http(c, u, _h(t), "N02-03")[:2])
    return {**out, "users": {k: list(v) for k, v in users.items()}}


def scenario_backfill_read() -> dict:
    """Fresh process: the backfilled profiles are persisted; reads do not write again."""
    st = _state()
    c = _client()
    users = st["users"]
    before = {k: _rev(u) for k, (u, _t) in users.items()}
    trees = {k: _tree_summary(c, u, t) for k, (u, t) in users.items()}
    return {"trees": trees, "rev_before": before, "rev_after": {k: _rev(u) for k, (u, _t) in users.items()}}


def scenario_backfill_demo_p2() -> dict:
    """Demo P2 seeded before this change (mastery seed, no Academy profile) → backfilled on read."""
    from tests._p0b_dbmode import scenario_seed_demo

    seeded = scenario_seed_demo()
    _x("DELETE FROM academy_profiles")
    c = _client()  # a fresh app object; this process' cache is dropped below
    from welora import academy

    academy.reset_academy_store()
    uid, tok = _demo_login(c, "P2")
    return {"p2": _tree_summary(c, uid, tok), "uid_ok": uid == seeded["P2"],
            "p4": _tree_summary(c, *_demo_login(c, "P4"))}


def scenario_guest_academy() -> dict:
    """Item 5 on a DB store: device guests use the Academy APIs only while WELORA_GUEST_DEMO is on."""
    from tests._followup2_dbmode import _register

    c = _client()
    g, gt = _guest(c)
    acc = _register(c, f"k019-ga-{uuid.uuid4().hex[:6]}@example.test", _rand_ip("192.0.2."))
    def calls(uid, tok):
        h = _h(tok)
        return [c.get("/academy/tree", params={"user_id": uid}, headers=h).status_code,
                c.get("/academy/nodes/N01-01", params={"user_id": uid}, headers=h).status_code,
                c.post("/academy/nodes/N01-01/read", json={"user_id": uid, "node_id": "N01-01"}, headers=h).status_code,
                c.post("/academy/kuat/start", json={"user_id": uid, "node_id": "N01-01"}, headers=h).status_code]
    r = c.get("/academy/tree", params={"user_id": g}, headers=_h(gt))
    page = c.get("/app/academy")
    return {"guest": calls(g, gt), "account": calls(acc["user_id"], acc["token"]),
            "guest_detail": r.json().get("detail") if r.status_code != 200 else None,
            "meta": 'name="welora-guest-academy"' in page.text, "health": c.get("/health").json().get("guest_academy")}


if __name__ == "__main__":
    print("RESULT=" + json.dumps(globals()["scenario_" + sys.argv[1]](), default=str))
