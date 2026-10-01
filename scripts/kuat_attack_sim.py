#!/usr/bin/env python3
"""GP P0b rounds 2–4 — KUAT brute-force simulation (reproduces the CoS review attacks on a REAL uvicorn).

    python scripts/kuat_attack_sim.py [--root <checkout>] [--pg postgresql://…/db] [--out result.json]
                                      [--skip a,b,c,d,e] [--max-days 120] [--max-fails 1500] [--demo-ips 1]

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
      'longest', 'shortest', 'middle', 'random' and (round 3) the opening patterns 'pick an option
      starting with Không', 'avoid Không…', 'avoid Không, trừ khi…' for N02-01 and N02-02.
  (d) round 3 — throwaway accounts: register a new account (e-mail + password, no OTP) for every
      probe, all from ONE IP, and learn the key from pass/fail only with an exact Bayesian attacker
      (posterior over all 4^12 keys per node, Thompson-sampled picks; needs numpy). Whenever the
      server answers 429 the simulation "waits" retry_after seconds by ageing every rate-limit
      event in the database by that much (simulated clock — no real waiting). Reports graded fails
      per IP in the first 24 h, simulated time until the attacker is confident (every marginal
      ≥ 0.99) and whether a fresh OTP-verified account on another IP then passes N02-01 + N02-02
      first try. Bounded by --max-days (simulated) and --max-fails.
  (e) round 4 — demo personas P1–P6 (public password): (e1) outsiders on three networks each fail P2's
      N02-01 until the server refuses for the day (short cooldowns waited out on the simulated clock);
      then the partner on its own network: can it still take the KUAT with P2? (e2) the (d) attacker,
      but probing with the six demo personas from --demo-ips client IPs (rotating): graded fails per
      24 h, simulated time until the key is learned, does a fresh OTP-verified account pass first try.
The /auth/device new-guest limit is raised for the run (WELORA_RL_DEVICE_NEW_IP_MAX) so only the KUAT
limits are measured (worst case: an attacker who paces guest creation). /auth/register keeps its real
limit (WELORA_RL_IP_MAX, 20 / IP / 15 min); in (d) a 429 there makes the attacker wait one window on
the simulated clock. WELORA_OTP_ECHO=1 (staging pilot flag) lets the script create phone-OTP accounts.
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
                    "WELORA_OTP_ECHO": "1",
                    "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""),
                    **(extra or {})})
        # server output → a file (an unread PIPE fills up on long runs and blocks the server)
        self.log = tempfile.NamedTemporaryFile(prefix="kuat-sim-server-", suffix=".log", delete=False)
        self.proc = subprocess.Popen(["bash", str(root / "start.sh")], cwd=str(root), env=env,
                                     stdout=self.log, stderr=subprocess.STDOUT)
        t = time.time() + 90
        while time.time() < t:
            if self.proc.poll() is not None:
                raise SystemExit("server exited: " + Path(self.log.name).read_text("utf-8", "replace")[-3000:])
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


def verified_account(srv: Server, ip: str = "198.51.100.77"):
    """Phone-OTP account (consumed OTP challenge = verified contact)."""
    phone = "09" + "%08d" % random.randrange(10 ** 8)
    st, req = srv.call("POST", "/auth/otp/request", {"phone": phone}, ip=ip)
    assert st == 200 and req.get("pilot_code"), (st, req)
    st, ver = srv.call("POST", "/auth/otp/verify", {"challenge_id": req["challenge_id"], "code": req["pilot_code"]}, ip=ip)
    assert st == 200, (st, ver)
    return ver["user_id"], ver["token"]


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
    # real (OTP-verified) account with the inferred key (fresh IP: the attacker's IP is locked)
    uid, tok = verified_account(srv, ip="198.51.100.77")
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


# ------------------------------------------------------------------------------------------ (d) throwaway accounts
class Posterior:
    """Pass/fail-only attacker: exact Bayesian posterior over every answer key of the prompts seen so
    far (4 options each → 4^n keys, n ≤ 12), Thompson-sampled picks. Hard flags are hidden, so a fail
    with exactly 4/5 right is explained by 'the wrong one was hard' with probability h; eps keeps a
    mis-modelled observation from zeroing the true key."""

    def __init__(self, seed=0, h=0.6, eps=1e-3):
        import numpy as np

        self.np = np
        self.prompts, self.opts, self.idx = [], [], {}
        self.w = np.ones(1)
        self.h, self.eps = h, eps
        self.rng = np.random.default_rng(seed)
        self._dig = []

    def learn(self, questions):
        np = self.np
        for q in questions:
            if q["prompt"] in self.idx:
                continue
            self.idx[q["prompt"]] = len(self.prompts)
            self.prompts.append(q["prompt"])
            self.opts.append(sorted(q["choices"]))
            self.w = np.tile(self.w, len(q["choices"]))
            ar = np.arange(self.w.size, dtype=np.int64)
            self._dig = [((ar // (4 ** i)) % 4).astype(np.uint8) for i in range(len(self.prompts))]

    def observe(self, picks, passed):
        np = self.np
        cnt = np.zeros(self.w.size, dtype=np.uint8)
        for p, c in picks.items():
            i = self.idx[p]
            cnt += self._dig[i] == self.opts[i].index(c)
        n = len(picks)
        need = int(np.ceil(0.7 * n - 1e-9))
        if passed:
            like = np.where(cnt == n, 1.0, np.where(cnt >= need, 1 - self.h, self.eps))
        else:
            like = np.where(cnt == n, self.eps, np.where(cnt >= need, self.h, 1.0))
        self.w *= like
        self.w /= self.w.sum()

    def marginals(self):
        return [self.np.bincount(d, weights=self.w, minlength=4) for d in self._dig]

    def picks(self, questions, greedy=False):
        self.learn(questions)
        if greedy:
            m = self.marginals()
            return {q["prompt"]: self.opts[self.idx[q["prompt"]]][int(m[self.idx[q["prompt"]]].argmax())] for q in questions}
        cs = self.np.cumsum(self.w)
        key = int(self.np.searchsorted(cs, self.rng.random() * cs[-1]))
        return {q["prompt"]: self.opts[self.idx[q["prompt"]]][int(self._dig[self.idx[q["prompt"]]][key])] for q in questions}

    def confidence(self):
        return float(min(m.max() for m in self.marginals())) if len(self.prompts) >= 12 else 0.0


def age_rate_events(env: dict, seconds: float) -> None:
    """Simulated waiting: move every rate-limit event ``seconds`` into the past."""
    from datetime import datetime, timedelta

    rows = db_query(env, "SELECT event_id, created_at FROM auth_rate_events")
    url = env["WELORA_DB_URL"]
    upd = [((datetime.fromisoformat(str(c)) - timedelta(seconds=seconds)).isoformat(), e) for e, c in rows]
    if url.startswith("sqlite"):
        import sqlite3

        con = sqlite3.connect(url.split("sqlite:///", 1)[1])
        try:
            con.executemany("UPDATE auth_rate_events SET created_at=? WHERE event_id=?", upd)
            con.commit()
        finally:
            con.close()
        return
    import psycopg

    with psycopg.connect(url) as con:
        with con.cursor() as cur:
            cur.executemany("UPDATE auth_rate_events SET created_at=%s WHERE event_id=%s", upd)


def attack_throwaway(srv: Server, env: dict, max_days: float, max_fails: int, ip: str = "203.0.113.70") -> dict:
    models = {n: Posterior(seed=i + 1) for i, n in enumerate(NODES)}
    waited = 0.0
    fails = {n: 0 for n in NODES}
    passes = {n: 0 for n in NODES}
    first_day_fails = 0
    accounts = 0
    waits: dict = {}
    learned_at: dict = {}
    started = time.time()

    def now_sim():  # simulated time = waited-out seconds + real seconds the run itself took (round 4)
        return waited + (time.time() - started)

    def wait(r):
        nonlocal waited
        d = r.get("detail") or {}
        sec = float(d.get("retry_after") or 60) + 1
        waits[d.get("reason") or "?"] = waits.get(d.get("reason") or "?", 0) + 1
        age_rate_events(env, sec)
        waited += sec

    while now_sim() < max_days * 86400 and sum(fails.values()) < max_fails and len(learned_at) < len(NODES):
        st, j = srv.call("POST", "/auth/register", {"email": f"t-{uuid.uuid4().hex[:12]}@example.test",
                                                    "password": "Mat-khau-that-dai-1"}, ip=ip)  # register only — no OTP
        if st == 429:  # register limit (20 / IP / 15 min): pace account creation
            waits["register"] = waits.get("register", 0) + 1
            age_rate_events(env, 901)
            waited += 901
            continue
        assert st in (200, 201), (st, j)
        uid, tok = j["user_id"], j["token"]
        accounts += 1
        for node in NODES:
            m = models[node]
            st, att = start(srv, uid, tok, node, ip=ip)
            if st == 429:
                wait(att)
                break
            if st != 200:
                break
            picks = m.picks(att["questions"], greedy=node in learned_at)
            st, r = submit(srv, uid, tok, node, att, picks, ip=ip)
            if st == 429:
                wait(r)
                break
            if st != 200:
                break
            ok = bool((r.get("kuat_result") or {}).get("passed"))
            m.observe(picks, ok)
            if node not in learned_at and (fails[node] + passes[node]) % 5 == 0 and m.confidence() >= 0.99:
                learned_at[node] = {"sim_hours": round(now_sim() / 3600, 2), "fails_total": sum(fails.values())}
            if ok:
                passes[node] += 1
                continue  # same account goes on to N02-02
            fails[node] += 1
            if now_sim() < 86400:
                first_day_fails += 1
            break
    out = {"ip": ip, "accounts_registered": accounts, "graded_fails": fails, "graded_passes": passes,
           "graded_fails_first_24h_one_ip": first_day_fails, "lock_reasons": waits,
           "simulated_days": round(now_sim() / 86400, 2), "key_learned_at": learned_at,
           "stopped_by": ("key_learned" if len(learned_at) == len(NODES) else
                          "max_days" if now_sim() >= max_days * 86400 else "max_fails"),
           "confidence": {n: round(models[n].confidence(), 3) for n in NODES}, "wall_s": round(time.time() - started)}
    uid, tok = verified_account(srv, ip="198.51.100.78")
    first = {}
    for node in NODES:
        st, att = start(srv, uid, tok, node, ip="198.51.100.78")
        if st != 200:
            first[node] = f"start {st}"
            break
        st, r = submit(srv, uid, tok, node, att, models[node].picks(att["questions"], greedy=True), ip="198.51.100.78")
        first[node] = bool((r.get("kuat_result") or {}).get("passed")) if st == 200 else f"submit {st}"
        if first[node] is not True:
            break
    out["verified_account_first_try"] = first
    out["verified_account_gate_mastery"] = all(first.get(n) is True for n in NODES)
    return out


# ------------------------------------------------------------------------------------------ (e) demo personas
def demo_logins(srv: Server) -> dict:
    """Log in as P1–P6 with the public demo password (the server seeds them at start-up)."""
    sys.path.insert(0, str(HERE))
    emails = {"P1": "demo-p1@welora.demo", "P2": "partner@welora.demo", "P3": "demo-p3@welora.demo",
              "P4": "demo-p4@welora.demo", "P5": "demo-p5@welora.demo", "P6": "demo-p6@welora.demo"}
    out = {}
    deadline = time.time() + 120
    for pid, email in emails.items():
        while True:
            st, j = srv.call("POST", "/auth/login", {"email": email, "password": "WeloraDemo1!"},
                             ip="192.0.2.%d" % (int(pid[1]) + 10))
            if st == 200:
                out[pid] = (j["user_id"], j["token"])
                break
            if time.time() > deadline:
                raise SystemExit(f"demo login {pid}: {st} {j}")
            time.sleep(1)
    return out


def attack_demo_burn(srv: Server, env: dict, personas: dict) -> dict:
    uid, tok = personas["P2"]
    nets = ["203.0.113.81", "203.0.113.82", "203.0.113.83"]
    per_net, reasons = {}, {}
    for ip in nets:
        graded, waited = 0, 0.0
        while waited < 86400:
            st, att = start(srv, uid, tok, "N02-01", ip=ip)
            r = att
            if st == 200:
                st, r = submit(srv, uid, tok, "N02-01", att, _wrong(att), ip=ip)
                if st == 200:
                    graded += 1
                    continue
            if st != 429:
                break
            d = r.get("detail") or {}
            if d.get("reason") in ("fails", "ip", "starts") and float(d.get("retry_after") or 0) <= 3600:
                age_rate_events(env, float(d["retry_after"]) + 1)  # short cooldown: wait it out
                waited += float(d["retry_after"]) + 1
                continue
            reasons[ip] = d.get("reason")
            break
        per_net[ip] = graded
    st, att = start(srv, uid, tok, "N02-01", ip="198.51.100.90")  # the partner's own network
    partner = {"start": st, "reason": (att.get("detail") or {}).get("reason") if st != 200 else None}
    if st == 200:
        st2, r = submit(srv, uid, tok, "N02-01", att, _wrong(att), ip="198.51.100.90")
        partner["submit"] = st2
        partner["graded"] = st2 == 200
    return {"outsider_graded_fails_per_network": per_net, "outsider_stopped_by": reasons,
            "partner_other_network": partner}


def attack_demo_learn(srv: Server, env: dict, personas: dict, max_days: float, max_fails: int, n_ips: int) -> dict:
    ips = ["203.0.113.%d" % (100 + i) for i in range(n_ips)]
    models = {n: Posterior(seed=11 + i) for i, n in enumerate(NODES)}
    waited = 0.0
    fails = {n: 0 for n in NODES}
    passes = {n: 0 for n in NODES}
    first_day_fails = 0
    waits: dict = {}
    learned_at: dict = {}
    started = time.time()
    blocked: set = set()  # (persona, ip) refused since the last wait
    order = [(pid, ip) for ip in ips for pid in sorted(personas)]
    k = 0

    def wait_min(sec):
        nonlocal waited
        age_rate_events(env, sec)
        waited += sec
        blocked.clear()

    def now_sim():  # simulated time = waited-out seconds + real seconds the run itself took
        return waited + (time.time() - started)

    pending_wait = []
    timeline = []
    while now_sim() < max_days * 86400 and sum(fails.values()) < max_fails and len(learned_at) < len(NODES):
        if len(blocked) >= len(order):  # every persona on every IP refused → wait the shortest retry
            wait_min(min(pending_wait) + 1)
            pending_wait.clear()
            continue
        pid, ip = order[k % len(order)]
        k += 1
        if (pid, ip) in blocked:
            continue
        uid, tok = personas[pid]
        for node in NODES:
            m = models[node]
            st, att = start(srv, uid, tok, node, ip=ip)
            r = att
            if st == 200:
                picks = m.picks(att["questions"], greedy=node in learned_at)
                st, r = submit(srv, uid, tok, node, att, picks, ip=ip)
            if len(timeline) < 40:
                timeline.append([round(now_sim() / 3600, 2), pid, ip, node, st, (r.get("detail") or {}).get("reason") if st != 200 else
                                 (r.get("kuat_result") or {}).get("passed")])
            if st == 429:
                d = r.get("detail") or {}
                waits[d.get("reason") or "?"] = waits.get(d.get("reason") or "?", 0) + 1
                pending_wait.append(float(d.get("retry_after") or 60))
                blocked.add((pid, ip))
                break
            if st == 403:  # N02-02 locked: this persona's N02-01 is not mastered (yet)
                break
            if st != 200:
                break
            ok = bool((r.get("kuat_result") or {}).get("passed"))
            m.observe(picks, ok)
            if node not in learned_at and (fails[node] + passes[node]) % 5 == 0 and m.confidence() >= 0.99:
                learned_at[node] = {"sim_hours": round(now_sim() / 3600, 2), "fails_total": sum(fails.values())}
            if ok:
                passes[node] += 1
                continue
            fails[node] += 1
            if now_sim() < 86400:
                first_day_fails += 1
            break
    out = {"ips": n_ips, "graded_fails": fails, "graded_passes": passes,
           "graded_fails_first_24h": first_day_fails,
           "graded_fails_first_24h_per_ip": round(first_day_fails / n_ips, 1), "lock_reasons": waits,
           "simulated_days": round(now_sim() / 86400, 2), "key_learned_at": learned_at,
           "stopped_by": ("key_learned" if len(learned_at) == len(NODES) else
                          "max_days" if now_sim() >= max_days * 86400 else "max_fails"),
           "confidence": {n: round(models[n].confidence(), 3) for n in NODES}, "wall_s": round(time.time() - started),
           "timeline_first_40": timeline}
    uid, tok = verified_account(srv, ip="198.51.100.79")
    first = {}
    for node in NODES:
        st, att = start(srv, uid, tok, node, ip="198.51.100.79")
        if st != 200:
            first[node] = f"start {st}"
            break
        st, r = submit(srv, uid, tok, node, att, models[node].picks(att["questions"], greedy=True), ip="198.51.100.79")
        first[node] = bool((r.get("kuat_result") or {}).get("passed")) if st == 200 else f"submit {st}"
        if first[node] is not True:
            break
    out["verified_account_first_try"] = first
    out["verified_account_gate_mastery"] = all(first.get(n) is True for n in NODES)
    return out


# ------------------------------------------------------------------------------------------ (c) Monte Carlo
def strategy_rates(root: Path, trials: int) -> dict:
    sys.path.insert(0, str(root))
    from welora import academy  # noqa: E402  (the checkout under test)

    rng = random.Random(2026)

    def starts(c, prefix):
        return c.strip().lower().startswith(prefix)

    def pick(strategy, choices):
        if strategy == "random":
            return rng.randrange(len(choices))
        if strategy in ("pick_khong", "avoid_khong", "avoid_khong_tru_khi"):  # round 3: opening patterns
            prefix = "không, trừ khi" if strategy == "avoid_khong_tru_khi" else "không"
            hit = [i for i, c in enumerate(choices) if starts(c, prefix)]
            pool = hit if strategy == "pick_khong" else [i for i in range(len(choices)) if i not in hit]
            return rng.choice(pool) if pool else rng.randrange(len(choices))
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
        for strategy in ("longest", "shortest", "middle", "random", "pick_khong", "avoid_khong", "avoid_khong_tru_khi"):
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
    ap.add_argument("--skip", default="", help="comma list of a,b,c,d to skip")
    ap.add_argument("--max-days", type=float, default=120.0, help="(d) simulated-time bound")
    ap.add_argument("--max-fails", type=int, default=1500, help="(d) graded-fail bound")
    ap.add_argument("--demo-ips", type=int, default=1, help="(e2) client IPs the demo-persona attacker rotates over")
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
    if "d" not in skip:  # own, fresh database (its simulated clock ages every rate-limit event)
        env = db_env(a.pg or None, tempfile.mkdtemp(prefix="kuat-sim-d-"))
        srv = Server(root, env)
        try:
            res["d_throwaway"] = attack_throwaway(srv, env, a.max_days, a.max_fails)
        finally:
            srv.stop()
    if "e" not in skip:  # demo personas: own database, seeded by the server at start-up
        env = db_env(a.pg or None, tempfile.mkdtemp(prefix="kuat-sim-e-"))
        srv = Server(root, env, {"WELORA_DEMO_AUTOSEED": "1", "WELORA_GUEST_DEMO": "1"})
        try:
            personas = demo_logins(srv)
            res["e1_demo_burn"] = attack_demo_burn(srv, env, personas)
            age_rate_events(env, 2 * 86400)  # a fresh day for the learning attacker
            res["e2_demo_learn"] = attack_demo_learn(srv, env, personas, a.max_days, a.max_fails, a.demo_ips)
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
