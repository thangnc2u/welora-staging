"""P1 — horizontal sticky ops tabs (CP-style) on hub + OS modules; Hard Deny untouched."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

STATIC = Path(__file__).resolve().parents[1] / "welora" / "api" / "static"
SHELL_CSS = STATIC / "shell.css"

OPS_TABS = (
    ("Điều khiển", "/app"),
    ("Mục tiêu", "/app/goals"),
    ("Tài khoản", "/app/accounts"),
    ("Giao dịch", "/app/transactions"),
    ("Danh mục", "/app/categories"),
    ("Ngân sách", "/app/budget"),
)

ROUTE_ACTIVE = {
    "/app": "/app",
    "/app/goals": "/app/goals",
    "/app/accounts": "/app/accounts",
    "/app/transactions": "/app/transactions",
    "/app/categories": "/app/categories",
    "/app/budget": "/app/budget",
}


class TestP2HotfixOpsTabsCpStyle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def _assert_tabs_in_order(self, html: str):
        positions = []
        for label, href in OPS_TABS:
            self.assertIn(label, html)
            self.assertIn(f'href="{href}"', html)
            # Prefer ops-nav anchors for order (avoid other page links)
            m = re.search(
                rf'<a[^>]*class="[^"]*ops-nav[^"]*"[^>]*href="{re.escape(href)}"[^>]*>|{re.escape(href)}"[^>]*class="[^"]*ops-nav',
                html,
            )
            # Find label after opsCluster
            idx_cluster = html.find('id="opsCluster"')
            self.assertGreaterEqual(idx_cluster, 0, "opsCluster missing")
            slice_html = html[idx_cluster : idx_cluster + 1200]
            li = slice_html.find(label)
            hi = slice_html.find(f'href="{href}"')
            self.assertGreaterEqual(li, 0, f"label {label} not in opsCluster")
            self.assertGreaterEqual(hi, 0, f"href {href} not in opsCluster")
            positions.append(hi)
        self.assertEqual(positions, sorted(positions), "tab hrefs not in order")

    def _assert_active(self, html: str, active_href: str):
        # Active marker on the correct tab
        pat = re.compile(
            rf'<a[^>]*href="{re.escape(active_href)}"[^>]*>',
            re.I,
        )
        # Find ops-nav for active_href inside cluster
        cluster = re.search(
            r'<nav[^>]*id="opsCluster"[^>]*>.*?</nav>',
            html,
            re.S,
        )
        self.assertIsNotNone(cluster, "opsCluster nav missing")
        nav = cluster.group(0)
        # Match the anchor for active_href
        m = re.search(
            rf'<a\s+[^>]*href="{re.escape(active_href)}"[^>]*>',
            nav,
        )
        self.assertIsNotNone(m, f"anchor for {active_href} missing in opsCluster")
        tag = m.group(0)
        self.assertTrue(
            'is-active' in tag or 'aria-current="page"' in tag,
            f"active marker missing on {active_href}: {tag}",
        )
        self.assertIn("is-active", tag)
        self.assertIn('aria-current="page"', tag)
        # Other ops tabs must not all be active
        active_count = nav.count("is-active")
        self.assertEqual(active_count, 1, f"expected exactly one is-active, got {active_count}")

    def test_routes_have_six_tabs_and_active(self):
        for route, active_href in ROUTE_ACTIVE.items():
            with self.subTest(route=route):
                r = self.client.get(route)
                self.assertEqual(r.status_code, 200)
                self._assert_tabs_in_order(r.text)
                self._assert_active(r.text, active_href)
                self.assertIn('id="opsCluster"', r.text)
                self.assertIn("ops-tabs", r.text)

    def test_shell_css_ops_tabs_sticky_gold(self):
        css = SHELL_CSS.read_text(encoding="utf-8")
        self.assertIn("ops-tabs", css)
        self.assertIn("position:sticky", css)
        self.assertIn("overflow-x:auto", css)
        self.assertIn("is-active", css)
        # gold underline for active
        self.assertTrue(
            "--gold-400" in css or "#E8C86A" in css or "--border-focus" in css,
            "expected gold/border-focus underline token in ops-tabs CSS",
        )
        self.assertIn("border-bottom", css)

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
