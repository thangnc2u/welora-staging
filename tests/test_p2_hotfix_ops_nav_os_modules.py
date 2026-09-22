"""P2 hotfix — ops nav cluster on /app/safety + /app/goals; shell ops tab; Hard Deny untouched."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"
SHELL_JS = STATIC / "shell.js"

OPS_HREFS = (
    "/app/goals",
    "/app/accounts",
    "/app/transactions",
    "/app/categories",
    "/app/budget",
)

OPS_LABELS = (
    "Mục tiêu",
    "Tài khoản",
    "Giao dịch",
    "Danh mục",
    "Ngân sách",
)

OPS_SHELL_PATHS = (
    "/app/accounts",
    "/app/transactions",
    "/app/categories",
    "/app/budget",
)


class TestP2HotfixOpsNavOsModules(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def test_safety_html_ops_cluster(self):
        r = self.client.get("/app/safety")
        self.assertEqual(r.status_code, 200)
        for href in OPS_HREFS:
            self.assertIn(f'href="{href}"', r.text)
        for lab in OPS_LABELS:
            self.assertIn(lab, r.text)
        self.assertIn('id="opsCluster"', r.text)

    def test_goals_html_ops_cluster(self):
        r = self.client.get("/app/goals")
        self.assertEqual(r.status_code, 200)
        for href in OPS_HREFS:
            self.assertIn(f'href="{href}"', r.text)
        for lab in OPS_LABELS:
            self.assertIn(lab, r.text)
        self.assertIn('id="opsCluster"', r.text)

    def test_shell_js_ops_tab_paths(self):
        js = SHELL_JS.read_text(encoding="utf-8")
        self.assertIn('active = "ops"', js)
        for path in OPS_SHELL_PATHS:
            self.assertIn(f'path.indexOf("{path}")', js)
        # Điều hành tab still points at safety hub
        self.assertIn('href: "/app/safety"', js)
        self.assertIn('key: "ops"', js)

    def test_health_gate_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
