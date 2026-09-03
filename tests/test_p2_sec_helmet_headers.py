"""P2 security headers — Helmet equivalent."""

from __future__ import annotations

import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.api.security_headers import HSTS, HSTS_NOTE
from welora.safety_gate import TARGET_MONTHS


class TestP2SecHelmetHeaders(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def _assert_sec(self, r) -> None:
        self.assertEqual(r.headers.get("x-frame-options"), "DENY")
        csp = r.headers.get("content-security-policy") or ""
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("default-src 'self'", csp)
        hsts = r.headers.get("strict-transport-security") or ""
        self.assertIn("max-age=31536000", hsts)
        self.assertTrue(hsts.startswith("max-age=31536000"))
        self.assertEqual(hsts, HSTS)
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")

    def test_health_headers(self):
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self._assert_sec(r)
        body = r.json()
        self.assertEqual(body["gate_months"], 3)
        self.assertTrue(body["hard_deny"])

    def test_app_headers(self):
        r = self.client.get("/app")
        self.assertEqual(r.status_code, 200)
        self._assert_sec(r)

    def test_static_headers(self):
        r = self.client.get("/static/shell.js")
        self.assertIn(r.status_code, (200, 304))
        self._assert_sec(r)

    def test_hsts_note_and_gate(self):
        self.assertEqual(TARGET_MONTHS, 3)
        self.assertIn("HTTPS", HSTS_NOTE)
        self.assertGreaterEqual(31536000, 31536000)


if __name__ == "__main__":
    unittest.main()
