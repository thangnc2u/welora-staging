"""PR #249 r3 (ticket 3eea91c4): the readers' stripFrontmatter (academy.html, content.html) cut every line
above the first «---» whenever that part mentioned «Mức rủi ro» / «Status:» … anywhere — e.g. a body
paragraph «**Mức rủi ro: …**» before the «---» that opens «Câu hỏi liên quan gợi ý». N03-04..07, N04-02/03
shrank to ~190 characters (N03-04: 3616 → 181) and INV-01 on /app/content was hit too.

Now a leading block is dropped only when EVERY non-empty line above the first «---» is an internal header
line (# WA-/# WP- title, **Module:** / **Mức rủi ro:** / **Version:** / **Status:** / **principle_key:** /
**secondary_keys:**). The JS itself is run with node on what the server serves: all 35 Academy nodes
(academy.html) and every /content key incl. INV-01 (content.html). The displayed text must be the server
body, minus at most the leading internal title line the reader hides (WA H1)."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from welora import academy, content_map
from welora.api.app import create_app

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "welora" / "api" / "static"
PAGES = ("academy.html", "content.html")
FN = re.compile(r"function isInternalHeaderLine[\s\S]*?\nfunction stripFrontmatter[\s\S]*?\n}\n")
TITLE = re.compile(r"^#\s*W[AP]-")
SHRUNK = ("N03-04", "N03-05", "N03-06", "N03-07", "N04-02", "N04-03")  # the round-2 regression


def _js(page: str) -> str:
    m = FN.search((STATIC / page).read_text(encoding="utf-8"))
    assert m, page
    return m.group(0)


def _run(page: str, bodies: dict[str, str]) -> dict[str, str]:
    out = subprocess.run(["node", "-e", _js(page) + "const b=JSON.parse(require('fs').readFileSync(0,'utf8'));"
                          "const o={};for(const k in b){o[k]=stripFrontmatter(b[k])};console.log(JSON.stringify(o))"],
                         input=json.dumps(bodies), capture_output=True, text=True, timeout=60, check=True)
    return json.loads(out.stdout)


def _expected(body: str) -> str:
    """What the reader should show for an already header-stripped server body: the same text, without
    leading blank lines and without a leading internal title line (the WA H1, shown as the page title)."""
    lines = body.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and TITLE.match(lines[0].strip()):
        lines.pop(0)
    return "\n".join(lines).lstrip()


class TestGuardSource(unittest.TestCase):
    def test_both_pages_share_the_guarded_function(self):
        a, c = _js("academy.html"), _js("content.html")
        self.assertEqual(a, c)
        self.assertIn("head.every(isInternalHeaderLine)", a)
        # the old any-keyword test on the whole head is gone
        self.assertNotIn("Version:|Status:", a)
        for page in PAGES:
            self.assertEqual((STATIC / page).read_text(encoding="utf-8").count("function stripFrontmatter("), 1, page)


@unittest.skipUnless(shutil.which("node"), "node not installed")
class TestReaderKeepsTheBody(unittest.TestCase):
    def setUp(self) -> None:
        self._env = mock.patch.dict(os.environ)
        self._env.start()
        os.environ.pop("WELORA_CONTENT_ROOT", None)

    def tearDown(self) -> None:
        self._env.stop()

    def test_academy_all_35_nodes(self):
        bodies = {nid: academy._lesson_body_markdown(n["lesson_id"], n["principle_key"])
                  for nid, n in academy._NODE_BY_ID.items()}
        self.assertEqual(len(bodies), 35)
        shown = _run("academy.html", bodies)
        for nid, body in bodies.items():
            self.assertEqual(shown[nid], _expected(body), nid)
            if not TITLE.match(body.strip().split("\n")[0]):  # WP-backed: nothing may be hidden
                self.assertGreaterEqual(len(shown[nid]), len(body.strip()), nid)
        for nid in SHRUNK:
            self.assertGreater(len(shown[nid]), 2000, nid)
            self.assertIn("Câu hỏi liên quan gợi ý", shown[nid], nid)

    def test_content_page_every_key_incl_inv01(self):
        client = TestClient(create_app())
        keys = list(content_map.CONTENT_BY_KEY)
        self.assertIn("INV-01", keys)
        bodies = {}
        for k in keys:
            r = client.get(f"/content/{k}")
            self.assertEqual(r.status_code, 200, k)
            bodies[k] = r.json()["body_markdown"]
        shown = _run("content.html", bodies)
        for k, body in bodies.items():
            self.assertEqual(shown[k], _expected(body), k)
            self.assertGreaterEqual(len(shown[k]), len(body.strip()) - len(body.strip().split("\n")[0]) - 2, k)
        self.assertGreater(len(shown["INV-01"]), 2000)

    def test_raw_header_block_is_still_dropped(self):
        raw = (ROOT / "content" / "WP-03-04-thu-nhap-thu-dong.md").read_text(encoding="utf-8")
        for page in PAGES:
            shown = _run(page, {"x": raw})["x"]
            self.assertTrue(shown.startswith("## 1. Câu hỏi thực tế"), (page, shown[:80]))
            self.assertIn("Câu hỏi liên quan gợi ý", shown, page)

    def test_body_keyword_before_a_rule_does_not_cut(self):
        md = ("## 1. Ý\nText.\n\n**Mức rủi ro: Cao.** Cẩn thận.\n\nThêm.\n\n---\n\n"
              "**Câu hỏi liên quan gợi ý:**\n- A?")
        for page in PAGES:
            self.assertEqual(_run(page, {"x": md})["x"], md, page)


if __name__ == "__main__":
    unittest.main()
