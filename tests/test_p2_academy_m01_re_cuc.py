"""P2 Welorademy M01 Rễ Cục."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.academy import (
    BADGE_RE_CUC,
    GATE_NODE,
    M01_MODULE_ID,
    M01_MODULE_TITLE,
    M01_NODE_IDS,
    M01_NODES,
    NODES,
    QUESTIONS,
    XP_PER_PASS,
    get_tree,
    os_nudge_for,
    reset_academy_store,
    submit_kuat,
)
from welora.api.app import create_app
from welora.mastery import get_node, reset_mastery_store
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "academy.html"


def _correct(node_id: str) -> list[dict]:
    return [{"question_id": q["id"], "choice": q["answer"]} for q in QUESTIONS[node_id]]


class TestP2AcademyM01ReCuc(unittest.TestCase):
    def setUp(self):
        reset_academy_store()
        reset_mastery_store()

    def test_m01_nodes_keys_linear_prereq(self):
        self.assertEqual(len(M01_NODES), 7)
        self.assertEqual(M01_MODULE_ID, "M01")
        self.assertEqual(M01_MODULE_TITLE, "Rễ Cục")
        expected = [
            ("N01-01", "WA-01-01", "MIND-01", "Xây dựng tư duy về tiền", 1, []),
            ("N01-02", "WA-01-02", "FLOW-01", "Hiểu dòng tiền – Thu nhập và chi tiêu", 2, ["N01-01"]),
            ("N01-03", "WA-01-03", "BUDG-01", "Lập ngân sách cơ bản", 3, ["N01-02"]),
            ("N01-04", "WA-01-04", "BUDG-02", "Áp dụng quy tắc 50/30/20", 4, ["N01-03"]),
            ("N01-05", "WA-01-05", "TRACK-01", "Theo dõi chi tiêu hiệu quả", 5, ["N01-04"]),
            ("N01-06", "WA-01-06", "GOAL-01", "Đặt mục tiêu tài chính đúng cách", 6, ["N01-05"]),
            ("N01-07", "WA-01-07", "TIME-01", "Hiểu lãi kép và giá trị thời gian của tiền", 7, ["N01-06"]),
        ]
        for n, exp in zip(M01_NODES, expected):
            self.assertEqual(n["node_id"], exp[0])
            self.assertEqual(n["lesson_id"], exp[1])
            self.assertEqual(n["principle_key"], exp[2])
            self.assertEqual(n["title"], exp[3])
            self.assertEqual(n["order"], exp[4])
            self.assertEqual(n["prereq_node_ids"], exp[5])
            self.assertEqual(n["module_id"], "M01")
            self.assertEqual(n["module_title"], "Rễ Cục")
        self.assertEqual(tuple(n["node_id"] for n in M01_NODES), M01_NODE_IDS)
        # M01 appears in flat NODES ahead of M02; M02 graph untouched
        m02 = [n for n in NODES if n["module_id"] == "M02"]
        self.assertEqual(
            [n["node_id"] for n in m02],
            ["N02-01", "N02-02", "N02-03", "N02-05", "N02-04", "N02-06", "N02-07"],
        )
        self.assertEqual(GATE_NODE, "N02-02")

    def test_kuat_pass_awards_xp(self):
        out = submit_kuat("u-m01", "N01-01", _correct("N01-01"))
        self.assertTrue(out["kuat_result"]["passed"])
        self.assertTrue(out["awarded_xp"])
        self.assertEqual(out["xp"], XP_PER_PASS)
        again = submit_kuat("u-m01", "N01-01", _correct("N01-01"))
        self.assertEqual(again["xp"], XP_PER_PASS)
        self.assertFalse(again["awarded_xp"])

    def test_all_m01_mastered_badge_re_cuc(self):
        uid = "u-badge"
        for nid in M01_NODE_IDS:
            out = submit_kuat(uid, nid, _correct(nid))
            self.assertTrue(out["kuat_result"]["passed"], nid)
        self.assertIn(BADGE_RE_CUC, out["badges"])
        tree = get_tree(uid)
        self.assertIn(BADGE_RE_CUC, tree["badges"])
        self.assertEqual(tree["xp"], XP_PER_PASS * 7)
        # modules grouping present
        self.assertTrue(tree.get("modules"))
        titles = [m["title"] for m in tree["modules"]]
        self.assertEqual(titles, ["Rễ Cục", "An Toàn Tài Chính"])
        flat_ids = [n["node_id"] for n in tree["nodes"]]
        self.assertIn("N01-01", flat_ids)
        self.assertIn("N02-01", flat_ids)

    def test_n01_pass_no_mastery_apply_no_gate_wire(self):
        out = submit_kuat("u-gate", "N01-01", _correct("N01-01"))
        self.assertTrue(out["kuat_result"]["passed"])
        m = get_node("u-gate", "no_efund_invest")
        self.assertNotEqual(m.state, "apply")
        self.assertFalse(m.meets_gate())
        self.assertIsNone(os_nudge_for("N01-01", first_pass=True))
        self.assertIsNone(out["os_nudge"])
        # completing all M01 still must not set mastery apply
        for nid in M01_NODE_IDS[1:]:
            submit_kuat("u-gate", nid, _correct(nid))
        m2 = get_node("u-gate", "no_efund_invest")
        self.assertNotEqual(m2.state, "apply")
        self.assertEqual(GATE_NODE, "N02-02")

    def test_os_nudge_m01_none(self):
        for nid in M01_NODE_IDS:
            self.assertIsNone(os_nudge_for(nid, first_pass=True))

    def test_html_groups_modules(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Rễ Cục", html)
        self.assertIn("An Toàn Tài Chính", html)
        self.assertIn("data.modules", html)
        self.assertIn("modHead", html)
        self.assertIn("baiLabel", html)
        self.assertIn("n.title||''", html)
        self.assertNotIn("node_id+' · '+n.title", html)
        self.assertNotIn("n.node_id+' · '+n.title", html)

    def test_page_and_health(self):
        self.assertEqual(TARGET_MONTHS, 3)
        client = TestClient(create_app())
        ui = client.get("/app/academy")
        self.assertEqual(ui.status_code, 200)
        self.assertIn("Welorademy", ui.text)
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
