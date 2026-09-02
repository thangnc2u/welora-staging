"""P0 Welorademy KUAT M02 An Toàn."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.academy import (
    KUAT_PASS_THRESHOLD,
    NODES,
    QUESTIONS,
    mark_read,
    reset_academy_store,
    submit_kuat,
)
from welora.api.app import create_app
from welora.mastery import reset_mastery_store, get_node, GATE_MIN
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "academy.html"
HOME = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "home.html"


def _correct(node_id: str) -> list[dict]:
    return [{"question_id": q["id"], "choice": q["answer"]} for q in QUESTIONS[node_id]]


def _wrong(node_id: str) -> list[dict]:
    return [{"question_id": q["id"], "choice": (q["answer"] + 1) % max(2, len(q["choices"]))} for q in QUESTIONS[node_id]]


class TestP0AcademyKuatM02(unittest.TestCase):
    def setUp(self):
        reset_academy_store()
        reset_mastery_store()

    def test_threshold_and_tree(self):
        self.assertEqual(KUAT_PASS_THRESHOLD, 0.70)
        ids = [n["node_id"] for n in NODES]
        self.assertEqual(ids, ["N02-01", "N02-02", "N02-03", "N02-05", "N02-04", "N02-06", "N02-07"])
        self.assertEqual(NODES[1]["prereq_node_ids"], ["N02-01"])
        self.assertEqual(NODES[3]["node_id"], "N02-05")

    def test_read_no_xp(self):
        before = mark_read("u1", "N02-01")
        self.assertEqual(before["xp"], 0)
        self.assertFalse(before["awarded_xp"])
        again = mark_read("u1", "N02-01")
        self.assertEqual(again["xp"], 0)

    def test_fail_no_unlock_no_mastery(self):
        mark_read("u1", "N02-01")
        out = submit_kuat("u1", "N02-01", _wrong("N02-01"))
        self.assertFalse(out["kuat_result"]["passed"])
        self.assertEqual(out["xp"], 0)
        tree = out["tree"]
        n02 = next(n for n in tree["nodes"] if n["node_id"] == "N02-02")
        self.assertEqual(n02["status"], "locked")
        m = get_node("u1", "no_efund_invest")
        self.assertNotEqual(m.state, "apply")
        self.assertFalse(m.meets_gate())

    def test_n02_02_pass_sets_mastery_apply(self):
        submit_kuat("u1", "N02-01", _correct("N02-01"))
        out = submit_kuat("u1", "N02-02", _correct("N02-02"))
        self.assertTrue(out["kuat_result"]["passed"])
        self.assertGreater(out["xp"], 0)
        m = get_node("u1", "no_efund_invest")
        self.assertEqual(m.state, "apply")
        self.assertTrue(m.meets_gate())
        self.assertEqual(GATE_MIN, "apply")

    def test_html_and_health(self):
        html = HTML.read_text(encoding="utf-8")
        self.assertIn("Welorademy", html)
        self.assertIn("KUAT", html)
        self.assertIn("/academy/tree", html)
        self.assertNotIn("innerHTML", html)
        home = HOME.read_text(encoding="utf-8")
        self.assertIn("Welorademy", home)
        self.assertIn("/app/academy", home)
        self.assertEqual(TARGET_MONTHS, 3)
        r = TestClient(create_app()).get("/health")
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(b["gate_months"], 3)
        self.assertTrue(b["hard_deny"])
        ui = TestClient(create_app()).get("/app/academy")
        self.assertEqual(ui.status_code, 200)
        self.assertIn("Welorademy", ui.text)


if __name__ == "__main__":
    unittest.main()
