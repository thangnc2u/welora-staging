"""P2 UX App shell — bottom nav + dashboard; deep-links; gate intact."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"


class TestP2UxAppShell(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_home_is_dashboard_not_only_sitemap(self):
        r = self.client.get("/app")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn("Trang chủ", body)
        self.assertIn("0–1000", body)
        self.assertIn("Cổng An Toàn", body)
        self.assertIn("Quỹ khẩn cấp", body)
        self.assertIn("hsArc", body)
        self.assertIn("efBar", body)
        self.assertIn("Mở Mục tiêu", body)
        self.assertIn("/app/goals", body)
        self.assertNotIn("Welora Academy", body)

    def test_shell_assets_and_four_tabs(self):
        self.assertTrue((STATIC / "shell.css").is_file())
        js = (STATIC / "shell.js").read_text(encoding="utf-8")
        for label in ("Trang chủ", "Từ điển", "Trợ lý AI", "Học viện"):
            self.assertIn(label, js)
        self.assertNotIn('label: "Mục tiêu"', js)
        self.assertNotIn("/app/goals", js)
        self.assertIn("/app/content", js)
        self.assertIn("/app/chat", js)
        self.assertIn("/app/academy", js)
        self.assertNotIn("Welora Academy", js)

    def test_tab_pages_load_shell(self):
        for path, tab in (("/app/content", "pedia"), ("/app/chat", "chat"), ("/app/academy", "academy")):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn("/static/shell.js", r.text)
            self.assertIn('data-shell-tab="%s"' % tab, r.text)
            self.assertNotIn("Welora Academy", r.text)

    def test_old_deeplinks_still_200(self):
        for path in (
            "/app/safety",
            "/app/health-score",
            "/app/content",
            "/app/onboarding",
            "/app/learn",
            "/app/goal",
            "/app/goals",
        ):
            r = self.client.get(path, follow_redirects=False)
            self.assertIn(r.status_code, (200, 307, 302), path)

        r = self.client.get("/app/goal", follow_redirects=False)
        self.assertIn(r.status_code, (302, 307))
        self.assertIn("/app/safety", r.headers.get("location", ""))

        home = self.client.get("/app").text
        for nid in ("navSafety", "navGoals", "navAcademy", "navChat", "navHealth", "navOnboarding"):
            self.assertIn(nid, home)

    def test_health_and_gate_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])


if __name__ == "__main__":
    unittest.main()
