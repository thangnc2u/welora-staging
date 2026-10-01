"""Welorademy M01 Rễ Cục + M02 An Toàn + M03 Tự Do + M04 Bền Vững & Di Sản + M05 Kết Nối & Thực Hành — cây ngữ nghĩa + cổng KUAT."""

from __future__ import annotations

import json
import math
import random
import re
from datetime import datetime, timezone
from typing import Any, Optional

KUAT_PASS_THRESHOLD = 0.70
MODULE_ID = "M02"
MODULE_TITLE = "An Toàn Tài Chính"
M01_MODULE_ID = "M01"
M01_MODULE_TITLE = "Rễ Cục"
M03_MODULE_ID = "M03"
M03_MODULE_TITLE = "Tự Do Tài Chính"
M04_MODULE_ID = "M04"
M04_MODULE_TITLE = "Bền Vững & Di Sản"
M05_MODULE_ID = "M05"
M05_MODULE_TITLE = "Kết Nối & Thực Hành"
XP_PER_PASS = 20
GATE_NODE = "N02-02"
MASTERY_NODE = "no_efund_invest"

STATUS_LOCKED = "locked"
STATUS_AVAILABLE = "available"
STATUS_LEARNING = "learning"
STATUS_KUAT_PENDING = "kuat_pending"
STATUS_MASTERED = "mastered"

MODULES: list[dict[str, Any]] = [
    {"module_id": M01_MODULE_ID, "title": M01_MODULE_TITLE, "order": 1},
    {"module_id": MODULE_ID, "title": MODULE_TITLE, "order": 2},
    {"module_id": M03_MODULE_ID, "title": M03_MODULE_TITLE, "order": 3},
    {"module_id": M04_MODULE_ID, "title": M04_MODULE_TITLE, "order": 4},
    {"module_id": M05_MODULE_ID, "title": M05_MODULE_TITLE, "order": 5},
]

M01_NODES: list[dict[str, Any]] = [
    {
        "node_id": "N01-01",
        "module_id": M01_MODULE_ID,
        "module_title": M01_MODULE_TITLE,
        "title": "Xây dựng tư duy về tiền",
        "lesson_id": "WA-01-01",
        "principle_key": "MIND-01",
        "core_map": ["CORE-01"],
        "prereq_node_ids": [],
        "order": 1,
    },
    {
        "node_id": "N01-02",
        "module_id": M01_MODULE_ID,
        "module_title": M01_MODULE_TITLE,
        "title": "Hiểu dòng tiền – Thu nhập và chi tiêu",
        "lesson_id": "WA-01-02",
        "principle_key": "FLOW-01",
        "core_map": ["CORE-03"],
        "prereq_node_ids": ["N01-01"],
        "order": 2,
    },
    {
        "node_id": "N01-03",
        "module_id": M01_MODULE_ID,
        "module_title": M01_MODULE_TITLE,
        "title": "Lập ngân sách cơ bản",
        "lesson_id": "WA-01-03",
        "principle_key": "BUDG-01",
        "core_map": ["CORE-03"],
        "prereq_node_ids": ["N01-02"],
        "order": 3,
    },
    {
        "node_id": "N01-04",
        "module_id": M01_MODULE_ID,
        "module_title": M01_MODULE_TITLE,
        "title": "Áp dụng quy tắc 50/30/20",
        "lesson_id": "WA-01-04",
        "principle_key": "BUDG-02",
        "core_map": ["CORE-03"],
        "prereq_node_ids": ["N01-03"],
        "order": 4,
    },
    {
        "node_id": "N01-05",
        "module_id": M01_MODULE_ID,
        "module_title": M01_MODULE_TITLE,
        "title": "Theo dõi chi tiêu hiệu quả",
        "lesson_id": "WA-01-05",
        "principle_key": "TRACK-01",
        "core_map": ["CORE-03"],
        "prereq_node_ids": ["N01-04"],
        "order": 5,
    },
    {
        "node_id": "N01-06",
        "module_id": M01_MODULE_ID,
        "module_title": M01_MODULE_TITLE,
        "title": "Đặt mục tiêu tài chính đúng cách",
        "lesson_id": "WA-01-06",
        "principle_key": "GOAL-01",
        "core_map": ["CORE-05"],
        "prereq_node_ids": ["N01-05"],
        "order": 6,
    },
    {
        "node_id": "N01-07",
        "module_id": M01_MODULE_ID,
        "module_title": M01_MODULE_TITLE,
        "title": "Hiểu lãi kép và giá trị thời gian của tiền",
        "lesson_id": "WA-01-07",
        "principle_key": "TIME-01",
        "core_map": ["CORE-01"],
        "prereq_node_ids": ["N01-06"],
        "order": 7,
    },
]

M02_NODES: list[dict[str, Any]] = [
    {
        "node_id": "N02-01",
        "module_id": MODULE_ID,
        "module_title": MODULE_TITLE,
        "title": "Xây dựng quỹ khẩn cấp",
        "lesson_id": "WA-02-01",
        "principle_key": "SAFE-01",
        "core_map": ["CORE-03", "CORE-07"],
        "prereq_node_ids": [],
        "order": 1,
    },
    {
        "node_id": "N02-02",
        "module_id": MODULE_ID,
        "module_title": MODULE_TITLE,
        "title": "Nguyên tắc sử dụng quỹ",
        "lesson_id": "WA-02-02",
        "principle_key": "SAFE-02",
        "core_map": ["CORE-07", "CORE-05"],
        "prereq_node_ids": ["N02-01"],
        "order": 2,
    },
    {
        "node_id": "N02-03",
        "module_id": MODULE_ID,
        "module_title": MODULE_TITLE,
        "title": "Nơi giữ quỹ",
        "lesson_id": "WA-02-03",
        "principle_key": "SAFE-03",
        "core_map": ["CORE-03", "CORE-07"],
        "prereq_node_ids": ["N02-02"],
        "order": 3,
    },
    {
        "node_id": "N02-05",
        "module_id": MODULE_ID,
        "module_title": MODULE_TITLE,
        "title": "Nhận diện nợ tốt/xấu",
        "lesson_id": "WA-02-05",
        "principle_key": "DEBT-01",
        "core_map": ["CORE-07"],
        "prereq_node_ids": ["N02-03"],
        "order": 4,
    },
    {
        "node_id": "N02-04",
        "module_id": MODULE_ID,
        "module_title": MODULE_TITLE,
        "title": "Chọn phương pháp trả nợ",
        "lesson_id": "WA-02-04",
        "principle_key": "DEBT-02",
        "core_map": ["CORE-07"],
        "prereq_node_ids": ["N02-05"],
        "order": 5,
    },
    {
        "node_id": "N02-06",
        "module_id": MODULE_ID,
        "module_title": MODULE_TITLE,
        "title": "Lập kế hoạch trả nợ",
        "lesson_id": "WA-02-06",
        "principle_key": "DEBT-02",
        "core_map": ["CORE-03", "CORE-07"],
        "prereq_node_ids": ["N02-04"],
        "order": 6,
    },
    {
        "node_id": "N02-07",
        "module_id": MODULE_ID,
        "module_title": MODULE_TITLE,
        "title": "Ưu tiên trả nợ vs đầu tư",
        "lesson_id": "WA-02-07",
        "principle_key": "DEBT-03",
        "core_map": ["CORE-07", "CORE-01"],
        "prereq_node_ids": ["N02-06"],
        "order": 7,
    },
]


M03_NODES: list[dict[str, Any]] = [
    {
        "node_id": "N03-01",
        "module_id": M03_MODULE_ID,
        "module_title": M03_MODULE_TITLE,
        "title": "Hiểu tự do tài chính",
        "lesson_id": "WA-03-01",
        "principle_key": "FREE-01",
        "core_map": ["CORE-01", "CORE-05"],
        "prereq_node_ids": [],
        "order": 1,
    },
    {
        "node_id": "N03-02",
        "module_id": M03_MODULE_ID,
        "module_title": M03_MODULE_TITLE,
        "title": "Phân biệt tài sản và nợ",
        "lesson_id": "WA-03-02",
        "principle_key": "ASSET-01",
        "core_map": ["CORE-01", "CORE-03"],
        "prereq_node_ids": ["N03-01"],
        "order": 2,
    },
    {
        "node_id": "N03-03",
        "module_id": M03_MODULE_ID,
        "module_title": M03_MODULE_TITLE,
        "title": "Hiểu thu nhập thụ động",
        "lesson_id": "WA-03-03",
        "principle_key": "PASSIVE-01",
        "core_map": ["CORE-01", "CORE-05"],
        "prereq_node_ids": ["N03-02"],
        "order": 3,
    },
    {
        "node_id": "N03-04",
        "module_id": M03_MODULE_ID,
        "module_title": M03_MODULE_TITLE,
        "title": "Nguyên tắc đầu tư cơ bản",
        "lesson_id": "WA-03-04",
        "principle_key": "INV-01",
        "core_map": ["CORE-01", "CORE-07"],
        "prereq_node_ids": ["N03-03"],
        "order": 4,
    },
    {
        "node_id": "N03-05",
        "module_id": M03_MODULE_ID,
        "module_title": M03_MODULE_TITLE,
        "title": "Đa dạng hóa danh mục",
        "lesson_id": "WA-03-05",
        "principle_key": "DIV-01",
        "core_map": ["CORE-01", "CORE-07"],
        "prereq_node_ids": ["N03-04"],
        "order": 5,
    },
    {
        "node_id": "N03-06",
        "module_id": M03_MODULE_ID,
        "module_title": M03_MODULE_TITLE,
        "title": "Lập kế hoạch hướng tới tự do tài chính",
        "lesson_id": "WA-03-06",
        "principle_key": "FREE-PLAN-01",
        "core_map": ["CORE-05", "CORE-03"],
        "prereq_node_ids": ["N03-05"],
        "order": 6,
    },
    {
        "node_id": "N03-07",
        "module_id": M03_MODULE_ID,
        "module_title": M03_MODULE_TITLE,
        "title": "Nhận diện rủi ro khi theo đuổi tự do tài chính",
        "lesson_id": "WA-03-07",
        "principle_key": "FREE-RISK-01",
        "core_map": ["CORE-07", "CORE-01"],
        "prereq_node_ids": ["N03-06"],
        "order": 7,
    },
]


M04_NODES: list[dict[str, Any]] = [
    {
        "node_id": "N04-01",
        "module_id": M04_MODULE_ID,
        "module_title": M04_MODULE_TITLE,
        "title": "Hiểu bền vững tài chính",
        "lesson_id": "WA-04-01",
        "principle_key": "SUSTAIN-01",
        "core_map": ["CORE-01", "CORE-10"],
        "prereq_node_ids": [],
        "order": 1,
    },
    {
        "node_id": "N04-02",
        "module_id": M04_MODULE_ID,
        "module_title": M04_MODULE_TITLE,
        "title": "Bảo hiểm và quản lý rủi ro",
        "lesson_id": "WA-04-02",
        "principle_key": "INSURE-01",
        "core_map": ["CORE-07", "CORE-10"],
        "prereq_node_ids": ["N04-01"],
        "order": 2,
    },
    {
        "node_id": "N04-03",
        "module_id": M04_MODULE_ID,
        "module_title": M04_MODULE_TITLE,
        "title": "Chuẩn bị tài chính cho tuổi già",
        "lesson_id": "WA-04-03",
        "principle_key": "RETIRE-01",
        "core_map": ["CORE-05", "CORE-10"],
        "prereq_node_ids": ["N04-02"],
        "order": 3,
    },
    {
        "node_id": "N04-04",
        "module_id": M04_MODULE_ID,
        "module_title": M04_MODULE_TITLE,
        "title": "Dạy con về tiền bạc",
        "lesson_id": "WA-04-04",
        "principle_key": "KIDS-01",
        "core_map": ["CORE-01", "CORE-10"],
        "prereq_node_ids": ["N04-03"],
        "order": 4,
    },
    {
        "node_id": "N04-05",
        "module_id": M04_MODULE_ID,
        "module_title": M04_MODULE_TITLE,
        "title": "Di sản và thừa kế cơ bản",
        "lesson_id": "WA-04-05",
        "principle_key": "LEGACY-01",
        "core_map": ["CORE-10"],
        "prereq_node_ids": ["N04-04"],
        "order": 5,
    },
    {
        "node_id": "N04-06",
        "module_id": M04_MODULE_ID,
        "module_title": M04_MODULE_TITLE,
        "title": "Di sản phi tài chính",
        "lesson_id": "WA-04-06",
        "principle_key": "LEGACY-SOFT-01",
        "core_map": ["CORE-10", "CORE-01"],
        "prereq_node_ids": ["N04-05"],
        "order": 6,
    },
    {
        "node_id": "N04-07",
        "module_id": M04_MODULE_ID,
        "module_title": M04_MODULE_TITLE,
        "title": "Cân bằng tích lũy và chất lượng sống",
        "lesson_id": "WA-04-07",
        "principle_key": "BALANCE-01",
        "core_map": ["CORE-10", "CORE-05"],
        "prereq_node_ids": ["N04-06"],
        "order": 7,
    },
]


M05_NODES: list[dict[str, Any]] = [
    {
        "node_id": "N05-01",
        "module_id": M05_MODULE_ID,
        "module_title": M05_MODULE_TITLE,
        "title": "Chuyển kiến thức thành hành động",
        "lesson_id": "WA-05-01",
        "principle_key": "ACT-01",
        "core_map": ["CORE-01", "CORE-10"],
        "prereq_node_ids": [],
        "order": 1,
    },
    {
        "node_id": "N05-02",
        "module_id": M05_MODULE_ID,
        "module_title": M05_MODULE_TITLE,
        "title": "Xây dựng thói quen tài chính",
        "lesson_id": "WA-05-02",
        "principle_key": "HABIT-01",
        "core_map": ["CORE-01", "CORE-10"],
        "prereq_node_ids": ["N05-01"],
        "order": 2,
    },
    {
        "node_id": "N05-03",
        "module_id": M05_MODULE_ID,
        "module_title": M05_MODULE_TITLE,
        "title": "Theo dõi và điều chỉnh kế hoạch",
        "lesson_id": "WA-05-03",
        "principle_key": "ADJUST-01",
        "core_map": ["CORE-05", "CORE-10"],
        "prereq_node_ids": ["N05-02"],
        "order": 3,
    },
    {
        "node_id": "N05-04",
        "module_id": M05_MODULE_ID,
        "module_title": M05_MODULE_TITLE,
        "title": "Ra quyết định tài chính hàng ngày",
        "lesson_id": "WA-05-04",
        "principle_key": "DECIDE-01",
        "core_map": ["CORE-01", "CORE-07"],
        "prereq_node_ids": ["N05-03"],
        "order": 4,
    },
    {
        "node_id": "N05-05",
        "module_id": M05_MODULE_ID,
        "module_title": M05_MODULE_TITLE,
        "title": "Cộng đồng và học hỏi cùng nhau",
        "lesson_id": "WA-05-05",
        "principle_key": "PEER-01",
        "core_map": ["CORE-01", "CORE-10"],
        "prereq_node_ids": ["N05-04"],
        "order": 5,
    },
    {
        "node_id": "N05-06",
        "module_id": M05_MODULE_ID,
        "module_title": M05_MODULE_TITLE,
        "title": "Sử dụng công cụ và hệ thống hỗ trợ",
        "lesson_id": "WA-05-06",
        "principle_key": "TOOLS-01",
        "core_map": ["CORE-10"],
        "prereq_node_ids": ["N05-05"],
        "order": 6,
    },
    {
        "node_id": "N05-07",
        "module_id": M05_MODULE_ID,
        "module_title": M05_MODULE_TITLE,
        "title": "Duy trì động lực dài hạn",
        "lesson_id": "WA-05-07",
        "principle_key": "DRIVE-01",
        "core_map": ["CORE-10", "CORE-01"],
        "prereq_node_ids": ["N05-06"],
        "order": 7,
    },
]

NODES: list[dict[str, Any]] = M01_NODES + M02_NODES + M03_NODES + M04_NODES + M05_NODES

_NODE_BY_ID = {n["node_id"]: n for n in NODES}

FUND_NODES = ("N02-01", "N02-02", "N02-03")
DEBT_NODES = ("N02-04", "N02-05", "N02-06", "N02-07")
M01_NODE_IDS = tuple(n["node_id"] for n in M01_NODES)
M03_NODE_IDS = tuple(n["node_id"] for n in M03_NODES)
M04_NODE_IDS = tuple(n["node_id"] for n in M04_NODES)
M05_NODE_IDS = tuple(n["node_id"] for n in M05_NODES)
BADGE_RE_CUC = "Rễ Cục"
BADGE_TU_DO = "Tự Do Tài Chính"
BADGE_BEN_VUNG = "Bền Vững & Di Sản"
BADGE_KET_NOI = "Kết Nối & Thực Hành"

def nodes_for_principle(key: str) -> list[str]:
    """Map principle_key / CORE code → node_id trên cây M02."""
    needle = (key or "").strip().upper()
    if not needle:
        return []
    out: list[str] = []
    for n in NODES:
        keys = [str(n.get("principle_key") or "")] + [str(c) for c in (n.get("core_map") or [])]
        if needle in keys:
            out.append(n["node_id"])
    return out


def os_nudge_for(node_id: str, *, first_pass: bool = True) -> dict[str, Any] | None:
    """Nudge WeloraOS Goal chỉ khi KUAT ĐẠT lần đầu. Không auto-create."""
    if not first_pass or node_id not in _NODE_BY_ID:
        return None
    n = _NODE_BY_ID[node_id]
    if node_id in FUND_NODES:
        goal_type = "emergency_fund"
        reason = "Đã thành thạo node quỹ — tạo Goal quỹ khẩn cấp trên WeloraOS."
    elif node_id in DEBT_NODES:
        goal_type = "debt_payoff"
        reason = "Đã thành thạo node nợ — tạo Goal trả nợ trên WeloraOS."
    else:
        return None
    return {
        "kind": "create_goal",
        "goal_type": goal_type,
        "href": "/app/goals",
        "reason": reason,
        "principle_key": n["principle_key"],
        "node_id": node_id,
    }


QUESTIONS: dict[str, list[dict[str, Any]]] = {
    "N01-01": [
        {"id": "q101a", "prompt": "Bước đầu phù hợp để điều chỉnh tư duy về tiền?", "choices": ["Ép tiêu nhiều hơn", "Nhận diện niềm tin đang chi phối rồi đặt quy tắc", "Rút hết tiết kiệm để đầu tư mạo hiểm"], "answer": 1, "hard": True},
        {"id": "q101b", "prompt": "Tư duy về tiền giống gì nhất?", "choices": ["Bản đồ trong đầu hướng dẫn quyết định", "Số dư tài khoản", "Lời khuyên trên mạng xã hội"], "answer": 0, "hard": False},
        {"id": "q101c", "prompt": "Thay đổi tư duy bắt đầu từ đâu?", "choices": ["Ép buộc nghĩ tích cực", "Nhận diện rồi điều chỉnh có chủ đích"], "answer": 1, "hard": False},
    ],
    "N01-02": [
        {"id": "q102a", "prompt": "Trước khi kiếm thêm thu nhập vì 'hết tiền', nên làm gì?", "choices": ["Ngay lập tức tăng ca", "Liệt kê chi tiêu thực tế rồi so với thu nhập", "Cắt hết giải trí ngay"], "answer": 1, "hard": True},
        {"id": "q102b", "prompt": "Dòng tiền là gì?", "choices": ["Thu nhập vào và chi tiêu ra theo thời gian", "Chỉ số dư cuối tháng", "Giá cổ phiếu"], "answer": 0, "hard": False},
        {"id": "q102c", "prompt": "Không theo dõi chi nhỏ có thể dẫn tới?", "choices": ["An toàn hơn", "Thâm hụt mà không rõ vì sao"], "answer": 1, "hard": False},
    ],
    "N01-03": [
        {"id": "q103a", "prompt": "Lập ngân sách lần đầu nên bắt đầu thế nào?", "choices": ["Hơn 20 hạng mục chi tiết ngay", "Ghi chi tiêu 2–4 tuần rồi chia 3 nhóm lớn", "Ép khớp 50/30/20 từ ngày đầu"], "answer": 1, "hard": True},
        {"id": "q103b", "prompt": "Ba nhóm ngân sách cơ bản thường là?", "choices": ["Thiết yếu – linh hoạt – cho tương lai", "Crypto – vàng – bất động sản", "Lương – thưởng – nợ"], "answer": 0, "hard": False},
        {"id": "q103c", "prompt": "Ngân sách quá chi tiết dễ dẫn tới?", "choices": ["Duy trì lâu hơn", "Bỏ cuộc sớm"], "answer": 1, "hard": False},
    ],
    "N01-04": [
        {"id": "q104a", "prompt": "Khi chi thiết yếu >50%, hướng điều chỉnh hợp lý?", "choices": ["Ép cắt thiết yếu ngay dù cần thiết", "Giữ thiết yếu thật, giảm linh hoạt để tăng phần tương lai", "Bỏ quy tắc 50/30/20"], "answer": 1, "hard": True},
        {"id": "q104b", "prompt": "Quy tắc 50/30/20 là gì?", "choices": ["La bàn phân bổ thiết yếu/linh hoạt/tương lai", "Công thức lãi suất ngân hàng", "Luật thuế bắt buộc"], "answer": 0, "hard": False},
        {"id": "q104c", "prompt": "50/30/20 nên hiểu như?", "choices": ["Xiềng xích cứng nhắc", "La bàn linh hoạt theo hoàn cảnh"], "answer": 1, "hard": False},
    ],
    "N01-05": [
        {"id": "q105a", "prompt": "Cách theo dõi chi tiêu bền vững khi hay quên?", "choices": ["Ép ghi mọi giao dịch ngay trong ngày", "Ít nhóm, ghi cuối ngày/tuần, xem số liệu không phải lời phê", "Chỉ theo dõi chi lớn"], "answer": 1, "hard": True},
        {"id": "q105b", "prompt": "Theo dõi chi tiêu giúp gì?", "choices": ["Có dữ liệu để cải thiện có chủ đích", "Tự động tăng lương", "Thay quỹ khẩn cấp"], "answer": 0, "hard": False},
        {"id": "q105c", "prompt": "Bỏ qua khoản nhỏ khi theo dõi?", "choices": ["Ổn vì không đáng kể", "Dễ bỏ sót khoản tích tụ thành lớn"], "answer": 1, "hard": False},
    ],
    "N01-06": [
        {"id": "q106a", "prompt": "Biến 'muốn tiết kiệm nhiều hơn' thành mục tiêu hành động?", "choices": ["Giữ chung chung", "Gắn số tiền, thời hạn, chia mốc hàng tháng", "Đặt ngay mục tiêu 1 tỷ / 2 năm"], "answer": 1, "hard": True},
        {"id": "q106b", "prompt": "Mục tiêu tài chính tốt cần?", "choices": ["Cụ thể, số tiền, thời hạn", "Chỉ cảm xúc", "Chờ lương tăng mới đặt"], "answer": 0, "hard": False},
        {"id": "q106c", "prompt": "Mục tiêu mơ hồ thường dẫn tới?", "choices": ["Hành động nhất quán", "Khó duy trì kỷ luật"], "answer": 1, "hard": False},
    ],
    "N01-07": [
        {"id": "q107a", "prompt": "Bắt đầu để dành sớm với số nhỏ hơn vs đợi 5 năm để nhiều hơn?", "choices": ["Đợi chắc chắn tốt hơn", "Bắt đầu sớm thường có lợi nhờ thời gian / lãi kép", "Hai phương án luôn như nhau"], "answer": 1, "hard": True},
        {"id": "q107b", "prompt": "Lãi kép là gì?", "choices": ["Lãi được tái đầu tư và tiếp tục sinh lãi", "Chỉ lãi suất vay ngân hàng", "Phí giao dịch"], "answer": 0, "hard": False},
        {"id": "q107c", "prompt": "Giá trị thời gian của tiền nói lên điều gì?", "choices": ["Tiền hôm nay có thể sinh sôi theo thời gian", "Tiền không đổi giá trị theo năm"], "answer": 0, "hard": False},
    ],
    "N02-01": [
        # GP P0b r2 — mỗi câu 4 lựa chọn, độ dài cân bằng (đáp án đúng dài nhất / nhì / ba / ngắn nhất
        # chia đều ~3 câu mỗi loại) — mọi câu trả lời được bằng nội dung bài WA-02-01.
        {"id": "q01a", "prompt": "Quỹ khẩn cấp dùng để làm gì?", "choices": ["Trả các khoản chi tiêu thường ngày trong tháng", "Làm khoản đệm khi mất thu nhập hoặc có sự cố bất ngờ", "Chờ sẵn để mua cổ phiếu khi thị trường giảm", "Dành dụm cho chuyến du lịch cuối năm"], "answer": 1, "hard": False},
        {"id": "q01b", "prompt": "Cổng An Toàn của Welora cần quỹ tối thiểu bao nhiêu tháng chi tiêu thiết yếu?", "choices": ["Một tháng", "Khoảng hai tháng", "Ba tháng", "Mười hai tháng"], "answer": 2, "hard": True},
        {"id": "q01c", "prompt": "Có nên dùng quỹ khẩn cấp để mua đồ đang giảm giá?", "choices": ["Có, miễn là tháng sau bù lại vào quỹ", "Không, mua sắm không phải sự cố bất ngờ", "Không, trừ khi món đó giảm hơn một nửa", "Có, vì mua lúc rẻ cũng là một cách tiết kiệm tiền"], "answer": 1, "hard": False},
        {"id": "q01d", "prompt": "Chi tiêu thiết yếu của bạn khoảng 15 triệu ₫ mỗi tháng. Quỹ tối thiểu để qua Cổng An Toàn là bao nhiêu?", "choices": ["15 triệu ₫ (đúng 1 tháng chi)", "30 triệu ₫", "45 triệu ₫ (15 × 3)", "150 triệu ₫"], "answer": 2, "hard": True},
        {"id": "q01e", "prompt": "Khoản nào nên tính vào chi tiêu thiết yếu khi đặt mục tiêu quỹ?", "choices": ["Du lịch và mua sắm mùa sale", "Số tiền bạn định đầu tư mỗi tháng", "Quà biếu và tiệc tùng theo sở thích", "Tiền nhà, ăn uống, điện nước, đi lại và học phí cần thiết"], "answer": 3, "hard": False},
        {"id": "q01f", "prompt": "Bắt đầu xây quỹ từ con số 0, cách nào dễ duy trì nhất?", "choices": ["Chờ có khoản thưởng lớn rồi gửi một lần cho đủ", "Tự động chuyển một khoản nhỏ ngay sau ngày nhận lương", "Cuối tháng còn dư bao nhiêu thì gửi bấy nhiêu, tháng nào hết thì thôi", "Vay người thân để có ngay đủ quỹ"], "answer": 1, "hard": False},
        {"id": "q01g", "prompt": "Vì sao nên để quỹ khẩn cấp ở một tài khoản riêng?", "choices": ["Để được hưởng lãi suất cao nhất có thể", "Để không lẫn với tiền tiêu và lỡ tay tiêu mất", "Vì quy định bắt buộc phải mở tài khoản riêng cho quỹ", "Để khi cần đầu tư thì rút ra cho nhanh, khỏi phải chờ"], "answer": 1, "hard": False},
        {"id": "q01h", "prompt": "Mục đích chính của quỹ khẩn cấp là gì?", "choices": ["Làm vốn đầu tư khi thị trường có cơ hội tốt, rồi nạp lại sau", "Sinh lời nhanh hơn gửi tiết kiệm ngân hàng thông thường", "Giúp bạn (và người phụ thuộc, nếu có) qua lúc có sự cố", "Để dành mua xe mới"], "answer": 2, "hard": True},
        {"id": "q01i", "prompt": "Bạn làm tự do, thu nhập lúc nhiều lúc ít, và quỹ vừa đủ 3 tháng chi thiết yếu. Bước tiếp theo hợp lý là gì?", "choices": ["Dừng góp, vì đã đủ mức của Cổng là xong", "Tiếp tục góp đều, hướng tới khoảng 6 tháng", "Rút bớt quỹ ra đầu tư cho sinh lời", "Chuyển toàn bộ quỹ sang tiêu dùng"], "answer": 1, "hard": True},
        {"id": "q01j", "prompt": "Nhà chỉ có một người tạo ra thu nhập chính. Mục tiêu quỹ khẩn cấp nên thế nào?", "choices": ["Chỉ cần nửa tháng là đủ", "Dày hơn 3 tháng", "Không cần quỹ, vì đã có người đi làm", "Đúng 3 tháng, không nên để dư thêm"], "answer": 1, "hard": False},
        {"id": "q01k", "prompt": "Đang xây quỹ thì có người rủ góp vốn «lời chắc 20% mỗi tháng». Bạn nên làm gì?", "choices": ["Rút quỹ góp ngay kẻo lỡ cơ hội", "Vay thêm tiền để góp được nhiều hơn", "Giữ nguyên quỹ", "Góp một nửa quỹ, nửa còn lại giữ phòng thân"], "answer": 2, "hard": True},
        {"id": "q01l", "prompt": "Quỹ chưa đủ 3 tháng chi tiêu thiết yếu thì Cổng An Toàn thế nào?", "choices": ["ĐẠT nếu điểm sức khỏe tài chính của bạn cao", "Chưa ĐẠT cho tới khi quỹ đủ 3 tháng", "Chưa ĐẠT, nhưng tự xác nhận là ổn thì mở", "ĐẠT khi quỹ được 2 tháng"], "answer": 1, "hard": True},
    ],
    "N02-02": [
        # GP P0b r2 — 4 lựa chọn, độ dài cân bằng; mọi câu trả lời được bằng nội dung bài WA-02-02.
        {"id": "q02a", "prompt": "Thấy cơ hội đầu tư ETF hấp dẫn, có được dùng quỹ khẩn cấp không?", "choices": ["Có, nếu chỉ dùng một phần nhỏ", "Không, cơ hội đầu tư không phải sự cố", "Không, trừ khi ETF đang giảm giá sâu", "Có, vì ETF phân tán rủi ro tốt hơn cổ phiếu riêng lẻ"], "answer": 1, "hard": True},
        {"id": "q02b", "prompt": "Quỹ khẩn cấp nên dùng khi nào?", "choices": ["Khi có cơ hội đầu tư tốt", "Khi mất việc, ốm đau hay sự cố bất ngờ", "Khi muốn đi du lịch", "Khi cửa hàng quen có đợt giảm giá lớn cuối năm"], "answer": 1, "hard": False},
        {"id": "q02c", "prompt": "Rút quỹ khẩn cấp để mua cổ phiếu thì sao?", "choices": ["Được, nếu chắc chắn có lời", "Không, đó là phá An Toàn", "Không, trừ khi giá đang giảm rất sâu", "Được, nếu bán ra trong một tháng rồi nạp lại"], "answer": 1, "hard": True},
        {"id": "q02d", "prompt": "Tình huống nào phù hợp để rút quỹ khẩn cấp?", "choices": ["Đặt cọc chuyến du lịch Tết", "Bị cắt giảm thu nhập đột ngột", "Mua điện thoại đời mới khi máy cũ vẫn dùng tốt", "Góp tiền mừng đám cưới đã biết lịch từ lâu"], "answer": 1, "hard": True},
        {"id": "q02e", "prompt": "Theo bài học, trước khi rút quỹ nên tự hỏi hai câu nào?", "choices": ["Bạn bè có làm vậy không, và có đang giảm giá không?", "Có bất ngờ không, và có cần thiết cho sinh hoạt hay đi làm không?", "Có lời không, và có nhanh không?", "Có ai cho vay không, và lãi vay có cao không?"], "answer": 1, "hard": False},
        {"id": "q02f", "prompt": "Đám cưới của bạn đã lên lịch từ năm ngoái. Nên chuẩn bị tiền thế nào?", "choices": ["Rút quỹ khẩn cấp vì cưới là việc hệ trọng", "Lập quỹ mục tiêu riêng và góp dần", "Vay nóng rồi trả dần", "Dùng quỹ khẩn cấp trước, sau cưới nạp lại sau"], "answer": 1, "hard": True},
        {"id": "q02g", "prompt": "Vừa rút quỹ để lo một ca nằm viện. Việc nên làm tiếp theo là gì?", "choices": ["Đầu tư phần còn lại để gỡ lại nhanh", "Nạp lại cho đủ 3 tháng trước khi nghĩ đến đầu tư", "Không cần nạp lại nữa", "Giữ nguyên mức quỹ hiện tại và mở quyền đầu tư như cũ"], "answer": 1, "hard": True},
        {"id": "q02h", "prompt": "Xe máy hỏng nặng, không đi làm được. Dùng quỹ khẩn cấp để sửa thì sao?", "choices": ["Không được, quỹ chỉ dùng khi mất việc", "Hợp lý, vì cần xe để đi làm", "Không nên, hãy vay nóng để giữ nguyên quỹ", "Chỉ được nếu sửa hết dưới một triệu đồng"], "answer": 1, "hard": False},
        {"id": "q02i", "prompt": "Tiền trong quỹ «nằm im» khiến bạn thấy tiếc. Cách nghĩ nào đúng?", "choices": ["Rút ra mua vàng cho khỏi phí", "Quỹ nằm yên là đang làm đúng việc của nó", "Chuyển hết sang chứng khoán để tiền sinh lời mỗi ngày", "Cho bạn bè vay lấy lãi để tiền khỏi nằm im"], "answer": 1, "hard": False},
        {"id": "q02j", "prompt": "Thị trường giảm mạnh, ai cũng bảo «bắt đáy». Quỹ khẩn cấp thì sao?", "choices": ["Dùng quỹ bắt đáy, có lời thì nạp lại", "Không đụng tới quỹ", "Không dùng hết, chỉ thử một ít", "Rút toàn bộ quỹ vì giá đang rẻ hiếm thấy"], "answer": 1, "hard": True},
        {"id": "q02k", "prompt": "Bạn biết trước sang năm phải đóng một khoản học phí lớn. Nên chuẩn bị thế nào?", "choices": ["Đến lúc đóng thì rút quỹ khẩn cấp", "Lập quỹ mục tiêu riêng, góp dần từ bây giờ", "Không cần chuẩn bị, đến đâu tính đến đó", "Vay thẻ tín dụng"], "answer": 1, "hard": False},
        {"id": "q02l", "prompt": "Điểm sức khỏe tài chính cao có thay được việc quỹ phải đủ 3 tháng không?", "choices": ["Có, điểm cao là đủ", "Không, Cổng không bị điểm số vượt qua", "Có, nếu điểm trên 80", "Không, trừ khi quỹ đã được 2 tháng"], "answer": 1, "hard": True},
    ],
    "N02-03": [
        {"id": "q03a", "prompt": "Nơi giữ quỹ khẩn cấp nên ưu tiên gì?", "choices": ["Lợi suất cao", "An toàn và rút được nhanh", "Tất tay crypto"], "answer": 1, "hard": True},
        {"id": "q03b", "prompt": "Có nên khoá quỹ khẩn cấp 5 năm để lấy lãi?", "choices": ["Có", "Không"], "answer": 1, "hard": False},
        {"id": "q03c", "prompt": "Quỹ khẩn cấp nên tách khỏi tiền tiêu hàng ngày?", "choices": ["Có", "Không cần"], "answer": 0, "hard": False},
    ],
    "N02-05": [
        {"id": "q05a", "prompt": "Nợ nguy hiểm thường là?", "choices": ["Nợ tiêu dùng lãi cao, không tạo tài sản", "Vay mua nhà ở trong khả năng"], "answer": 0, "hard": True},
        {"id": "q05b", "prompt": "Nợ tốt khác nợ xấu ở điểm nào?", "choices": ["Có tài sản / thu nhập tương ứng", "Lãi càng cao càng tốt"], "answer": 0, "hard": False},
        {"id": "q05c", "prompt": "Vay nóng để đầu tư là?", "choices": ["Chiến lược hay", "Nợ nguy hiểm"], "answer": 1, "hard": True},
    ],
    "N02-04": [
        {"id": "q04a", "prompt": "Hai phương pháp trả nợ phổ biến?", "choices": ["Snowball và Avalanche", "All-in và FOMO"], "answer": 0, "hard": False},
        {"id": "q04b", "prompt": "Chọn phương pháp xong rồi mới đầu tư tăng trưởng?", "choices": ["Có — phòng thủ trước", "Không cần"], "answer": 0, "hard": True},
        {"id": "q04c", "prompt": "Trả nợ nguy hiểm nên ưu tiên?", "choices": ["Đúng", "Sai, nên mua ETF trước"], "answer": 0, "hard": False},
    ],
    "N02-06": [
        {"id": "q06a", "prompt": "Kế hoạch trả nợ cần có?", "choices": ["Số dư, lãi, trả định kỳ", "Chỉ cảm xúc"], "answer": 0, "hard": False},
        {"id": "q06b", "prompt": "Có nên bỏ quỹ khẩn cấp để trả hết nợ lãi thấp ngay?", "choices": ["Luôn luôn", "Không — giữ lớp đệm"], "answer": 1, "hard": True},
        {"id": "q06c", "prompt": "Kế hoạch nên theo dõi tiến độ?", "choices": ["Có", "Không"], "answer": 0, "hard": False},
    ],
    "N02-07": [
        {"id": "q07a", "prompt": "Khi còn nợ nguy hiểm, ưu tiên?", "choices": ["All-in ETF", "Xử lý nợ + giữ An Toàn"], "answer": 1, "hard": True},
        {"id": "q07b", "prompt": "Đầu tư trước khi Cổng ĐẠT?", "choices": ["Được", "Không"], "answer": 1, "hard": True},
        {"id": "q07c", "prompt": "Ai chịu trách nhiệm quyết định cuối?", "choices": ["User", "Agent quyết thay"], "answer": 0, "hard": False},
    ],
    "N03-01": [
        {"id": "q301a", "prompt": "Tự do tài chính nên hiểu trước hết là gì?", "choices": ["Chỉ nghỉ hưu sớm và không làm gì nữa", "Tăng dần khả năng lựa chọn nhờ quan hệ lành mạnh giữa chi tiêu và tài sản", "All-in đầu tư để giàu nhanh"], "answer": 1, "hard": True},
        {"id": "q301b", "prompt": "Mức An toàn cơ bản (biết nổi) thường gồm gì?", "choices": ["Quỹ khẩn cấp, không nợ lãi rất cao, sống trong tầm thu nhập", "Chỉ sở hữu nhiều bất động sản", "Vay nóng để đầu tư"], "answer": 0, "hard": False},
        {"id": "q301c", "prompt": "Có bắt buộc phải là vận động viên 'bơi marathon' mới gọi là tự do tài chính?", "choices": ["Có — chỉ một định nghĩa đúng", "Không — có nhiều mức tự do"], "answer": 1, "hard": False},
    ],
    "N03-02": [
        {"id": "q302a", "prompt": "Câu hỏi đơn giản để phân loại tài sản vs trách nhiệm?", "choices": ["Giá mua ban đầu cao hay thấp", "Giữ thêm 1 năm thì túi tiền dày hơn hay mỏng hơn", "Bạn bè có thích không"], "answer": 1, "hard": True},
        {"id": "q302b", "prompt": "Máy 'bỏ tiền vào túi' gần với?", "choices": ["Tài sản tạo giá trị / dòng tiền", "Khoản vay tiêu dùng lãi cao", "Đồ mua sắm mất giá nhanh"], "answer": 0, "hard": False},
        {"id": "q302c", "prompt": "Một căn nhà vừa ở vừa cho thuê một phần?", "choices": ["Luôn chỉ là nợ", "Có thể mang cả đặc điểm tài sản và chi phí — nhìn tác động ròng"], "answer": 1, "hard": False},
    ],
    "N03-03": [
        {"id": "q303a", "prompt": "Thu nhập thụ động đúng nghĩa gần với?", "choices": ["Không bao giờ phải đụng vào hệ thống", "Giảm mức độ phải 'xách xô mỗi ngày', vẫn cần bảo trì", "Cam kết lãi cao không rủi ro"], "answer": 1, "hard": True},
        {"id": "q303b", "prompt": "Thang đo hữu ích hơn 'thụ động / không thụ động' là?", "choices": ["Mức độ phụ thuộc vào thời gian trực tiếp của bạn", "Số follower mạng xã hội", "Giá vàng hôm nay"], "answer": 0, "hard": False},
        {"id": "q303c", "prompt": "Lời hứa 'máy tưới vĩnh viễn, không bao giờ hỏng, tự đẻ thêm máy'?", "choices": ["Nên tin ngay", "Cần nghi ngờ"], "answer": 1, "hard": False},
    ],
    "N03-04": [
        {"id": "q304a", "prompt": "Trước khi all-in ETF / đầu tư tăng trưởng, điều kiện nền tảng nào đúng?", "choices": ["Được all-in ngay nếu thấy cơ hội", "An Toàn trước — không all-in trước khi Cổng ĐẠT / có lớp đệm", "Vay nóng để tăng vốn luôn đúng"], "answer": 1, "hard": True},
        {"id": "q304b", "prompt": "Nguyên tắc đầu tư cơ bản ưu tiên gì?", "choices": ["Chỉ dùng tiền chấp nhận biến động; hiểu sản phẩm; không đụng quỹ khẩn cấp", "Cam kết lãi cao không rủi ro", "Bỏ hết trứng vào một mã"], "answer": 0, "hard": False},
        {"id": "q304c", "prompt": "Chưa có quỹ khẩn cấp + còn nợ thẻ lãi cao, bạn quen rủ góp tiền 'lời mạnh 1–2 tháng'. Hướng hợp lý?", "choices": ["Góp hết vì cơ hội hiếm", "Ưu tiên An Toàn (quỹ + xử lý nợ lãi cao); chỉ đầu tư bằng tiền dài hạn sau khi hiểu rõ", "Vay thêm để vừa trả nợ vừa đầu tư"], "answer": 1, "hard": True},
    ],
    "N03-05": [
        {"id": "q305a", "prompt": "Đa dạng hóa danh mục nhằm?", "choices": ["All-in một mã để tối đa lời", "Giảm rủi ro tập trung — không bỏ tất cả vào một chỗ", "Bỏ qua An Toàn vì đã đa dạng"], "answer": 1, "hard": True},
        {"id": "q305b", "prompt": "Đa dạng hóa thay thế Cổng An Toàn?", "choices": ["Có — đủ để bỏ quỹ khẩn cấp", "Không — An Toàn vẫn trước"], "answer": 1, "hard": True},
        {"id": "q305c", "prompt": "Bỏ hết tiền vào một kênh vì 'chắc chắn lên'?", "choices": ["Chiến lược hay", "Rủi ro tập trung — trái đa dạng hóa"], "answer": 1, "hard": False},
    ],
    "N03-06": [
        {"id": "q306a", "prompt": "Kế hoạch hướng tới tự do tài chính nên bắt đầu từ đâu?", "choices": ["All-in ngay kênh lời cao", "Định mức sống chấp nhận được, đo khoảng cách, gắn mốc có An Toàn làm nền", "Chờ giàu rồi mới lập kế hoạch"], "answer": 1, "hard": True},
        {"id": "q306b", "prompt": "Kế hoạch tốt cần?", "choices": ["Mốc cụ thể, số liệu, thứ tự ưu tiên (An Toàn → rồi tăng trưởng)", "Chỉ cảm xúc FOMO", "Bỏ quỹ để tăng tốc"], "answer": 0, "hard": False},
        {"id": "q306c", "prompt": "Có nên bỏ lớp đệm An Toàn để 'tăng tốc' kế hoạch tự do?", "choices": ["Nên — nhanh hơn", "Không — giữ An Toàn làm nền"], "answer": 1, "hard": False},
    ],
    "N03-07": [
        {"id": "q307a", "prompt": "Rủi ro phổ biến khi theo đuổi tự do tài chính?", "choices": ["Giữ quỹ khẩn cấp quá lâu", "All-in / vay để đầu tư / bỏ An Toàn vì lời hứa giàu nhanh", "Học nguyên tắc trước khi đầu tư"], "answer": 1, "hard": True},
        {"id": "q307b", "prompt": "Khi thấy 'lãi cao + không rủi ro', nên?", "choices": ["Tin và all-in", "Dừng lại suy nghĩ — tín hiệu cảnh báo"], "answer": 1, "hard": True},
        {"id": "q307c", "prompt": "Ai chịu trách nhiệm quyết định cuối trên hành trình tự do tài chính?", "choices": ["User", "Agent quyết thay"], "answer": 0, "hard": False},
    ],
    "N04-01": [
        {"id": "q401a", "prompt": "Bền vững tài chính khác An Toàn / Tự Do ở điểm nào?", "choices": ["Chỉ là tên gọi khác của tự do sớm", "Nhìn thêm giai đoạn thu nhập giảm, rủi ro lớn và chuyển giao cho thế hệ sau", "Chỉ dành cho người đã giàu"], "answer": 1, "hard": True},
        {"id": "q401b", "prompt": "Ba trụ cột bền vững đơn giản gồm?", "choices": ["Bảo vệ – duy trì – chuyển giao", "All-in – FOMO – vay nóng", "Chỉ tích lũy tài sản"], "answer": 0, "hard": False},
        {"id": "q401c", "prompt": "Có thể bắt đầu bền vững khi chưa giàu?", "choices": ["Không — phải chờ giàu", "Có — bảo hiểm phù hợp, để dành nhỏ đều, trao đổi gia đình"], "answer": 1, "hard": False},
    ],
    "N04-02": [
        {"id": "q402a", "prompt": "Bảo hiểm nên hiểu trước hết là gì?", "choices": ["Cách làm giàu nhanh", "Công cụ quản lý rủi ro lớn — lớp bảo vệ, không thay An Toàn / quỹ khẩn cấp", "Sản phẩm bắt buộc phải mua hết mọi gói"], "answer": 1, "hard": True},
        {"id": "q402b", "prompt": "Trước khi mua thêm bảo hiểm phức tạp, nên ưu tiên?", "choices": ["An Toàn (quỹ khẩn cấp) + hiểu rủi ro thật sự cần bảo vệ", "All-in gói lời cao do tư vấn", "Bỏ quỹ để trả phí bảo hiểm"], "answer": 0, "hard": True},
        {"id": "q402c", "prompt": "Bảo hiểm thay thế quỹ khẩn cấp?", "choices": ["Có — đủ rồi", "Không — An Toàn vẫn cần lớp đệm riêng"], "answer": 1, "hard": False},
    ],
    "N04-03": [
        {"id": "q403a", "prompt": "Chuẩn bị tài chính tuổi già nên bắt đầu thế nào?", "choices": ["Đợi giàu rồi mới nghĩ", "Để dành đều đặn sớm, giữ An Toàn làm nền, tránh all-in vì 'đuổi kịp hưu trí'", "Vay nóng để đầu tư hưu trí"], "answer": 1, "hard": True},
        {"id": "q403b", "prompt": "Khi chưa có quỹ khẩn cấp, ưu tiên hưu trí thế nào?", "choices": ["Bỏ An Toàn để đóng hết vào hưu trí", "Giữ An Toàn trước; đóng góp hưu trí vừa sức bằng tiền dài hạn", "All-in cổ phiếu để bù nhanh"], "answer": 1, "hard": True},
        {"id": "q403c", "prompt": "Mục tiêu chuẩn bị tuổi già hữu ích cần?", "choices": ["Số tiền / mức sống chấp nhận được + thời hạn + kỷ luật đều", "Chỉ cảm xúc sợ già", "Chờ lương tăng gấp đôi"], "answer": 0, "hard": False},
    ],
    "N04-04": [
        {"id": "q404a", "prompt": "Dạy con về tiền nên bắt đầu từ đâu?", "choices": ["Chỉ đưa tiền khi xin, không giải thích", "Theo độ tuổi: chi tiêu – tiết kiệm – chia sẻ có chủ đích", "Ép con all-in đầu tư sớm"], "answer": 1, "hard": True},
        {"id": "q404b", "prompt": "Mục tiêu dạy con về tiền là?", "choices": ["Truyền thói quen và giá trị, không chỉ số dư", "Khiến con giàu nhanh hơn bố mẹ", "Giấu hoàn toàn chuyện tiền bạc"], "answer": 0, "hard": False},
        {"id": "q404c", "prompt": "Cho con tiêu không giới hạn để 'học hỏi'?", "choices": ["Ổn — tự học được", "Không — cần khung rõ ràng và trò chuyện"], "answer": 1, "hard": False},
    ],
    "N04-05": [
        {"id": "q405a", "prompt": "Di sản / thừa kế cơ bản nên bắt đầu bằng gì?", "choices": ["Chờ đến khi ốm nặng mới nói", "Liệt kê tài sản – mong muốn – trao đổi gia đình sớm, rõ ràng", "All-in một tài sản rồi để mặc số phận"], "answer": 1, "hard": True},
        {"id": "q405b", "prompt": "Di sản tài chính tốt kèm theo?", "choices": ["Thông tin, thỏa thuận, giảm tranh chấp về sau", "Chỉ giấu kín tuyệt đối", "Chỉ chuyển hết thành crypto"], "answer": 0, "hard": False},
        {"id": "q405c", "prompt": "Có cần luật sư / giấy tờ khi tài sản phức tạp?", "choices": ["Không bao giờ", "Nên tìm hiểu / nhờ chuyên môn phù hợp khi cần"], "answer": 1, "hard": False},
    ],
    "N04-06": [
        {"id": "q406a", "prompt": "Di sản phi tài chính gồm gì?", "choices": ["Chỉ số dư ngân hàng", "Giá trị, câu chuyện, kỹ năng sống, cách xử lý tiền và quan hệ", "Chỉ bất động sản"], "answer": 1, "hard": True},
        {"id": "q406b", "prompt": "Truyền di sản phi tài chính hữu ích bằng?", "choices": ["Thực hành và trò chuyện có chủ đích", "Chỉ để lại thư không giải thích", "Ép con sao chép mọi quyết định của mình"], "answer": 0, "hard": False},
        {"id": "q406c", "prompt": "Di sản phi tài chính có thể bắt đầu khi chưa giàu?", "choices": ["Không", "Có — giá trị và thói quen không chờ giàu"], "answer": 1, "hard": False},
    ],
    "N04-07": [
        {"id": "q407a", "prompt": "Cân bằng tích lũy và chất lượng sống nghĩa là?", "choices": ["Bỏ hết tiêu dùng để all-in tích lũy", "Tích lũy có kỷ luật nhưng vẫn dành phần hợp lý cho sống tốt hôm nay — không phá An Toàn", "Tiêu hết vì 'sống một lần'"], "answer": 1, "hard": True},
        {"id": "q407b", "prompt": "Khi tích lũy quá mức làm khổ hiện tại, hướng điều chỉnh?", "choices": ["Giữ An Toàn, điều chỉnh tỷ lệ tiết kiệm/tiêu dùng theo giá trị sống", "Bỏ quỹ khẩn cấp để vui hơn", "Vay để vừa tích lũy vừa tiêu"], "answer": 0, "hard": False},
        {"id": "q407c", "prompt": "Chất lượng sống có thay thế lớp An Toàn?", "choices": ["Có", "Không — An Toàn vẫn là nền"], "answer": 1, "hard": False},
    ],
    "N05-01": [
        {"id": "q501a", "prompt": "Cách thu hẹp khoảng cách biết → làm hiệu quả nhất?", "choices": ["Đọc thêm nhiều sách rồi mới bắt đầu", "Chọn một hành động đủ nhỏ và rõ trong 7 ngày, rồi đánh giá lại — không phá An Toàn", "Đặt mục tiêu all-in quỹ 6 tháng ngay tuần này"], "answer": 1, "hard": True},
        {"id": "q501b", "prompt": "Hành động đầu tiên tốt nên có đặc điểm nào?", "choices": ["Đủ rõ, đủ nhỏ, có phản hồi sớm", "Càng lớn càng tốt", "Chỉ cảm xúc quyết tâm"], "answer": 0, "hard": False},
        {"id": "q501c", "prompt": "Chờ 'ổn định hơn' rồi mới làm thường dẫn tới?", "choices": ["Bắt đầu sớm hơn", "Trì hoãn kéo dài"], "answer": 1, "hard": False},
    ],
    "N05-02": [
        {"id": "q502a", "prompt": "Xây thói quen tài chính bền nên bắt đầu thế nào?", "choices": ["Ép thay đổi 10 thói quen cùng lúc", "Một thói quen nhỏ lặp lại (vd. chuyển đều vào quỹ) — giữ An Toàn làm nền, tránh all-in vì hứng", "Bỏ quỹ khẩn cấp để 'tập kỷ luật mạnh'"], "answer": 1, "hard": True},
        {"id": "q502b", "prompt": "Thói quen tốt thường gắn với?", "choices": ["Mốc thời gian / trigger rõ + phần thưởng nhỏ hợp lý", "Chỉ dựa vào ý chí mỗi sáng", "FOMO mạng xã hội"], "answer": 0, "hard": False},
        {"id": "q502c", "prompt": "Thất bại một ngày với thói quen nghĩa là?", "choices": ["Bỏ hết chương trình", "Quay lại lần sau — không all-in bù đắp bằng rủi ro"], "answer": 1, "hard": False},
    ],
    "N05-03": [
        {"id": "q503a", "prompt": "Theo dõi và điều chỉnh kế hoạch nghĩa là?", "choices": ["Đổi kế hoạch mỗi ngày theo tin nóng", "Đo tiến độ định kỳ, chỉnh vừa sức — không phá An Toàn / all-in đuổi kịp", "Bỏ kế hoạch khi lệch một lần"], "answer": 1, "hard": True},
        {"id": "q503b", "prompt": "Khi kế hoạch lệch nhẹ, hướng xử lý hợp lý?", "choices": ["Giữ An Toàn, điều chỉnh mốc / mức đóng góp", "Vay nóng để đuổi kịp ngay", "All-in kênh lời cao"], "answer": 0, "hard": True},
        {"id": "q503c", "prompt": "Theo dõi có ích khi?", "choices": ["Có số liệu và nhịp xem lại cố định", "Chỉ cảm giác 'đang ổn'"], "answer": 0, "hard": False},
    ],
    "N05-04": [
        {"id": "q504a", "prompt": "Ra quyết định tài chính hàng ngày nên ưu tiên gì?", "choices": ["Theo FOMO / lời hứa lãi cao", "Khớp với ngân sách và lớp An Toàn — không all-in vì cơ hội nóng", "Quyết nhanh không cần nghĩ"], "answer": 1, "hard": True},
        {"id": "q504b", "prompt": "Trước khi chi lớn ngoài kế hoạch, nên?", "choices": ["Hỏi: có phá quỹ khẩn cấp / An Toàn không? Có chờ 24–48h?", "Mua ngay kẻo lỡ", "Vay tiêu dùng để không đụng tiết kiệm"], "answer": 0, "hard": True},
        {"id": "q504c", "prompt": "Quyết định nhỏ lặp lại ảnh hưởng thế nào?", "choices": ["Ít ảnh hưởng tổng thể", "Tạo quỹ đạo lớn theo thời gian"], "answer": 1, "hard": False},
    ],
    "N05-05": [
        {"id": "q505a", "prompt": "Học hỏi cùng cộng đồng hữu ích khi?", "choices": ["Copy all-in chiến lược người khác không xét An Toàn của mình", "Trao đổi kinh nghiệm, giữ quyết định cuối thuộc về bạn và lớp An Toàn", "Tin mọi tip lãi cao trên nhóm"], "answer": 1, "hard": True},
        {"id": "q505b", "prompt": "Peer learning tốt nên kèm?", "choices": ["Câu hỏi phản biện và kiểm chứng nguồn", "Chỉ like và FOMO", "Ép nhau all-in cùng một mã"], "answer": 0, "hard": False},
        {"id": "q505c", "prompt": "Ai chịu trách nhiệm quyết định cuối khi học cùng nhóm?", "choices": ["Admin nhóm", "Bạn — không giao An Toàn cho đám đông"], "answer": 1, "hard": False},
    ],
    "N05-06": [
        {"id": "q506a", "prompt": "Công cụ / hệ thống hỗ trợ (app, Goal, ngân sách) nên dùng thế nào?", "choices": ["Thay thế hoàn toàn kỷ luật và An Toàn", "Giảm ma sát thực hành — nhắc nhở, theo dõi — không khuyến khích all-in", "Càng nhiều app càng tốt dù rối"], "answer": 1, "hard": True},
        {"id": "q506b", "prompt": "Chọn công cụ phù hợp bắt đầu từ?", "choices": ["Nhu cầu thật (theo dõi / Goal / nhắc) rồi giữ đơn giản", "App đắt nhất", "Bot trade tự động all-in"], "answer": 0, "hard": False},
        {"id": "q506c", "prompt": "Công cụ có thay quỹ khẩn cấp?", "choices": ["Có", "Không — An Toàn vẫn cần lớp đệm thật"], "answer": 1, "hard": False},
    ],
    "N05-07": [
        {"id": "q507a", "prompt": "Duy trì động lực dài hạn nên dựa vào?", "choices": ["Hứng FOMO và all-in theo sóng", "Mốc nhỏ lặp lại, nhìn tiến bộ, giữ An Toàn làm nền — không đốt hết vì 'một lần nữa'", "Chỉ mục tiêu khổng lồ không chia nhỏ"], "answer": 1, "hard": True},
        {"id": "q507b", "prompt": "Khi mất động lực, hướng phục hồi lành mạnh?", "choices": ["Quay lại hành động đủ nhỏ + ôn lại vì sao bắt đầu", "Bỏ An Toàn để 'reset mạnh'", "All-in một cú để lấy lại cảm giác thắng"], "answer": 0, "hard": True},
        {"id": "q507c", "prompt": "Động lực bền thường đi kèm?", "choices": ["Hệ thống và thói quen, không chỉ cảm xúc", "Chỉ chờ cảm hứng"], "answer": 0, "hard": False},
    ],

}

_PROFILES: dict[str, dict[str, Any]] = {}
_REVS: dict[str, int] = {}  # DB revision each cached profile was loaded from / saved as
ATTEMPT_LOG_MAX = 20

# GP P0b — KUAT draw: each attempt shows KUAT_DRAW questions picked at random from the node's bank
# (at least KUAT_MIN_HARD "hard" ones when the bank has them), in random order, each with its
# options in random order. Pass rule unchanged: score ≥ KUAT_PASS_THRESHOLD (70 %) AND every hard
# question shown answered correctly → with 5 questions: ≥ 4/5 and all hard right; 3-question
# banks: 3/3 (as before). Round 2: the result is pass / fail ONLY — no score, no correct count, no
# percent, no per-question data, and no "hard" marker — in every response and stored record.
KUAT_DRAW = 5
KUAT_MIN_HARD = 2
PASS_RULE_VI = "Đạt khi đúng từ 70% số câu trở lên và đúng mọi câu trọng tâm."


def reset_academy_store() -> None:
    _PROFILES.clear()
    _REVS.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_attempt(a: Any) -> Any:
    """Attempt summary safe to store / return: pass / fail only (no score, no count, never per-question)."""
    if not isinstance(a, dict):
        return a
    return {k: a[k] for k in ("node_id", "passed", "ts", "principle_keys") if k in a}


def _normalise(p: dict[str, Any]) -> dict[str, Any]:
    p.setdefault("xp", 0)
    p.setdefault("badges", [])
    p.setdefault("awarded_xp", [])
    p.setdefault("nodes", {})
    p.setdefault("attempts", [])
    p.setdefault("read", [])
    for n in NODES:
        p["nodes"].setdefault(
            n["node_id"],
            {
                "node_id": n["node_id"],
                "status": STATUS_AVAILABLE if not n["prereq_node_ids"] else STATUS_LOCKED,
                "mastery_level": "not_started",
                "last_kuat": None,
            },
        )
    for st in p["nodes"].values():
        if st.get("last_kuat"):
            st["last_kuat"] = _public_attempt(st["last_kuat"])
    p["attempts"] = [_public_attempt(a) for a in p["attempts"]][-ATTEMPT_LOG_MAX:]
    return p


def _sync_from_db(user_id: str) -> None:
    """DB-store mode: (re)load the persisted profile when this process has none or another
    instance / request saved a newer revision. An unsaved in-process copy with the same revision is
    kept as is."""
    from welora import academy_store as store

    if not store.use_db_profiles():
        return
    rev = store.profile_rev(user_id)
    if rev is None or (user_id in _PROFILES and _REVS.get(user_id) == rev):
        return
    loaded = store.load_profile(user_id)
    if loaded:
        _PROFILES[user_id], _REVS[user_id] = loaded[0], loaded[1]


def _profile(user_id: str) -> dict[str, Any]:
    _sync_from_db(user_id)
    p = _PROFILES.setdefault(user_id, {})
    return _normalise(p)


def _save(user_id: str) -> None:
    from welora import academy_store as store

    if store.use_db_profiles() and user_id in _PROFILES:
        _REVS[user_id] = store.save_profile(user_id, _PROFILES[user_id])


def profile_snapshot(user_id: str) -> dict[str, Any]:
    """Read-only view for other modules (checkout usage): persisted progress after a restart."""
    _sync_from_db(user_id)
    return _PROFILES.get(user_id) or {}


def merge_profiles(account: dict[str, Any], guest: dict[str, Any]) -> dict[str, Any]:
    """Guest claim: keep the account's progress and add what the guest really earned (mastered
    nodes, read lessons, XP for nodes not yet awarded to the account)."""
    a = _normalise(json.loads(json.dumps(account or {})))
    g = _normalise(json.loads(json.dumps(guest or {})))
    for nid, gst in g["nodes"].items():
        ast = a["nodes"].get(nid)
        if gst.get("status") == STATUS_MASTERED and (ast or {}).get("status") != STATUS_MASTERED:
            a["nodes"][nid] = dict(gst)
            if nid in g["awarded_xp"] and nid not in a["awarded_xp"]:
                a["awarded_xp"].append(nid)
                a["xp"] = int(a["xp"]) + XP_PER_PASS
    for nid in g["read"]:
        if nid not in a["read"]:
            a["read"].append(nid)
    a["attempts"] = (a["attempts"] + g["attempts"])[-ATTEMPT_LOG_MAX:]
    _refresh_locks(a)
    _refresh_badges(a)
    return a


def _refresh_locks(p: dict[str, Any]) -> None:
    for n in NODES:
        st = p["nodes"][n["node_id"]]
        if st["status"] == STATUS_MASTERED:
            continue
        prereq_ok = all(p["nodes"][pid]["status"] == STATUS_MASTERED for pid in n["prereq_node_ids"])
        if not prereq_ok:
            st["status"] = STATUS_LOCKED
        elif st["status"] == STATUS_LOCKED:
            st["status"] = STATUS_AVAILABLE


def _refresh_badges(p: dict[str, Any]) -> None:
    re_cuc = all(p["nodes"][i]["status"] == STATUS_MASTERED for i in M01_NODE_IDS)
    fund = all(p["nodes"][i]["status"] == STATUS_MASTERED for i in ("N02-01", "N02-02", "N02-03"))
    debt = all(p["nodes"][i]["status"] == STATUS_MASTERED for i in ("N02-04", "N02-05", "N02-06", "N02-07"))
    tu_do = all(p["nodes"][i]["status"] == STATUS_MASTERED for i in M03_NODE_IDS)
    ben_vung = all(p["nodes"][i]["status"] == STATUS_MASTERED for i in M04_NODE_IDS)
    ket_noi = all(p["nodes"][i]["status"] == STATUS_MASTERED for i in M05_NODE_IDS)
    if re_cuc and BADGE_RE_CUC not in p["badges"]:
        p["badges"].append(BADGE_RE_CUC)
    if fund and "An Toàn — Quỹ" not in p["badges"]:
        p["badges"].append("An Toàn — Quỹ")
    if debt and "An Toàn — Nợ" not in p["badges"]:
        p["badges"].append("An Toàn — Nợ")
    if tu_do and BADGE_TU_DO not in p["badges"]:
        p["badges"].append(BADGE_TU_DO)
    if ben_vung and BADGE_BEN_VUNG not in p["badges"]:
        p["badges"].append(BADGE_BEN_VUNG)
    if ket_noi and BADGE_KET_NOI not in p["badges"]:
        p["badges"].append(BADGE_KET_NOI)


def _served_public(node_id: str, served: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """What the learner sees for one attempt: slot ids k1…kN, options in the served order. No "hard"
    marker (round 2: it would tell which questions decide the verdict)."""
    by_id = {q["id"]: q for q in QUESTIONS.get(node_id, [])}
    out = []
    for i, slot in enumerate(served):
        q = by_id[slot["q"]]
        out.append({"id": f"k{i + 1}", "prompt": q["prompt"], "choices": [q["choices"][j] for j in slot["perm"]]})
    return out


def _draw(node_id: str) -> list[dict[str, Any]]:
    rng = random.SystemRandom()
    bank = list(QUESTIONS.get(node_id, []))
    k = min(KUAT_DRAW, len(bank))
    hard = [q for q in bank if q["hard"]]
    n_hard = min(KUAT_MIN_HARD, len(hard), k)
    picked = rng.sample(hard, n_hard)
    rest = [q for q in bank if q not in picked]
    picked += rng.sample(rest, k - n_hard)
    rng.shuffle(picked)
    out = []
    for q in picked:
        perm = list(range(len(q["choices"])))
        rng.shuffle(perm)
        out.append({"q": q["id"], "perm": perm})
    return out


def kuat_info(node_id: str) -> dict[str, Any]:
    return {"threshold": KUAT_PASS_THRESHOLD, "pass_rule": PASS_RULE_VI,
            "question_count": min(KUAT_DRAW, len(QUESTIONS.get(node_id, []))),
            "bank_size": len(QUESTIONS.get(node_id, []))}


def get_tree(user_id: str) -> dict[str, Any]:
    p = _profile(user_id)
    _refresh_locks(p)
    nodes = []
    for n in NODES:
        st = p["nodes"][n["node_id"]]
        item = dict(n)
        item.update({"status": st["status"], "mastery_level": st["mastery_level"],
                     "last_kuat": _public_attempt(st["last_kuat"])})
        nodes.append(item)
    modules = []
    for mod in MODULES:
        mid = mod["module_id"]
        mod_nodes = [x for x in nodes if x.get("module_id") == mid]
        mod_nodes = sorted(mod_nodes, key=lambda x: int(x.get("order") or 0))
        modules.append(
            {
                "module_id": mid,
                "title": mod["title"],
                "order": mod.get("order"),
                "nodes": mod_nodes,
            }
        )
    return {
        "module_id": MODULE_ID,
        "title": MODULE_TITLE,
        "threshold": KUAT_PASS_THRESHOLD,
        "xp": p["xp"],
        "badges": list(p["badges"]),
        "nodes": nodes,
        "modules": modules,
    }



def _lesson_body_markdown(lesson_id: str, principle_key: str) -> str:
    """Load WA markdown by lesson_id; fall back to mapped WA/WP, then FALLBACK_BODY."""
    from welora.content_map import CONTENT_BY_KEY, FALLBACK_BODY, content_root, _read_rel

    root = content_root()
    lid = (lesson_id or "").strip()
    if lid:
        matches = sorted(root.glob(f"{lid}-*.md"))
        if not matches:
            direct = root / f"{lid}.md"
            if direct.is_file():
                matches = [direct]
        if matches:
            body = matches[0].read_text(encoding="utf-8", errors="replace")
            if len(body) > 20000:
                return body[:20000] + "\n\n… (truncated)"
            return body
    meta = CONTENT_BY_KEY.get(principle_key) or {}
    for rel in (meta.get("path_wa"), meta.get("path_wp")):
        body, _ = _read_rel(root, rel)
        if (body or "").strip():
            if len(body) > 20000:
                return body[:20000] + "\n\n… (truncated)"
            return body
    for rel in meta.get("path_wp_extra") or []:
        body, _ = _read_rel(root, rel)
        if (body or "").strip():
            if len(body) > 20000:
                return body[:20000] + "\n\n… (truncated)"
            return body
    fb = FALLBACK_BODY.get(principle_key) or ""
    return fb


def get_node(user_id: str, node_id: str, *, issue_attempt: bool = True, ip: Optional[str] = None) -> dict[str, Any] | None:
    """Lesson + (when the node is open and the learner is not cooling down) the learner's server-held
    KUAT attempt — the OPEN one if still valid (same questions / option order in every tab), a new one
    only when none is open: ``kuat.attempt_id`` and the shuffled ``questions`` (no answers, no verdicts)."""
    from welora import academy_store as store

    if node_id not in _NODE_BY_ID:
        return None
    p = _profile(user_id)
    _refresh_locks(p)
    n = dict(_NODE_BY_ID[node_id])
    st = p["nodes"][node_id]
    body = _lesson_body_markdown(str(n.get("lesson_id") or ""), str(n.get("principle_key") or ""))
    kuat: dict[str, Any] = kuat_info(node_id)
    questions: list[dict[str, Any]] = []
    if st["status"] != STATUS_LOCKED and issue_attempt and QUESTIONS.get(node_id):
        try:
            att = start_attempt(user_id, node_id, ip=ip)
            questions = att["questions"]
            kuat.update({"attempt_id": att["attempt_id"], "expires_at": att["expires_at"]})
        except store.KuatCooldown as e:
            kuat.update({"cooldown": cooldown_payload(e)})
    n.update(
        {
            "status": st["status"],
            "mastery_level": st["mastery_level"],
            "last_kuat": _public_attempt(st["last_kuat"]),
            "questions": questions,
            "kuat": kuat,
            "content_href": "/app/content?key=" + n["principle_key"],
            # Learner-facing stub: VI title only — never leak principle_key / SAFE-* / DEBT-*
            "lesson_stub": n["title"],
            "body_markdown": body,
        }
    )
    return n


def mark_read(user_id: str, node_id: str) -> dict[str, Any]:
    if node_id not in _NODE_BY_ID:
        return {"error": "unknown node"}
    p = _profile(user_id)
    _refresh_locks(p)
    st = p["nodes"][node_id]
    if st["status"] == STATUS_LOCKED:
        return {"error": "locked", "xp": p["xp"]}
    if node_id not in p["read"]:
        p["read"].append(node_id)
    if st["status"] in (STATUS_AVAILABLE, STATUS_LEARNING):
        st["status"] = STATUS_KUAT_PENDING
        if st["mastery_level"] == "not_started":
            st["mastery_level"] = "learning"
    _save(user_id)
    return {"ok": True, "xp": p["xp"], "status": st["status"], "awarded_xp": False}


def _verdict(results: list[tuple[bool, bool]]) -> tuple[float, bool]:
    """results = [(correct, hard)] → (score, passed). Pass rule: ≥ 70 % and every hard one right."""
    if not results:
        return 0.0, False
    score = sum(1 for ok, _h in results if ok) / len(results)
    return score, score >= KUAT_PASS_THRESHOLD and all(ok for ok, h in results if h)


def _choice(raw: Any) -> int:
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -1


def _grade(node_id: str, answers: list[dict[str, Any]]) -> tuple[float, bool]:
    """In-process grading against the node's whole bank by canonical question id (tests / internal
    tools only — the HTTP API grades against a server-held attempt, ``_grade_served``)."""
    picked = {str(a.get("question_id") or a.get("id")): a.get("choice") for a in answers or []}
    return _verdict([(_choice(picked.get(q["id"])) == q["answer"], bool(q["hard"])) for q in QUESTIONS.get(node_id, [])])


def _grade_served(node_id: str, served: list[dict[str, Any]], answers: list[dict[str, Any]]) -> tuple[float, bool]:
    """Grade an attempt against exactly what the server served: slot k<i> → canonical question,
    the submitted option index → original option via the served permutation."""
    by_id = {q["id"]: q for q in QUESTIONS.get(node_id, [])}
    picked = {str(a.get("question_id") or a.get("id")): a.get("choice") for a in answers or []}
    results = []
    for i, slot in enumerate(served):
        q = by_id.get(slot.get("q"))
        if q is None:
            results.append((False, True))
            continue
        c = _choice(picked.get(f"k{i + 1}"))
        perm = slot.get("perm") or []
        ok = 0 <= c < len(perm) and perm[c] == q["answer"]
        results.append((ok, bool(q["hard"])))
    return _verdict(results)


def _wire_mastery(user_id: str) -> None:
    """The ONLY user-driven way to gate mastery: a KUAT for the gate node graded here on the
    server (against the server-held attempt, never a client verdict) → mastery "apply" (source academy)."""
    from welora.mastery import grant_from_academy

    grant_from_academy(user_id)


def _apply_result(user_id: str, node_id: str, passed: bool) -> dict[str, Any]:
    p = _profile(user_id)
    st = p["nodes"][node_id]
    attempt = {
        "node_id": node_id,
        "passed": passed,
        "ts": _now(),
        "principle_keys": [_NODE_BY_ID[node_id]["principle_key"]],
    }
    p["attempts"].append(attempt)
    p["attempts"] = p["attempts"][-ATTEMPT_LOG_MAX:]
    awarded = False
    if passed:
        st["status"] = STATUS_MASTERED
        st["mastery_level"] = "apply"
        st["last_kuat"] = attempt
        if node_id not in p["awarded_xp"]:
            p["xp"] += XP_PER_PASS
            p["awarded_xp"].append(node_id)
            awarded = True
        if node_id == GATE_NODE:
            _wire_mastery(user_id)
        _refresh_locks(p)
        _refresh_badges(p)
    else:
        st["status"] = STATUS_KUAT_PENDING
        st["mastery_level"] = "familiar"
        st["last_kuat"] = attempt
        _refresh_locks(p)
    _save(user_id)
    return {
        "kuat_result": {  # pass / fail only (round 2): no score / count / percent
            "passed": passed,
            "node_id": node_id,
            "principle_keys": [_NODE_BY_ID[node_id]["principle_key"]],
            "ts": attempt["ts"],
        },
        "xp": p["xp"],
        "awarded_xp": awarded,
        "badges": list(p["badges"]),
        "status": st["status"],
        "tree": get_tree(user_id),
        "os_nudge": os_nudge_for(node_id, first_pass=bool(awarded)),
    }


def submit_kuat(user_id: str, node_id: str, answers: list[dict[str, Any]]) -> dict[str, Any]:
    """In-process only (tests / internal tools): grade against the whole bank. Not reachable over
    HTTP — /academy/kuat goes through ``submit_kuat_attempt`` (server-held attempt + limits)."""
    if node_id not in _NODE_BY_ID:
        return {"error": "unknown node"}
    p = _profile(user_id)
    _refresh_locks(p)
    if p["nodes"][node_id]["status"] == STATUS_LOCKED:
        return {"error": "locked", "passed": False, "xp": p["xp"]}
    _score, passed = _grade(node_id, answers)
    return _apply_result(user_id, node_id, passed)


def start_attempt(user_id: str, node_id: str, *, ip: Optional[str] = None) -> dict[str, Any]:
    """The learner's KUAT attempt for this node: the open one if still valid, else a new draw
    (raises academy_store.KuatCooldown while cooling down / too many new attempts)."""
    from welora import academy_store as store

    store.check_kuat_allowed(user_id, node_id, ip)
    att = store.open_or_create_attempt(user_id, node_id, lambda: _draw(node_id))
    return {**kuat_info(node_id), "attempt_id": att["attempt_id"], "expires_at": att["expires_at"],
            "node_id": node_id, "questions": _served_public(node_id, att["served"])}


_SLOT_RE = re.compile(r"^k([1-9][0-9]?)$")


def submit_kuat_attempt(user_id: str, node_id: str, attempt_id: Optional[str], answers: list[dict[str, Any]],
                        *, ip: Optional[str] = None) -> dict[str, Any]:
    """Grade one server-held attempt. Order (round 2): validate (old tab → "reload", nothing
    counted) → consume the attempt atomically (only one concurrent submit continues) → RESERVE a
    failed-KUAT slot in every limit bucket BEFORE grading (429 if any is full; the attempt is
    re-opened, nothing graded) → grade → keep the reserved fail, or release it on pass."""
    from welora import academy_store as store

    if node_id not in _NODE_BY_ID:
        return {"error": "unknown node"}
    p = _profile(user_id)
    _refresh_locks(p)
    if p["nodes"][node_id]["status"] == STATUS_LOCKED:
        return {"error": "locked", "passed": False, "xp": p["xp"]}
    store.check_kuat_allowed(user_id, node_id, ip)  # cooling down → 429 before anything else
    ids = [str((a or {}).get("question_id") or (a or {}).get("id") or "") for a in answers or [] if isinstance(a, dict)]
    if not ids or len(ids) != len(answers or []):
        return {"error": "no_answers"}
    if not all(_SLOT_RE.match(i) for i in ids):
        return {"error": "reload"}  # a tab from before the attempt format (canonical question ids)
    # Clients that post without attempt_id get the open attempt the server issued with the lesson —
    # still server-held, still single-use.
    aid = (attempt_id or "").strip() or store.latest_open_attempt_id(user_id, node_id)
    served = store.peek_attempt(aid, user_id, node_id) if aid else None
    if not served:
        return {"error": "attempt_invalid"}
    if any(int(_SLOT_RE.match(i).group(1)) > len(served) for i in ids):
        return {"error": "reload"}  # answers for questions this attempt never showed
    served = store.consume_attempt(aid, user_id, node_id)  # atomic: one concurrent submit wins
    if not served:
        return {"error": "attempt_invalid"}
    try:
        reservation = store.reserve_kuat_fail(user_id, node_id, ip)
    except store.KuatCooldown:
        store.reopen_attempt(aid, user_id, node_id)  # not graded → the learner keeps the attempt
        raise
    try:
        _score, passed = _grade_served(node_id, served, answers)
        store.finish_attempt(aid, passed=passed)
    except Exception:
        reservation.release()
        raise
    if passed:
        reservation.release()
    return _apply_result(user_id, node_id, passed)


def _wait_vi(seconds: int) -> str:
    m = max(1, math.ceil(seconds / 60))
    if m < 60:
        return f"{m} phút"
    h, mm = divmod(m, 60)
    return f"{h} giờ" + (f" {mm} phút" if mm else "")


COOLDOWN_MSG_VI = {
    "fails": "Bạn đã làm bài KUAT này chưa đạt vài lần liền. Hãy ôn lại bài học rồi thử lại sau khoảng {wait}.",
    "daily": "Hôm nay bạn đã làm bài KUAT này chưa đạt nhiều lần. Hãy nghỉ ngơi, ôn lại bài và quay lại sau khoảng {wait}.",
    "ip": "Có quá nhiều lượt KUAT chưa đạt từ mạng này. Vui lòng thử lại sau khoảng {wait}.",
    "guest_ip": "Có quá nhiều lượt KUAT chưa đạt từ mạng này. Hãy đăng nhập tài khoản của bạn hoặc thử lại sau khoảng {wait}.",
    "device": "Thiết bị này đã làm bài KUAT chưa đạt nhiều lần. Hãy ôn lại bài, đăng nhập tài khoản của bạn hoặc thử lại sau khoảng {wait}.",
    "starts": "Bạn đã mở bài KUAT này quá nhiều lần. Vui lòng thử lại sau khoảng {wait}.",
}
ATTEMPT_INVALID_MSG_VI = "Lượt KUAT này đã hết hạn hoặc đã được nộp. Hãy tải lại bài để làm lượt mới."
RELOAD_MSG_VI = "Bài KUAT trên trang này đã cũ. Vui lòng tải lại trang để làm lượt mới."
NO_ANSWERS_MSG_VI = "Bạn chưa chọn câu trả lời nào."


def cooldown_payload(e: Any) -> dict[str, Any]:
    retry_at = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + e.retry_after, tz=timezone.utc)
    return {
        "error_code": "KUAT_COOLDOWN",
        "reason": e.reason,
        "message": COOLDOWN_MSG_VI.get(e.reason, COOLDOWN_MSG_VI["fails"]).format(wait=_wait_vi(e.retry_after)),
        "retry_after": int(e.retry_after),
        "retry_at": retry_at.isoformat(),
    }


def service_get_tree(user_id: str) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    return 200, get_tree(user_id)


def service_get_node(user_id: str, node_id: str, *, ip: Optional[str] = None) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    n = get_node(user_id, node_id, ip=ip)
    if not n:
        return 404, {"error": "unknown node"}
    return 200, n


def service_mark_read(body: dict) -> tuple[int, dict]:
    user_id = (body or {}).get("user_id") or ""
    node_id = (body or {}).get("node_id") or ""
    if not user_id or not node_id:
        return 400, {"error": "user_id and node_id required"}
    out = mark_read(user_id, node_id)
    if out.get("error"):
        return 400, out
    return 200, out


def service_start_kuat(body: dict, *, ip: Optional[str] = None) -> tuple[int, dict]:
    from welora import academy_store as store

    user_id = (body or {}).get("user_id") or ""
    node_id = (body or {}).get("node_id") or ""
    if not user_id or not node_id:
        return 400, {"error": "user_id and node_id required"}
    if node_id not in _NODE_BY_ID or not QUESTIONS.get(node_id):
        return 404, {"error": "unknown node"}
    p = _profile(user_id)
    _refresh_locks(p)
    if p["nodes"][node_id]["status"] == STATUS_LOCKED:
        return 403, {"error": "locked"}
    try:
        return 200, start_attempt(user_id, node_id, ip=ip)
    except store.KuatCooldown as e:
        return 429, cooldown_payload(e)


def service_submit_kuat(body: dict, *, ip: Optional[str] = None) -> tuple[int, dict]:
    from welora import academy_store as store

    user_id = (body or {}).get("user_id") or ""
    node_id = (body or {}).get("node_id") or ""
    answers = (body or {}).get("answers") or []
    if not user_id or not node_id:
        return 400, {"error": "user_id and node_id required"}
    try:
        out = submit_kuat_attempt(user_id, node_id, (body or {}).get("attempt_id"), answers, ip=ip)
    except store.KuatCooldown as e:
        return 429, cooldown_payload(e)
    if out.get("error") == "locked":
        return 403, out
    if out.get("error") == "attempt_invalid":
        return 409, {"error_code": "KUAT_ATTEMPT_INVALID", "message": ATTEMPT_INVALID_MSG_VI}
    if out.get("error") == "reload":
        return 409, {"error_code": "KUAT_RELOAD", "message": RELOAD_MSG_VI}
    if out.get("error") == "no_answers":
        return 400, {"error_code": "KUAT_NO_ANSWERS", "message": NO_ANSWERS_MSG_VI}
    if out.get("error"):
        return 400, out
    return 200, out
