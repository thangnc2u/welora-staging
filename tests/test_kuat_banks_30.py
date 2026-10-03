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

import itertools
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from fractions import Fraction
from math import ceil, comb
from pathlib import Path

import pytest

from tests._db_target import db_env
from welora import academy

ROOT = Path(__file__).resolve().parents[1]
VI = re.compile(r"[ạảãáàâầấậẩẫăằắặẳẵđêềếệểễôồốộổỗơờớợởỡưừứựửữìíịỉĩòóọỏõùúụủũỳýỵỷỹ]", re.I)
FORBIDDEN = r"(?i)^không,\s*trừ khi|chắc lời|cam kết lãi"
BANKS_30 = tuple([f"N01-0{i}" for i in range(2, 8)] + [f"N02-0{i}" for i in range(3, 8)]
                 + [f"N03-0{i}" for i in range(2, 8)] + [f"N04-0{i}" for i in range(2, 8)]
                 + [f"N05-0{i}" for i in range(1, 8)])
# N01-06, N02-03..07 and N04-05 are the Founder-approved v1.3 text, entered verbatim
# (tests/test_founder_v13_lessons.py). Ticket 3eea91c4: every quality bar below applies to them like to
# the other 23 banks; the 20 xfails kept for v1.2 are gone. v1.3 meets length rank, opening word and
# grounding on all 7 and length / random guessing on all 7. Still missed (wording may not be edited —
# reported to the Founder): the «avoid never-right» opening-word strategy (never pick an option whose
# opening word, seen ≥ 2× in the bank, never opens a correct answer) on 4 nodes. Exact pass rates over
# every draw (exact_rates below): N02-04 2.67 %, N02-05 2.35 %, N02-06 2.52 %, N04-05 3.12 % (bar 2 %).
# Those pairs are skipped in the all-banks loop and run on their own as xfail in TestFounderGaps.
# PR #249 r2: the check is exact now (deterministic); the 4 stay non-strict until the Founder's v1.4
# text lands, then the remaining pairs (if any) become strict.
_AVOID = "«avoid never-right» opening-word strategy passes KUAT {rate} (exact; bar 2 %) — never-right openings {words}; beats 1/4 on {qids}"
FOUNDER_XFAIL: dict[tuple[str, str], str] = {
    ("mc_opening", "N02-04"): _AVOID.format(rate="2.67 %", words="chỉ / có / nhà / đổi",
                                            qids="q204-04, 05, 06, 07, 09, 10, 12"),
    ("mc_opening", "N02-05"): _AVOID.format(rate="2.35 %", words="chỉ / có / được",
                                            qids="q205-01, 06 (→ 100 %), 08, 10, 12"),
    ("mc_opening", "N02-06"): _AVOID.format(rate="2.52 %", words="chỉ / có / là / vay",
                                            qids="q206-01, 03, 04, 06, 07, 09, 10, 11, 12"),
    ("mc_opening", "N04-05"): _AVOID.format(rate="3.12 %", words="chuyển / chỉ / có / phải / thay",
                                            qids="q405-01, 03, 04, 06, 07, 08, 09, 11, 12"),
}


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
    # Founder v1.3 lessons (follow-up #246/#247 item 1, ticket 3eea91c4): passage of the served lesson per question.
    "N01-06": [
        "những câu đó là mong muốn, chưa phải mục tiêu",
        "đạt được gì + số tiền hoặc trạng thái + trong bao lâu + vì lý do gì",
        "không gắn với việc so với đồng nghiệp",
        "chỉ giữ một đến hai mục tiêu trọng tâm",
        "theo hướng an toàn trước",
        "quỹ khẩn cấp ít nhất 3 tháng chi tiêu thiết yếu",
        "để không chờ đến ngày cuối mới biết mình lệch",
        "quỹ khẩn cấp 36 triệu (3 tháng chi tiêu thiết yếu) trong 12 tháng",
        "giảm một khoản chi không thiết yếu hoặc kéo dài thời hạn có chủ đích",
        "lý do phải gắn đời sống của chính mình hoặc gia đình",
        "ba câu hỏi tối thiểu: đạt cái gì, khi nào, vì sao",
        "có thể tự đặt goal cao hơn. không có cửa passed dưới 3 tháng",
    ],
    "N02-03": [
        "quỹ phải thanh khoản cao và tách khỏi tài khoản chi tiêu hàng ngày",
        "quỹ là lớp bảo vệ, không phải công cụ sinh lời",
        "tiền nằm chung rất dễ bị tiêu dần",
        "chỗ giá lên xuống mạnh",
        "đúng lúc cần tiền thì có thể không lấy ra được",
        "ít nhất 3 tháng chi tiêu thiết yếu",
        "chuyển 30 triệu sang một chỗ rút được trong ít ngày",
        "đều có thể hợp mục tiêu khác",
        "rút được trong ít ngày, không phải chờ đáo hạn dài",
        "tháo lớp đệm trước khi biết sự cố nào sẽ đến",
        "bài này không chỉ tên ngân hàng, không chỉ tên sản phẩm",
        "có thể để dày hơn",
    ],
    "N02-04": [
        "avalanche: ưu tiên khoản lãi suất cao nhất",
        "snowball: ưu tiên khoản dư nợ nhỏ nhất",
        "vẫn trả tối thiểu các khoản còn lại",
        "chọn cách mình làm được đến cuối",
        "chỉ trả tối thiểu mọi khoản rồi không có khoản nào được dồn thêm",
        "quỹ tối thiểu 3 tháng chi tiêu thiết yếu vẫn là lớp đệm",
        "hợp người từng bỏ cuộc vì mục tiêu quá dài",
        "avalanche cũng chọn thẻ 8 triệu trước vì lãi cao nhất",
        "đổi phương pháp mỗi tháng vì nghe chuyện người khác là chưa có phương pháp",
        "số tiết kiệm phụ thuộc lãi thực, dư nợ và việc có trả thêm đều hay không",
        "phần trả thêm mới làm dư nợ giảm thật",
        "khoản tôi dồn thêm tiền vào là khoản này, vì lãi cao nhất",
    ],
    "N02-05": [
        "nợ tốt xây năng lực; nợ xấu làm suy yếu",
        "thẻ quay vòng, vay ứng để tiêu",
        "vay nóng để đầu tư không phải chiến lược",
        "đưa về trả đúng hạn trước khi bàn chuyện khác",
        "gắn với tài sản hoặc năng lực",
        "vẫn là nợ xấu nếu không tạo năng lực",
        "dồn trả thêm vào khoản a",
        "khoản này còn lại cái gì sau khi tiêu hết tiền vay",
        "một khoản lãi thấp vẫn nguy hiểm nếu hộ không trả được mà không cắt chi tiêu thiết yếu",
        "nợ quá hạn và nợ tiêu dùng lãi cao trước",
        "khoản b còn gắn với việc tạo thu nhập và đang đúng hạn",
        "nợ vẫn là nghĩa vụ",
    ],
    "N02-06": [
        "kế hoạch cần dư nợ, số tối thiểu, số trả thêm, khoản được dồn",
        "tiền còn lại sau chi tiêu thiết yếu và sau phần giữ quỹ",
        "không lấy từ quỹ khẩn cấp đang dưới 3 tháng chi tiêu thiết yếu",
        "một tháng hụt thì ghi lý do và giảm số trả thêm",
        "chuyển khoản đúng ngày đỡ hơn nhớ lúc mệt",
        "không hứa ngày hết nợ chính xác cho mọi người, vì lãi và thu nhập đổi",
        "giữ quỹ, không rút",
        "các khoản khác giữ tối thiểu",
        "dư nợ giảm chưa, có khoản mới không, tháng sau còn dồn được bao nhiêu",
        "bài này không hướng dẫn một sản phẩm đảo nợ",
        "không phải 5 triệu cho đẹp",
        "tên khoản, dư nợ còn, số trả tối thiểu tháng này, số trả thêm",
    ],
    "N02-07": [
        "ưu tiên an toàn, gồm quỹ và nợ nguy hiểm, trước đầu tư tăng trưởng",
        "quỹ khẩn cấp ít nhất 3 tháng chi tiêu thiết yếu thì mới passed",
        "khi cổng chưa đạt, tiền chưa được đưa sang đầu tư tăng trưởng",
        "dùng quỹ để đầu tư là tháo lớp bảo vệ",
        "nợ tiêu dùng lãi cao, nợ quá hạn",
        "công cụ không hạ ngưỡng 3 tháng, không tắt hard deny",
        "giữ quỹ, đưa quỹ lên đủ 3 tháng chi tiêu thiết yếu, dồn trả thêm vào thẻ",
        "vẫn không được lấy quỹ tối thiểu để tất toán khoản đó",
        "tiền đầu tư là tiền không cần cho chi tiêu thiết yếu",
        "là dữ liệu, không phải người cầm lái",
        "không có sản phẩm để chỉ mua",
        "quyết định cuối là của người dùng",
    ],
    "N04-05": [
        "di sản và thừa kế cần được thiết kế, không để mặc định",
        "nó đẩy việc sang người ở lại",
        "rõ tài sản nào và nghĩa vụ nào còn gắn",
        "không cần văn bản hoàn chỉnh ngay",
        "giấy không đúng thủ tục có thể không có hiệu lực",
        "hỏi người có chuyên môn pháp lý",
        "một buổi nói với vợ về chỗ ở, chăm sóc bố mẹ, và nợ còn lại",
        "chưa hiểu hệ quả sở hữu và quan hệ",
        "liệt kê nhà, sổ, xe, bảo hiểm, nợ ngân hàng, nợ người thân",
        "dừng ở mức trao đổi rồi tìm người hành nghề pháp lý",
        "nó giảm khoảng trống hiểu lầm",
        "welora không thay việc đó",
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
        for nid in _checked("length_rank"):
            check_length_rank(self, nid)

    def test_no_opening_marks_the_answer(self):
        for nid in _checked("opening"):
            check_opening(self, nid)

    def test_answers_grounded_in_the_served_lesson(self):
        self.assertEqual(set(GROUNDING), set(BANKS_30))
        for nid in _checked("grounding"):
            check_grounding(self, nid)

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
    """Length heuristics, random guessing and opening-word strategies pass ≤ 2 % for every one of the
    30 banks. PR #249 r2: computed EXACTLY over every possible draw (no sampling, deterministic) — the
    3000-attempt Monte Carlo it replaces flaked (N01-02 «avoid vì» sampled 2.03 % vs 1.54 % exact)."""

    def test_exact_model_matches_draw_and_grader(self):
        # the model below mirrors academy._draw (k questions, ≥ min-hard core) and _grade_served
        # (≥ KUAT_PASS_THRESHOLD of the shown questions AND every core one right)
        bank = academy.QUESTIONS["N02-01"]
        dist = _draw_dist("N02-01")
        self.assertEqual(sum(dist.values()), 1)
        n_hard, k, m = sum(q["hard"] for q in bank), academy.KUAT_DRAW, academy.KUAT_MIN_HARD
        self.assertEqual(len(dist), sum(comb(n_hard, h) * comb(12 - n_hard, k - h) for h in range(m, k + 1)))
        by_id = {q["id"]: q for q in bank}
        for _ in range(20):
            served = academy._draw("N02-01")
            self.assertIn(frozenset(s["q"] for s in served), dist)
            right = [s["perm"].index(by_id[s["q"]]["answer"]) for s in served]
            soft = [i for i, s in enumerate(served) if not by_id[s["q"]]["hard"]]
            core = [i for i, s in enumerate(served) if by_id[s["q"]]["hard"]]
            cases = [((), True), (core[:1], False), (core[:2], False)]
            if soft:
                cases.append((soft[:1], True))
            if len(soft) >= 2:
                cases.append((soft[:2], False))
            for wrong, expect in cases:
                ans = [{"question_id": f"k{i + 1}", "choice": (r + 1) % 4 if i in wrong else r} for i, r in enumerate(right)]
                self.assertEqual(academy._grade_served("N02-01", served, ans)[1], expect, (wrong, served))
                pq = {s["q"]: Fraction(0 if i in wrong else 1) for i, s in enumerate(served)}
                self.assertEqual(_pass_prob_on(bank, frozenset(pq), pq), Fraction(int(expect)))
        self.assertEqual(_exact_pass("N02-01", {q["id"]: Fraction(1) for q in bank}), 1)
        self.assertEqual(_exact_pass("N02-01", {q["id"]: Fraction(0) for q in bank}), 0)

    def test_length_and_random_strategies(self):
        for node in _checked("mc_length"):
            check_mc_length(self, node)

    def test_opening_strategies(self):
        for node in _checked("mc_opening"):
            check_mc_opening(self, node)


def _checked(check: str) -> list[str]:
    return [n for n in BANKS_30 if (check, n) not in FOUNDER_XFAIL]


def check_length_rank(tc: unittest.TestCase, nid: str) -> None:
    ranks = []
    for q in academy.QUESTIONS[nid]:
        lens = [len(c) for c in q["choices"]]
        tc.assertEqual(len(set(lens)), 4, q["id"])  # no ties
        ranks.append(sorted(lens, reverse=True).index(lens[q["answer"]]))
    tc.assertEqual([ranks.count(r) for r in range(4)], [3, 3, 3, 3], nid)


def check_opening(tc: unittest.TestCase, nid: str) -> None:
    right = Counter(sorted(_openings(q["choices"][q["answer"]]), key=len)[0] for q in academy.QUESTIONS[nid])
    tc.assertLessEqual(max(right.values()), 1, (nid, right.most_common(3)))


def check_grounding(tc: unittest.TestCase, nid: str) -> None:
    body = _body(nid)
    tc.assertGreater(len(body), 1500, nid)  # a full lesson, not a stub
    tc.assertEqual(len(GROUNDING[nid]), 12, nid)
    for phrase in GROUNDING[nid]:
        tc.assertIn(phrase, body, (nid, phrase))


# Exact guessing rates (PR #249 r2). Logic adapted from the reviewer's reference
# /workspace/rev249/exact.py (PR #249 review, 2026-10-03): the distribution of the question SET drawn by
# academy._draw (KUAT_MIN_HARD core sampled first, the rest from all remaining questions), then per set a
# DP over "question answered right" with every core question forced right and ≥ ceil(threshold × k)
# right overall (academy._grade_served). A strategy is a per-question probability of picking the right
# option; option order does not matter (it only looks at the texts), ties are broken uniformly at random.
# Fractions → exact and deterministic; the bar is the same 2 %.
BAR = Fraction(1, 50)
_DIST_CACHE: dict[str, dict] = {}


def _draw_dist(node: str) -> dict:
    if node not in _DIST_CACHE:
        bank = academy.QUESTIONS[node]
        hard = [q["id"] for q in bank if q["hard"]]
        ids = [q["id"] for q in bank]
        k = min(academy.KUAT_DRAW, len(bank))
        nh = min(academy.KUAT_MIN_HARD, len(hard), k)
        dist: Counter = Counter()
        for h in itertools.combinations(hard, nh):
            rest = [i for i in ids if i not in h]
            w = Fraction(1, comb(len(hard), nh) * comb(len(rest), k - nh))
            for r in itertools.combinations(rest, k - nh):
                dist[frozenset(h + r)] += w
        _DIST_CACHE[node] = dict(dist)
    return _DIST_CACHE[node]


def _pass_prob_on(bank, served: frozenset, pq: dict) -> Fraction:
    hard = {q["id"] for q in bank if q["hard"]}
    need = ceil(academy.KUAT_PASS_THRESHOLD * len(served) - 1e-9)
    dp = {0: Fraction(1)}
    for qid in served:
        p, nd = Fraction(pq[qid]), Counter()
        for c, v in dp.items():
            nd[c + 1] += v * p
            if qid not in hard:
                nd[c] += v * (1 - p)
        dp = nd
    return sum((v for c, v in dp.items() if c >= need), Fraction(0))


def _exact_pass(node: str, pq: dict) -> Fraction:
    bank = academy.QUESTIONS[node]
    return sum((w * _pass_prob_on(bank, s, pq) for s, w in _draw_dist(node).items()), Fraction(0))


def _length_pq(bank, kind: str) -> dict:
    out = {}
    for q in bank:
        lens = [len(c) for c in q["choices"]]
        if kind == "random":
            out[q["id"]] = Fraction(1, len(lens))
            continue
        # sorted(range(n), key=(len, random tie-break)) → every tie order equally likely
        hits = total = 0
        for tie in itertools.permutations(range(len(lens))):
            order = sorted(range(len(lens)), key=lambda i: (lens[i], tie[i]))
            pick = {"longest": order[-1], "shortest": order[0], "middle": order[len(order) // 2]}[kind]
            hits += pick == q["answer"]
            total += 1
        out[q["id"]] = Fraction(hits, total)
    return out


def _opening_strategies(bank) -> list[tuple[str, dict]]:
    total, wrong = Counter(), Counter()
    for q in bank:
        for i, c in enumerate(q["choices"]):
            for p in _openings(c):
                total[p] += 1
                wrong[p] += i != q["answer"]
    repeated = [p for p, n in total.items() if n >= 2]
    never_right = {p for p in repeated if wrong[p] == total[p]}

    def pq(keep):
        out = {}
        for q in bank:
            el = [i for i, c in enumerate(q["choices"]) if keep(c)] or list(range(len(q["choices"])))
            out[q["id"]] = Fraction(1, len(el)) if q["answer"] in el else Fraction(0)
        return out

    strategies = [(f"pick {p}", pq(lambda c, p=p: p in _openings(c))) for p in repeated]
    strategies += [(f"avoid {p}", pq(lambda c, p=p: p not in _openings(c))) for p in repeated]
    strategies.append(("avoid never-right", pq(lambda c: not (_openings(c) & never_right))))
    return strategies


def exact_rates(node: str) -> dict[str, Fraction]:
    bank = academy.QUESTIONS[node]
    rates = {s: _exact_pass(node, _length_pq(bank, s)) for s in ("longest", "shortest", "middle", "random")}
    rates.update({name: _exact_pass(node, pq) for name, pq in _opening_strategies(bank)})
    return rates


def check_mc_length(tc: unittest.TestCase, node: str) -> None:
    bank = academy.QUESTIONS[node]
    for s in ("longest", "shortest", "middle", "random"):
        rate = _exact_pass(node, _length_pq(bank, s))
        tc.assertLessEqual(rate, BAR, (node, s, float(rate)))


def check_mc_opening(tc: unittest.TestCase, node: str) -> None:
    for name, pq in _opening_strategies(academy.QUESTIONS[node]):
        rate = _exact_pass(node, pq)
        tc.assertLessEqual(rate, BAR, (node, name, float(rate)))


_CHECKS = {"length_rank": check_length_rank, "opening": check_opening, "grounding": check_grounding,
           "mc_length": check_mc_length, "mc_opening": check_mc_opening}


class TestFounderGaps(unittest.TestCase):
    """One xfail per (check, node) the Founder wording still misses (FOUNDER_XFAIL)."""


def _gap_test(check, node):
    def t(self):
        _CHECKS[check](self, node)
    return pytest.mark.xfail(strict=check != "mc_opening",  # mc_opening: strict after v1.4 (PR #249 r2)
                             reason=f"Founder {node} {check}: {FOUNDER_XFAIL[(check, node)]}")(t)


for (_check, _node) in FOUNDER_XFAIL:
    setattr(TestFounderGaps, f"test_{_check}_{_node.replace('-', '_')}", _gap_test(_check, _node))


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
