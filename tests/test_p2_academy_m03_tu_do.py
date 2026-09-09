"""P2 Welorademy M03 Tự Do Tài Chính."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.academy import (
    BADGE_RE_CUC,
    BADGE_TU_DO,
    GATE_NODE,
    M03_MODULE_ID,
    M03_MODULE_TITLE,
    M03_NODE_IDS,
    M03_NODES,
    MODULES,
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


class TestP2AcademyM03TuDo(unittest.TestCase):
    def setUp(self):
        reset_academy_store()
        reset_mastery_store()

    def test_m03_nodes_keys_linear_prereq(self):
        self.assertEqual(len(M03_NODES), 7)
        self.assertEqual(M03_MODULE_ID, "M03")
        self.assertEqual(M03_MODULE_TITLE, "Tự Do Tài Chính")
        expected = [
            ("N03-01", "WA-03-01", "FREE-01", "Hiểu tự do tài chính", 1, []),
            ("N03-02", "WA-03-02", "ASSET-01", "Phân biệt tài sản và nợ", 2, ["N03-01"]),
            ("N03-03", "WA-03-03", "PASSIVE-01", "Hiểu thu nhập thụ động", 3, ["N03-02"]),
            ("N03-04", "WA-03-04", "INV-01", "Nguyên tắc đầu tư cơ bản", 4, ["N03-03"]),
            ("N03-05", "WA-03-05", "DIV-01", "Đa dạng hóa danh mục", 5, ["N03-04"]),
            ("N03-06", "WA-03-06", "FREE-PLAN-01", "Lập kế hoạch hướng tới tự do tài chính", 6, ["N03-05"]),
            ("N03-07", "WA-03-07", "FREE-RISK-01", "Nhận diện rủi ro khi theo đuổi tự do tài chính", 7, ["N03-06"]),
        ]
        for n, exp in zip(M03_NODES, expected):
            self.assertEqual(n["node_id"], exp[0])
            self.assertEqual(n["lesson_id"], exp[1])
            self.assertEqual(n["principle_key"], exp[2])
            self.assertEqual(n["title"], exp[3])
            self.assertEqual(n["order"], exp[4])
            self.assertEqual(n["prereq_node_ids"], exp[5])
            self.assertEqual(n["module_id"], "M03")
            self.assertEqual(n["module_title"], "Tự Do Tài Chính")
            self.assertEqual(len(QUESTIONS[n["node_id"]]), 3)
        self.assertEqual(tuple(n["node_id"] for n in M03_NODES), M03_NODE_IDS)
        # M01/M02 graph untouched; GATE stays N02-02
        m02 = [n for n in NODES if n["module_id"] == "M02"]
        self.assertEqual(
            [n["node_id"] for n in m02],
            ["N02-01", "N02-02", "N02-03", "N02-05", "N02-04", "N02-06", "N02-07"],
        )
        self.assertEqual(GATE_NODE, "N02-02")
        self.assertEqual(
            [(m["module_id"], m["order"]) for m in MODULES],
            [("M01", 1), ("M02", 2), ("M03", 3)],
        )
        self.assertEqual(len(NODES), 21)

    def test_kuat_pass_awards_xp(self):
        out = submit_kuat("u-m03", "N03-01", _correct("N03-01"))
        self.assertTrue(out["kuat_result"]["passed"])
        self.assertTrue(out["awarded_xp"])
        self.assertEqual(out["xp"], XP_PER_PASS)
        again = submit_kuat("u-m03", "N03-01", _correct("N03-01"))
        self.assertEqual(again["xp"], XP_PER_PASS)
        self.assertFalse(again["awarded_xp"])

    def test_all_m03_mastered_badge_tu_do(self):
        uid = "u-badge-m03"
        for nid in M03_NODE_IDS:
            out = submit_kuat(uid, nid, _correct(nid))
            self.assertTrue(out["kuat_result"]["passed"], nid)
        self.assertIn(BADGE_TU_DO, out["badges"])
        tree = get_tree(uid)
        self.assertIn(BADGE_TU_DO, tree["badges"])
        self.assertEqual(tree["xp"], XP_PER_PASS * 7)
        titles = [m["title"] for m in tree["modules"]]
        self.assertEqual(titles, ["Rễ Cục", "An Toàn Tài Chính", "Tự Do Tài Chính"])
        flat_ids = [n["node_id"] for n in tree["nodes"]]
        self.assertIn("N03-01", flat_ids)
        self.assertIn("N01-01", flat_ids)
        self.assertIn("N02-01", flat_ids)
        # Rễ Cục + An Toàn badge paths still exist independently
        self.assertEqual(BADGE_RE_CUC, "Rễ Cục")

    def test_n03_pass_no_mastery_apply_no_gate_wire(self):
        out = submit_kuat("u-gate-m03", "N03-01", _correct("N03-01"))
        self.assertTrue(out["kuat_result"]["passed"])
        m = get_node("u-gate-m03", "no_efund_invest")
        self.assertNotEqual(m.state, "apply")
        self.assertFalse(m.meets_gate())
        self.assertIsNone(os_nudge_for("N03-01", first_pass=True))
        self.assertIsNone(out["os_nudge"])
        for nid in M03_NODE_IDS[1:]:
            submit_kuat("u-gate-m03", nid, _correct(nid))
        m2 = get_node("u-gate-m03", "no_efund_invest")
        self.assertNotEqual(m2.state, "apply")
        self.assertEqual(GATE_NODE, "N02-02")

    def test_os_nudge_m03_none(self):
        for nid in M03_NODE_IDS:
            self.assertIsNone(os_nudge_for(nid, first_pass=True))

    def test_inv_hard_q_emphasizes_an_toan(self):
        qs = QUESTIONS["N03-04"]
        hard = [q for q in qs if q["hard"]]
        self.assertTrue(hard)
        blob = " ".join(q["prompt"] + " " + " ".join(q["choices"]) for q in hard)
        self.assertTrue(
            "An Toàn" in blob or "Cổng" in blob or "all-in" in blob.lower() or "All-in" in blob,
            blob,
        )
        # Correct answers affirm An Toàn first / no all-in before gate
        for q in hard:
            ans = q["choices"][q["answer"]]
            self.assertTrue(
                any(k in ans for k in ("An Toàn", "không all-in", "Không", "ưu tiên")),
                ans,
            )

    def test_html_groups_modules(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Rễ Cục", html)
        self.assertIn("An Toàn Tài Chính", html)
        self.assertIn("Tự Do Tài Chính", html)
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
        self.assertIn("Tự Do Tài Chính", ui.text)
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
