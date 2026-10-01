#!/usr/bin/env python3
"""GP P0b round 2 — KUAT brute-force simulation (reproduces the CoS review attacks on a REAL uvicorn).

    python scripts/kuat_attack_sim.py [--root <checkout>] [--pg postgresql://…/db] [--out result.json]

--root  the checkout to attack (default: this repo) — run it on an older commit to get "before" numbers.
--pg    attack a PostgreSQL 17 database (schema ``public`` is dropped first — throwaway DB only);
        default: a fresh SQLite file.

Attacks (all from ONE client IP, via X-Forwarded-For through a trusted local proxy hop):
  (a) oracle key inference: new guests one after another; each probes N02-01 (then N02-02 once the
      attacker can pass N02-01) choosing the most likely options given everything learned so far
      (first guess "longest option", like the CoS script). Learns from whatever the submit returns:
      total score if any (exact count constraint), otherwise only pass/fail. Stops when the IP is
      locked out or after --budget graded submits. Then a fresh REAL account (e-mail + password)
      answers with the inferred key: does it pass N02-01 + N02-02 first try (= gate mastery)?
  (b) parallel burst: 25 parallel /academy/kuat/start for one user+node → open attempts in the DB;
      then every returned attempt submitted in parallel (wrong) → graded fails vs cap;
      plus 20 guests on the IP each submitting one wrong attempt at the same moment.
  (c) strategy pass rate (in-process Monte Carlo over the checkout's real draw/shuffle/grade):
      'longest', 'shortest', 'middle', 'random' for N02-01 and N02-02.
The /auth/device new-guest limit is raised for the run (WELORA_RL_DEVICE_NEW_IP_MAX) so only the KUAT
limits are measured (worst case: an attacker who paces guest creation).
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import random
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
NODES = ("N02-01", "N02-02")
ENUM_MAX = 600_000
SAMPLES = 40_000


# ------------------------------------------------------------------------------------------ server
def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Server:
    def __init__(self, root: Path, db_env: dict, extra: dict | None = None) -> None:
        self.port = _free_port()
        env = {k: v for k, v in os.environ.items() if not k.startswith("WELORA_")}
        env.update(db_env)
        env.update({"PORT": str(self.port), "PYTHONPATH": str(root), "WELORA_ENV": "staging",
                    "WELORA_DEMO_AUTOSEED": "0", "WELORA_RL_DEVICE_NEW_IP_MAX": "100000",
                    "WELORA_RL_REGISTER_IP_MAX": "100000",
                    "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""),
                    **(extra or {})})
        self.proc = subprocess.Popen(["bash", str(root / "start.sh")], cwd=str(root), env=env,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        t = time.time() + 90
        while time.time() < t:
            if self.proc.poll() is not None:
                raise SystemExit("server exited: " + self.proc.stdout.read().decode("utf-8", "replace")[-3000:])
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1)
                return
            except Exception:
                time.sleep(0.2)
        self.stop()
        raise SystemExit("server did not start")

    def call(self, method: str, path: str, body=None, token: str | None = None, ip: str = "203.0.113.50"):
        h = {"Content-Type": "application/json", "X-Forwarded-For": f"10.9.{random.randint(0, 255)}.1, {ip}"}
        if token:
            h["Authorization"] = "Bearer " + token
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except Exception:
                return e.code, {}

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def db_env(pg: str | None, tmp: str) -> dict:
    if pg:
        import psycopg

        with psycopg.connect(pg, autocommit=True) as c:
            c.execute("DROP SCHEMA IF EXISTS public CASCADE")
            c.execute("CREATE SCHEMA public")
        return {"WELORA_STORE": "postgres", "WELORA_DB_URL": pg}
    return {"WELORA_STORE": "sqlite", "WELORA_DB_URL": f"sqlite:///{tmp}/sim.db"}


def db_query(env: dict, sql: str, params=()):
    url = env["WELORA_DB_URL"]
    if url.startswith("sqlite"):
        import sqlite3

        c = sqlite3.connect(url.split("sqlite:///", 1)[1])
        try:
            return c.execute(sql, params).fetchall()
        finally:
            c.close()
    import psycopg

    with psycopg.connect(url) as c:
        return c.execute(sql.replace("?", "%s"), params).fetchall()


# ------------------------------------------------------------------------------------------ actors
def guest(srv: Server, ip: str = "203.0.113.50"):
    st, j = srv.call("POST", "/auth/device", {"device_id": "web-" + uuid.uuid4().hex[:16]}, ip=ip)
    assert st == 200, (st, j)
    return j["user_id"], j["token"]


def account(srv: Server, ip: str = "203.0.113.50"):
    st, j = srv.call("POST", "/auth/register", {"email": f"real-{uuid.uuid4().hex[:10]}@example.test",
                                                "password": "Mat-khau-that-dai-1"}, ip=ip)
    assert st in (200, 201), (st, j)
    return j["user_id"], j["token"]


def start(srv, uid, tok, node, ip="203.0.113.50"):
    srv.call("POST", f"/academy/nodes/{node}/read", {"user_id": uid, "node_id": node}, tok, ip=ip)
    return srv.call("POST", "/academy/kuat/start", {"user_id": uid, "node_id": node}, tok, ip=ip)


def submit(srv, uid, tok, node, att, picks: dict, ip="203.0.113.50"):
    """picks: prompt → chosen option TEXT."""
    answers = [{"question_id": q["id"], "choice": q["choices"].index(picks[q["prompt"]])} for q in att["questions"]]
    return srv.call("POST", "/academy/kuat", {"user_id": uid, "node_id": node, "attempt_id": att["attempt_id"],
                                              "answers": answers}, tok, ip=ip)


# ------------------------------------------------------------------------------------------ attacker model
class Model:
    """Consistent answer keys for one node given the observations (exact enumeration while small,
    else rejection sampling)."""

    def __init__(self) -> None:
        self.q: dict[str, list[str]] = {}  # prompt → sorted options
        self.hard: dict[str, bool] = {}
        self.obs: list[tuple[dict, str, object]] = []  # (picks, kind, value)

    def learn_questions(self, att: dict) -> None:
        for q in att["questions"]:
            self.q.setdefault(q["prompt"], sorted(q["choices"]))
            if "hard" in q:
                self.hard[q["prompt"]] = bool(q["hard"])

    def _consistent(self, key: dict) -> bool:
        for picks, kind, val in self.obs:
            ok = [key[p] == c for p, c in picks.items()]
            n = sum(ok)
            if kind == "count" and n != val:
                return False
            if kind == "pass":
                hard_ok = all(o for (p, _c), o in zip(picks.items(), ok) if self.hard.get(p, False))
                passed = n / len(ok) >= 0.7 and (hard_ok if self.hard else True)
                if val and n / len(ok) < 0.7:
                    return False
                if not val and self.hard and passed:
                    return False
        return True

    def keyspace(self) -> int:
        n = 1
        for opts in self.q.values():
            n *= len(opts)
        return n

    def candidates(self) -> tuple[list[dict], bool]:
        prompts = list(self.q)
        if self.keyspace() <= ENUM_MAX:
            cache = getattr(self, "_cache", None)
            if cache and cache[0] == tuple(prompts):
                obs_all, self.obs = self.obs, self.obs[cache[1]:]
                out = [k for k in cache[2] if self._consistent(k)]
                self.obs = obs_all
            else:
                out = [dict(zip(prompts, combo)) for combo in itertools.product(*(self.q[p] for p in prompts))]
                out = [k for k in out if self._consistent(k)]
            self._cache = (tuple(prompts), len(self.obs), out)
            return out, True
        rng = random.Random(7)
        out = []
        for _ in range(SAMPLES):
            k = {p: rng.choice(self.q[p]) for p in prompts}
            if self._consistent(k):
                out.append(k)
        return out, False

    def best_picks(self, att: dict) -> dict:
        cands, _exact = self.candidates()
        picks = {}
        for q in att["questions"]:
            p = q["prompt"]
            if cands:
                cnt = {c: 0 for c in q["choices"]}
                for k in cands:
                    cnt[k[p]] = cnt.get(k[p], 0) + 1
                picks[p] = max(q["choices"], key=lambda c: (cnt.get(c, 0), len(c)))
            else:
                picks[p] = max(q["choices"], key=len)
        return picks

    def summary(self) -> dict:
        cands, exact = self.candidates()
        frac = len(cands) / (len(cands) if exact else SAMPLES) if cands else 0.0
        remaining = len(cands) if exact else int(frac * self.keyspace())
        unique = exact and len(cands) == 1 and len(self.q) >= 12
        return {"questions_seen": len(self.q), "keyspace": self.keyspace(), "consistent_keys": remaining,
                "exact": exact, "key_inferred": unique}


def attack_oracle(srv: Server, budget: int) -> dict:
    models = {n: Model() for n in NODES}
    graded = {n: 0 for n in NODES}
    oracle_kind = None
    guests = 0
    blocked_streak = 0
    events = []
    fails = 0
    inferred_at: dict = {}
    while sum(graded.values()) < budget and blocked_streak < 3:
        uid, tok = guest(srv)
        guests += 1
        progressed = False
        for node in NODES:
            m = models[node]
            st, att = start(srv, uid, tok, node)
            if st != 200:
                events.append(f"guest{guests} {node} start {st}")
                break
            m.learn_questions(att)
            picks = m.best_picks(att)
            st, r = submit(srv, uid, tok, node, att, picks)
            if st != 200:
                events.append(f"guest{guests} {node} submit {st} {(r.get('detail') or r).get('reason', '') if isinstance(r.get('detail') or r, dict) else ''}")
                break
            progressed = True
            graded[node] += 1
            kr = r.get("kuat_result") or {}
            if kr.get("score") is not None:
                oracle_kind = "score"
                m.obs.append((picks, "count", round(float(kr["score"]) * len(att["questions"]))))
            else:
                oracle_kind = oracle_kind or "pass_fail"
                m.obs.append((picks, "pass", bool(kr.get("passed"))))
            if not kr.get("passed"):
                fails += 1
            if node not in inferred_at and m.summary()["key_inferred"]:
                inferred_at[node] = {"graded_submits_so_far": sum(graded.values()), "fails_so_far": fails,
                                     "guests_so_far": guests}
            if not kr.get("passed"):
                break  # next guest (N02-02 needs N02-01 passed first)
        blocked_streak = 0 if progressed else blocked_streak + 1
        if len(inferred_at) == len(NODES):
            break
    out = {"guests_used": guests, "graded_submits": graded, "graded_fails": fails, "oracle": oracle_kind,
           "stopped_by": ("key_inferred" if len(inferred_at) == len(NODES) else
                          "ip_lockout" if blocked_streak >= 3 else "budget"),
           "key_inferred_at": inferred_at,
           "model": {n: models[n].summary() for n in NODES}, "last_events": events[-4:]}
    # real account with the inferred key (fresh IP: the attacker's IP is locked)
    uid, tok = account(srv, ip="198.51.100.77")
    first_try = {}
    for node in NODES:
        st, att = start(srv, uid, tok, node, ip="198.51.100.77")
        if st != 200:
            first_try[node] = f"start {st}"
            break
        models[node].learn_questions(att)
        st, r = submit(srv, uid, tok, node, att, models[node].best_picks(att), ip="198.51.100.77")
        first_try[node] = bool((r.get("kuat_result") or {}).get("passed")) if st == 200 else f"submit {st}"
        if first_try[node] is not True:
            break
    out["real_account_first_try"] = first_try
    out["real_account_gate_mastery"] = all(first_try.get(n) is True for n in NODES)
    return out


def _wrong(att):
    return {q["prompt"]: q["choices"][0] for q in att["questions"]}  # arbitrary, mostly wrong


def attack_burst(srv: Server, env: dict) -> dict:
    uid, tok = guest(srv, ip="203.0.113.60")
    node = "N02-01"
    srv.call("POST", f"/academy/nodes/{node}/read", {"user_id": uid, "node_id": node}, tok, ip="203.0.113.60")
    with ThreadPoolExecutor(25) as ex:
        starts = list(ex.map(lambda _i: srv.call("POST", "/academy/kuat/start", {"user_id": uid, "node_id": node},
                                                 tok, ip="203.0.113.60"), range(25)))
    ok = [a for s, a in starts if s == 200]
    ids = {a["attempt_id"] for a in ok}
    open_db = db_query(env, "SELECT COUNT(*) FROM academy_kuat_attempts WHERE user_id=? AND node_id=? AND used_at IS NULL",
                       (uid, node))[0][0]
    with ThreadPoolExecutor(25) as ex:  # every start response submitted at once (same id → same attempt)
        subs = list(ex.map(lambda a: submit(srv, uid, tok, node, a, _wrong(a), ip="203.0.113.60"), ok))
    graded_fail = sum(1 for s, r in subs if s == 200 and not (r.get("kuat_result") or {}).get("passed"))
    graded_pass = sum(1 for s, r in subs if s == 200 and (r.get("kuat_result") or {}).get("passed"))
    fails_db = db_query(env, "SELECT COUNT(*) FROM academy_kuat_attempts WHERE user_id=? AND outcome='failed'", (uid,))[0][0]
    # many guests, one IP, one wrong attempt each, all submitted at once
    gs = [guest(srv, ip="203.0.113.61") for _ in range(20)]
    atts = []
    for g_uid, g_tok in gs:
        st, a = start(srv, g_uid, g_tok, node, ip="203.0.113.61")
        if st == 200:
            atts.append((g_uid, g_tok, a))
    with ThreadPoolExecutor(20) as ex:
        gsubs = list(ex.map(lambda t: submit(srv, t[0], t[1], node, t[2], _wrong(t[2]), ip="203.0.113.61"), atts))
    return {
        "single_user": {"parallel_starts": 25, "start_status": sorted({s for s, _ in starts}),
                        "distinct_attempt_ids": len(ids), "open_attempts_in_db": int(open_db),
                        "parallel_submits": len(ok), "graded_fails": graded_fail, "graded_passes": graded_pass,
                        "failed_attempts_in_db": int(fails_db),
                        "submit_status": {str(k): sum(1 for s, _ in subs if s == k) for k in sorted({s for s, _ in subs})}},
        "guests_one_ip": {"guests": len(gs), "attempts_started": len(atts),
                          "graded": sum(1 for s, _ in gsubs if s == 200),
                          "status": {str(k): sum(1 for s, _ in gsubs if s == k) for k in sorted({s for s, _ in gsubs})}},
    }


# ------------------------------------------------------------------------------------------ (c) Monte Carlo
def strategy_rates(root: Path, trials: int) -> dict:
    sys.path.insert(0, str(root))
    from welora import academy  # noqa: E402  (the checkout under test)

    rng = random.Random(2026)

    def pick(strategy, choices):
        if strategy == "random":
            return rng.randrange(len(choices))
        order = sorted(range(len(choices)), key=lambda i: (len(choices[i]), rng.random()))
        if strategy == "longest":
            return order[-1]
        if strategy == "shortest":
            return order[0]
        return order[len(order) // 2]  # middle

    by_id = {}
    out = {}
    for node in NODES:
        by_id = {q["id"]: q for q in academy.QUESTIONS[node]}
        out[node] = {}
        for strategy in ("longest", "shortest", "middle", "random"):
            passed = 0
            for _ in range(trials):
                served = academy._draw(node)
                answers = []
                for i, slot in enumerate(served):
                    q = by_id[slot["q"]]
                    shown = [q["choices"][j] for j in slot["perm"]]
                    answers.append({"question_id": f"k{i + 1}", "choice": pick(strategy, shown)})
                res = academy._grade_served(node, served, answers)
                passed += bool(res[1] if isinstance(res, tuple) else res)
            out[node][strategy] = round(passed / trials, 4)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(HERE))
    ap.add_argument("--pg", default="")
    ap.add_argument("--budget", type=int, default=80)
    ap.add_argument("--trials", type=int, default=20000)
    ap.add_argument("--out", default="")
    ap.add_argument("--skip", default="", help="comma list of a,b,c to skip")
    a = ap.parse_args()
    root = Path(a.root).resolve()
    skip = set(filter(None, a.skip.split(",")))
    res: dict = {"root": str(root), "db": "postgres" if a.pg else "sqlite"}
    try:
        res["commit"] = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        pass
    tmp = tempfile.mkdtemp(prefix="kuat-sim-")
    if not {"a", "b"} <= skip:
        env = db_env(a.pg or None, tmp)
        srv = Server(root, env)
        try:
            if "a" not in skip:
                res["a_oracle"] = attack_oracle(srv, a.budget)
            if "b" not in skip:
                res["b_burst"] = attack_burst(srv, env)
        finally:
            srv.stop()
    if "c" not in skip:
        res["c_strategies"] = strategy_rates(root, a.trials)
    text = json.dumps(res, ensure_ascii=False, indent=2)
    print(text)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
