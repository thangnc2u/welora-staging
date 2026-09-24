"""P2 hotfix — P1 shared overflow CSS (budget / consent / dual-control).

CSS/layout only via shell.css (+ minimal page hooks). Does not regress #209/#210.
Hard Deny · TARGET_MONTHS / gate_months · APIs untouched.
"""

from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

os.environ.setdefault("WELORA_STORE", "memory")

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.fixtures import reset_all_stores
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
SHELL_CSS = (ROOT / "welora" / "api" / "static" / "shell.css").read_text(encoding="utf-8")
BUDGET_HTML = (ROOT / "welora" / "api" / "static" / "budget.html").read_text(encoding="utf-8")
ACCOUNTS_HTML = (ROOT / "welora" / "api" / "static" / "accounts.html").read_text(
    encoding="utf-8"
)
TX_HTML = (ROOT / "welora" / "api" / "static" / "transactions.html").read_text(
    encoding="utf-8"
)
DUAL_HTML = (ROOT / "welora" / "api" / "static" / "dual-control.html").read_text(
    encoding="utf-8"
)


class TestP2HotfixP1SharedOverflowCss(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(create_app())

    def setUp(self) -> None:
        reset_all_stores()

    def test_shell_checkbox_radio_width_auto(self):
        self.assertRegex(
            SHELL_CSS,
            r'input\[type=["\']checkbox["\']\][^\{]*\{[^}]*width:\s*auto',
        )
        self.assertRegex(
            SHELL_CSS,
            r'input\[type=["\']radio["\']\]',
        )
        # flex-shrink:0 on the shared checkbox/radio block
        block = re.search(
            r'input\[type=["\']checkbox["\']\],\s*input\[type=["\']radio["\']\]\{([^}]+)\}',
            SHELL_CSS,
            flags=re.S,
        )
        self.assertIsNotNone(block, msg="shared checkbox/radio rule block missing")
        body = block.group(1)
        self.assertIn("width:auto", body.replace(" ", ""))
        self.assertIn("flex-shrink:0", body.replace(" ", ""))

    def test_shell_check_consent_flex_wrap(self):
        # Shared row helpers
        self.assertRegex(SHELL_CSS, r"\.check[,\{]")
        self.assertRegex(SHELL_CSS, r"\.consent[,\{]")
        # Flex + min-width:0 on the shared group (or individually)
        flex_block = re.search(
            r"\.check,\s*\.consent,\s*\.show-hidden,\s*\.show-disabled\{([^}]+)\}",
            SHELL_CSS,
            flags=re.S,
        )
        self.assertIsNotNone(flex_block, msg="shared .check/.consent flex block missing")
        fb = flex_block.group(1).replace(" ", "")
        self.assertIn("display:flex", fb)
        self.assertIn("min-width:0", fb)
        # Text wrap on label/span children
        wrap_ok = (
            "overflow-wrap:anywhere" in SHELL_CSS
            or "word-break:break-word" in SHELL_CSS
            or "overflow-wrap:break-word" in SHELL_CSS
        )
        self.assertTrue(wrap_ok, msg="shell needs overflow-wrap or word-break for check/consent text")
        self.assertRegex(
            SHELL_CSS,
            r"\.(check\s+span|consent\s+label)",
        )

    def test_shell_row_btns_button_not_full_width(self):
        self.assertIn(".row-btns", SHELL_CSS)
        self.assertRegex(
            SHELL_CSS,
            r"\.row-btns\s+button\{[^}]*(width:\s*auto|flex:\s*1)",
        )

    def test_budget_check_labels_span_wrapped(self):
        self.assertIn('id="confirmSave"', BUDGET_HTML)
        self.assertIn('id="replaceExisting"', BUDGET_HTML)
        self.assertIn('id="confirmClose"', BUDGET_HTML)
        self.assertIn('class="check"', BUDGET_HTML)
        # Text inside span so overflow-wrap can apply
        self.assertRegex(
            BUDGET_HTML,
            r'id="confirmSave"[^>]*>\s*<span>',
        )
        self.assertTrue(
            "overflow-wrap:anywhere" in BUDGET_HTML
            or "word-break:break-word" in BUDGET_HTML
            or "overflow-wrap:anywhere" in SHELL_CSS,
            msg="budget check text needs wrap protection (page or shell)",
        )

    def test_accounts_consent_wrap_and_show_hidden_intact(self):
        self.assertIn('id="consentAck"', ACCOUNTS_HTML)
        self.assertIn('id="showHidden"', ACCOUNTS_HTML)
        self.assertIn("show-hidden", ACCOUNTS_HTML)
        # #209 page-level checkbox override must remain
        self.assertRegex(
            ACCOUNTS_HTML,
            r'input\[type=["\']checkbox["\']\]\{[^}]*width:\s*auto',
        )
        self.assertRegex(
            ACCOUNTS_HTML,
            r'input\[type=["\']checkbox["\']\]\{[^}]*flex-shrink:\s*0',
        )
        # Consent label wrap (page and/or shell)
        consent_wrap = (
            ".consent label" in ACCOUNTS_HTML
            or ".consent label" in SHELL_CSS
            or "overflow-wrap:anywhere" in ACCOUNTS_HTML
        )
        self.assertTrue(consent_wrap, msg="consent label needs min-width:0 / wrap")

    def test_transactions_consent_hooks(self):
        self.assertIn('id="consentAck"', TX_HTML)
        self.assertIn(".consent", TX_HTML)
        self.assertTrue(
            'input[type="checkbox"]' in TX_HTML
            or 'input[type=checkbox]' in TX_HTML
            or 'input[type="checkbox"]' in SHELL_CSS,
            msg="transactions or shell must override checkbox width",
        )

    def test_dual_control_row_btns(self):
        self.assertIn("row-btns", DUAL_HTML)
        self.assertIn('className="row-btns"', DUAL_HTML)
        # Page and/or shell override button width:100%
        page_or_shell = (
            re.search(r"\.row-btns\s+button\{[^}]*(width:\s*auto|flex:\s*1)", DUAL_HTML)
            or re.search(r"\.row-btns\s+button\{[^}]*(width:\s*auto|flex:\s*1)", SHELL_CSS)
        )
        self.assertIsNotNone(page_or_shell)

    def test_routes_200_key_hooks(self):
        cases = [
            ("/app/budget", ('id="confirmSave"', "check")),
            ("/app/accounts", ('id="consentAck"', "showHidden")),
            ("/app/transactions", ('id="consentAck"', "consent")),
            ("/app/dual-control", ("row-btns", "Đồng kiểm")),
        ]
        for path, needles in cases:
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200, path)
                for n in needles:
                    self.assertIn(n, r.text, msg=f"{path} missing {n}")

    def test_shell_css_served(self):
        r = self.client.get("/static/shell.css")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn('input[type="checkbox"]', body)
        self.assertIn(".row-btns", body)
        self.assertIn(".consent", body)

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
