"""P2 Native UI /app/metrics — readable counters, no JSON dump."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"


class TestP2MetricsUi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_get_app_metrics_200(self):
        r = self.client.get("/app/metrics")
        self.assertEqual(r.status_code, 200)
        body = r.text
        for i in ("mDenyLlm", "mGateMonths", "mHardDeny", "mChatTotal", "mDenyTotal", "navHome"):
            self.assertIn(f'id="{i}"', body, i)
        self.assertNotIn("JSON.stringify", body)
        self.assertIn('href="/app"', body)

    def test_home_has_nav_metrics(self):
        html = (STATIC / "home.html").read_text(encoding="utf-8")
        self.assertIn('id="navMetrics"', html)
        self.assertIn('href="/app/metrics"', html)

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
