"""Subprocess scenarios for P0 follow-up 2 (guest → account claim) that need a DB store from
import time (goals STORE is chosen when welora.goals_api is imported). Also importable in-process
for the memory-store variant. Usage: python -m tests._followup2_dbmode <scenario>
"""

from __future__ import annotations

import json
import sys
import threading
import uuid

PW = "matkhau-claim-1"
ESS_A = 12_000_000
ESS_B = 20_000_000


def _client():
    from fastapi.testclient import TestClient

    from welora.api.app import create_app

    return TestClient(create_app())


def _h(tok):
    return {"Authorization": "Bearer " + tok}


def _guest_onboard(c, essential, debt=False):
    d = c.post("/auth/device", json={"device_id": "web-" + uuid.uuid4().hex[:12]}).json()
    tok, uid = d["token"], d["user_id"]
    s = c.post("/onboarding/session", json={"user_id": uid}, headers=_h(tok)).json()
    sid = s["session_id"]
    for n, body in (
        (1, {"household": "solo", "life_stage": "solo", "income_stability": "stable", "family_context": "alone"}),
        (2, {"essential_expense_monthly": essential, "emergency_fund_months_self": 0,
             "has_dangerous_debt_self": debt, "near_term_priority": "debt" if debt else "safety"}),
        (3, {"surplus_habit": "hold", "risk_tolerance": 3, "agent_role_preference": "advisor_only"}),
        (4, {}),
    ):
        assert c.patch(f"/onboarding/session/{sid}/step/{n}", json=body, headers=_h(tok)).status_code == 200
    assert c.post(f"/onboarding/session/{sid}/complete", headers=_h(tok)).status_code == 200
    g = c.post("/goals", json={"user_id": uid, "type": "emergency_fund", "essential_expense_monthly": essential,
                               "current_amount": 0, "linked_from_onboarding": True}, headers=_h(tok))
    assert g.status_code == 201, g.text
    return {"uid": uid, "token": tok, "device_id": d.get("device_id"), "sid": sid}


def _register(c, ident, ip):
    body = {"password": PW, **({"email": ident} if "@" in ident else {"phone": ident})}
    r = c.post("/auth/register", json=body, headers={"CF-Connecting-IP": ip})
    assert r.status_code == 201, r.text
    return r.json()


def _claim(c, account_tok, guest_tok):
    r = c.post("/auth/guest/claim", json={"guest_token": guest_tok}, headers=_h(account_tok) if account_tok else {})
    body = r.json()
    return r.status_code, body


def _ef(c, tok):
    items = c.get("/goals", params={"type": "emergency_fund"}, headers=_h(tok)).json().get("items") or []
    return [g.get("essential_expense_monthly") for g in items]


def scenario_guest_claim() -> dict:
    from welora import auth as auth_svc
    from welora import guest_claim
    from welora.db.connection import get_connection

    c = _client()
    out: dict = {}
    page = c.get("/app/onboarding/result")
    out["page"] = [page.status_code, "/static/auth-gate.js" in page.text, "Đăng ký để lưu" in page.text]

    # 1) guest A onboards + 3-month fund, then registers → claim moves everything
    a = _guest_onboard(c, ESS_A)
    x = _register(c, "claim-x@example.test", "192.0.2.150")
    out["x_before"] = _ef(c, x["token"])
    code, body = _claim(c, x["token"], a["token"])
    out["claim1"] = [code, body.get("already"), body.get("moved", {}).get("goals"),
                     body.get("moved", {}).get("onboarding_sessions"), sorted(body.get("skipped", {}))]
    out["x_after"] = _ef(c, x["token"])
    dna = c.get(f"/users/{x['user_id']}/dna", headers=_h(x["token"]))
    out["x_dna"] = [dna.status_code, (dna.json() or {}).get("user_id") == x["user_id"],
                    ((dna.json() or {}).get("financial_snapshot_self") or {}).get("essential_expense_monthly")]
    out["x_gate"] = c.get(f"/users/{x['user_id']}/safety-gate", headers=_h(x["token"])).status_code
    out["x_constitution"] = c.get(f"/users/{x['user_id']}/personal-constitution", headers=_h(x["token"])).status_code
    # 2) idempotent + guest session closed
    code2, body2 = _claim(c, x["token"], a["token"])
    out["claim_again"] = [code2, body2.get("already")]
    out["guest_token_after"] = c.get("/goals", headers=_h(a["token"])).status_code
    out["x_after_again"] = _ef(c, x["token"])
    # 3) another account cannot take A's data
    y = _register(c, "0977 111 222", "192.0.2.151")
    code3, body3 = _claim(c, y["token"], a["token"])
    out["other_account"] = [code3, (body3.get("detail") or {}).get("error_code"), _ef(c, y["token"])]

    # 4) conflict policy: guest B (20M) into X which already has onboarding + EF (12M)
    b = _guest_onboard(c, ESS_B)
    code4, body4 = _claim(c, x["token"], b["token"])
    out["conflict"] = [code4, sorted(body4.get("skipped", {}).items()), body4.get("moved", {}).get("goals")]
    out["x_after_conflict"] = _ef(c, x["token"])
    conn = get_connection(None)
    try:
        out["b_goal_owner"] = [r["user_id"] == b["uid"] for r in conn.execute(
            "SELECT user_id FROM goals WHERE essential_expense_monthly=?", (ESS_B,)).fetchall()]
        out["b_sessions_kept"] = int(conn.execute(
            "SELECT COUNT(*) AS n FROM onboarding_sessions WHERE user_id=?", (b["uid"],)).fetchone()["n"])
        out["claimed_rows"] = sorted(
            [r["user_id"] == a["uid"] or r["user_id"] == b["uid"], r["claimed_by_user_id"] == x["user_id"],
             r["device_id"] is None]
            for r in conn.execute("SELECT user_id, claimed_by_user_id, device_id FROM users "
                                  "WHERE claimed_by_user_id IS NOT NULL").fetchall())
    finally:
        conn.close()

    # 5) steal / misuse attempts
    g = _guest_onboard(c, ESS_A)
    out["no_auth"] = _claim(c, None, g["token"])[0]
    out["password_token_as_guest"] = (lambda r: [r[0], (r[1].get("detail") or {}).get("error_code")])(
        _claim(c, y["token"], x["token"]))
    out["random_guest_token"] = _claim(c, y["token"], "x" * 40)[0]
    out["guest_as_account"] = (lambda r: [r[0], (r[1].get("detail") or {}).get("error_code")])(
        _claim(c, g["token"], _guest_onboard(c, ESS_A)["token"]))
    auth_svc.seed_partner_demo()
    demo = c.post("/auth/login", json={"email": auth_svc.DEMO_EMAIL, "password": auth_svc.DEMO_PASSWORD},
                  headers={"CF-Connecting-IP": "192.0.2.152"}).json()
    out["demo_target"] = (lambda r: [r[0], (r[1].get("detail") or {}).get("error_code")])(
        _claim(c, demo["token"], g["token"]))
    out["g_still_own"] = _ef(c, g["token"])

    # 6) existing account via LOGIN claims (no onboarding of its own) — phone account Y
    code6, body6 = _claim(c, c.post("/auth/login", json={"phone": "+84977111222", "password": PW},
                                    headers={"CF-Connecting-IP": "192.0.2.153"}).json()["token"], g["token"])
    out["login_claim"] = [code6, body6.get("moved", {}).get("goals"), _ef(c, y["token"])]

    # 7) concurrency: two accounts race for one guest → exactly one winner
    h = _guest_onboard(c, ESS_A)
    p = _register(c, "race-p@example.test", "192.0.2.154")
    q = _register(c, "race-q@example.test", "192.0.2.155")
    res: list = []
    barrier = threading.Barrier(2)

    def worker(acc):
        barrier.wait(timeout=10)
        try:
            r = guest_claim.claim_guest_data(acc["user_id"], h["token"])
            res.append(("ok", r["already"]))
        except guest_claim.ClaimError as e:
            res.append((e.status, e.code))
        except Exception as e:  # pragma: no cover
            res.append(("err", repr(e)))

    ts = [threading.Thread(target=worker, args=(acc,)) for acc in (p, q)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(60)
    out["race"] = sorted(str(r) for r in res)
    out["race_goals"] = sorted([len(_ef(c, p["token"])), len(_ef(c, q["token"]))])
    return out


def scenario_guest_claim_memory() -> dict:
    """Memory goal/onboarding store (local default): same claim path through the caches."""
    from welora import goals_api, onboarding

    c = _client()
    a = _guest_onboard(c, ESS_A)
    x = _register(c, "mem-x@example.test", "192.0.2.160")
    code, body = _claim(c, x["token"], a["token"])
    return {
        "store": type(goals_api.STORE).__name__,
        "claim": [code, body.get("already")],
        "x_goals": _ef(c, x["token"]),
        "x_dna": c.get(f"/users/{x['user_id']}/dna", headers=_h(x["token"])).status_code,
        "dna_cache_owner": (onboarding.DNA_BY_USER.get(x["user_id"]) or {}).get("user_id") == x["user_id"],
        "guest_cache_gone": a["uid"] not in onboarding.DNA_BY_USER,
    }


def scenario_guest_claim_otp() -> dict:
    """CoS review #239: phone-OTP-only and e-mail-OTP-only accounts (no password) are valid targets."""
    import os

    from welora import auth as auth_svc
    from welora.db.connection import get_connection

    os.environ["WELORA_OTP_ECHO"] = "1"
    c = _client()
    out: dict = {}
    g = _guest_onboard(c, ESS_A)
    req = c.post("/auth/otp/request", json={"phone": "0966 555 444"}, headers={"CF-Connecting-IP": "192.0.2.170"})
    ver = c.post("/auth/otp/verify", json={"challenge_id": req.json()["challenge_id"],
                                           "code": req.json()["pilot_code"]},
                 headers={"CF-Connecting-IP": "192.0.2.170"}).json()
    code, body = _claim(c, ver["token"], g["token"])
    out["phone_otp"] = [code, body.get("already"), body.get("moved", {}).get("goals"), _ef(c, ver["token"])]
    out["phone_otp_again"] = list(_claim(c, ver["token"], g["token"]))[0]

    # e-mail-OTP-only account (email_verified_at, no password) — row as written by verify_email_otp
    g2 = _guest_onboard(c, ESS_B)
    auth_svc.ensure_auth_schema()
    conn = get_connection(None)
    try:
        uid = "email-otp-" + uuid.uuid4().hex[:8]
        conn.execute("INSERT INTO users(user_id, display_name, device_id, email, role, email_verified_at) "
                     "VALUES (?,?,?,?,?,?)", (uid, "e", auth_svc.internal_device_key("email:"),
                                              uid + "@example.test", "guest", "2026-10-01T00:00:00+00:00"))
        etok = auth_svc._insert_token(conn, uid, kind="email_otp")
        # unverified e-mail account without password (not a real login) → still refused
        uid2 = "email-unverified-" + uuid.uuid4().hex[:8]
        conn.execute("INSERT INTO users(user_id, display_name, device_id, email, role) VALUES (?,?,?,?,?)",
                     (uid2, "u", auth_svc.internal_device_key("email:"), uid2 + "@example.test", "guest"))
        utok = auth_svc._insert_token(conn, uid2, kind="email_otp")
        conn.commit()
    finally:
        conn.close()
    code2, body2 = _claim(c, etok, g2["token"])
    out["email_otp"] = [code2, body2.get("moved", {}).get("goals"), _ef(c, etok)]
    g3 = _guest_onboard(c, ESS_A)
    code3, body3 = _claim(c, utok, g3["token"])
    out["unverified"] = [code3, (body3.get("detail") or {}).get("error_code")]
    return out


if __name__ == "__main__":
    name = sys.argv[1]
    result = globals()["scenario_" + name]()
    print("RESULT=" + json.dumps(result, default=str))
