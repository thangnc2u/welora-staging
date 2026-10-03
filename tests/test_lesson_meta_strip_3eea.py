"""Ticket 3eea91c4 item 3: the «**principle_key:** … · Bài liên kết …» metadata line of a lesson file is
dropped from body_markdown by the SERVER, for every lesson (not only by academy.html stripFrontmatter).
The key stays in the node's `principle_key` field; the linked WP ids move to `related_links`."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest
import uuid
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from tests._authz import authed
from welora import academy
from welora.api.app import create_app

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "welora" / "api" / "static" / "academy.html"
META = re.compile(r"(?m)^\s*\*\*(?:principle_key|secondary_keys):\*\*")
WP_HEADER = re.compile(r"(?mi)^\s*\*\*\s*(?:module|mức rủi ro|version|status)\s*:?\s*\*\*")
WP_TITLE = re.compile(r"(?m)^#{1,3}\s*WP-[0-9A-Za-z-]+\s*[:：]")
FOUNDER = ("N01-06", "N02-03", "N02-04", "N02-05", "N02-06", "N02-07", "N04-05")


class TestSplit(unittest.TestCase):
    def test_split_lesson_meta(self):
        body, links = academy._split_lesson_meta(
            "# WA-01-06 T\n\n**principle_key:** GOAL-01 · Bài liên kết: WP-01-07\n\n**Mục tiêu:** G\n\n## A\n\nx\n")
        self.assertEqual(body, "# WA-01-06 T\n\n**Mục tiêu:** G\n\n## A\n\nx\n")
        self.assertEqual(links, ["WP-01-07"])
        body, links = academy._split_lesson_meta("# WA-02-01 X\n\n**principle_key:** SAFE-01\n\nText")
        self.assertEqual((body, links), ("# WA-02-01 X\n\nText", []))
        self.assertEqual(academy._split_lesson_meta("plain"), ("plain", []))

    def test_every_lesson_served_without_meta_line(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("WELORA_CONTENT_ROOT", None)
            raw_with_meta = 0
            for nid, n in academy._NODE_BY_ID.items():
                raw = academy._lesson_source_markdown(n["lesson_id"], n["principle_key"])
                raw_with_meta += bool(META.search(raw))
                served = academy._lesson_body_markdown(n["lesson_id"], n["principle_key"])
                self.assertNotRegex(served, META, nid)
                if "\n\n\n" not in raw:
                    self.assertNotIn("\n\n\n", served, nid)  # no blank-line pile-up where the line was
            self.assertGreaterEqual(raw_with_meta, 10)  # files that carry the line (the 7 Founder lessons + WA-02-01/02, …)


class TestWpBackedBody(unittest.TestCase):
    """PR #249 r2 (b): a lesson served from a WP article goes through content_map.strip_internal_headers
    — no «# WP-xx-xx:» title and no **Module:** / **Mức rủi ro:** / **Version:** / **Status:** block."""

    def test_wp_backed_lessons_lose_the_internal_headers(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("WELORA_CONTENT_ROOT", None)
            wp_backed = 0
            for nid, n in academy._NODE_BY_ID.items():
                raw, from_wp = academy._lesson_source(n["lesson_id"], n["principle_key"])
                served = academy._lesson_body_markdown(n["lesson_id"], n["principle_key"])
                if not from_wp:
                    self.assertTrue(served.startswith("# WA-") or not raw.startswith("# WA-"), nid)
                    continue
                wp_backed += 1
                self.assertRegex(raw, WP_HEADER, nid)  # the source does carry the block
                self.assertNotRegex(served, WP_HEADER, nid)
                self.assertNotRegex(served, WP_TITLE, nid)
                self.assertGreater(len(served), 1000, nid)
            self.assertGreaterEqual(wp_backed, 20)


class TestNodeApi(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict(os.environ)
        self._env.start()
        os.environ.pop("WELORA_CONTENT_ROOT", None)
        self.client = authed(TestClient(create_app()))
        auth = self.client.post("/auth/device", json={"device_id": "meta-strip-" + uuid.uuid4().hex[:10]})
        self.assertEqual(auth.status_code, 200)
        self.uid = auth.json()["user_id"]

    def tearDown(self) -> None:
        self._env.stop()

    def _node(self, nid):
        r = self.client.get(f"/academy/nodes/{nid}", params={"user_id": self.uid})
        self.assertEqual(r.status_code, 200)
        return r.json()

    def test_body_has_no_meta_line_and_links_are_separate(self):
        n = self._node("N01-06")
        self.assertNotIn("principle_key", n["body_markdown"])
        self.assertNotIn("Bài liên kết", n["body_markdown"])
        self.assertEqual(n["principle_key"], "GOAL-01")
        self.assertEqual(n["related_links"], ["WP-01-07"])
        self.assertTrue(n["body_markdown"].startswith("# WA-01-06 Đặt mục tiêu tài chính đúng cách\n\n**Mục tiêu:** "))
        m = self._node("N02-01")
        self.assertNotRegex(m["body_markdown"], META)
        self.assertIn("WA-02-01", m["body_markdown"])  # the H1 stays (the reader strips it)
        self.assertEqual((m["principle_key"], m["related_links"]), ("SAFE-01", []))
        self.assertEqual(self._node("N04-05")["principle_key"], "LEGACY-01")
        wp = self._node("N01-02")  # WP-backed (no WA-01-02 file)
        self.assertNotRegex(wp["body_markdown"], WP_HEADER)
        self.assertNotRegex(wp["body_markdown"], WP_TITLE)
        self.assertGreater(len(wp["body_markdown"]), 1000)

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_reader_shows_the_goal_first(self):
        js = re.search(r"function isInternalHeaderLine[\s\S]*?\nfunction stripFrontmatter[\s\S]*?\n}\n",
                       HTML.read_text(encoding="utf-8")).group(0)
        bodies = {nid: self._node(nid)["body_markdown"] for nid in FOUNDER}
        out = subprocess.run(["node", "-e", js + "const b=JSON.parse(require('fs').readFileSync(0,'utf8'));"
                              "const o={};for(const k in b){o[k]=stripFrontmatter(b[k]).split('\\n')[0]};"
                              "console.log(JSON.stringify(o))"],
                             input=json.dumps(bodies), capture_output=True, text=True, timeout=30, check=True)
        for nid, first in json.loads(out.stdout).items():
            self.assertTrue(first.startswith("**Mục tiêu:** "), (nid, first))


if __name__ == "__main__":
    unittest.main()
