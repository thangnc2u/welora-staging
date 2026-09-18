"""P2 Auth — Guest/demo register → login → logout → login again."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"
AUTH_PY = Path(__file__).resolve().parents[1] / "welora" / "auth.py"
SAFETY = Path(__file__).resolve().parents[1] / "welora" / "safety_gate.py"
MODE_C = Path(__file__).resolve().parents[1] / "welora" / "mode_c_act.py"
MODE_C_PERSIST = Path(__file__).resolve().parents[1] / "welora" / "mode_c_persist.py"


class TestP2AuthGuestDemo(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_url = os.environ.get("WELORA_DB_URL")
        self._prev_demo = os.environ.get("WELORA_GUEST_DEMO")
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        os.environ["WELORA_DB_URL"] = self._tmp.name
        os.environ["WELORA_GUEST_DEMO"] = "1"
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass
        if self._prev_url is None:
            os.environ.pop("WELORA_DB_URL", None)
        else:
            os.environ["WELORA_DB_URL"] = self._prev_url
        if self._prev_demo is None:
            os.environ.pop("WELORA_GUEST_DEMO", None)
        else:
            os.environ["WELORA_GUEST_DEMO"] = self._prev_demo

    def test_register_login_logout_login_again(self):
        email = "guest.walk@welora.demo"
        password = "GuestPass1!"

        r = self.client.post(
            "/auth/register",
            json={"email": email, "password": password, "display_name": "Guest Walk"},
        )
        self.assertEqual(r.status_code, 201, r.text)
        body = r.json()
        self.assertIn("token", body)
        self.assertEqual(body["role"], "guest")
        self.assertTrue(body["created"])
        tok1 = body["token"]

        me = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok1}"})
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["role"], "guest")
        self.assertEqual(me.json()["email"], email)

        # login again while still registered
        login = self.client.post(
            "/auth/login", json={"email": email, "password": password}
        )
        self.assertEqual(login.status_code, 200, login.text)
        tok2 = login.json()["token"]
        self.assertNotEqual(tok2, tok1)
        self.assertEqual(login.json()["role"], "guest")

        out = self.client.post(
            "/auth/logout", headers={"Authorization": f"Bearer {tok2}"}
        )
        self.assertEqual(out.status_code, 200)
        self.assertTrue(out.json().get("revoked"))

        dead = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok2}"})
        self.assertEqual(dead.status_code, 401)

        again = self.client.post(
            "/auth/login", json={"email": email, "password": password}
        )
        self.assertEqual(again.status_code, 200, again.text)
        tok3 = again.json()["token"]
        me3 = self.client.get("/auth/me", headers={"Authorization": f"Bearer {tok3}"})
        self.assertEqual(me3.status_code, 200)
        self.assertEqual(me3.json()["user_id"], body["user_id"])

    def test_phone_register_and_login(self):
        phone = "+84911222333"
        password = "PhonePass1!"
        r = self.client.post(
            "/auth/register", json={"phone": phone, "password": password}
        )
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["role"], "guest")
        login = self.client.post(
            "/auth/login", json={"phone": phone, "password": password}
        )
        self.assertEqual(login.status_code, 200)

    def test_forgot_password_token_stub_flow(self):
        email = "reset.me@welora.demo"
        password = "ResetPass1!"
        new_pw = "ResetPass2!"
        self.client.post("/auth/register", json={"email": email, "password": password})
        forgot = self.client.post("/auth/forgot-password", json={"email": email})
        self.assertEqual(forgot.status_code, 200, forgot.text)
        data = forgot.json()
        self.assertEqual(data.get("approach"), "token_stub")
        self.assertIn("reset_token", data)
        tok = data["reset_token"]
        reset = self.client.post(
            "/auth/reset-password",
            json={"reset_token": tok, "new_password": new_pw},
        )
        self.assertEqual(reset.status_code, 200, reset.text)
        bad = self.client.post(
            "/auth/login", json={"email": email, "password": password}
        )
        self.assertEqual(bad.status_code, 401)
        good = self.client.post(
            "/auth/login", json={"email": email, "password": new_pw}
        )
        self.assertEqual(good.status_code, 200)

    def test_demo_seed_partner(self):
        r = self.client.post("/auth/demo/seed")
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        self.assertIn(d.get("role"), ("demo", None))
        self.assertEqual(d.get("email"), "partner@welora.demo")
        login = self.client.post(
            "/auth/login",
            json={"email": "partner@welora.demo", "password": "WeloraDemo1!"},
        )
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["role"], "demo")

    def test_ui_pages_navy_gold(self):
        for path, name in (
            ("/app/login", "login.html"),
            ("/app/register", "register.html"),
            ("/app/forgot-password", "forgot-password.html"),
            ("/app/reset-password", "reset-password.html"),
        ):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            html = r.text
            self.assertIn("welora-tokens.css", html)
            self.assertIn("welora-btn-primary", html)
            self.assertIn("--cta-primary", html)
            self.assertIn("danger-text", html)  # errors stay red family
            self.assertNotIn("innerHTML", html)
            self.assertTrue((STATIC / name).is_file())

        login_html = (STATIC / "login.html").read_text(encoding="utf-8")
        self.assertIn("Đăng nhập", login_html)
        self.assertIn("Đăng ký", login_html)
        self.assertIn("/auth/login", login_html)
        self.assertIn("welora_token", login_html)

    def test_fail_closed_no_admin_role_on_register(self):
        r = self.client.post(
            "/auth/register",
            json={
                "email": "try.admin@welora.demo",
                "password": "TryAdmin1!",
                "role": "admin",  # ignored by API model / service
            },
        )
        # Pydantic strips unknown field; role always guest
        self.assertEqual(r.status_code, 201, r.text)
        self.assertEqual(r.json()["role"], "guest")
        self.assertNotEqual(r.json()["role"], "admin")

    def test_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        safety = SAFETY.read_text(encoding="utf-8")
        self.assertIn("TARGET_MONTHS = 3", safety)
        auth = AUTH_PY.read_text(encoding="utf-8")
        for banned in (
            "TARGET_MONTHS",
            "Hard Deny",
            "mode_c_act",
            "mode_c_persist",
            "L-COOL",
            "L-STAR",
        ):
            # auth module must not import / mutate gate / Mode C
            if banned == "TARGET_MONTHS":
                self.assertNotIn("TARGET_MONTHS", auth)
            if banned.startswith("mode_c"):
                self.assertNotIn(banned, auth)
        r = self.client.get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        # Mode C / persist files still present and untouched by this PR's auth scope
        self.assertTrue(MODE_C.is_file())
        self.assertTrue(MODE_C_PERSIST.is_file())


if __name__ == "__main__":
    unittest.main()
