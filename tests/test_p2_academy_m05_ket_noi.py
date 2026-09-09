"""P2 Welorademy M05 Kết Nối & Thực Hành."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.academy import (
    BADGE_BEN_VUNG,
    BADGE_KET_NOI,
    GATE_NODE,
    M05_MODULE_ID,
    M05_MODULE_TITLE,
    M05_NODE_IDS,
    M05_NODES,
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


class TestP2AcademyM05KetNoi(unittest.TestCase):
    def setUp(self):
        reset_academy_store()
        reset_mastery_store()

    def test_m05_nodes_keys_linear_prereq(self):
        self.assertEqual(len(M05_NODES), 7)
        self.assertEqual(M05_MODULE_ID, "M05")
        self.assertEqual(M05_MODULE_TITLE, "Kết Nối & Thực Hành")
        expected = [
            ("N05-01", "WA-05-01", "ACT-01", "Chuyển kiến thức thành hành động", 1, []),
            ("N05-02", "WA-05-02", "HABIT-01", "Xây dựng thói quen tài chính", 2, ["N05-01"]),
            ("N05-03", "WA-05-03", "ADJUST-01", "Theo dõi và điều chỉnh kế hoạch", 3, ["N05-02"]),
            ("N05-04", "WA-05-04", "DECIDE-01", "Ra quyết định tài chính hàng ngày", 4, ["N05-03"]),
            ("N05-05", "WA-05-05", "PEER-01", "Cộng đồng và học hỏi cùng nhau", 5, ["N05-04"]),
            ("N05-06", "WA-05-06", "TOOLS-01", "Sử dụng công cụ và hệ thống hỗ trợ", 6, ["N05-05"]),
            ("N05-07", "WA-05-07", "DRIVE-01", "Duy trì động lực dài hạn", 7, ["N05-06"]),
        ]
        for n, exp in zip(M05_NODES, expected):
            self.assertEqual(n["node_id"], exp[0])
            self.assertEqual(n["lesson_id"], exp[1])
            self.assertEqual(n["principle_key"], exp[2])
            self.assertEqual(n["title"], exp[3])
            self.assertEqual(n["order"], exp[4])
            self.assertEqual(n["prereq_node_ids"], exp[5])
            self.assertEqual(n["module_id"], "M05")
            self.assertEqual(n["module_title"], "Kết Nối & Thực Hành")
            self.assertEqual(len(QUESTIONS[n["node_id"]]), 3)
        self.assertEqual(tuple(n["node_id"] for n in M05_NODES), M05_NODE_IDS)
        m02 = [n for n in NODES if n["module_id"] == "M02"]
        self.assertEqual(
            [n["node_id"] for n in m02],
            ["N02-01", "N02-02", "N02-03", "N02-05", "N02-04", "N02-06", "N02-07"],
        )
        m03 = [n for n in NODES if n["module_id"] == "M03"]
        self.assertEqual(
            [n["node_id"] for n in m03],
            ["N03-01", "N03-02", "N03-03", "N03-04", "N03-05", "N03-06", "N03-07"],
        )
        m04 = [n for n in NODES if n["module_id"] == "M04"]
        self.assertEqual(
            [n["node_id"] for n in m04],
            ["N04-01", "N04-02", "N04-03", "N04-04", "N04-05", "N04-06", "N04-07"],
        )
        self.assertEqual(GATE_NODE, "N02-02")
        self.assertEqual(
            [(m["module_id"], m["order"]) for m in MODULES],
            [("M01", 1), ("M02", 2), ("M03", 3), ("M04", 4), ("M05", 5)],
        )
        self.assertEqual(len(NODES), 35)

    def test_kuat_pass_awards_xp(self):
        out = submit_kuat("u-m05", "N05-01", _correct("N05-01"))
        self.assertTrue(out["kuat_result"]["passed"])
        self.assertTrue(out["awarded_xp"])
        self.assertEqual(out["xp"], XP_PER_PASS)
        again = submit_kuat("u-m05", "N05-01", _correct("N05-01"))
        self.assertEqual(again["xp"], XP_PER_PASS)
        self.assertFalse(again["awarded_xp"])

    def test_all_m05_mastered_badge_ket_noi(self):
        uid = "u-badge-m05"
        for nid in M05_NODE_IDS:
            out = submit_kuat(uid, nid, _correct(nid))
            self.assertTrue(out["kuat_result"]["passed"], nid)
        self.assertIn(BADGE_KET_NOI, out["badges"])
        tree = get_tree(uid)
        self.assertIn(BADGE_KET_NOI, tree["badges"])
        self.assertEqual(tree["xp"], XP_PER_PASS * 7)
        titles = [m["title"] for m in tree["modules"]]
        self.assertEqual(
            titles,
            [
                "Rễ Cục",
                "An Toàn Tài Chính",
                "Tự Do Tài Chính",
                "Bền Vững & Di Sản",
                "Kết Nối & Thực Hành",
            ],
        )
        flat_ids = [n["node_id"] for n in tree["nodes"]]
        self.assertIn("N05-01", flat_ids)
        self.assertIn("N01-01", flat_ids)
        self.assertIn("N02-01", flat_ids)
        self.assertIn("N03-01", flat_ids)
        self.assertIn("N04-01", flat_ids)
        self.assertEqual(BADGE_BEN_VUNG, "Bền Vững & Di Sản")

    def test_n05_pass_no_mastery_apply_no_gate_wire(self):
        out = submit_kuat("u-gate-m05", "N05-01", _correct("N05-01"))
        self.assertTrue(out["kuat_result"]["passed"])
        m = get_node("u-gate-m05", "no_efund_invest")
        self.assertNotEqual(m.state, "apply")
        self.assertFalse(m.meets_gate())
        self.assertIsNone(os_nudge_for("N05-01", first_pass=True))
        self.assertIsNone(out["os_nudge"])
        for nid in M05_NODE_IDS[1:]:
            submit_kuat("u-gate-m05", nid, _correct(nid))
        m2 = get_node("u-gate-m05", "no_efund_invest")
        self.assertNotEqual(m2.state, "apply")
        self.assertEqual(GATE_NODE, "N02-02")

    def test_os_nudge_m05_none(self):
        for nid in M05_NODE_IDS:
            self.assertIsNone(os_nudge_for(nid, first_pass=True))

    def test_action_habit_hard_q_emphasizes_an_toan(self):
        for nid in ("N05-01", "N05-02", "N05-04", "N05-07"):
            qs = QUESTIONS[nid]
            hard = [q for q in qs if q["hard"]]
            self.assertTrue(hard, nid)
            blob = " ".join(q["prompt"] + " " + " ".join(q["choices"]) for q in hard)
            self.assertTrue(
                "An Toàn" in blob or "quỹ khẩn cấp" in blob or "all-in" in blob.lower(),
                blob,
            )
            for q in hard:
                ans = q["choices"][q["answer"]]
                self.assertTrue(
                    any(k in ans for k in ("An Toàn", "Không", "không", "ưu tiên", "Giữ", "đủ nhỏ")),
                    ans,
                )

    def test_html_groups_modules(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Rễ Cục", html)
        self.assertIn("An Toàn Tài Chính", html)
        self.assertIn("Tự Do Tài Chính", html)
        self.assertIn("Bền Vững & Di Sản", html)
        self.assertIn("Kết Nối & Thực Hành", html)
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
        self.assertIn("Kết Nối & Thực Hành", ui.text)
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
