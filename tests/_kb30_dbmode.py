"""Subprocess scenarios for item 15 of "GP follow-up sau OTP #244 + Academy #245" (the 30 new
12-question KUAT banks) on a DB store (SQLite, or PG17 when the parent passes a postgres WELORA_DB_URL).
Usage: python -m tests._kb30_dbmode <scenario> → RESULT=<json>."""

from __future__ import annotations

import json
import sys
import time
import uuid

from tests._k019_dbmode import _open, _q, _start, _x
from tests._p0b_dbmode import _client, _guest, _h, _rand_ip


def _chain(node: str) -> list[str]:
    """The prerequisite chain of ``node`` (module order), node itself last."""
    from welora import academy

    out = [node]
    while academy._NODE_BY_ID[out[0]]["prereq_node_ids"]:
        out.insert(0, academy._NODE_BY_ID[out[0]]["prereq_node_ids"][0])
    return out


def scenario_banks_http() -> dict:
    """Every new bank over HTTP, walking each module's unlock chain as one learner: 5 questions × 4
    options, no answer / correctness / hard marker; a wrong set fails, then a learner who knows the
    lesson passes (pass / fail only) and the next node unlocks."""
    from tests._kuat import pass_kuat_http
    from tests.test_kuat_banks_30 import BANKS_30

    c = _client()
    out = {}
    for last in ("N01-07", "N02-07", "N03-07", "N04-07", "N05-07"):
        g, gt = _guest(c)
        h = _h(gt, _rand_ip("203.0.113."))
        for node in _chain(last):
            if node in BANKS_30:
                n = c.get(f"/academy/nodes/{node}", params={"user_id": g}, headers=h).json()
                qs = n["questions"]
                fail = pass_kuat_http(c, g, h, node, correct=False)
            ok = pass_kuat_http(c, g, h, node)
            if node in BANKS_30:
                out[node] = {"count": len(qs), "choices": sorted({len(q["choices"]) for q in qs}),
                             "keys": sorted({k for q in qs for k in q}),
                             "bank_size": n["kuat"].get("bank_size"), "question_count": n["kuat"].get("question_count"),
                             "fail": fail[:2], "fail_result_keys": sorted((fail[2].get("kuat_result") or {}).keys()),
                             "pass": ok[:2]}
    return out


def scenario_stale_bank_attempt() -> dict:
    """An attempt issued from the OLD 3-question bank (ids q102a…) before the deploy: reopening the
    lesson retires it and serves the new bank; submitting it → 409, nothing graded or counted."""
    from tests._kuat import pass_kuat_http
    from welora import academy
    from welora.auth_ratelimit import _iso

    c = _client()
    out = {}
    for node in ("N01-02", "N03-05", "N05-07"):
        pre = "q" + node[2] + node[4:]
        old_served = [{"q": pre + "a", "perm": [2, 0, 1]}, {"q": pre + "b", "perm": [1, 2, 0]},
                      {"q": pre + "c", "perm": [1, 0, 2]}]
        res = {}
        for label in ("start", "submit"):
            uid, tok = _guest(c)
            ip = _rand_ip("203.0.113.")
            for prev in _chain(node)[:-1]:  # unlock the node the way a learner does
                assert pass_kuat_http(c, uid, _h(tok, ip), prev)[:2] == (200, True), prev
            old = uuid.uuid4().hex
            _x("INSERT INTO academy_kuat_attempts(attempt_id, user_id, node_id, served_json, created_at, expires_at, "
               "scope_key) VALUES (?,?,?,?,?,?,?)",
               (old, uid, node, json.dumps(old_served), _iso(time.time() - 60), _iso(time.time() + 1500), ""))
            if label == "start":
                st, j = _start(c, uid, tok, node, ip)
                prompts = {q["prompt"] for q in academy.QUESTIONS[node]}
                res["start"] = {"status": st, "new_attempt": j.get("attempt_id") != old,
                                "five_current": len(j.get("questions") or []) == 5
                                and all(q["prompt"] in prompts and len(q["choices"]) == 4 for q in j["questions"]),
                                "old_outcome": _q("SELECT outcome FROM academy_kuat_attempts WHERE attempt_id=?",
                                                  (old,))[0]["outcome"],
                                "open": len(_open(uid, node))}
            else:
                fails0 = len(_q("SELECT 1 FROM auth_rate_events WHERE action='kuat_fail'"))
                r = c.post("/academy/kuat", json={"user_id": uid, "node_id": node, "attempt_id": old,
                                                  "answers": [{"question_id": f"k{i}", "choice": 0} for i in (1, 2, 3)]},
                           headers=_h(tok, ip))
                res["submit"] = {"status": r.status_code, "code": (r.json().get("detail") or {}).get("error_code"),
                                 "fails": len(_q("SELECT 1 FROM auth_rate_events WHERE action='kuat_fail'")) - fails0,
                                 "old_outcome": _q("SELECT outcome FROM academy_kuat_attempts WHERE attempt_id=?",
                                                   (old,))[0]["outcome"]}
        out[node] = res
    return out


if __name__ == "__main__":
    print("RESULT=" + json.dumps(globals()["scenario_" + sys.argv[1]](), default=str))
