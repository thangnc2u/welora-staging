"""Ticket "GP follow-up sau OTP #244 + Academy #245", group (B) item 15: the nodes still on 3-question
KUAT banks (ticket says 28; the code had 30: N01-02..07, N02-03..07, N03-02..07, N04-02..07,
N05-01..07) move to the N02 standard: 12 questions × 4 options, 6 core, 5 drawn per server-issued
single-use attempt with ≥ 2 core, pass / fail only. Same quality bars as the #245 banks: correct-answer
length rank balanced 3/3/3/3 with no ties, no opening word that marks the answer, every answer grounded
in the lesson body the Academy actually serves, and length / random / opening-word guessing ≤ 2 %.
Attempts issued from the old 3-question banks are retired (served_valid, #245).
DB scenarios run in subprocesses (tests/_kb30_dbmode.py) on SQLite, or PG17 via WELORA_TEST_POSTGRES_URL.
"""

from __future__ import annotations

import json
import os
import random
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from tests._db_target import db_env
from welora import academy

ROOT = Path(__file__).resolve().parents[1]
VI = re.compile(r"[ạảãáàâầấậẩẫăằắặẳẵđêềếệểễôồốộổỗơờớợởỡưừứựửữìíịỉĩòóọỏõùúụủũỳýỵỷỹ]", re.I)
FORBIDDEN = r"(?i)^không,\s*trừ khi|chắc lời|cam kết lãi"
BANKS_30 = tuple([f"N01-0{i}" for i in range(2, 8)] + [f"N02-0{i}" for i in range(3, 8)]
                 + [f"N03-0{i}" for i in range(2, 8)] + [f"N04-0{i}" for i in range(2, 8)]
                 + [f"N05-0{i}" for i in range(1, 8)])
# Follow-up #246/#247 item 1: these 7 banks are now the Founder-approved v1.1 text, entered verbatim
# (tests/test_founder_v11_lessons.py checks prompt / options / answer / core against the source and the
# A–D spread). The authoring bars below that only rewording could meet — length rank 3/3/3/3 without
# ties, no answer-marking opening word, phrase grounding against the old stub, length / opening-word
# guessing ≤ 2 % — are NOT applied to them (wording may not be edited; reported to the Founder). Shape,
# ids, 6 core, draw / served_valid and random guessing ≤ 2 % still apply to all 30.
FOUNDER_V11 = set(academy.FOUNDER_V11_NODES)
AUTHORED = tuple(n for n in BANKS_30 if n not in FOUNDER_V11)


def run(name: str, env: dict, timeout: int = 600) -> dict:
    full = {k: v for k, v in os.environ.items() if not k.startswith("WELORA_")}
    full.update({"PYTHONPATH": str(ROOT), "WELORA_DEMO_AUTOSEED": "0", "WELORA_ENV": "staging",
                 "WELORA_GUEST_DEMO": "1"})
    full.update(env)
    p = subprocess.run([sys.executable, "-m", "tests._kb30_dbmode", name], cwd=str(ROOT), env=full,
                       capture_output=True, text=True, timeout=timeout)
    for line in reversed(p.stdout.splitlines()):
        if line.startswith("RESULT="):
            return json.loads(line[len("RESULT="):])
    raise AssertionError(f"scenario {name} failed rc={p.returncode}\n{p.stdout[-2000:]}\n{p.stderr[-4000:]}")


def _openings(text: str) -> set[str]:
    words = [w for w in (re.sub(r"[^\w]", "", x.lower()) for x in text.split()) if w]
    return {words[0], " ".join(words[:2])} if words else set()


def _body(nid: str) -> str:
    n = academy._NODE_BY_ID[nid]
    return academy._lesson_body_markdown(n["lesson_id"], n["principle_key"]).replace("**", "").lower()


# One phrase per question (in bank order): the passage of the served lesson the correct answer comes from.
GROUNDING = {
    "N01-02": [
        "mối quan hệ giữa thu nhập và chi tiêu",
        "thu nhập lớn hơn chi tiêu một cách bền vững",
        "chi tiêu là các lỗ thoát nước",
        "các lỗ thoát đang ngày càng lớn",
        "phải nhìn đồng thời cả hai phía",
        "tổng chi tiêu thực tế có thể chạm hoặc vượt 35 triệu",
        "chi tiêu bị phân mảnh thành nhiều khoản nhỏ",
        "càng khó hơn nếu không ghi chép",
        "làm giảm chất lượng cuộc sống và không bền vững",
        "dòng tiền dương chưa đồng nghĩa với giàu có",
        "số dư là mực nước còn lại trong bồn",
        "không đưa ra mức chi tiêu",
    ],
    "N01-03": [
        "kế hoạch phân bổ thu nhập vào các khoản chi tiêu, tiết kiệm và mục tiêu",
        "không phải là công cụ để",
        "vừa có bản đồ, vừa có đồng hồ báo xăng",
        "để lại phần cho tiết kiệm/mục tiêu trước",
        "có khoản chi đột xuất",
        "không biết lấy tiền từ đâu",
        "chỉ chia 3–4 nhóm lớn",
        "dễ khiến người dùng bỏ cuộc sau vài tuần",
        "nếu không được thực hiện và điều chỉnh",
        "nó là công cụ phục vụ mục tiêu lớn hơn",
        "lái xe chỉ dựa vào cảm giác",
        "không đưa ra mẫu ngân sách bắt buộc",
    ],
    "N01-04": [
        "lấy dữ liệu chi tiêu đã xảy ra",
        "xuất phát từ hành vi hiện tại",
        "giảm dần từng bước có kiểm soát",
        "thu thập dữ liệu 30 ngày",
        "thường là phần",
        "đặt mục tiêu giảm còn 6 triệu",
        "bạn có thể sống chung được",
        "cho tương lai 5–6 triệu",
        "ngân sách là bản nháp sống",
        "dễ bị lệch",
        "cần được chia đều hoặc dự phòng riêng",
        "không có công thức duy nhất đúng",
    ],
    "N01-05": [
        "dữ liệu trung thực",
        "nó không cấm bạn đi",
        "thường khác với con số thật",
        "không nhất thiết 20 hạng mục",
        "phù hợp người còn dùng nhiều tiền mặt",
        "phù hợp người đã thanh toán không dùng tiền mặt nhiều",
        "bắt đầu chỉ với 3–5 nhóm lớn",
        "đã tốt hơn không theo dõi gì",
        "chiếm tỷ lệ lớn bất ngờ",
        "theo dõi quá chi tiết ngay từ đầu",
        "chu kỳ dài",
        "không khuyến nghị một app hay phương pháp duy nhất",
    ],
    "N01-07": [
        "tiền lãi phát sinh được cộng dồn vào gốc",
        "có giá trị hơn cùng một khoản tiền đó trong tương lai",
        "thời gian = chiều dài con dốc",
        "bắt đầu sớm",
        "người a thường vẫn có lợi thế",
        "không rút gốc giữa chừng",
        "phần lớn tiền trả hàng tháng đang bị lãi",
        "điều quan trọng cần nắm là cơ chế",
        "kèm kỷ luật không rút sớm",
        "không có khoản đầu tư nào đảm bảo",
        "không đồng nghĩa với việc nên chấp nhận rủi ro cao",
        "nợ lãi suất cao trở nên nặng nhanh chóng",
    ],
    "N03-02": [
        "bỏ tiền vào túi bạn",
        "lấy tiền ra khỏi túi bạn",
        "tác động lên dòng tiền và khả năng lựa chọn dài hạn",
        "đang đưa tiền vào túi tôi, hay đang lấy tiền ra",
        "tài sản (theo nghĩa tạo thu nhập) giống máy loại a",
        "chiếc điện thoại mới hầu như luôn là khoản tiêu dùng",
        "cho thuê một phần hoặc tăng giá trị dài hạn",
        "khấu hao + lãi + bảo dưỡng",
        "khác biệt rõ",
        "không phải mọi thứ gọi là",
        "không phải mọi khoản chi tiêu đều",
        "công cụ tư duy",
    ],
    "N03-03": [
        "trao đổi thời gian và công sức",
        "mức độ tham gia trực tiếp thấp hơn sau giai đoạn xây dựng ban đầu",
        "không có nghĩa là không cần làm gì và không có rủi ro",
        "hệ thống dẫn nước",
        "khách thuê bỏ đi",
        "trừ trống phòng, sửa chữa, thuế, công quản lý",
        "livestream",
        "thường là dấu hiệu cần hết sức thận trọng",
        "quỹ khẩn cấp, kiểm soát nợ, dòng tiền dương",
        "giảm dần mức độ phụ thuộc vào việc bán từng giờ lao động",
        "có thể giảm hoặc mất",
        "thường thấp hơn sau lạm phát và thuế",
    ],
    "N03-04": [
        "khả năng mất một phần hoặc toàn bộ",
        "rủi ro đổi lấy khả năng sinh lời cao hơn",
        "chỉ đầu tư tiền có thể chấp nhận biến động / mất",
        "cơ chế tạo ra lợi nhuận và rủi ro",
        "buộc phải bán lúc giá xuống",
        "cần được xem xét hết sức thận trọng",
        "chỉ phần 30 triệu dài hạn",
        "vay tiền để đầu tư",
        "không bỏ tất cả vào một chỗ",
        "lịch sử lợi nhuận không đảm bảo kết quả tương lai",
        "mức rủi ro: cao",
        "không khuyến nghị bất kỳ sản phẩm",
    ],
    "N03-05": [
        "giảm rủi ro tập trung",
        "đa dạng hóa không đảm bảo lãi",
        "chia trứng vào nhiều giỏ",
        "đa dạng hóa trên hình thức",
        "giảm rủi ro có hạn",
        "xem xét sự khác biệt về loại rủi ro",
        "phần này không nên",
        "chia thành nhiều phần với mức rủi ro khác nhau",
        "làm tăng chi phí",
        "vay nợ lớn để tập trung vào một kênh duy nhất",
        "không thay thế việc hiểu từng thành phần",
        "không đưa ra tỷ lệ phân bổ chuẩn",
    ],
    "N03-06": [
        "xác định mức sống mong muốn",
        "lộ trình có thể điều chỉnh",
        "bỏ qua bước chuẩn bị",
        "quỹ khẩn cấp, kiểm soát nợ, dòng tiền, kiến thức",
        "an toàn vững + bắt đầu đệm linh hoạt",
        "mỗi 6–12 tháng",
        "là đảo ngược thứ tự",
        "chỉ mở rộng các kênh phức tạp hơn khi nền đã vững",
        "quỹ khẩn cấp, nợ lãi cao, tỷ lệ tiết kiệm/đầu tư dài hạn",
        "chỉ mang tính minh họa",
        "dựa trên giả định",
        "linh hoạt nghề nghiệp",
    ],
    "N03-07": [
        "bị chậm, bị đảo lộn, hoặc đi ngược mục tiêu",
        "chịu đựng được khi mọi thứ không diễn ra đúng giả định",
        "bị buộc phải dừng cuộc chơi đúng lúc bất lợi",
        "mang đủ xăng dự phòng",
        "rủi ro hành vi",
        "tiền nằm ở chỗ khó rút đúng lúc cần",
        "một sự cố nhỏ cũng có thể buộc phải bán lỗ",
        "kế hoạch dài hạn bị lùi nhiều năm",
        "mất việc, ốm đau",
        "rủi ro pháp lý",
        "không nhằm khuyến khích sợ hãi",
        "rủi ro tập trung",
    ],
    "N04-02": [
        "chuyển giao một phần rủi ro tài chính",
        "phá hủy toàn bộ kế hoạch tài chính",
        "khi bão đến, bạn không mất trắng",
        "bảo vệ trước rủi ro có thể phá hủy",
        "điều khoản loại trừ, thời gian chờ",
        "không dùng bảo hiểm thay cho quỹ khẩn cấp hay đầu tư",
        "phí bảo hiểm là chi phí bảo vệ",
        "đã xác định rõ rủi ro cần chuyển giao",
        "trụ cột mất khả năng lao động",
        "không phải lúc nào cũng đúng",
        "duy trì bhyt",
        "cần tách bạch phần nào là bảo vệ",
    ],
    "N04-03": [
        "khi thu nhập từ lao động giảm hoặc dừng lại",
        "giảm phụ thuộc hoàn toàn vào con cháu",
        "nhờ thời gian và lãi kép",
        "y tế tăng, một số chi phí khác giảm",
        "không dựa 100% vào một nguồn",
        "không phải ai cũng có và không phải lúc nào cũng đủ",
        "không rút khoản này cho chi tiêu ngắn hạn",
        "bắt đầu để dành 2 triệu/tháng",
        "dài hơn trước",
        "review mỗi vài năm",
        "đều mang tính giả định",
        "đều chứa rủi ro riêng",
    ],
    "N04-04": [
        "hình thành nhận thức, thói quen và kỹ năng",
        "di sản phi vật chất",
        "bắt đầu với xe nhỏ, có bánh phụ",
        "việc người lớn làm",
        "chọn một trong hai",
        "khoản tiền tiêu vặt định kỳ",
        "tham gia một phần quyết định chi tiêu gia đình đơn giản",
        "mở lời sớm, ngắn, đều đặn",
        "dễ làm lệch động lực nội tại",
        "gây lo âu không cần thiết",
        "không có một độ tuổi hay một cách dạy duy nhất đúng",
        "heo đất / lọ tiết kiệm đơn giản cho mục tiêu ngắn",
    ],
    "N04-06": [
        "không nhất thiết đo bằng tiền",
        "định hình cách họ kiếm, tiêu, tiết kiệm",
        "tự định hướng dù túi tiền có lúc đầy",
        "cách nghĩ và thói quen",
        "được sống hàng ngày chứ không chỉ nói",
        "giảm chi phí và tăng khả năng tự chủ",
        "nói chuyện cởi mở về ngân sách",
        "cũng là một cực đoan",
        "chuyển giao năng lực tạo thu nhập",
        "không nên biến việc truyền giá trị thành áp lực",
        "không thay thế hoàn toàn việc chuẩn bị tài chính vật chất",
        "nói rõ, không trách móc kéo dài",
    ],
    "N04-07": [
        "không đánh đổi hoàn toàn sức khỏe",
        "vùng giữa có chủ đích",
        "lưng đau, không còn sức ngắm cảnh",
        "tiết kiệm vì mục tiêu rõ ràng",
        "ghi thành ngân sách",
        "không phải lý do để phá vỡ quỹ khẩn cấp",
        "20% thu nhập cho tương lai",
        "chuyến đi ngắn",
        "tránh so sánh với người chỉ khoe",
        "không có tỷ lệ vàng đúng cho mọi người",
        "mục tiêu còn phù hợp không",
        "không phải lý do để bỏ bê sức khỏe",
    ],
    "N05-01": [
        "khoảng cách giữa kiến thức và hành động",
        "mục tiêu đủ rõ, bước đầu đủ nhỏ",
        "bắt đầu với vũng nông",
        "một hành động đủ nhỏ",
        "mục tiêu quá lớn / quá mơ hồ",
        "quy trình phức tạp, app nhiều",
        "xem lại sao kê và ghi 3 nhóm chi tiêu lớn",
        "tháng này chuyển 500.000",
        "chọn một cách ghi đơn giản",
        "hình thức trì hoãn tinh vi",
        "thực hành có cổng (welorademy)",
        "cần nhìn thực tế thay vì chỉ tự trách",
    ],
    "N05-02": [
        "ít phụ thuộc vào quyết tâm từng lần",
        "thiết kế hành vi",
        "bớt phải quyết định từ đầu mỗi lần",
        "thời điểm hoặc sự kiện kích hoạt",
        "thói quen nhỏ xếp chồng lên nhau thì có",
        "chỉ phân 3 nhóm lớn",
        "mỗi chủ nhật tối mở app ngân hàng",
        "dễ thất bại đồng loạt",
        "thường kém bền hơn",
        "không thay thế việc chọn hành vi đủ nhỏ",
        "2–3 ngày trước hạn",
        "không có một bộ thói quen bắt buộc",
    ],
    "N05-03": [
        "định kỳ so sánh thực tế",
        "thay đổi mức đóng góp, thứ tự ưu tiên",
        "có thông tin kịp thời",
        "đi đường khác, nghỉ, hoặc chấp nhận đến muộn hơn",
        "dựa trên vị trí thực",
        "chi tiêu có đang vượt nhóm linh hoạt",
        "chỉnh tạm còn 1 triệu",
        "chậm hơn dự kiến nhưng không chết",
        "gây mệt và bỏ cuộc",
        "mỗi 3–6 tháng",
        "dạng cứng nhắc có hại",
        "dao động vô hướng",
    ],
    "N05-04": [
        "tập hợp các lựa chọn nhỏ",
        "thành hoặc bại",
        "lỗ thủng nhỏ ở đáy",
        "chờ 24–48 giờ",
        "tắt thông báo sale",
        "môi trường và quy tắc",
        "nếu chờ 48 giờ, mình vẫn muốn mua chứ",
        "giảm rõ vì có tín hiệu trước khi trả tiền",
        "gây mệt và phản tác dụng",
        "không phải khoản chi nhỏ nào cũng là",
        "cần cân nhắc riêng",
        "không đưa danh sách",
    ],
    "N05-05": [
        "chia sẻ kiến thức, kinh nghiệm, câu hỏi và hỗ trợ tinh thần",
        "duy trì trách nhiệm nhẹ",
        "chê bai người chậm",
        "kể cả thất bại",
        "liên tục khoe lợi nhuận ngắn hạn",
        "lời khuyên từ người lạ trên mạng",
        "tháng này để dành được không",
        "duy trì được thói quen lâu hơn",
        "không thay thế trách nhiệm cá nhân",
        "dễ méo mó",
        "dấu hiệu cộng đồng cần thận trọng",
        "tôn trọng hoàn cảnh khác nhau",
    ],
    "N05-06": [
        "giảm gánh nặng ghi nhớ",
        "giảm ma sát",
        "phản xạ nhẹ nhàng hơn",
        "có cổng kuat",
        "đủ đơn giản để dùng khi mệt",
        "không nhảy sang công cụ mới mỗi khi nản",
        "chỉ dùng weloraos để đặt 2 goal",
        "duy trì được 5 tháng liên tục",
        "dữ liệu đẹp mà không có hành vi",
        "không chia sẻ otp, mật khẩu",
        "khó thích ứng",
        "công cụ phục vụ người dùng",
    ],
    "N05-07": [
        "kể cả khi sự hứng khởi ban đầu đã hết",
        "hệ thống + ý nghĩa + phản hồi",
        "có lý do đủ rõ để tiếp tục khi mệt",
        "mốc 30 ngày, 3 tháng",
        "coi đứt quãng là bình thường",
        "so sánh với người khoe trên mạng",
        "đọc lại khi nản",
        "vẫn tốt hơn tốc độ 0%",
        "1 tháng chi tiêu trong 4 tháng",
        "động lực không thay được thu nhập thấp đột ngột",
        "làm giảm, không tăng, khả năng quay lại",
        "hỗ trợ chuyên môn phù hợp",
    ],
}


class TestBanksShape(unittest.TestCase):
    def test_every_node_is_on_the_n02_standard(self):
        self.assertEqual(len(BANKS_30), 30)
        self.assertEqual(set(academy.QUESTIONS), set(academy._NODE_BY_ID))
        for nid, bank in academy.QUESTIONS.items():
            self.assertEqual(len(bank), 12, nid)  # no 3-question bank left anywhere

    def test_shape(self):
        ids = [q["id"] for qs in academy.QUESTIONS.values() for q in qs]
        self.assertEqual(len(ids), len(set(ids)))
        for nid in BANKS_30:
            bank = academy.QUESTIONS[nid]
            pre = "q" + nid[2] + nid[4:]
            self.assertEqual([q["id"] for q in bank], [f"{pre}-{i:02d}" for i in range(1, 13)], nid)
            self.assertEqual(sum(q["hard"] for q in bank), 6, nid)
            self.assertEqual(len({q["prompt"] for q in bank}), 12, nid)
            for q in bank:
                self.assertEqual(len(q["choices"]), 4, q["id"])
                self.assertEqual(len(set(q["choices"])), 4, q["id"])
                self.assertTrue(0 <= q["answer"] < 4, q["id"])
                self.assertIsInstance(q["hard"], bool, q["id"])
                self.assertRegex(q["prompt"] + " ".join(q["choices"]), VI, q["id"])
                for c in q["choices"] + [q["prompt"]]:
                    self.assertNotRegex(c, FORBIDDEN, q["id"])
            info = academy.kuat_info(nid)
            self.assertEqual((info["question_count"], info["bank_size"]), (5, 12), nid)

    def test_old_ids_are_gone(self):
        ids = {q["id"] for qs in academy.QUESTIONS.values() for q in qs}
        self.assertFalse({i for i in ids if re.fullmatch(r"q\d{3}[a-z]", i)})

    def test_answer_length_rank_balanced(self):
        for nid in AUTHORED:
            ranks = []
            for q in academy.QUESTIONS[nid]:
                lens = [len(c) for c in q["choices"]]
                self.assertEqual(len(set(lens)), 4, q["id"])  # no ties
                ranks.append(sorted(lens, reverse=True).index(lens[q["answer"]]))
            self.assertEqual([ranks.count(r) for r in range(4)], [3, 3, 3, 3], nid)

    def test_no_opening_marks_the_answer(self):
        for nid in AUTHORED:
            right = Counter(sorted(_openings(q["choices"][q["answer"]]), key=len)[0] for q in academy.QUESTIONS[nid])
            self.assertLessEqual(max(right.values()), 1, (nid, right.most_common(3)))

    def test_answers_grounded_in_the_served_lesson(self):
        self.assertEqual(set(GROUNDING), set(AUTHORED))
        for nid in BANKS_30:
            self.assertGreater(len(_body(nid)), 1500, nid)  # the 7 former stubs now serve full lessons
        for nid in AUTHORED:
            body = _body(nid)
            self.assertEqual(len(GROUNDING[nid]), 12, nid)
            for phrase in GROUNDING[nid]:
                self.assertIn(phrase, body, (nid, phrase))

    def test_draw_five_with_two_core_shuffled(self):
        for nid in BANKS_30:
            by_id = {q["id"]: q for q in academy.QUESTIONS[nid]}
            subsets = set()
            for _ in range(30):
                served = academy._draw(nid)
                self.assertEqual(len(served), 5)
                self.assertGreaterEqual(sum(by_id[s["q"]]["hard"] for s in served), 2)
                self.assertTrue(academy.served_valid(nid, served))
                subsets.add(tuple(sorted(s["q"] for s in served)))
                pub = academy._served_public(nid, served)
                self.assertEqual(sorted({k for q in pub for k in q}), ["choices", "id", "prompt"])
            self.assertGreater(len(subsets), 5, nid)

    def test_served_valid_rejects_old_bank_attempts(self):
        for nid in BANKS_30:
            old = "q" + nid[2] + nid[4:]
            self.assertFalse(academy.served_valid(nid, [{"q": old + "a", "perm": [0, 1, 2]}]), nid)
            self.assertFalse(academy.served_valid(nid, [{"q": old + "-01", "perm": [0, 1, 2]}]), nid)  # 3 options
            self.assertTrue(academy.served_valid(nid, [{"q": old + "-01", "perm": [3, 1, 0, 2]}]), nid)


class TestBanksMonteCarlo(unittest.TestCase):
    """Length heuristics, random guessing and opening-word strategies pass ≤ 2 % over the real
    draw / shuffle / grader, for every authored bank; random guessing for all 30 (FOUNDER_V11 above)."""

    TRIALS = 3000

    def _rate(self, node, choose, rng):
        by_id = {q["id"]: q for q in academy.QUESTIONS[node]}
        passed = 0
        for _ in range(self.TRIALS):
            served = academy._draw(node)
            answers = []
            for i, slot in enumerate(served):
                shown = [by_id[slot["q"]]["choices"][j] for j in slot["perm"]]
                answers.append({"question_id": f"k{i + 1}", "choice": choose(shown, rng)})
            passed += academy._grade_served(node, served, answers)[1]
        return passed / self.TRIALS

    def test_length_and_random_strategies(self):
        def by_len(pos):
            def f(shown, rng):
                order = sorted(range(len(shown)), key=lambda k: (len(shown[k]), rng.random()))
                return {"longest": order[-1], "shortest": order[0], "middle": order[len(order) // 2],
                        "random": rng.randrange(len(shown))}[pos]
            return f

        rng = random.Random(2446)
        for node in BANKS_30:
            for s in ("longest", "shortest", "middle", "random") if node in AUTHORED else ("random",):
                rate = self._rate(node, by_len(s), rng)
                self.assertLessEqual(rate, 0.02, (node, s, rate))

    def test_opening_strategies(self):
        rng = random.Random(24461)

        def pick(p):
            return lambda shown, r: r.choice([i for i, x in enumerate(shown) if p in _openings(x)] or list(range(4)))

        def avoid(ps):
            return lambda shown, r: r.choice([i for i, x in enumerate(shown) if not (_openings(x) & ps)] or list(range(4)))

        for node in AUTHORED:
            total, wrong = Counter(), Counter()
            for q in academy.QUESTIONS[node]:
                for i, c in enumerate(q["choices"]):
                    for p in _openings(c):
                        total[p] += 1
                        wrong[p] += i != q["answer"]
            repeated = [p for p, n in total.items() if n >= 2]
            never_right = {p for p in repeated if wrong[p] == total[p]}
            strategies = [(f"pick {p}", pick(p)) for p in repeated] + [(f"avoid {p}", avoid({p})) for p in repeated]
            strategies.append(("avoid never-right", avoid(never_right)))
            for name, fn in strategies:
                rate = self._rate(node, fn, rng)
                self.assertLessEqual(rate, 0.02, (node, name, rate))


class TestBanksDb(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http = run("banks_http", db_env(tempfile.mkdtemp()))
        cls.stale = run("stale_bank_attempt", db_env(tempfile.mkdtemp()))

    def test_http_attempts_pass_fail_only(self):
        self.assertEqual(sorted(self.http), sorted(BANKS_30))
        for node in BANKS_30:
            o = self.http[node]
            self.assertEqual((o["count"], o["choices"], o["bank_size"], o["question_count"]), (5, [4], 12, 5), node)
            self.assertEqual(o["keys"], ["choices", "id", "prompt"], node)  # no answer / hard / correctness
            self.assertEqual(o["fail"], [200, False], node)
            self.assertEqual(o["fail_result_keys"], ["node_id", "passed", "principle_keys", "ts"], node)
            self.assertEqual(o["pass"], [200, True], node)

    def test_attempts_from_the_old_bank_are_retired(self):
        for node in ("N01-02", "N03-05", "N05-07"):
            s = self.stale[node]["start"]
            self.assertEqual(s, {"status": 200, "new_attempt": True, "five_current": True, "old_outcome": "expired",
                                 "open": 1}, node)
            u = self.stale[node]["submit"]
            self.assertEqual((u["status"], u["code"], u["fails"], u["old_outcome"]),
                             (409, "KUAT_ATTEMPT_INVALID", 0, "expired"), node)


if __name__ == "__main__":
    unittest.main()
