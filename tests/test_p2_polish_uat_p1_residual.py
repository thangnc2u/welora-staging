"""P2 polish — git_sha /health, /app/os alias, money.css stub (+ light Academy UX)."""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
ACADEMY = STATIC / "academy.html"


class TestP2PolishUatP1Residual(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = {
            k: os.environ.get(k)
            for k in (
                "WELORA_ENV",
                "WELORA_STORE",
                "WELORA_LLM_PROVIDER",
                "WELORA_GIT_SHA",
                "RENDER_GIT_COMMIT",
            )
        }
        os.environ["WELORA_ENV"] = "staging"
        os.environ["WELORA_STORE"] = "memory"
        os.environ["WELORA_LLM_PROVIDER"] = "stub"
        os.environ["WELORA_GIT_SHA"] = "abc1234deadbeef"
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_health_includes_git_sha_short(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["gate_months"], 3)
        self.assertTrue(body["hard_deny"])
        self.assertEqual(body["git_sha"], "abc1234")
        self.assertEqual(len(body["git_sha"]), 7)
        self.assertTrue(re.fullmatch(r"[0-9a-fA-F]{7}", body["git_sha"]))

    def test_healthz_also_git_sha(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["git_sha"], "abc1234")
        self.assertEqual(r.json()["gate_months"], 3)
        self.assertTrue(r.json()["hard_deny"])

    def test_app_os_not_404(self):
        r = self.client.get("/app/os", follow_redirects=False)
        self.assertNotEqual(r.status_code, 404)
        self.assertIn(r.status_code, (302, 303, 307, 200))
        if r.status_code in (302, 303, 307):
            loc = r.headers.get("location") or ""
            self.assertTrue(
                loc.endswith("/app") or loc.endswith("/app/") or loc == "/app",
                loc,
            )

    def test_money_css_200_and_js_intact(self):
        css = self.client.get("/static/money.css")
        self.assertEqual(css.status_code, 200)
        self.assertTrue((STATIC / "money.css").is_file())
        js = self.client.get("/static/money.js")
        self.assertEqual(js.status_code, 200)
        self.assertIn("formatVnd", js.text)
        self.assertIn("formatPct", js.text)
        goals = self.client.get("/app/goals")
        self.assertEqual(goals.status_code, 200)
        self.assertIn("/static/money.js", goals.text)

    def test_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.json()["gate_months"], 3)
        self.assertTrue(r.json()["hard_deny"])

    def test_academy_p1_nudge_gold_and_card_openable(self):
        html = ACADEMY.read_text(encoding="utf-8")
        self.assertIn('id="osNudge" class="btn-primary"', html)
        self.assertNotIn('id="osNudge" class="nudge"', html)
        self.assertIn("openable", html)
        self.assertIn("user_id:uid", html)
        self.assertIn("Thiếu user_id", html)
        page = self.client.get("/app/academy")
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="osNudge" class="btn-primary"', page.text)


if __name__ == "__main__":
    unittest.main()
