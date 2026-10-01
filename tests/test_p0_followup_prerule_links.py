"""P0 follow-up #2 — /app/pre-rule is a working, login-gated page; no dead internal /app links."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests._db_target import db_env
from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"
# literals that are not navigations: shell.js path comparison, service-worker script (/app/sw.js)
NOT_LINKS = {"/app/home", "/app/sw"}


class TestPreRulePage(unittest.TestCase):
    def setUp(self) -> None:
        self.keys = ("WELORA_DEBUG_PRERULE", "WELORA_DB_URL", "WELORA_STORE")
        self.prev = {k: os.environ.get(k) for k in self.keys}
        os.environ.pop("WELORA_DEBUG_PRERULE", None)
        self.tmp = tempfile.mkdtemp()
        os.environ.update(db_env(self.tmp))
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_page_served_and_consistent(self):
        r = self.client.get("/app/pre-rule")
        self.assertEqual(r.status_code, 200)
        html = r.text
        self.assertIn('<html lang="vi"', html)
        self.assertIn('<script src="/static/auth-gate.js"></script>', html)
        self.assertIn("/static/welora-tokens.css", html)
        self.assertIn("/static/shell.css", html)
        self.assertRegex(html, r'src="/static/shell\.js(\?v=[^"]*)?" data-shell-tab="ops"')
        self.assertLess(html.index("/static/session.js"), html.index("fetch('/agent/pre-rule'"))
        self.assertNotIn("innerHTML", html)
        home = (STATIC / "home.html").read_text(encoding="utf-8")
        self.assertIn('href="/app/pre-rule"', home)

    def test_agent_prerule_with_logged_in_token(self):
        reg = self.client.post("/auth/register", json={"email": "prerule@example.test", "password": "matkhau-dai-1"})
        self.assertEqual(reg.status_code, 201, reg.text)
        tok, uid = reg.json()["token"], reg.json()["user_id"]
        r = self.client.post("/agent/pre-rule", json={"user_id": uid, "message": "Tôi muốn tất tay ETF ngay"},
                             headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r.status_code, 200, r.text)
        b = r.json()
        for k in ("guardrail_result", "rule_hit", "should_call_llm", "safety_gate_status"):
            self.assertIn(k, b)
        self.assertEqual(self.client.post("/agent/pre-rule", json={"user_id": uid, "message": "x"}).status_code, 401)

    def test_no_dead_internal_app_links(self):
        found: dict[str, set[str]] = {}
        for f in sorted(list(STATIC.glob("*.html")) + list(STATIC.glob("*.js"))):
            for m in re.finditer(r"""["'`](/app(?:/[A-Za-z0-9_\-/]*)?)""", f.read_text(encoding="utf-8")):
                found.setdefault(m.group(1), set()).add(f.name)
        dead = []
        for path, files in sorted(found.items()):
            if path in NOT_LINKS:
                continue
            probe = path + ("x1" if path.endswith("/") and path.count("/") > 2 else "")  # '/app/content/'+id
            code = self.client.get(probe, follow_redirects=False).status_code
            if code >= 400:
                dead.append((path, code, sorted(files)))
        self.assertEqual(dead, [])
        self.assertGreater(len(found), 25)

    def test_constraints(self):
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
