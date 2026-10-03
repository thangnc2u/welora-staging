"""Ticket "GP follow-up sau #246/#247" item 1: the 7 placeholder lessons (N01-06, N02-03..07, N04-05)
and their 84 KUAT questions are the Founder-approved v1.7 text (CoS-checked, ticket 3eea91c4; lessons as v1.6), entered
verbatim (docs/content/Welora_Academy_7_Bai_v1.7.md, copied byte-for-byte from the Founder file).

- Runtime titles = the WA titles (not the short M02 tree names); each lesson carries its locked
  one-sentence goal; the M02 tree order is unchanged (N02-05 before N02-04).
- The 84 questions replace those 7 nodes' #247 banks: same prompts, same four options, same correct
  option, same core flag. Founder OK (2026-10-02 22:39 ICT): 70 / 84 answers were B in the source, so the
  option positions — and only the positions — were moved once, fixed in academy.QUESTIONS; per node no
  letter holds > 40 % of the correct answers.
"""

from __future__ import annotations

import random
import re
import unittest
from collections import Counter
from pathlib import Path

from welora import academy

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "content" / "Welora_Academy_7_Bai_v1.7.md"
NODES = ("N01-06", "N02-03", "N02-04", "N02-05", "N02-06", "N02-07", "N04-05")
SECTIONS = ("Nội dung", "Ý chính", "Ví dụ tình huống", "Việc nên làm ngay")
GOAL = "Mục tiêu"  # label since v1.3 (was «Mục tiêu (khóa 2026-10-02)»)
CODE = re.compile(r"\b[A-Z]{2,7}-\d{2}\b")
QRE = re.compile(r"(?ms)^\*\*q(\d+)\.\*\*\s*(.*?)\s*\nA\. (.*?)\s*\nB\. (.*?)\s*\nC\. (.*?)\s*\nD\. (.*?)\s*\n"
                 r"Đáp án: ([ABCD])\s*\nCore: (có|không)\s*$")


def parse_source() -> dict[str, dict]:
    text = SOURCE.read_text(encoding="utf-8")
    parts = re.split(r"(?m)^## (N0\d-0\d)\s*$", text)
    out = {}
    for i in range(1, len(parts), 2):
        nid, body = parts[i], parts[i + 1]
        meta = {}
        for k in ("Tên", "Tên runtime", "Nguồn tên", GOAL, "principle_key"):
            m = re.search(r"(?m)^\*\*" + re.escape(k) + r":\*\*\s*(.*?)\s*$", body)
            meta[k] = m.group(1) if m else None
        secs = {m.group(1).strip(): m.group(2).strip("\n")
                for m in re.finditer(r"(?ms)^### (.+?)\n(.*?)(?=^### |^---\s*$|\Z)", body)}
        raw_q = len(re.findall(r"(?m)^\*\*q\d+\.\*\*", secs.get("Câu hỏi", "")))
        qs = [{"n": int(m.group(1)), "prompt": m.group(2).strip(), "choices": [m.group(j).strip() for j in (3, 4, 5, 6)],
               "answer": "ABCD".index(m.group(7)), "core": m.group(8) == "có"}
              for m in QRE.finditer(secs.get("Câu hỏi", ""))]
        out[nid] = {"meta": meta, "sections": secs, "questions": qs, "raw_q": raw_q}
    return out


SRC = parse_source()


def _body(nid: str) -> str:
    n = academy._NODE_BY_ID[nid]
    return academy._lesson_body_markdown(n["lesson_id"], n["principle_key"])


class TestSource(unittest.TestCase):
    def test_source_is_the_founder_v17_file(self):
        self.assertEqual(tuple(SRC), NODES)
        self.assertEqual(tuple(academy.FOUNDER_LESSON_NODES), NODES)
        for nid in NODES:
            self.assertEqual(SRC[nid]["raw_q"], 12, nid)  # every question block parsed
            self.assertEqual(len(SRC[nid]["questions"]), 12, nid)
            self.assertEqual(SRC[nid]["meta"]["Nguồn tên"], academy._NODE_BY_ID[nid]["lesson_id"], nid)
        letters = Counter("ABCD"[q["answer"]] for nid in NODES for q in SRC[nid]["questions"])
        self.assertEqual(sum(letters.values()), 84)
        self.assertEqual(letters["B"], 70)  # why the positions were moved


class TestLessons(unittest.TestCase):
    def test_titles_are_the_wa_titles(self):
        for nid in NODES:
            meta = SRC[nid]["meta"]
            self.assertEqual(academy._NODE_BY_ID[nid]["title"], meta["Tên runtime"], nid)
            self.assertEqual(meta["Tên runtime"], meta["Tên"], nid)

    def test_m02_tree_order_unchanged(self):
        self.assertEqual([n["node_id"] for n in academy.M02_NODES],
                         ["N02-01", "N02-02", "N02-03", "N02-05", "N02-04", "N02-06", "N02-07"])
        self.assertEqual(academy._NODE_BY_ID["N02-04"]["prereq_node_ids"], ["N02-05"])
        self.assertEqual(academy._NODE_BY_ID["N02-05"]["prereq_node_ids"], ["N02-03"])

    def test_served_lesson_is_the_source_text(self):
        for nid in NODES:
            body, meta = _body(nid), SRC[nid]["meta"]
            lines = body.split("\n")
            self.assertEqual(lines[0], f"# {academy._NODE_BY_ID[nid]['lesson_id']} {meta['Tên runtime']}", nid)
            # Ticket 3eea91c4 item 3: the server drops the «**principle_key:** … · Bài liên kết …» line, so the
            # locked one-sentence goal comes right after the H1 (academy.html strips only the H1).
            self.assertEqual(lines[1:3], ["", f"**{GOAL}:** {meta[GOAL]}"], nid)
            self.assertNotIn("principle_key", body, nid)
            self.assertNotIn("Bài liên kết", body, nid)
            for sec in SECTIONS:
                src = "\n".join(x.rstrip() for x in SRC[nid]["sections"][sec].split("\n"))
                self.assertIn(f"\n## {sec}\n\n{src}\n", body + "\n", (nid, sec))
            self.assertNotIn("Đáp án:", body, nid)  # questions stay in the KUAT bank, not the lesson
            # v1.2: no principle code in what the learner reads (only the hidden principle_key line has one)
            self.assertNotRegex("\n".join(lines[1:]), CODE, nid)

    def test_n04_05_disclaimer_is_served(self):
        disclaimer = ("Bài này chỉ là giáo dục chung, không phải tư vấn pháp lý, không hướng dẫn soạn di chúc.")
        self.assertTrue(SRC["N04-05"]["sections"]["Nội dung"].startswith(disclaimer))
        self.assertIn(f"## Nội dung\n\n{disclaimer}", _body("N04-05"))

    def test_no_principle_code_in_questions(self):
        for nid in NODES:
            for q in academy.QUESTIONS[nid]:
                self.assertNotRegex(" ".join([q["prompt"], *q["choices"]]), CODE, q["id"])


class TestBanks(unittest.TestCase):
    def test_bank_text_matches_source_exactly_except_positions(self):
        for nid in NODES:
            bank, src = academy.QUESTIONS[nid], SRC[nid]["questions"]
            pre = "q" + nid[2] + nid[4:]
            self.assertEqual([q["id"] for q in bank], [f"{pre}-{s['n']:02d}" for s in src], nid)
            for q, s in zip(bank, src):
                self.assertEqual(q["prompt"], s["prompt"], q["id"])
                self.assertEqual(sorted(q["choices"]), sorted(s["choices"]), q["id"])
                self.assertEqual(q["choices"][q["answer"]], s["choices"][s["answer"]], q["id"])
                self.assertEqual(q["hard"], s["core"], q["id"])
                # only the correct option moved: the distractors keep their source order
                self.assertEqual([c for i, c in enumerate(q["choices"]) if i != q["answer"]],
                                 [c for i, c in enumerate(s["choices"]) if i != s["answer"]], q["id"])

    def test_correct_letters_spread_per_node(self):
        for nid in NODES:
            letters = Counter("ABCD"[q["answer"]] for q in academy.QUESTIONS[nid])
            self.assertLessEqual(max(letters.values()) / 12, 0.40, (nid, letters))
            self.assertEqual(set(letters), set("ABCD"), nid)

    def test_six_core_per_node_and_draw_rules(self):
        for nid in NODES:
            bank = academy.QUESTIONS[nid]
            self.assertEqual((len(bank), sum(q["hard"] for q in bank)), (12, 6), nid)
            self.assertEqual((academy.kuat_info(nid)["question_count"], academy.kuat_info(nid)["bank_size"]), (5, 12))
            by_id = {q["id"]: q for q in bank}
            for _ in range(20):
                served = academy._draw(nid)
                self.assertEqual(len(served), 5)
                self.assertGreaterEqual(sum(by_id[s["q"]]["hard"] for s in served), 2)
                self.assertTrue(academy.served_valid(nid, served))

    def test_random_guessing_stays_low(self):
        rng = random.Random(110)
        for nid in NODES:
            by_id = {q["id"]: q for q in academy.QUESTIONS[nid]}
            passed = 0
            for _ in range(2000):
                served = academy._draw(nid)
                answers = [{"question_id": f"k{i + 1}", "choice": rng.randrange(len(by_id[s["q"]]["choices"]))}
                           for i, s in enumerate(served)]
                passed += academy._grade_served(nid, served, answers)[1]
            self.assertLessEqual(passed / 2000, 0.02, nid)


if __name__ == "__main__":
    unittest.main()
