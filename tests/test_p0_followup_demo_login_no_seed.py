"""CoS review of PR #237 — opening /app/login must never reseed demo data.

* login.html reads GET /auth/demo/accounts (aliases + labels, no user_ids) — never the seed.
* POST /auth/demo/seed: admin + 2FA only; 404 whenever WELORA_ENV=production.
* P1–P6 demo login still works from the login page after the startup seed alone.
Runs on SQLite, or PG17 via WELORA_TEST_POSTGRES_URL.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests._authz import admin_2fa_headers, admin_demo_seed, token_for
from tests._db_target import db_env
from welora import auth as auth_svc
from welora import demo_seed_runner
from welora.api.app import create_app
from welora.db.connection import get_connection
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
LOGIN_HTML = ROOT / "welora" / "api" / "static" / "login.html"
NODE = shutil.which("node")
ENV_KEYS = ("WELORA_ENV", "WELORA_STORE", "WELORA_DB_URL", "WELORA_GUEST_DEMO", "WELORA_ADMIN_TOTP_SECRETS")
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = {k: os.environ.get(k) for k in ENV_KEYS}
        for k in ENV_KEYS:
            os.environ.pop(k, None)
        self.tmp = tempfile.mkdtemp(prefix="welora-dl-")
        os.environ.update({"WELORA_ENV": "staging", "WELORA_GUEST_DEMO": "1", **db_env(self.tmp)})
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def demo_users(self) -> int:
        auth_svc.ensure_auth_schema(None)
        conn = get_connection(None)
        try:
            return conn.execute("SELECT COUNT(*) AS n FROM users WHERE email LIKE '%@welora.demo'").fetchone()["n"]
        finally:
            conn.close()


class TestDemoAccountsEndpoint(_Base):
    def test_lists_p1_p6_without_ids_and_never_seeds(self):
        before = self.demo_users()
        r = self.client.get("/auth/demo/accounts")
        self.assertEqual(r.status_code, 200)
        d = r.json()
        self.assertTrue(d["enabled"])
        self.assertEqual(d["email"], auth_svc.DEMO_EMAIL)
        self.assertEqual([a["persona"] for a in d["accounts"]], ["P1", "P2", "P3", "P4", "P5", "P6"])
        for a in d["accounts"]:
            self.assertEqual(set(a), {"persona", "email", "label", "household"})
        self.assertNotIn("user_id", r.text)
        self.assertIsNone(UUID_RE.search(r.text))
        for word in ("token", "hash", "secret"):
            self.assertNotIn(word, r.text.lower())
        for _ in range(3):
            self.client.get("/auth/demo/accounts")
        self.assertEqual(self.demo_users(), before)  # read-only

    def test_disabled_when_demo_off_or_production(self):
        os.environ["WELORA_GUEST_DEMO"] = "0"
        self.assertEqual(self.client.get("/auth/demo/accounts").json(), {"enabled": False, "accounts": []})
        os.environ["WELORA_GUEST_DEMO"] = "1"
        os.environ["WELORA_ENV"] = "production"
        self.assertEqual(self.client.get("/auth/demo/accounts").json(), {"enabled": False, "accounts": []})


class TestDemoSeedAdminOnly(_Base):
    def test_anonymous_and_non_admin_refused(self):
        r = self.client.post("/auth/demo/seed")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"]["error_code"], "ADMIN_LOGIN_REQUIRED")
        user = {"Authorization": "Bearer " + token_for("plain-user-1", kind="password")}
        self.assertEqual(self.client.post("/auth/demo/seed", headers=user).status_code, 403)
        self.assertEqual(self.demo_users(), 0)  # nothing seeded

    def test_admin_without_2fa_session_refused(self):
        from welora import admin_2fa

        secret = admin_2fa.generate_secret()
        os.environ["WELORA_ADMIN_TOTP_SECRETS"] = f"seed-admin-no2fa:{secret}"
        tok = token_for("seed-admin-no2fa", kind="email_otp", role="admin")
        r = self.client.post("/auth/demo/seed", headers={"Authorization": "Bearer " + tok})
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.json()["detail"]["error_code"], "ADMIN_2FA_REQUIRED")
        self.assertEqual(self.demo_users(), 0)

    def test_admin_2fa_seeds(self):
        r = admin_demo_seed(self.client)
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json()["rich"]["p2_gate"], "passed")
        self.assertEqual(r.json()["rich"]["p4_gate"], "not_passed")
        self.assertEqual(self.demo_users(), 6)

    def test_production_always_404(self):
        os.environ["WELORA_ENV"] = "production"
        with admin_2fa_headers() as h:
            r = self.client.post("/auth/demo/seed", headers=h)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.client.post("/auth/demo/seed").status_code, 404)
        self.assertEqual(self.demo_users(), 0)


class TestLoginPageNoSeed(_Base):
    def test_login_html_never_calls_seed(self):
        html = LOGIN_HTML.read_text(encoding="utf-8")
        self.assertNotIn("/auth/demo/seed", html)
        self.assertIn("fetch('/auth/demo/accounts')", html)
        self.assertNotIn("innerHTML", html)
        self.assertIn('id="demoBox"', html)
        self.assertIn('id="demoList"', html)

    def test_opening_login_does_not_touch_demo_data(self):
        demo_seed_runner.run_demo_seed(wait=True)  # = what startup auto-seed does
        conn = get_connection(None)
        try:
            conn.execute("UPDATE users SET display_name='Đang demo' WHERE email=?", (auth_svc.DEMO_EMAIL,))
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(self.client.get("/app/login").status_code, 200)
        self.client.get("/auth/demo/accounts")
        conn = get_connection(None)
        try:
            name = conn.execute("SELECT display_name FROM users WHERE email=?", (auth_svc.DEMO_EMAIL,)).fetchone()["display_name"]
        finally:
            conn.close()
        self.assertEqual(name, "Đang demo")

    def test_p1_p6_login_after_startup_seed_only(self):
        demo_seed_runner.run_demo_seed(wait=True)
        d = self.client.get("/auth/demo/accounts").json()
        gates = {}
        for a in d["accounts"]:
            r = self.client.post("/auth/login", json={"email": a["email"], "password": d["password_hint"]})
            self.assertEqual(r.status_code, 200, (a["persona"], r.text))
            uid, tok = r.json()["user_id"], r.json()["token"]
            g = self.client.get(f"/users/{uid}/safety-gate", headers={"Authorization": "Bearer " + tok})
            self.assertEqual(g.status_code, 200, g.text)
            gates[a["persona"]] = g.json().get("status")
        self.assertEqual(gates["P2"], "passed")
        self.assertEqual(gates["P4"], "not_passed")

    @unittest.skipUnless(NODE, "node not installed")
    def test_login_page_script_only_reads_accounts(self):
        p = subprocess.run([NODE, str(ROOT / "tests" / "js" / "fe_harness.js"), "login_page_demo_list"],
                           capture_output=True, text=True, timeout=60)
        out = json.loads([ln for ln in p.stdout.splitlines() if ln.startswith("RESULT=")][0][7:])
        self.assertEqual(out["methods"], ["GET /auth/demo/accounts"])
        self.assertFalse(out["box_hidden"])
        self.assertEqual(out["picks"], ["P1 · demo-p1@welora.demo", "P4 · demo-p4@welora.demo"])
        self.assertEqual(out["identifier"], "demo-p4@welora.demo")
        self.assertTrue(out["pw_focused"])

    def test_constraints(self):
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
