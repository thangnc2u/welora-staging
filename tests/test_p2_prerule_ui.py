"""P2 Native UI /app/pre-rule — debug Hard Deny; gated off by default."""

from __future__ import annotations

import os
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"


class TestP2PreRuleUi(unittest.TestCase):
    def setUp(self) -> None:
        self._prev = os.environ.get("WELORA_DEBUG_PRERULE")
        os.environ.pop("WELORA_DEBUG_PRERULE", None)
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        if self._prev is None:
            os.environ.pop("WELORA_DEBUG_PRERULE", None)
        else:
            os.environ["WELORA_DEBUG_PRERULE"] = self._prev

    def test_get_app_prerule_404_by_default(self):
        r = self.client.get("/app/pre-rule")
        self.assertEqual(r.status_code, 404)
        r2 = self.client.get("/app/pre-rule/")
        self.assertEqual(r2.status_code, 404)

    def test_get_app_prerule_200_when_debug_on(self):
        os.environ["WELORA_DEBUG_PRERULE"] = "1"
        client = TestClient(create_app())
        r = client.get("/app/pre-rule")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('id="q"', body)
        self.assertIn('id="go"', body)
        self.assertIn('id="guardrail"', body)
        self.assertIn('id="ruleHit"', body)
        self.assertIn('id="llmCalled"', body)
        self.assertIn('id="gateStatus"', body)
        self.assertIn('id="reply"', body)
        self.assertIn('id="navHome"', body)
        self.assertIn("welora_device_id", body)
        self.assertIn("/agent/pre-rule", body)
        self.assertNotIn("JSON.stringify(d)", body)
        self.assertNotIn("JSON.stringify(data)", body)
        self.assertNotIn("textContent=user_id", body)

    def test_home_has_nav_prerule(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        self.assertIn('id="navPreRule"', html)
        self.assertIn('href="/app/pre-rule"', html)

    def test_health_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertIn("dialect", b)
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
