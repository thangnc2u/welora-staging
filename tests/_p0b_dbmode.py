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
        rows = conn.execute("SELECT outcome, score FROM academy_kuat_attempts WHERE user_id=?", (uid,)).fetchall()
        outcomes = sorted(r["outcome"] or "open" for r in rows)
        scores = [r["score"] for r in rows]
    finally:
        conn.close()
    return {"before": before, "read_kept": "N02-01" in json.loads(prof["profile_json"])["read"],
            "last_kuat_keys": sorted((node.get("last_kuat") or {}).keys()),
            "submit": [sub.status_code, (sub.json().get("kuat_result") or {}).get("passed")],
            "again": [again.status_code, (again.json().get("detail") or {}).get("error_code")],
            "after": _tree_summary(c, uid, tok), "mastery": gate.get("state"),
            "profile_forbidden": sorted(_keys(json.loads(prof["profile_json"])) & FORBIDDEN_KEYS),
            "attempt_columns": sorted(cols), "outcomes": outcomes, "attempt_scores": scores}


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


# --------------------------------------------------------------------------- round 2: guest limits / stale tab
def _fail_once(c, uid, tok, node, ip=None):
    from tests._kuat import solve

    h = _h(tok, ip)
    c.post(f"/academy/nodes/{node}/read", json={"user_id": uid, "node_id": node}, headers=h)
    st = c.post("/academy/kuat/start", json={"user_id": uid, "node_id": node}, headers=h)
    if st.status_code != 200:
        return [st.status_code, (st.json().get("detail") or {}).get("reason")]
    a = st.json()
    r = c.post("/academy/kuat", json={"user_id": uid, "node_id": node, "attempt_id": a["attempt_id"],
                                      "answers": solve(node, a["questions"], correct=False)}, headers=h)
    if r.status_code != 200:
        return [r.status_code, (r.json().get("detail") or {}).get("reason")]
    return [200, r.json()["kuat_result"]["passed"]]


def scenario_guest_limits() -> dict:
    """Fails of ALL guests on one IP are aggregated (6 / 24 h); a guest device is capped at 6 / 24 h
    across nodes; real accounts on the same IP keep the (shared-NAT) IP limit."""
    from tests._followup2_dbmode import _register

    c = _client()
    ip = "198.51.100.%d" % (uuid.uuid4().int % 200 + 1)
    guests = [_guest(c) for _ in range(7)]
    per_guest = [_fail_once(c, u, t, "N02-01", ip) for u, t in guests]
    msg = c.post("/academy/kuat/start", json={"user_id": guests[6][0], "node_id": "N02-01"},
                 headers=_h(guests[6][1], ip)).json().get("detail") or {}
    acc = _phone_otp_account(c)  # round 3: a VERIFIED account (register alone is "unverified" = guest budget)
    real_same_ip = _fail_once(c, acc["user_id"], acc["token"], "N02-01", ip)
    other_ip_guest = _fail_once(c, *_guest(c), "N02-01", "198.51.100.250" if not ip.endswith(".250") else "198.51.100.251")
    # one guest, no IP header (round 4: the device bucket counts per GATE node): 3 fails on N02-01
    # (its per-node cooldown), 30 min later 3 more → device cap on N02-01; non-gate nodes unaffected
    du, dt = _guest(c)
    dev = [_fail_once(c, du, dt, "N02-01") for _ in range(3)]
    _age_kuat_events(1801)
    dev += [_fail_once(c, du, dt, "N02-01") for _ in range(3)]
    _age_kuat_events(1801)
    dev_next = _fail_once(c, du, dt, "N02-01")
    dev_msg = (c.post("/academy/kuat/start", json={"user_id": du, "node_id": "N02-01"}, headers=_h(dt)).json()
               .get("detail") or {}).get("message")
    dev_non_gate = [_fail_once(c, du, dt, n) for n in ("N01-01", "N03-01", "N04-01")]
    return {"per_guest": per_guest, "guest_ip_msg": msg.get("message"), "guest_ip_reason": msg.get("reason"),
            "real_same_ip": real_same_ip, "other_ip_guest": other_ip_guest, "device": dev, "device_next": dev_next,
            "device_msg": dev_msg, "device_non_gate": dev_non_gate}


def _age_kuat_events(seconds: float) -> None:
    """Simulated waiting: move every KUAT rate-limit event ``seconds`` into the past."""
    from welora import academy_store
    from welora.auth_ratelimit import _iso
    from welora.db.connection import get_connection

    conn = get_connection(None)
    try:
        rows = conn.execute("SELECT event_id, created_at FROM auth_rate_events WHERE action IN ('kuat_fail','kuat_start')"
                            ).fetchall()
        for row in rows:
            conn.execute("UPDATE auth_rate_events SET created_at=? WHERE event_id=?",
                         (_iso(academy_store._ts(row["created_at"]) - seconds), row["event_id"]))
        conn.commit()
    finally:
        conn.close()


# --------------------------------------------------------------------------- round 3: throwaway accounts
def _rand_ip(prefix="198.51.100."):
    return prefix + str(uuid.uuid4().int % 200 + 1)


def _phone_otp_account(c, creation_ip=None):
    """A phone-OTP account (consumed challenge = verified contact). WELORA_OTP_ECHO=1 (staging pilot)."""
    os.environ["WELORA_OTP_ECHO"] = "1"
    phone = "09" + "%08d" % (uuid.uuid4().int % 10 ** 8)
    hdr = {"CF-Connecting-IP": creation_ip or _rand_ip("192.0.2.")}
    req = c.post("/auth/otp/request", json={"phone": phone}, headers=hdr)
    assert req.status_code == 200, req.text
    ver = c.post("/auth/otp/verify", json={"challenge_id": req.json()["challenge_id"], "code": req.json()["pilot_code"]},
                 headers=hdr)
    assert ver.status_code == 200, ver.text
    return ver.json()


def _mark_email_verified(uid):
    """``users.email_verified_at`` exactly as verify_email_otp writes it (e-mail OTP is admin-listed
    only today, so a regular account cannot complete it over HTTP — same approach as the #239 tests)."""
    from welora.auth_ratelimit import _iso
    from welora.db.connection import get_connection
    import time as _t

    conn = get_connection(None)
    try:
        conn.execute("UPDATE users SET email_verified_at=? WHERE user_id=?", (_iso(_t.time()), uid))
        conn.commit()
    finally:
        conn.close()


def _kind(uid):
    from welora import academy_store
    from welora.db.connection import get_connection

    conn = get_connection(None)
    try:
        return academy_store._identity(conn, uid)[0]
    finally:
        conn.close()


def scenario_throwaway_accounts() -> dict:
    """Round 3 blocking: accounts that only registered (password + e-mail/phone, no OTP) count as
    guests — they share the 6 / IP / 24 h guest bucket with device guests. OTP-verified accounts and
    the demo personas P1–P6 keep the account budgets."""
    from tests._followup2_dbmode import _register
    from welora import partner_demo_seed

    c = _client()
    ip = _rand_ip()
    accs = [_register(c, f"p0b-r3-{uuid.uuid4().hex[:8]}@example.test", _rand_ip("192.0.2.")) for _ in range(8)]
    per_acc = [_fail_once(c, a["user_id"], a["token"], "N02-01", ip) for a in accs]
    detail = c.post("/academy/kuat/start", json={"user_id": accs[7]["user_id"], "node_id": "N02-01"},
                    headers=_h(accs[7]["token"], ip)).json().get("detail") or {}
    guest_after = _fail_once(c, *_guest(c), "N02-01", ip)  # device guests share the same bucket
    # the same kind of account counts as verified once its e-mail is OTP-verified
    email = f"p0b-r3-ver-{uuid.uuid4().hex[:8]}@example.test"
    reg = _register(c, email, _rand_ip("192.0.2."))
    kind_before = _kind(reg["user_id"])
    blocked_before = _fail_once(c, reg["user_id"], reg["token"], "N02-01", ip)
    _mark_email_verified(reg["user_id"])
    email_verified = [_kind(reg["user_id"]), *_fail_once(c, reg["user_id"], reg["token"], "N02-01", ip)]
    ph = _phone_otp_account(c)
    phone_verified = [_kind(ph["user_id"]), *_fail_once(c, ph["user_id"], ph["token"], "N02-01", ip)]
    seed = partner_demo_seed.seed_partner_rich_demo()
    demo_kinds = {pid: _kind(b["user_id"]) for pid, b in (seed.get("personas") or {}).items()}
    p1 = seed["personas"]["P1"]
    from welora import auth as auth_svc

    login = c.post("/auth/login", json={"email": partner_demo_seed.DEMO_P1_EMAIL, "password": auth_svc.DEMO_PASSWORD})
    demo_fail = _fail_once(c, p1["user_id"], login.json()["token"], "N02-01", ip) if login.status_code == 200 else [login.status_code]
    g_uid, _ = _guest(c)
    return {"per_account": per_acc, "reason": detail.get("reason"), "message": detail.get("message"),
            "retry_after": detail.get("retry_after"), "guest_after": guest_after,
            "kind_registered": kind_before, "blocked_before_otp": blocked_before, "email_verified": email_verified,
            "phone_verified": phone_verified, "demo_kinds": demo_kinds, "demo_fail": demo_fail,
            "kind_device_guest": _kind(g_uid), "kind_unknown": _kind("u-does-not-exist")}


def _insert_fail_events(scope, key, n, now, spread=(2 * 3600, 20 * 3600)):
    from welora import academy_store
    from welora.auth_ratelimit import _iso
    from welora.db.connection import get_connection

    conn = get_connection(None)
    try:
        for i in range(n):
            age = spread[0] + (spread[1] - spread[0]) * i / max(1, n - 1)
            conn.execute("INSERT INTO auth_rate_events(event_id, action, scope, key_hash, created_at) VALUES (?,?,?,?,?)",
                         (str(uuid.uuid4()), "kuat_fail", scope, academy_store._key_hash(scope, key), _iso(now - age)))
        conn.commit()
    finally:
        conn.close()


def _count_events(scope, key):
    from welora import academy_store
    from welora.db.connection import get_connection

    conn = get_connection(None)
    try:
        return int(conn.execute("SELECT COUNT(*) AS n FROM auth_rate_events WHERE action='kuat_fail' AND scope=? "
                                "AND key_hash=?", (scope, academy_store._key_hash(scope, key))).fetchone()["n"])
    finally:
        conn.close()


def _attempt_row(aid):
    from welora.db.connection import get_connection

    conn = get_connection(None)
    try:
        r = conn.execute("SELECT used_at, outcome FROM academy_kuat_attempts WHERE attempt_id=?", (aid,)).fetchone()
        return [r["used_at"], r["outcome"]]
    finally:
        conn.close()


def scenario_ip_day_cap() -> dict:
    """Round 3 blocking: every account (verified or not) shares 60 failed KUATs / client IP / 24 h
    (IPv6 → /64). The cap is reserved before grading: hitting it → 429 ip_day (VI + retry), the
    attempt is re-opened (not consumed) and can be submitted once the window frees up."""
    import time as _t

    from tests._kuat import solve
    from welora import academy_store
    from welora.auth_ratelimit import ip_bucket

    c = _client()
    net = "2001:db8:%x:%x" % (uuid.uuid4().int % 0xffff, uuid.uuid4().int % 0xffff)
    ip_a, ip_b, ip_other = net + "::1", net + "::beef:2", "2001:db8:ffff:%x::1" % (uuid.uuid4().int % 0xffff)
    now = _t.time()
    _insert_fail_events("kuat_ip_day", academy_store.ip_bucket_day(ip_a), academy_store.ip_day_max_fails() - 1, now)
    a, b = _phone_otp_account(c), _phone_otp_account(c)
    hb = _h(b["token"], ip_b)
    c.post("/academy/nodes/N02-01/read", json={"user_id": b["user_id"], "node_id": "N02-01"}, headers=hb)
    att_b = c.post("/academy/kuat/start", json={"user_id": b["user_id"], "node_id": "N02-01"}, headers=hb).json()
    last_ok = _fail_once(c, a["user_id"], a["token"], "N02-01", ip_a)  # the 60th fail of this /64
    wrong = solve("N02-01", att_b["questions"], correct=False)
    r = c.post("/academy/kuat", json={"user_id": b["user_id"], "node_id": "N02-01", "attempt_id": att_b["attempt_id"],
                                      "answers": wrong}, headers=hb)
    d = r.json().get("detail") or {}
    capped = {"status": r.status_code, "reason": d.get("reason"), "message": d.get("message"),
              "retry_after": d.get("retry_after"), "retry_header": r.headers.get("Retry-After"),
              "retry_at": d.get("retry_at")}
    attempt_after_429 = _attempt_row(att_b["attempt_id"])
    events_after_429 = _count_events("kuat_ip_day", academy_store.ip_bucket_day(ip_a))
    again = c.post("/academy/kuat/start", json={"user_id": b["user_id"], "node_id": "N02-01"}, headers=hb).json()
    other = _fail_once(c, *_guest_or_verified(c), "N02-01", ip_other)
    # the window frees up (age every event by 24 h) → the SAME attempt is graded
    from welora.auth_ratelimit import _iso
    from welora.db.connection import get_connection

    conn = get_connection(None)
    try:
        rows = conn.execute("SELECT event_id, created_at FROM auth_rate_events WHERE action='kuat_fail'").fetchall()
        for row in rows:
            conn.execute("UPDATE auth_rate_events SET created_at=? WHERE event_id=?",
                         (_iso(academy_store._ts(row["created_at"]) - 86400 - 60), row["event_id"]))
        conn.commit()
    finally:
        conn.close()
    later = c.post("/academy/kuat", json={"user_id": b["user_id"], "node_id": "N02-01", "attempt_id": att_b["attempt_id"],
                                          "answers": wrong}, headers=hb)
    return {"last_ok": last_ok, "capped": capped, "attempt_after_429": attempt_after_429,
            "events_after_429": events_after_429, "max": academy_store.ip_day_max_fails(),
            "same_attempt_on_restart": again.get("attempt_id") == att_b["attempt_id"] if isinstance(again, dict) else None,
            "start_detail": (again.get("detail") or {}).get("reason") if isinstance(again, dict) else None,
            "other_net": other, "later": [later.status_code, (later.json().get("kuat_result") or {}).get("passed")]}


def _guest_or_verified(c):
    a = _phone_otp_account(c)
    return a["user_id"], a["token"]


def scenario_stale_tab() -> dict:
    """GET node / start return the SAME open attempt; a tab from before the attempt format
    (canonical question ids) or with unknown slots gets 409 KUAT_RELOAD and nothing is counted."""
    from tests._kuat import solve
    from welora import academy, academy_store
    from welora.db.connection import get_connection

    c = _client()
    uid, tok = _guest(c)
    h = _h(tok, "198.51.100.%d" % (uuid.uuid4().int % 200 + 1))
    n1 = c.get("/academy/nodes/N02-01", params={"user_id": uid}, headers=h).json()
    n2 = c.get("/academy/nodes/N02-01", params={"user_id": uid}, headers=h).json()
    st = c.post("/academy/kuat/start", json={"user_id": uid, "node_id": "N02-01"}, headers=h).json()
    same = (n1["kuat"]["attempt_id"] == n2["kuat"]["attempt_id"] == st["attempt_id"]
            and n1["questions"] == n2["questions"] == st["questions"])
    old = [{"question_id": q["id"], "choice": q["answer"]} for q in academy.QUESTIONS["N02-01"][:5]]
    stale = []
    for _ in range(5):
        r = c.post("/academy/kuat", json={"user_id": uid, "node_id": "N02-01", "answers": old}, headers=h)
        stale.append([r.status_code, (r.json().get("detail") or {}).get("error_code")])
    r = c.post("/academy/kuat", json={"user_id": uid, "node_id": "N02-01", "attempt_id": st["attempt_id"],
                                      "answers": [{"question_id": "k9", "choice": 0}]}, headers=h)
    slot = [r.status_code, (r.json().get("detail") or {}).get("error_code"), (r.json().get("detail") or {}).get("message")]
    kh = academy_store._key_hash("kuat_user_node", f"user:{uid}|node:N02-01")
    conn = get_connection(None)
    try:
        fails = conn.execute("SELECT COUNT(*) AS n FROM auth_rate_events WHERE action='kuat_fail' AND key_hash=?",
                             (kh,)).fetchone()["n"]
    finally:
        conn.close()
    ok = c.post("/academy/kuat", json={"user_id": uid, "node_id": "N02-01", "attempt_id": st["attempt_id"],
                                       "answers": solve("N02-01", st["questions"])}, headers=h)
    return {"same_attempt": same, "stale": stale, "slot": slot, "fails_recorded": int(fails),
            "then_pass": [ok.status_code, (ok.json().get("kuat_result") or {}).get("passed")]}


# --------------------------------------------------------------------------- round 4
def _detail(r):
    try:
        return r.json().get("detail") or {}
    except Exception:
        return {}


def scenario_gate_scope() -> dict:
    """Round 4 item 1: the network buckets (guest/unverified 6 / network / 24 h, IP 30 / 30 min,
    IP 60 / 24 h) count GATE KUAT fails only (N02-01, N02-02), the guest one per gate node. Non-gate
    nodes keep the per-user limits. Item 2: the unverified 429 copy."""
    from tests._followup2_dbmode import _register
    from tests._kuat import pass_kuat_http
    from welora import academy_store
    from welora.auth_ratelimit import ip_bucket

    c = _client()
    ip = _rand_ip("198.51.100.")
    out: dict = {}
    # the CoS repro: A fails N02-01 ×3 + N01-01 ×3 → B (same IP) on N04-01
    a = _guest(c)
    c_pre = _guest(c)  # passes N02-01 before the network bucket fills (for the per-node check)
    out["c_pre_pass"] = list(pass_kuat_http(c, c_pre[0], _h(c_pre[1], ip), "N02-01")[:2])
    out["a"] = [_fail_once(c, *a, "N02-01", ip) for _ in range(3)] + [_fail_once(c, *a, "N01-01", ip) for _ in range(3)]
    b = _guest(c)
    out["b_n04"] = _fail_once(c, *b, "N04-01", ip)
    out["b_n01"] = _fail_once(c, *b, "N01-01", ip)
    out["b_n02"] = _fail_once(c, *b, "N02-01", ip)  # 4th gate fail of the network: still graded
    out["guest_bucket_n02_01"] = _count_events("kuat_guest_ip", f"{academy_store.ip_bucket_day(ip)}|node:N02-01")
    out["guest_bucket_non_gate"] = sum(_count_events("kuat_guest_ip", f"{academy_store.ip_bucket_day(ip)}|node:{n}")
                                       for n in ("N01-01", "N04-01"))
    out["ip_bucket_events"] = [_count_events("kuat_ip", ip_bucket(ip)), _count_events("kuat_ip_day", ip_bucket(ip))]
    # fill N02-01 for the network with register-only (unverified) accounts
    accs = [_register(c, f"p0b-r4-{uuid.uuid4().hex[:8]}@example.test", _rand_ip("192.0.2.")) for _ in range(3)]
    out["fill"] = [_fail_once(c, x["user_id"], x["token"], "N02-01", ip) for x in accs[:2]]
    u = accs[2]
    hu = _h(u["token"], ip)
    c.post("/academy/nodes/N02-01/read", json={"user_id": u["user_id"], "node_id": "N02-01"}, headers=hu)
    st = c.post("/academy/kuat/start", json={"user_id": u["user_id"], "node_id": "N02-01"}, headers=hu)
    d = _detail(st)
    out["unverified_429"] = {"status": st.status_code, "reason": d.get("reason"), "message": d.get("message"),
                             "retry_after": d.get("retry_after"), "retry_at": d.get("retry_at"),
                             "retry_at_vn": d.get("retry_at_vn"), "lesson_href": d.get("lesson_href"),
                             "lesson_title": d.get("lesson_title"), "retry_header": st.headers.get("Retry-After")}
    node = c.get("/academy/nodes/N02-01", params={"user_id": u["user_id"]}, headers=hu).json()
    out["node_cooldown_reason"] = ((node.get("kuat") or {}).get("cooldown") or {}).get("reason")
    out["node_lesson_served"] = bool(node.get("body_markdown"))
    # same network, gate bucket of N02-01 full: non-gate nodes and N02-02 (own bucket) still graded
    out["after_full_n04"] = _fail_once(c, u["user_id"], u["token"], "N04-01", ip)
    out["after_full_n03"] = _fail_once(c, *_guest(c), "N03-01", ip)
    out["after_full_n02_02"] = _fail_once(c, *c_pre, "N02-02", ip)
    out["after_full_guest_n02_01"] = _fail_once(c, *_guest(c), "N02-01", ip)
    # verified accounts: non-gate fails never reach the IP buckets
    ip2 = _rand_ip("203.0.113.")
    v = _phone_otp_account(c)
    out["verified_non_gate"] = [_fail_once(c, v["user_id"], v["token"], n, ip2) for n in ("N01-01", "N03-01", "N04-01")]
    out["verified_ip_events_non_gate"] = [_count_events("kuat_ip", ip_bucket(ip2)), _count_events("kuat_ip_day", ip_bucket(ip2))]
    out["verified_gate"] = _fail_once(c, v["user_id"], v["token"], "N02-01", ip2)
    out["verified_ip_events_gate"] = [_count_events("kuat_ip", ip_bucket(ip2)), _count_events("kuat_ip_day", ip_bucket(ip2))]
    # IPv6: 24 h network bucket per /56, short-window IP bucket per /64
    net = "2001:db8:%x:%02x" % (uuid.uuid4().int % 0xffff, uuid.uuid4().int % 0xfe + 1)
    ip6a, ip6b = net + "00::1", net + "ff::1"  # two /64s of one /56
    out["v6_same_56"] = academy_store.ip_bucket_day(ip6a) == academy_store.ip_bucket_day(ip6b)
    out["v6_diff_64"] = ip_bucket(ip6a) != ip_bucket(ip6b)
    for _ in range(3):
        _fail_once(c, *_guest(c), "N02-01", ip6a)
    out["v6_after_3_on_a"] = [_fail_once(c, *_guest(c), "N02-01", ip6b) for _ in range(4)]
    return out


def scenario_seed_demo() -> dict:
    from welora import partner_demo_seed

    seed = partner_demo_seed.seed_partner_rich_demo()
    return {pid: b["user_id"] for pid, b in (seed.get("personas") or {}).items()}


def _demo_login(c, pid):
    from welora import auth as auth_svc, partner_demo_seed

    email = partner_demo_seed.DEMO_PERSONA_ALIASES[pid]["email"]
    r = c.post("/auth/login", json={"email": email, "password": auth_svc.DEMO_PASSWORD},
               headers={"CF-Connecting-IP": _rand_ip("192.0.2.")})
    assert r.status_code == 200, r.text
    return r.json()["user_id"], r.json()["token"]


def scenario_demo_personas() -> dict:
    """Round 4 item 3: outsiders burning a demo persona from their networks never block the persona
    on the partner's network; demo personas share the guest network bucket of the gate KUATs."""
    from tests._kuat import pass_kuat_http
    from welora import academy_store
    from welora.auth_ratelimit import ip_bucket

    seeded = scenario_seed_demo()
    c = _client()
    out: dict = {"kinds": {pid: _kind(uid) for pid, uid in seeded.items()}}
    p2 = _demo_login(c, "P2")
    ip_a, ip_a2, ip_b = _rand_ip("203.0.113."), "198.18.0.%d" % (uuid.uuid4().int % 200 + 1), "198.51.100.%d" % (
        uuid.uuid4().int % 200 + 1)
    burn = []
    for ip in (ip_a, ip_a2):  # two outsider networks, each fails P2's N02-01 until refused
        seq = [_fail_once(c, *p2, "N02-01", ip) for _ in range(4)]
        _age_kuat_events(1801)
        seq += [_fail_once(c, *p2, "N02-01", ip) for _ in range(4)]
        burn.append(seq)
    out["burn"] = burn
    out["burn_detail_reason"] = _detail(c.post("/academy/kuat/start", json={"user_id": p2[0], "node_id": "N02-01"},
                                               headers=_h(p2[1], ip_a))).get("reason")
    out["graded_outsider_fails"] = sum(1 for seq in burn for x in seq if x == [200, False])
    # the partner on its own network: still takes (and can pass) the KUAT with P2
    out["partner_fail"] = _fail_once(c, *p2, "N02-01", ip_b)
    out["partner_pass"] = list(pass_kuat_http(c, p2[0], _h(p2[1], ip_b), "N02-01")[:2])
    out["partner_n02_02"] = list(pass_kuat_http(c, p2[0], _h(p2[1], ip_b), "N02-02")[:2])
    # per (persona, network) keys; the outsider network's non-gate KUATs keep only the per-user limit
    un = f"user:{p2[0]}|node:N02-01"
    out["user_node_day_events"] = {"ip_a": _count_events("kuat_user_node_day", f"{un}|ip:{ip_bucket(ip_a)}"),
                                   "ip_b": _count_events("kuat_user_node_day", f"{un}|ip:{ip_bucket(ip_b)}"),
                                   "global": _count_events("kuat_user_node_day", un)}
    out["outsider_non_gate"] = _fail_once(c, *p2, "N04-01", ip_a)
    # other personas from the burnt outsider network share its demo / guest bucket (6 per gate node)
    others = [_demo_login(c, pid) for pid in ("P1", "P3", "P4", "P5", "P6")]
    out["other_personas_ip_a"] = [_fail_once(c, *o, "N02-01", ip_a) for o in others]
    out["guest_on_ip_a"] = _fail_once(c, *_guest(c), "N02-01", ip_a)
    # start limit per (persona, network)
    out["start_events"] = {"ip_a": _count_events_action("kuat_start", "kuat_start", f"{un}|ip:{ip_bucket(ip_a)}"),
                           "ip_b": _count_events_action("kuat_start", "kuat_start", f"{un}|ip:{ip_bucket(ip_b)}"),
                           "global": _count_events_action("kuat_start", "kuat_start", un)}
    out["demo_ip_bucket"] = _count_events("kuat_guest_ip", f"{academy_store.ip_bucket_day(ip_a)}|node:N02-01")
    return out


def _count_events_action(action, scope, key):
    from welora import academy_store
    from welora.db.connection import get_connection

    conn = get_connection(None)
    try:
        return int(conn.execute("SELECT COUNT(*) AS n FROM auth_rate_events WHERE action=? AND scope=? AND key_hash=?",
                                (action, scope, academy_store._key_hash(scope, key))).fetchone()["n"])
    finally:
        conn.close()


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
