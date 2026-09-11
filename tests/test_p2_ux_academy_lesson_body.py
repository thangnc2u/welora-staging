"""P2 UAT — Welorademy lesson shows WA body; no SAFE-/DEBT- in learner stub/UI."""

from __future__ import annotations

from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from welora.api.app import create_app
from welora.content_map import CONTENT_BY_KEY
from welora.safety_gate import TARGET_MONTHS

HTML = Path(__file__).resolve().parents[1] / "welora" / "api" / "static" / "academy.html"
ROOT = Path(__file__).resolve().parents[1]


class TestP2UxAcademyLessonBody(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())
        self.html = HTML.read_text(encoding="utf-8")
        auth = self.client.post("/auth/device", json={"device_id": "uat-lesson-body-01"})
        self.assertEqual(auth.status_code, 200)
        self.uid = auth.json()["user_id"]

    def test_html_renders_body_not_key_stub(self):
        self.assertIn("lessonBody", self.html)
        self.assertIn("renderMarkdown", self.html)
        self.assertIn("stripFrontmatter", self.html)
        self.assertIn("body_markdown", self.html)
        # Learner-facing assignment must not concatenate principle_key into stub
        self.assertNotIn("lesson_stub||'')+' · '", self.html)
        self.assertNotIn("+ n.principle_key", self.html)
        self.assertNotIn("+n.principle_key", self.html)
        # Guard: openNode must not dump raw lesson_stub alone without body render
        self.assertIn("renderMarkdown(bodyEl", self.html)

    def test_node_api_wa_body_no_key_in_stub(self):
        r = self.client.get("/academy/nodes/N02-01", params={"user_id": self.uid})
        self.assertEqual(r.status_code, 200)
        n = r.json()
        stub = n.get("lesson_stub") or ""
        body = n.get("body_markdown") or ""
        self.assertEqual(stub, n.get("title"))
        self.assertNotRegex(stub, r"SAFE-|DEBT-|N0\d-")
        self.assertNotIn("SAFE-01", stub)
        self.assertGreater(len(body.strip().splitlines()), 1)
        self.assertGreater(len(body.strip()), 80)
        self.assertIn("WA-02-01", body)  # source heading ok in API; UI strips
        self.assertTrue(n.get("content_href", "").startswith("/app/content?key="))
        self.assertEqual(n.get("principle_key"), "SAFE-01")  # keys kept for API
        self.assertTrue(n.get("questions"))

    def test_wa_02_06_maps_debt02(self):
        p = ROOT / "content" / "WA-02-06-lap-ke-hoach-tra-no.md"
        self.assertTrue(p.is_file())
        self.assertIn("WA-02-06", CONTENT_BY_KEY["DEBT-02"].get("wa") or [])
        r = self.client.get("/academy/nodes/N02-06", params={"user_id": self.uid})
        self.assertEqual(r.status_code, 200)
        n = r.json()
        self.assertNotIn("DEBT-02", n.get("lesson_stub") or "")
        self.assertNotRegex(n.get("lesson_stub") or "", r"SAFE-|DEBT-")
        self.assertIn("WA-02-06", n.get("body_markdown") or "")
        self.assertGreater(len((n.get("body_markdown") or "").strip().splitlines()), 1)

    def test_kuat_and_pedia_link_intact(self):
        r = self.client.get("/academy/nodes/N02-01", params={"user_id": self.uid})
        n = r.json()
        self.assertTrue(n.get("content_href"))
        self.assertIn("key=SAFE-01", n["content_href"])
        qs = n.get("questions") or []
        self.assertGreaterEqual(len(qs), 2)
        self.client.post(
            "/academy/nodes/N02-01/read",
            json={"user_id": self.uid, "node_id": "N02-01"},
        )
        answers = [{"question_id": q["id"], "choice": 0} for q in qs]
        kr = self.client.post(
            "/academy/kuat",
            json={"user_id": self.uid, "node_id": "N02-01", "answers": answers},
        )
        self.assertIn(kr.status_code, (200, 403))
        if kr.status_code == 200:
            self.assertIn("kuat_result", kr.json())

    def test_health_gate(self):
        self.assertEqual(TARGET_MONTHS, 3)
        h = self.client.get("/health").json()
        self.assertEqual(h["gate_months"], 3)
        self.assertTrue(h["hard_deny"])
        page = self.client.get("/app/academy")
        self.assertEqual(page.status_code, 200)
        self.assertIn("lessonBody", page.text)


if __name__ == "__main__":
    unittest.main()
