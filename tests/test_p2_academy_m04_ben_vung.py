"""P2 Welorademy M04 Bền Vững & Di Sản."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.academy import (
    BADGE_BEN_VUNG,
    BADGE_TU_DO,
    GATE_NODE,
    M04_MODULE_ID,
    M04_MODULE_TITLE,
    M04_NODE_IDS,
    M04_NODES,
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


class TestP2AcademyM04BenVung(unittest.TestCase):
    def setUp(self):
        reset_academy_store()
        reset_mastery_store()

    def test_m04_nodes_keys_linear_prereq(self):
        self.assertEqual(len(M04_NODES), 7)
        self.assertEqual(M04_MODULE_ID, "M04")
        self.assertEqual(M04_MODULE_TITLE, "Bền Vững & Di Sản")
        expected = [
            ("N04-01", "WA-04-01", "SUSTAIN-01", "Hiểu bền vững tài chính", 1, []),
            ("N04-02", "WA-04-02", "INSURE-01", "Bảo hiểm và quản lý rủi ro", 2, ["N04-01"]),
            ("N04-03", "WA-04-03", "RETIRE-01", "Chuẩn bị tài chính cho tuổi già", 3, ["N04-02"]),
            ("N04-04", "WA-04-04", "KIDS-01", "Dạy con về tiền bạc", 4, ["N04-03"]),
            ("N04-05", "WA-04-05", "LEGACY-01", "Di sản và thừa kế cơ bản", 5, ["N04-04"]),
            ("N04-06", "WA-04-06", "LEGACY-SOFT-01", "Di sản phi tài chính", 6, ["N04-05"]),
            ("N04-07", "WA-04-07", "BALANCE-01", "Cân bằng tích lũy và chất lượng sống", 7, ["N04-06"]),
        ]
        for n, exp in zip(M04_NODES, expected):
            self.assertEqual(n["node_id"], exp[0])
            self.assertEqual(n["lesson_id"], exp[1])
            self.assertEqual(n["principle_key"], exp[2])
            self.assertEqual(n["title"], exp[3])
            self.assertEqual(n["order"], exp[4])
            self.assertEqual(n["prereq_node_ids"], exp[5])
            self.assertEqual(n["module_id"], "M04")
            self.assertEqual(n["module_title"], "Bền Vững & Di Sản")
            self.assertEqual(len(QUESTIONS[n["node_id"]]), 3)
        self.assertEqual(tuple(n["node_id"] for n in M04_NODES), M04_NODE_IDS)
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
        self.assertEqual(GATE_NODE, "N02-02")
        self.assertEqual(
            [(m["module_id"], m["order"]) for m in MODULES],
            [("M01", 1), ("M02", 2), ("M03", 3), ("M04", 4)],
        )
        self.assertEqual(len(NODES), 28)

    def test_kuat_pass_awards_xp(self):
        out = submit_kuat("u-m04", "N04-01", _correct("N04-01"))
        self.assertTrue(out["kuat_result"]["passed"])
        self.assertTrue(out["awarded_xp"])
        self.assertEqual(out["xp"], XP_PER_PASS)
        again = submit_kuat("u-m04", "N04-01", _correct("N04-01"))
        self.assertEqual(again["xp"], XP_PER_PASS)
        self.assertFalse(again["awarded_xp"])

    def test_all_m04_mastered_badge_ben_vung(self):
        uid = "u-badge-m04"
        for nid in M04_NODE_IDS:
            out = submit_kuat(uid, nid, _correct(nid))
            self.assertTrue(out["kuat_result"]["passed"], nid)
        self.assertIn(BADGE_BEN_VUNG, out["badges"])
        tree = get_tree(uid)
        self.assertIn(BADGE_BEN_VUNG, tree["badges"])
        self.assertEqual(tree["xp"], XP_PER_PASS * 7)
        titles = [m["title"] for m in tree["modules"]]
        self.assertEqual(
            titles,
            ["Rễ Cục", "An Toàn Tài Chính", "Tự Do Tài Chính", "Bền Vững & Di Sản"],
        )
        flat_ids = [n["node_id"] for n in tree["nodes"]]
        self.assertIn("N04-01", flat_ids)
        self.assertIn("N01-01", flat_ids)
        self.assertIn("N02-01", flat_ids)
        self.assertIn("N03-01", flat_ids)
        self.assertEqual(BADGE_TU_DO, "Tự Do Tài Chính")

    def test_n04_pass_no_mastery_apply_no_gate_wire(self):
        out = submit_kuat("u-gate-m04", "N04-01", _correct("N04-01"))
        self.assertTrue(out["kuat_result"]["passed"])
        m = get_node("u-gate-m04", "no_efund_invest")
        self.assertNotEqual(m.state, "apply")
        self.assertFalse(m.meets_gate())
        self.assertIsNone(os_nudge_for("N04-01", first_pass=True))
        self.assertIsNone(out["os_nudge"])
        for nid in M04_NODE_IDS[1:]:
            submit_kuat("u-gate-m04", nid, _correct(nid))
        m2 = get_node("u-gate-m04", "no_efund_invest")
        self.assertNotEqual(m2.state, "apply")
        self.assertEqual(GATE_NODE, "N02-02")

    def test_os_nudge_m04_none(self):
        for nid in M04_NODE_IDS:
            self.assertIsNone(os_nudge_for(nid, first_pass=True))

    def test_insure_retire_hard_q_emphasizes_an_toan(self):
        for nid in ("N04-02", "N04-03"):
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
                    any(k in ans for k in ("An Toàn", "Không", "không", "ưu tiên", "Giữ")),
                    ans,
                )

    def test_html_groups_modules(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Rễ Cục", html)
        self.assertIn("An Toàn Tài Chính", html)
        self.assertIn("Tự Do Tài Chính", html)
        self.assertIn("Bền Vững & Di Sản", html)
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
        self.assertIn("Bền Vững & Di Sản", ui.text)
        h = client.get("/health").json()
        self.assertEqual(h["status"], "ok")
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])


if __name__ == "__main__":
    unittest.main()
