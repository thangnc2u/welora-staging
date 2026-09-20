"""P2 UAT residual: demo seed P2+P4 DNA · hide WELORA_GUEST_DEMO · gate /app/pre-rule."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
HARD_DENY = ROOT / "welora" / "agent.py"
SAFETY = ROOT / "welora" / "safety_gate.py"
PERSONAS = ROOT / "welora" / "personas.py"


class TestP2UatResidualDemoPrerule(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_url = os.environ.get("WELORA_DB_URL")
        self._prev_demo = os.environ.get("WELORA_GUEST_DEMO")
        self._prev_debug = os.environ.get("WELORA_DEBUG_PRERULE")
        self._prev_store = os.environ.get("WELORA_STORE")
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        os.environ["WELORA_DB_URL"] = self._tmp.name
        os.environ["WELORA_GUEST_DEMO"] = "1"
        os.environ.pop("WELORA_DEBUG_PRERULE", None)
        os.environ["WELORA_STORE"] = "memory"
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        try:
            os.unlink(self._tmp.name)
        except OSError:
            pass
        for key, prev in (
            ("WELORA_DB_URL", self._prev_url),
            ("WELORA_GUEST_DEMO", self._prev_demo),
            ("WELORA_DEBUG_PRERULE", self._prev_debug),
            ("WELORA_STORE", self._prev_store),
        ):
            if prev is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = prev

    def test_demo_seed_p2_p4_dna_and_goals(self):
        r = self.client.post("/auth/demo/seed")
        self.assertEqual(r.status_code, 200, r.text)
        body = r.json()
        self.assertEqual(body.get("email"), "partner@welora.demo")
        self.assertNotIn("WELORA_GUEST_DEMO", r.text)
        personas = body.get("personas") or {}
        self.assertEqual(set(personas.keys()), {"P2", "P4"})
        for pid in ("P2", "P4"):
            meta = personas[pid]
            uid = meta["user_id"]
            dna = self.client.get(f"/users/{uid}/dna")
            self.assertEqual(dna.status_code, 200, dna.text)
            ident = dna.json().get("identity_context") or {}
            self.assertEqual(ident.get("persona_id") or ident.get("persona"), pid)
            goals = self.client.get("/goals", params={"user_id": uid})
            self.assertEqual(goals.status_code, 200, goals.text)
            items = goals.json().get("items") or []
            self.assertGreaterEqual(len(items), 1)
            types = {g.get("type") for g in items}
            self.assertTrue(types <= {"emergency_fund", "debt_payoff"}, types)
            self.assertTrue(set(meta.get("os_goals") or []) <= {"emergency_fund", "debt_payoff"})
            gate = self.client.get(f"/users/{uid}/safety-gate")
            self.assertEqual(gate.status_code, 200)
            # Must not bypass Hard Deny — R01 still denies all-in
            chat = self.client.post(
                "/agent/chat",
                json={"user_id": uid, "message": "Tôi muốn rút 50 triệu từ quỹ khẩn cấp để all-in một mã cổ phiếu đang nóng."},
            )
            self.assertEqual(chat.status_code, 200, chat.text)
            cj = chat.json()
            self.assertEqual(cj.get("guardrail_result"), "deny")
            self.assertIn(cj.get("rule_hit") or cj.get("rule_id"), ("R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"))

    def test_demo_html_selects_p2_and_p4(self):
        html = (STATIC / "demo.html").read_text(encoding="utf-8")
        self.assertIn('id="persona"', html)
        self.assertIn("P2", html)
        self.assertIn("P4", html)
        self.assertIn("young_family", html)
        self.assertIn("sandwich_3gen", html)
        self.assertIn("debt_payoff", html)
        self.assertIn("emergency_fund", html)

    def test_login_html_scrubs_guest_demo_flag_name(self):
        html = (STATIC / "login.html").read_text(encoding="utf-8")
        self.assertNotIn("WELORA_GUEST_DEMO", html)
        r = self.client.get("/app/login")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("WELORA_GUEST_DEMO", r.text)
        self.assertIn("Tài khoản demo partner", r.text)

    def test_prerule_gated_off_by_default(self):
        r = self.client.get("/app/pre-rule")
        self.assertEqual(r.status_code, 404)
        os.environ["WELORA_DEBUG_PRERULE"] = "1"
        client = TestClient(create_app())
        r2 = client.get("/app/pre-rule")
        self.assertEqual(r2.status_code, 200)
        self.assertIn('id="q"', r2.text)

    def test_health_and_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        safety = SAFETY.read_text(encoding="utf-8")
        self.assertIn("TARGET_MONTHS = 3", safety)
        agent = HARD_DENY.read_text(encoding="utf-8")
        for code in ("R01", "R02", "R03", "R04", "R05", "R06", "R07", "R08", "R09"):
            self.assertIn(code, agent)
        personas = PERSONAS.read_text(encoding="utf-8")
        for pid in ("P1", "P2", "P3", "P4", "P5", "P6"):
            self.assertIn(f'"{pid}"', personas)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
