"""P0 authz — user-scoped endpoints: effective user = bearer token owner (IDOR fix).

Per endpoint: no token → 401 (VI message) · other user's token → 403 (VI message) · owner → 2xx.
Onboarding sessions persist in the shared DB (create → instance cache lost → PATCH still 200).
Runs on SQLite by default; set WELORA_TEST_POSTGRES_URL to run the same tests on PostgreSQL.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from tests._db_target import db_env
from welora.api.app import AUTH_REQUIRED_MSG, FORBIDDEN_OTHER_USER_MSG, create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"

STEP1 = {"life_stage": "young_single", "income_stability": "stable", "family_context": "alone"}
STEP2 = {"essential_expense_monthly": 8_000_000, "has_dangerous_debt_self": False, "near_term_priority": "safety"}


class _Base(unittest.TestCase):
    ENV_KEYS = ("WELORA_STORE", "WELORA_DB_URL", "WELORA_GUEST_DEMO")

    def setUp(self) -> None:
        self._prev = {k: os.environ.get(k) for k in self.ENV_KEYS}
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ.update(db_env(self._tmpdir.name))
        os.environ["WELORA_GUEST_DEMO"] = "1"
        import welora.onboarding as ob

        ob.SESSIONS.clear()
        ob.DNA_BY_USER.clear()
        ob.CONSTITUTION_BY_USER.clear()
        self.ob = ob
        self.client = TestClient(create_app())
        self.a = self.device("p0-authz-a")
        self.b = self.device("p0-authz-b")

    def tearDown(self) -> None:
        for k, v in self._prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self._tmpdir.cleanup()

    def device(self, device_id: str) -> dict:
        r = self.client.post("/auth/device", json={"device_id": device_id})
        self.assertIn(r.status_code, (200, 201), r.text)
        out = r.json()
        self.assertTrue(out.get("token"))
        return out

    @staticmethod
    def h(user: dict) -> dict:
        return {"Authorization": "Bearer " + user["token"]}

    def call(self, method: str, url: str, body=None, headers=None):
        kw = {"headers": headers or {}}
        if body is not None:
            kw["json"] = body
        return self.client.request(method.upper(), url, **kw)

    def assert_401(self, r):
        self.assertEqual(r.status_code, 401, r.text)
        self.assertEqual(r.json()["detail"]["error_code"], "AUTH_REQUIRED")
        self.assertEqual(r.json()["detail"]["message"], AUTH_REQUIRED_MSG)

    def assert_403(self, r):
        self.assertEqual(r.status_code, 403, r.text)
        self.assertEqual(r.json()["detail"]["error_code"], "FORBIDDEN_OTHER_USER")
        self.assertEqual(r.json()["detail"]["message"], FORBIDDEN_OTHER_USER_MSG)

    def triad(self, method: str, url: str, body=None, owner_ok=(200, 201)):
        """no token → 401 · other user's token → 403 · owner → 2xx."""
        with self.subTest(case="no-token", url=url):
            self.assert_401(self.call(method, url, body))
        with self.subTest(case="other-user", url=url):
            self.assert_403(self.call(method, url, body, self.h(self.b)))
        r = self.call(method, url, body, self.h(self.a))
        with self.subTest(case="owner", url=url):
            self.assertIn(r.status_code, owner_ok, r.text)
        return r


class TestUserIdRoutes(_Base):
    def test_query_and_path_user_id_routes(self):
        A = self.a["user_id"]
        for url in (
            f"/os/accounts?user_id={A}",
            f"/goals?user_id={A}",
            f"/users/{A}/safety-gate",
            f"/academy/tree?user_id={A}",
            f"/users/{A}/health-score",
            f"/users/{A}/mastery",
            f"/budget?user_id={A}",
            f"/os/envelopes?user_id={A}",
            f"/os/reminders?user_id={A}",
            f"/os/estate-checklist?user_id={A}",
            f"/os/companion?user_id={A}",
            f"/os/dual-control/pending?user_id={A}",
            f"/os/transactions?user_id={A}",
            f"/os/categories?user_id={A}",
            f"/os/persona?user_id={A}",
            f"/agent/decision-logs?user_id={A}",
            f"/api/core/v1/entitlements/me?user_id={A}",
        ):
            self.triad("GET", url)

    def test_owner_without_user_id_defaults_to_token_user(self):
        for url in ("/os/accounts", "/goals", "/academy/tree", "/os/categories"):
            self.assert_401(self.call("GET", url))
            self.assertEqual(self.call("GET", url, headers=self.h(self.a)).status_code, 200, url)

    def test_body_user_id_routes(self):
        A = self.a["user_id"]
        self.triad("POST", "/agent/pre-rule", {"user_id": A, "message": "tôi muốn mua vàng"})
        self.triad("POST", "/os/categories/seed-defaults", {"user_id": A})
        self.triad("POST", "/onboarding/session", {"user_id": A}, owner_ok=(201,))

    def test_body_without_user_id_uses_token_user(self):
        r = self.call("POST", "/onboarding/session", {}, self.h(self.a))
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["user_id"], self.a["user_id"])

    def test_resource_id_routes_check_owner(self):
        A = self.a["user_id"]
        self.assertEqual(self.call("POST", "/os/categories/seed-defaults", {"user_id": A}, self.h(self.a)).status_code, 200)
        cats = self.call("GET", "/os/categories", headers=self.h(self.a)).json()
        items = cats.get("items") or cats.get("categories") or []
        self.assertTrue(items, cats)
        self.triad("GET", f"/os/categories/{items[0]['category_id']}")

    def test_admin_role_gets_no_bypass(self):
        from welora.db.connection import get_connection

        conn = get_connection(None)
        try:
            conn.execute("UPDATE users SET role='admin' WHERE user_id=?", (self.b["user_id"],))
            conn.commit()
        finally:
            conn.close()
        self.assert_403(self.call("GET", f"/os/accounts?user_id={self.a['user_id']}", headers=self.h(self.b)))
        self.assert_403(self.call("GET", f"/users/{self.a['user_id']}/safety-gate", headers=self.h(self.b)))

    def test_invalid_token_is_401(self):
        self.assert_401(self.call("GET", f"/goals?user_id={self.a['user_id']}", headers={"Authorization": "Bearer nope"}))

    def test_anonymous_entitlements_view_still_public(self):
        self.assertEqual(self.call("GET", "/api/core/v1/entitlements/me").status_code, 200)
        self.assertEqual(self.call("GET", "/api/core/v1/entitlements/pricing").status_code, 200)

    def test_public_by_design_routes(self):
        for url in ("/constitution/core", "/os/categories/defaults", "/content"):
            self.assertEqual(self.call("GET", url).status_code, 200, url)


class TestOnboardingPersistence(_Base):
    def _start(self) -> str:
        r = self.call("POST", "/onboarding/session", {"user_id": self.a["user_id"]}, self.h(self.a))
        self.assertEqual(r.status_code, 201, r.text)
        return r.json()["session_id"]

    def test_step_patch_authz(self):
        sid = self._start()
        self.triad("PATCH", f"/onboarding/session/{sid}/step/1", STEP1)
        self.assert_401(self.call("POST", f"/onboarding/session/{sid}/complete"))
        self.assert_403(self.call("POST", f"/onboarding/session/{sid}/complete", headers=self.h(self.b)))

    def test_create_then_patch_survives_instance_cache_loss(self):
        """C1 regression: 201 then PATCH 404 — sessions must live in the shared DB."""
        sid = self._start()
        self.ob.SESSIONS.clear()  # another worker / restarted instance
        r = self.call("PATCH", f"/onboarding/session/{sid}/step/1", STEP1, self.h(self.a))
        self.assertEqual(r.status_code, 200, r.text)
        self.ob.SESSIONS.clear()
        r = self.call("PATCH", f"/onboarding/session/{sid}/step/2", STEP2, self.h(self.a))
        self.assertEqual(r.status_code, 200, r.text)
        self.ob.SESSIONS.clear()
        done = self.call("POST", f"/onboarding/session/{sid}/complete", headers=self.h(self.a))
        self.assertEqual(done.status_code, 200, done.text)
        # DNA + constitution readable after the in-process cache is gone
        self.ob.SESSIONS.clear()
        self.ob.DNA_BY_USER.clear()
        self.ob.CONSTITUTION_BY_USER.clear()
        A = self.a["user_id"]
        self.assertEqual(self.call("GET", f"/users/{A}/dna", headers=self.h(self.a)).status_code, 200)
        self.assertEqual(self.call("GET", f"/users/{A}/personal-constitution", headers=self.h(self.a)).status_code, 200)
        self.assert_403(self.call("GET", f"/users/{A}/dna", headers=self.h(self.b)))
        self.assert_401(self.call("GET", f"/users/{A}/personal-constitution"))

    def test_unknown_session_is_404_for_logged_in_user(self):
        r = self.call("PATCH", "/onboarding/session/does-not-exist/step/1", STEP1, self.h(self.a))
        self.assertEqual(r.status_code, 404, r.text)

    def test_session_row_in_shared_db(self):
        sid = self._start()
        from welora.db.connection import get_connection

        conn = get_connection(None)
        try:
            row = conn.execute("SELECT user_id, status FROM onboarding_sessions WHERE session_id=?", (sid,)).fetchone()
        finally:
            conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row["user_id"], self.a["user_id"])

    def test_migration_idempotent(self):
        from welora.db.migrate import migrate

        migrate(None)
        self.assertEqual(migrate(None), [])  # second run applies nothing
        sid = self._start()
        self.assertTrue(sid)


class TestMetricsContentAndDemo(_Base):
    def test_metrics_admin_only(self):
        r = self.call("GET", "/metrics")
        self.assertEqual(r.status_code, 401, r.text)
        r = self.call("GET", "/metrics", headers=self.h(self.a))
        self.assertEqual(r.status_code, 403, r.text)

    def test_content_body_strips_internal_header_keeps_keys(self):
        """No internal WP/WA header block anywhere in any body (incl. the 6 multi-WP keys);
        user-facing warnings like '- **Mức rủi ro: Cao.**' survive; keys/metadata intact."""
        import re

        from welora import content_map as cm

        internal = re.compile(
            r"^\s*(#{1,3}\s*W[PA]-[0-9A-Za-z-]+\s*[:：]|\*\*\s*(Module|Mức rủi ro|Version|Status|principle_key|secondary_keys)\s*:\s*\*\*)",
            re.IGNORECASE,
        )
        items = self.call("GET", "/content").json()["items"]
        self.assertGreaterEqual(len(items), 38)
        multi = {"SAFE-01", "BUDG-01", "ADJUST-01", "DEBT-02", "FREE-01", "INSURE-01"}
        self.assertTrue(multi <= {it["principle_key"] for it in items})
        kept_warnings = 0
        for it in items:
            key = it["principle_key"]
            r = self.call("GET", f"/content/{key}")
            self.assertEqual(r.status_code, 200, key)
            art = r.json()
            body = art["body_markdown"]
            self.assertTrue(body.strip(), key)
            bad = [ln for ln in body.splitlines() if internal.match(ln)]
            self.assertEqual(bad, [], key)
            self.assertEqual(art["principle_key"], key)
            self.assertTrue(art.get("risk_level") is not None or art.get("risk_label") is not None, key)
            # user-facing "Mức rủi ro:" warning lines from the raw source are all preserved
            _, raw = cm.service_get_content(key)
            raw_warn = [ln for ln in raw["body_markdown"].splitlines() if "Mức rủi ro:" in ln and not internal.match(ln)]
            got_warn = [ln for ln in body.splitlines() if "Mức rủi ro:" in ln]
            self.assertEqual(raw_warn, got_warn, key)
            kept_warnings += len(got_warn)
            if key in multi:
                self.assertTrue(re.search(r"(?m)^# WP-", raw["body_markdown"].split("\n", 3)[-1]), f"{key}: fixture no longer multi-WP")
        self.assertGreater(kept_warnings, 0)
        self.assertTrue(any(ln.lstrip().startswith("- **Mức rủi ro:") for it in items for ln in self.call("GET", f"/content/{it['principle_key']}").json()["body_markdown"].splitlines()))

    def test_demo_personas_login_and_read_own_data(self):
        from welora.auth import DEMO_PASSWORD

        seed = self.call("POST", "/auth/demo/seed")
        self.assertEqual(seed.status_code, 200, seed.text)
        emails = ((seed.json().get("rich") or {}).get("persona_emails")) or {}
        self.assertEqual(set(emails), {"P1", "P2", "P3", "P4", "P5", "P6"})
        uids = {}
        for pid, email in emails.items():
            login = self.call("POST", "/auth/login", {"email": email, "password": DEMO_PASSWORD})
            self.assertEqual(login.status_code, 200, login.text)
            tok = {"Authorization": "Bearer " + login.json()["token"]}
            uid = login.json()["user_id"]
            uids[pid] = (uid, tok)
            for url in (f"/os/accounts?user_id={uid}", f"/goals?user_id={uid}", f"/users/{uid}/safety-gate", f"/academy/tree?user_id={uid}"):
                self.assertEqual(self.call("GET", url, headers=tok).status_code, 200, f"{pid} {url}")
        p1, p2 = uids["P1"], uids["P2"]
        self.assert_403(self.call("GET", f"/os/accounts?user_id={p2[0]}", headers=p1[1]))
        self.assert_401(self.call("GET", f"/os/accounts?user_id={p2[0]}"))
        accts = self.call("GET", "/os/accounts", headers=p2[1]).json()
        self.assertTrue(accts.get("items") or accts.get("accounts"), accts)

    def test_frontend_sends_bearer(self):
        js = (STATIC / "session.js").read_text(encoding="utf-8")
        self.assertIn('h.set("Authorization", "Bearer " + t)', js)
        self.assertIn('path === "/auth/device"', js)
        self.assertNotIn("localStorage.setItem(TOKEN_KEY", js)  # guest token stays in memory
        for page in ("constitution", "onboarding", "parser", "prerule", "demo", "metrics"):
            html = (STATIC / f"{page}.html").read_text(encoding="utf-8")
            s = html.find('src="/static/session.js"')
            i = html.find("<script>")
            self.assertTrue(0 <= s < i, f"{page}: session.js must load before inline scripts")
        # logged-in token first; a device token is minted only when there is none
        self.assertIn("(!token() || storedRejected)", js)
        for page in ("parser", "prerule", "demo", "constitution", "onboarding"):
            html = (STATIC / f"{page}.html").read_text(encoding="utf-8")
            self.assertIn("WeloraSession.resolveUserId", html, page)

    def test_invariants_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)


if __name__ == "__main__":
    unittest.main()
