"""PR #239 CoS review fixes (P0 follow-up 2):

  B. XFF spoofing through uvicorn --proxy-headers on Render (FORWARDED_ALLOW_IPS=*) — start.sh /
     Dockerfile run uvicorn with --no-proxy-headers; verified through a REAL uvicorn process.
  1. Guest claim targets: phone-OTP / e-mail-OTP accounts (no password) are valid.
  2. /entitlements/events: body / payload caps (413 / 422) + per-user DB rate limit (429).
  3. IPv6 rate-limit buckets grouped by /64 (IPv4 unchanged, IPv4-mapped → IPv4).
  4. Phone numbers in phone_e164_conflicts (or matching several accounts): phone login, phone
     OTP and phone reset are refused for EVERY account of that number (Vietnamese "use e-mail").

SQLite by default; PostgreSQL 17 when WELORA_TEST_POSTGRES_URL is set (tests/_db_target.py).
"""

from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import uuid
from collections import Counter
from pathlib import Path

from tests._db_target import db_env
from tests.test_p0_followup2_auth import ENV_KEYS as _BASE_KEYS
from tests.test_p0_followup2_auth import PW, _Base
from tests.test_p0_followup2_guest_claim import run2
from welora import auth as auth_svc
from welora import auth_ratelimit as rl
from welora import entitlements as ent
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
EXTRA_KEYS = ("WELORA_RL_EVENT_USER_MAX", "WELORA_EVENT_MAX_BYTES")


class _ReviewBase(_Base):
    def setUp(self) -> None:
        self.prev_extra = {k: os.environ.get(k) for k in EXTRA_KEYS}
        for k in EXTRA_KEYS:
            os.environ.pop(k, None)
        super().setUp()

    def tearDown(self) -> None:
        super().tearDown()
        for k, v in self.prev_extra.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


# --- B. uvicorn proxy headers ----------------------------------------------------------------------

def _start_sh_args() -> list[str]:
    text = (ROOT / "start.sh").read_text(encoding="utf-8")
    m = re.search(r"exec python -m uvicorn(.*?)(?:\n\s*\n|\Z)", text, re.S)
    assert m, "uvicorn exec line not found in start.sh"
    return shlex.split(m.group(1).replace("\\\n", " "), comments=True)


class TestLaunchFlags(unittest.TestCase):
    def test_start_sh_disables_uvicorn_proxy_headers(self):
        args = _start_sh_args()
        self.assertIn("--no-proxy-headers", args)
        self.assertNotIn("--proxy-headers", args)
        self.assertNotIn("--forwarded-allow-ips", " ".join(args))
        text = (ROOT / "start.sh").read_text(encoding="utf-8")
        self.assertRegex(text, r'(?m)^export FORWARDED_ALLOW_IPS="127\.0\.0\.1"$')

    def test_every_launch_path(self):
        self.assertIn("startCommand: bash start.sh", (ROOT / "render.yaml").read_text(encoding="utf-8"))
        docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        cmd = [ln for ln in docker.splitlines() if ln.startswith("CMD ")]
        self.assertEqual(len(cmd), 1)
        self.assertIn('"--no-proxy-headers"', cmd[0])
        self.assertNotIn('"--proxy-headers"', cmd[0])
        for name in ("Procfile", "gunicorn.conf.py", "gunicorn_conf.py"):
            self.assertFalse((ROOT / name).exists(), name)
        for path in list(ROOT.glob("*.sh")) + list(ROOT.glob("*.toml")) + list(ROOT.glob("*.yaml")):
            code = "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#"))
            self.assertNotRegex(code, r"(?<!no-)--proxy-headers\b", str(path))


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _Server:
    """Real uvicorn via start.sh (or an explicit argv) with Render's FORWARDED_ALLOW_IPS=*."""

    def __init__(self, tmp: str, *, argv=None, extra_env: dict | None = None) -> None:
        self.port = _free_port()
        env = {k: v for k, v in os.environ.items() if not k.startswith("WELORA_")}
        env.update(db_env(tmp))
        env.update({
            "PORT": str(self.port), "FORWARDED_ALLOW_IPS": "*", "PYTHONPATH": str(ROOT), "WELORA_ENV": "staging",
            "WELORA_DEMO_AUTOSEED": "0", "WELORA_RL_LOGIN_IP_MAX": "5", "WELORA_RL_DEVICE_NEW_IP_MAX": "5",
            "PATH": os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", ""),
            **(extra_env or {}),
        })
        cmd = argv(self.port) if argv else ["bash", str(ROOT / "start.sh")]
        self.proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise AssertionError("server exited: " + self.proc.stdout.read().decode("utf-8", "replace")[-3000:])
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}/health", timeout=1)
                return
            except Exception:
                time.sleep(0.1)
        self.stop()
        raise AssertionError("server did not start")

    def post(self, path: str, body: dict, headers: dict) -> int:
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **headers})
        try:
            return urllib.request.urlopen(req, timeout=15).status
        except urllib.error.HTTPError as e:
            return e.code

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(10)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def _hammer(srv: _Server, n: int = 8) -> dict:
    """Rotating client-forged LEFTMOST XFF; the hop appended by Render's proxy stays the same."""
    login = [srv.post("/auth/login", {"email": f"nobody{i}@example.test", "password": "sai-mat-khau-1"},
                      {"X-Forwarded-For": f"198.18.0.{i + 1}, 203.0.113.7"}) for i in range(n)]
    device = [srv.post("/auth/device", {"device_id": "web-" + uuid.uuid4().hex[:12]},
                       {"X-Forwarded-For": f"198.19.0.{i + 1}, 203.0.113.8"}) for i in range(n)]
    # through Cloudflare: Render appends the CF edge; CF-Connecting-IP is the real client
    cf = [srv.post("/auth/device", {"device_id": "web-" + uuid.uuid4().hex[:12]},
                   {"X-Forwarded-For": f"198.20.0.{i + 1}, 198.51.100.9, 173.245.48.5",
                    "CF-Connecting-IP": "198.51.100.9"}) for i in range(n)]
    return {"login": login, "device": device, "cf": cf}


class TestRealUvicornClientIp(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="welora-uv-")

    def test_start_sh_rotating_leftmost_xff_still_hits_429(self):
        srv = _Server(self.tmp)
        try:
            out = _hammer(srv)
        finally:
            srv.stop()
        self.assertEqual(out["login"], [401] * 5 + [429] * 3)
        self.assertEqual(out["device"], [200] * 5 + [429] * 3)
        self.assertEqual(out["cf"], [200] * 5 + [429] * 3)

    def test_control_proxy_headers_is_spoofable(self):
        """Proves the test above detects the bug: the OLD flags (uvicorn --proxy-headers with
        FORWARDED_ALLOW_IPS=*) take the forged leftmost hop and never limit."""
        def argv(port):
            return [sys.executable, "-m", "uvicorn", "welora.api.app:app", "--host", "127.0.0.1", "--port", str(port),
                    "--workers", "1", "--proxy-headers", "--timeout-keep-alive", "5"]

        srv = _Server(self.tmp, argv=argv)
        try:
            out = _hammer(srv)
        finally:
            srv.stop()
        self.assertNotIn(429, out["login"])
        self.assertNotIn(429, out["device"])


# --- 1. guest claim: OTP accounts ------------------------------------------------------------------

class TestGuestClaimOtpTargets(unittest.TestCase):
    def test_phone_and_email_otp_accounts_can_claim(self):
        tmp = tempfile.mkdtemp()
        out = run2("guest_claim_otp", {"WELORA_GUEST_DEMO": "1", **db_env(tmp)})
        self.assertEqual(out["phone_otp"], [200, False, 1, [12000000.0]])
        self.assertEqual(out["phone_otp_again"], 200)
        self.assertEqual(out["email_otp"], [200, 1, [20000000.0]])
        self.assertEqual(out["unverified"], [403, "CLAIM_TARGET_NOT_ALLOWED"])


# --- 2. events caps + per-user rate limit ------------------------------------------------------------

class TestEventLimits(_ReviewBase):
    def setUp(self):
        super().setUp()
        ent.reset_state_for_tests()
        self.tok = {u: self.client.post("/auth/device", json={"device_id": "web-ev-" + u}).json()["token"]
                    for u in ("a", "b")}

    def post(self, user="a", event="pricing.view", payload=None, raw=None, headers=None):
        h = {"Authorization": "Bearer " + self.tok[user], "Content-Type": "application/json", **(headers or {})}
        data = raw if raw is not None else json.dumps({"event": event, "payload": payload or {"path": "/pricing"}})
        return self.client.post("/api/core/v1/entitlements/events", content=data, headers=h)

    def code(self, r):
        return r.status_code, (r.json().get("detail") or {}).get("error_code")

    def test_body_size_cap_413(self):
        big = {"path": "/pricing", "k": "x" * 3000}
        self.assertEqual(self.code(self.post(payload=big)), (413, "EVENT_TOO_LARGE"))
        os.environ["WELORA_EVENT_MAX_BYTES"] = "8192"
        self.assertEqual(self.code(self.post(payload=big)), (422, "EVENT_PAYLOAD_INVALID"))  # still > 256 chars
        self.assertEqual(self.post(raw="{" + " " * 9000 + "}").status_code, 413)
        self.assertEqual(len(ent.list_events(50)), 0)

    def test_payload_shape_422(self):
        cases = [
            {"nested": {"a": 1}}, {"list": [1, 2]}, {"s": "y" * 257}, {"bad key!": 1}, {"k" * 41: 1},
            {f"k{i}": i for i in range(21)},
        ]
        for p in cases:
            self.assertEqual(self.code(self.post(payload=p)), (422, "EVENT_PAYLOAD_INVALID"), p)
        for raw in ("not json", "[1,2]", json.dumps({"payload": {}})):
            self.assertEqual(self.code(self.post(raw=raw)), (422, "EVENT_PAYLOAD_INVALID"), raw)
        ok = self.post(payload={"path": "/pricing", "n": 3, "f": 1.5, "b": True, "z": None, "s": "y" * 256})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(len(ent.list_events(50)), 1)

    def test_per_user_rate_limit_429(self):
        os.environ["WELORA_RL_EVENT_USER_MAX"] = "3"
        self.assertEqual([self.post().status_code for _ in range(5)], [200, 200, 200, 429, 429])
        self.assertEqual(self.code(self.post()), (429, "RATE_LIMITED"))
        self.assertEqual(self.post(user="b").status_code, 200)  # per user, not global
        self.assertEqual(len(ent.list_events(50)), 4)
        rows = self.q("SELECT scope FROM auth_rate_events WHERE action='event'")
        self.assertEqual({r["scope"] for r in rows}, {"target"})

    def test_anonymous_still_401_and_not_counted(self):
        r = self.client.post("/api/core/v1/entitlements/events", json={"event": "pricing.view"})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM auth_rate_events WHERE action='event'")[0]["n"], 0)


# --- 3. IPv6 /64 buckets -----------------------------------------------------------------------------

class TestIpv6Buckets(_ReviewBase):
    def test_ip_bucket(self):
        self.assertEqual(rl.ip_bucket("203.0.113.9"), "203.0.113.9")
        self.assertEqual(rl.ip_bucket("2001:db8:1:2:aaaa::1"), "2001:db8:1:2::/64")
        self.assertEqual(rl.ip_bucket("2001:DB8:1:2:ffff:ffff:ffff:ffff"), "2001:db8:1:2::/64")
        self.assertNotEqual(rl.ip_bucket("2001:db8:1:3::1"), rl.ip_bucket("2001:db8:1:2::1"))
        self.assertEqual(rl.ip_bucket("::ffff:203.0.113.9"), "203.0.113.9")
        self.assertEqual(rl.ip_bucket("garbage"), "garbage")
        self.assertEqual(rl.ip_bucket(""), "")

    def test_device_new_limit_per_64(self):
        os.environ["WELORA_RL_DEVICE_NEW_IP_MAX"] = "3"
        codes = [self.client.post("/auth/device", json={"device_id": f"web-v6-{i:04d}"},
                                  headers=self.ip(f"2001:db8:aa:bb:{i:x}::{i + 1:x}")).status_code for i in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])
        other = self.client.post("/auth/device", json={"device_id": "web-v6-other"},
                                 headers=self.ip("2001:db8:aa:bc::1"))
        self.assertEqual(other.status_code, 200)  # next /64 is another subscriber

    def test_login_ip_limit_per_64_and_mapped_v4(self):
        os.environ["WELORA_RL_LOGIN_IP_MAX"] = "2"
        codes = [self.client.post("/auth/login", json={"email": f"v6-{i}@example.test", "password": "sai-1"},
                                  headers=self.ip(f"2001:db8:cc:dd::{i + 1:x}")).status_code for i in range(3)]
        self.assertEqual(codes, [401, 401, 429])
        mapped = [self.client.post("/auth/login", json={"email": f"v4-{i}@example.test", "password": "sai-1"},
                                   headers=self.ip(ip)).status_code
                  for i, ip in enumerate(("203.0.113.44", "::ffff:203.0.113.44", "203.0.113.44"))]
        self.assertEqual(mapped, [401, 401, 429])
        self.assertEqual(self.client.post("/auth/login", json={"email": "v4-x@example.test", "password": "sai-1"},
                                          headers=self.ip("203.0.113.45")).status_code, 401)  # IPv4 unchanged


# --- 4. phone conflicts ------------------------------------------------------------------------------

class TestPhoneConflictRefused(_ReviewBase):
    def setUp(self):
        super().setUp()
        auth_svc.ensure_auth_schema()
        # migration collision as left by 014: legacy '0…' row + '+84…' row = two accounts, reported
        for uid, phone, pw in (("pc-old", "0900111222", PW), ("pc-new", "+84900111222", "mat-khau-khac-3")):
            self.x("INSERT INTO users(user_id, display_name, device_id, phone, password_hash, role, email) "
                   "VALUES (?,?,?,?,?,?,?)", (uid, uid, "guest:" + uid, phone, auth_svc._hash_password(pw), "guest",
                                              uid + "@example.test"))
        self.x("INSERT INTO phone_e164_conflicts(id, table_name, normalized, user_ids, raw_values, detected_at) "
               "VALUES ('c1','users','+84900111222','[\"pc-new\",\"pc-old\"]','[]','2026-10-01T00:00:00+00:00')")

    def login(self, phone, pw, ip="192.0.2.201"):
        return self.client.post("/auth/login", json={"phone": phone, "password": pw}, headers=self.ip(ip))

    def test_login_refused_for_both_accounts_with_vi_message(self):
        for form in ("0900111222", "+84900111222", "84900111222"):
            for pw in (PW, "mat-khau-khac-3"):
                r = self.login(form, pw)
                self.assertEqual(r.status_code, 409, (form, pw))
                d = r.json()["detail"]
                self.assertEqual(d["error_code"], "PHONE_CONFLICT_USE_EMAIL")
                self.assertIn("đăng nhập bằng email", d["message"])
        # e-mail login still works for both
        for uid, pw in (("pc-old", PW), ("pc-new", "mat-khau-khac-3")):
            r = self.client.post("/auth/login", json={"email": uid + "@example.test", "password": pw},
                                 headers=self.ip("192.0.2.202"))
            self.assertEqual((r.status_code, r.json()["user_id"]), (200, uid))

    def test_wrong_password_looks_like_unknown_number(self):
        wrong = self.login("0900111222", "sai-mat-khau-9", ip="192.0.2.203")
        unknown = self.login("0900999888", "sai-mat-khau-9", ip="192.0.2.204")
        self.assertEqual((wrong.status_code, wrong.json()), (unknown.status_code, unknown.json()))
        self.assertEqual(wrong.status_code, 401)

    def test_reset_refused_for_both_and_identical_to_missing(self):
        os.environ["WELORA_RESET_ECHO"] = "1"
        bodies = [self.client.post("/auth/forgot-password", json={"phone": p}, headers=self.ip("192.0.2.205")).json()
                  for p in ("0900111222", "+84900111222", "0900999777")]
        for b in bodies:
            self.assertNotIn("reset_token", b)
            self.assertIn("dùng email", b["phone_note"])
        self.assertEqual(bodies[0], bodies[2])
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM password_reset_tokens")[0]["n"], 0)
        # the e-mail path still resets
        r = self.client.post("/auth/forgot-password", json={"email": "pc-old@example.test"}, headers=self.ip("192.0.2.206"))
        self.assertTrue(r.json().get("reset_token"))

    def test_phone_otp_refused_for_conflicted_number(self):
        os.environ["WELORA_OTP_FIXED"] = "1"
        ch = self.client.post("/auth/otp/request", json={"phone": "0900111222"}, headers=self.ip("192.0.2.207")).json()
        r = self.client.post("/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": "123456"},
                             headers=self.ip("192.0.2.207"))
        self.assertEqual((r.status_code, r.json()["detail"]["error_code"]), (409, "PHONE_CONFLICT_USE_EMAIL"))
        self.assertEqual(self.q("SELECT COUNT(*) AS n FROM auth_tokens WHERE kind='otp'")[0]["n"], 0)

    def test_reported_otp_conflict_alone_refuses(self):
        """A number reported only for otp_challenges (two OTP owners) is refused too."""
        os.environ["WELORA_OTP_FIXED"] = "1"
        self.x("INSERT INTO phone_e164_conflicts(id, table_name, normalized, user_ids, raw_values, detected_at) "
               "VALUES ('c2','otp_challenges','+84911222333','[\"a\",\"b\"]','[]','2026-10-01T00:00:00+00:00')")
        ch = self.client.post("/auth/otp/request", json={"phone": "+84911222333"}, headers=self.ip("192.0.2.208")).json()
        r = self.client.post("/auth/otp/verify", json={"challenge_id": ch["challenge_id"], "code": "123456"},
                             headers=self.ip("192.0.2.208"))
        self.assertEqual(r.status_code, 409)

    def test_rate_key_is_number_level_and_resolution_restores_login(self):
        self.assertEqual(auth_svc.login_rate_key(phone="0900111222"), "phone:+84900111222")
        # manual resolution: give the legacy account another number + drop the report → login works
        self.x("UPDATE users SET phone='+84900111999' WHERE user_id='pc-old'")
        self.x("DELETE FROM phone_e164_conflicts WHERE id='c1'")
        self.assertEqual(self.login("0900111222", "mat-khau-khac-3").json()["user_id"], "pc-new")
        self.assertEqual(self.login("0900111999", PW).json()["user_id"], "pc-old")

    def test_unreported_duplicate_rows_also_refused(self):
        self.x("INSERT INTO users(user_id, display_name, device_id, phone, password_hash, role) VALUES (?,?,?,?,?,?)",
               ("dup-a", "a", "guest:dup-a", "0977333444", auth_svc._hash_password(PW), "guest"))
        self.x("INSERT INTO users(user_id, display_name, device_id, phone, password_hash, role) VALUES (?,?,?,?,?,?)",
               ("dup-b", "b", "guest:dup-b", "+84977333444", auth_svc._hash_password(PW), "guest"))
        self.assertEqual(self.login("0977333444", PW).status_code, 409)

    def test_login_page_renders_object_detail(self):
        html = (ROOT / "welora" / "api" / "static" / "login.html").read_text(encoding="utf-8")
        self.assertIn("(dt&&(dt.message||dt.error))", html)
        self.assertIn("d.phone_note", (ROOT / "welora" / "api" / "static" / "forgot-password.html").read_text(encoding="utf-8"))


class TestConstraints(unittest.TestCase):
    def test_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
