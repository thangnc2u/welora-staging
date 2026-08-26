"""P2-E2 — GET /health and /healthz must be light liveness probes."""

from __future__ import annotations

import os
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app


class TestHealthLiveness(unittest.TestCase):
    def setUp(self) -> None:
        self.prev = {
            k: os.environ.get(k)
            for k in ("WELORA_ENV", "WELORA_STORE", "WELORA_LLM_PROVIDER")
        }
        os.environ["WELORA_ENV"] = "staging"
        os.environ["WELORA_STORE"] = "sqlite"
        os.environ["WELORA_LLM_PROVIDER"] = "stub"
        self.client = TestClient(create_app())

    def tearDown(self) -> None:
        for k, v in self.prev.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def _assert_body(self, body: dict) -> None:
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["service"], "welora")
        self.assertEqual(body["gate_months"], 3)
        self.assertTrue(body["hard_deny"])
        self.assertEqual(body["env"], "staging")

    def test_health_200(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self._assert_body(r.json())

    def test_healthz_alias(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        self._assert_body(r.json())


if __name__ == "__main__":
    unittest.main()
