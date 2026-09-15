"""P2 UX — tab Điều hành + 3 trụ Trang chủ."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
SHELL_JS = (STATIC / "shell.js").read_text(encoding="utf-8")
HOME = (STATIC / "home.html").read_text(encoding="utf-8")
GOALS = (STATIC / "goals.html").read_text(encoding="utf-8")
SAFETY = (STATIC / "safety.html").read_text(encoding="utf-8")


class TestP2UxDieuHanhTabHome(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_always_visible_tabs_order_and_ops(self):
        for label in ("Trang chủ", "Từ điển", "Học viện", "Điều hành"):
            self.assertIn(label, SHELL_JS)
        self.assertIn('id: "tabOps"', SHELL_JS)
        self.assertIn('label: "Điều hành"', SHELL_JS)
        self.assertIn('href: "/app/safety"', SHELL_JS)
        self.assertIn('key: "ops"', SHELL_JS)
        self.assertIn('ico: "▣"', SHELL_JS)
        # distinct icon — not ○ □ ◈
        self.assertIn('ico: "▣"', SHELL_JS)
        self.assertNotIn('ico: "○", key: "ops"', SHELL_JS)
        i_home = SHELL_JS.index('label: "Trang chủ"')
        i_pedia = SHELL_JS.index('label: "Từ điển"')
        i_acad = SHELL_JS.index('label: "Học viện"')
        i_ops = SHELL_JS.index('label: "Điều hành"')
        i_chat = SHELL_JS.index('label: "Chat với Agent"')
        self.assertTrue(i_home < i_pedia < i_acad < i_ops < i_chat)

    def test_chat_still_gated_after_ops(self):
        self.assertIn("gate: true", SHELL_JS)
        self.assertIn("a.hidden = true", SHELL_JS)
        self.assertIn('chatLink.hidden = st !== "passed"', SHELL_JS)
        self.assertIn("/safety-gate", SHELL_JS)
        # gate logic unchanged — Chat still after Điều hành
        self.assertGreater(
            SHELL_JS.index('id: "tabChat"'),
            SHELL_JS.index('id: "tabOps"'),
        )

    def test_ops_cluster_active_not_home(self):
        self.assertNotIn('forced === "goals"', SHELL_JS)
        for frag in (
            'path.indexOf("/app/safety")',
            'path.indexOf("/app/goals")',
            'path.indexOf("/app/dna")',
            'path.indexOf("/app/constitution")',
            'path.indexOf("/app/health-score")',
            'path.indexOf("/app/onboarding")',
        ):
            self.assertIn(frag, SHELL_JS)
        self.assertIn('active = "ops"', SHELL_JS)
        # goals/safety force ops tab
        self.assertIn('data-shell-tab="ops"', GOALS)
        self.assertIn('data-shell-tab="ops"', SAFETY)
        self.assertNotIn('data-shell-tab="home"', GOALS)
        self.assertNotIn('data-shell-tab="home"', SAFETY)

    def test_home_three_pillars(self):
        self.assertIn('id="homePillars"', HOME)
        self.assertIn('id="pillarPedia" href="/app/content"', HOME)
        self.assertIn('id="pillarAcademy" href="/app/academy"', HOME)
        self.assertIn('id="pillarOps" href="/app/safety"', HOME)
        # short VI titles present
        self.assertIn("Từ điển", HOME)
        self.assertIn("Học viện", HOME)
        self.assertIn("Điều hành", HOME)
        # no raw CORE/SAFE/DEBT keys in pillar block
        pillars = HOME[HOME.index("homePillars") : HOME.index("hsCard")]
        self.assertNotRegex(pillars, r"\b(CORE|SAFE|DEBT)-")
        # keep existing Cổng / HS / EF / debt cards
        for nid in ("hsCard", "gateCard", "efCard", "debtCard"):
            self.assertIn('id="%s"' % nid, HOME)

    def test_http_smoke_shell_and_home(self):
        home = self.client.get("/app")
        self.assertEqual(home.status_code, 200)
        self.assertIn("homePillars", home.text)
        self.assertIn("/static/shell.js", home.text)
        self.assertIn('data-shell-tab="home"', home.text)

        safety = self.client.get("/app/safety")
        self.assertEqual(safety.status_code, 200)
        self.assertIn('data-shell-tab="ops"', safety.text)

        goals = self.client.get("/app/goals")
        self.assertEqual(goals.status_code, 200)
        self.assertIn('data-shell-tab="ops"', goals.text)

        js = self.client.get("/static/shell.js")
        self.assertEqual(js.status_code, 200)
        self.assertIn("Điều hành", js.text)

    def test_hard_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        b = self.client.get("/health").json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        self.assertTrue((ROOT / "welora" / "mode_c_act.py").is_file())


if __name__ == "__main__":
    unittest.main()
