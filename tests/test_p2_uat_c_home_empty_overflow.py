"""P2 UAT-C — home empty states (EF / gate CTA) + learner overflow cull."""

from __future__ import annotations

from pathlib import Path
import re
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.safety_gate import TARGET_MONTHS

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
HOME = (STATIC / "home.html").read_text(encoding="utf-8")
SAFETY = (STATIC / "safety.html").read_text(encoding="utf-8")
SHELL_JS = (STATIC / "shell.js").read_text(encoding="utf-8")

# Learner-visible tools (not .dev-only)
LEARNER_NAV_ALLOW = {
    "navOnboarding",
    "navChat",
    "navConstitution",
    "navDna",
    "navGoals",
    "navHealth",
}

# Must be hidden from learners (dev-only) — DoD overflow cull
OVERFLOW_DEV_ONLY = {
    "navOtp",
    "navParser",
    "navMetrics",
    "navCoreConstitution",
    "navContent",  # duplicate bottom tab (pedia)
    "navAcademy",  # duplicate bottom tab (academy)
    "navDemo",
    "navLogs",
    "navPreRule",
}


class TestP2UatCHomeEmptyOverflow(unittest.TestCase):
    def test_ef_empty_when_goal_null_or_target_zero(self):
        self.assertIn("Chưa có quỹ", HOME)
        # empty when goal_id missing OR target_amount == 0 (not only months==null)
        self.assertIn("!det.goal_id", HOME)
        self.assertIn("Number(tgt)===0", HOME)
        self.assertIn("efLabel').textContent='Chưa có quỹ'", HOME)
        # must not keep months==null-only empty check as sole path
        self.assertNotIn("months==null?'Chưa có quỹ'", HOME)
        # money zero pair dropped on empty path (no 0 ₫ / 0 ₫ append there)
        empty_idx = HOME.index("if(noGoal){")
        empty_block = HOME[empty_idx : HOME.index("}else{", empty_idx)]
        self.assertIn("Chưa có quỹ", empty_block)
        self.assertNotIn("formatVnd", empty_block)
        # months must not show raw .0 via String(months)
        self.assertNotIn("String(months)+' / 3 tháng'", HOME)
        self.assertIn("Math.round(mNum)", HOME)
        # Safety parity copy still present on Safety
        self.assertIn("Chưa có quỹ", SAFETY)

    def test_gate_data_missing_cta_onboarding(self):
        self.assertIn("data_missing", HOME)
        self.assertIn("Bắt đầu · Hiến pháp", HOME)
        self.assertIn("gateCta.href='/app/onboarding'", HOME)
        self.assertIn("gateCta.textContent='Bắt đầu · Hiến pháp'", HOME)
        self.assertIn("GATE_REASON_VI", HOME)
        self.assertIn("Thiếu dữ liệu", HOME)
        # no raw lesson/rule key flash patterns in home learner copy paths
        self.assertNotIn("SAFE-01", HOME)
        self.assertNotIn("DEBT-", HOME)
        self.assertNotIn("CORE-01", HOME)
        self.assertNotIn("N01", HOME)
        # filter strips raw keys if they ever leak
        self.assertIn("SAFE|DEBT|CORE|N0", HOME)

    def test_overflow_cull_dev_only_allowlist(self):
        for nid in OVERFLOW_DEV_ONLY:
            self.assertRegex(
                HOME,
                r'class="nav dev-only" id="%s"' % nid,
                msg="%s must be dev-only" % nid,
            )
        for nid in LEARNER_NAV_ALLOW:
            # learner entries must exist and must NOT be marked dev-only
            self.assertIn('id="%s"' % nid, HOME)
            self.assertNotRegex(
                HOME,
                r'class="nav dev-only" id="%s"' % nid,
                msg="%s must stay learner-visible" % nid,
            )
        # CSS hide rule still present
        self.assertIn(".tools:not(.dev) .dev-only{display:none}", HOME)

    def test_hs_pct_label_clean(self):
        self.assertIn("hsPctLabel').textContent=pct(s/10);", HOME)
        self.assertNotIn("thang 1000", HOME)
        # optional VI checklist wording
        self.assertIn("Xem danh sách kiểm Cổng", HOME)
        self.assertNotIn("Xem checklist Cổng", HOME)

    def test_shell_chat_gate_not_regressed(self):
        # #173 hard: do not regress shell Chat gate / shell.js patterns
        self.assertIn('id="navChat" href="/app/chat" hidden', HOME)
        self.assertIn("navChat.hidden=!passed", HOME)
        self.assertIn("chatLink.hidden = st !== \"passed\"", SHELL_JS)
        self.assertIn('data-shell-tab="home"', HOME)
        self.assertIn("/static/shell.js", HOME)

    def test_app_home_200_spotcheck(self):
        r = TestClient(create_app()).get("/app")
        self.assertEqual(r.status_code, 200)
        body = r.text
        self.assertIn("Chưa có quỹ", body)
        self.assertIn("Bắt đầu · Hiến pháp", body)
        self.assertIn('class="nav dev-only" id="navOtp"', body)
        self.assertIn('class="nav dev-only" id="navParser"', body)
        self.assertIn('class="nav dev-only" id="navMetrics"', body)
        self.assertIn('class="nav dev-only" id="navCoreConstitution"', body)
        self.assertNotIn("thang 1000", body)

    def test_hard_constraints_untouched(self):
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        # GATE mastery node still present in safety chrome
        self.assertIn("no_efund_invest", SAFETY)
        # R01–R09 / academy body not touched by this PR (spot: safety mastery node)
        self.assertIn("masteryState", SAFETY)


if __name__ == "__main__":
    unittest.main()
