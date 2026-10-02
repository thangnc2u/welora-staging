"""Welorademy M01 Rễ Cục + M02 An Toàn + M03 Tự Do + M04 Bền Vững & Di Sản + M05 Kết Nối & Thực Hành — cây ngữ nghĩa + cổng KUAT."""

from __future__ import annotations

import json
import math
import random
import re
from datetime import datetime, timedelta, timezone
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
        # Follow-up item 5 — chuẩn N02 (P0b r2/r3): 12 câu × 4 lựa chọn, 6 câu trọng tâm; độ dài cân bằng (đáp án
        # đúng dài nhất / nhì / ba / ngắn nhất đúng 3 câu mỗi loại), mở đầu đáp án đúng không lặp; mọi câu trả lời
        # được bằng nội dung bài WA-01-01. Mỗi lượt KUAT bốc 5 câu (≥ 2 câu trọng tâm), xáo thứ tự lựa chọn.
        {"id": "q101-01", "prompt": "Theo bài học, tư duy về tiền là gì?", "choices": ["Những lời khuyên được chia sẻ nhiều nhất trên mạng xã hội mỗi ngày", "Hệ thống niềm tin và thái độ của bạn đối với tiền bạc", "Số dư hiện có trong tài khoản ngân hàng", "Kỹ năng chọn đúng cổ phiếu sẽ tăng giá mạnh trong năm tới"], "answer": 1, "hard": False},
        {"id": "q101-02", "prompt": "Vì sao tư duy về tiền ảnh hưởng lớn đến tài chính của gia đình?", "choices": ["Ngân hàng chỉ cho vay khi bạn có tư duy đúng", "Có tư duy tốt thì đầu tư kênh nào cũng chắc chắn có lãi, khỏi cần tìm hiểu thêm", "Nó chi phối hành vi hằng ngày, thường mạnh hơn cả kiến thức kỹ thuật", "Tư duy quyết định mức lương"], "answer": 2, "hard": False},
        {"id": "q101-03", "prompt": "Trong ví dụ cái búa, cách nhìn tiền lành mạnh là gì?", "choices": ["Càng nhiều tiền càng tốt, dù chưa biết dùng vào việc gì", "Xem tiền là công cụ phục vụ mục tiêu sống", "Coi tiền là mục tiêu cuối cùng của đời người, quan trọng hơn mọi thứ khác", "Tránh đụng đến tiền vì nguy hiểm"], "answer": 1, "hard": True},
        {"id": "q101-04", "prompt": "Dấu hiệu nào cho thấy một người đang có tư duy khan hiếm?", "choices": ["Lập ngân sách và xem lại mỗi tháng", "Có sẵn quỹ dự phòng", "Phân bổ tiền theo thứ tự ưu tiên đã thống nhất rõ ràng với cả gia đình từ trước", "Luôn thấy không đủ, sợ mất tiền và khó quyết định việc dài hạn"], "answer": 3, "hard": False},
        {"id": "q101-05", "prompt": "Theo bài học, tư duy về tiền lành mạnh là kiểu tư duy nào?", "choices": ["Tiết kiệm bằng mọi giá, kể cả bỏ qua sức khỏe", "Tiêu thật nhiều để khẳng định bản thân với mọi người xung quanh", "Thực tế và có chủ đích", "Lạc quan tuyệt đối, tin rằng mọi chuyện rồi sẽ ổn"], "answer": 2, "hard": True},
        {"id": "q101-06", "prompt": "Bài thực hành của bài học yêu cầu bạn làm gì đầu tiên?", "choices": ["Mở ngay một tài khoản chứng khoán", "Hỏi bạn bè lương bao nhiêu", "Viết ra niềm tin về tiền rồi đối chiếu với cách bạn chi, vay, tiết kiệm tháng này", "Đọc thêm mười cuốn sách làm giàu rồi mới bắt đầu"], "answer": 2, "hard": True},
        {"id": "q101-07", "prompt": "Ai là người quyết định cuối cùng về tiền của bạn?", "choices": ["Người thu nhập cao nhất trong nhóm bạn bè", "Bạn — Agent chỉ hỗ trợ, không quyết thay", "Agent của Welora, vì máy tính toán chính xác hơn con người", "Những chuyên gia nổi tiếng nhất trên mạng xã hội"], "answer": 1, "hard": True},
        {"id": "q101-08", "prompt": "Trước khi nhận thêm rủi ro, như đầu tư, bài học nhắc bạn cần nhìn rõ điều gì?", "choices": ["Thu nhập, chi tiêu thiết yếu và quỹ 3 tháng", "Mức lãi bạn bè khoe trong nhóm chat", "Giá vàng tuần này", "Kênh đầu tư đang được bàn tán nhiều nhất trên mạng xã hội gần đây"], "answer": 0, "hard": True},
        {"id": "q101-09", "prompt": "Muốn thay đổi tư duy về tiền, cách nào thực tế nhất?", "choices": ["Ép bản thân nghĩ tích cực mỗi sáng", "Làm theo đúng cách tiêu tiền của một người nổi tiếng", "Đọc một bài viết là đủ", "Dành thời gian thực hành và tự nhìn lại, vì tư duy hình thành qua nhiều năm"], "answer": 3, "hard": False},
        {"id": "q101-10", "prompt": "Hai cặp vợ chồng cùng thu nhập 40 triệu ₫/tháng. Vì sao sau 5 năm kết quả tài chính thường khác nhau rõ rệt?", "choices": ["Hoàn toàn do may mắn", "Cặp kia sống ở thành phố lớn nên chi phí cao hơn", "Lương của một cặp chắc chắn đã tăng gấp đôi", "Một cặp xem tiền là công cụ xây an toàn, cặp kia tiêu để không thua kém ai"], "answer": 3, "hard": False},
        {"id": "q101-11", "prompt": "Ngại nói chuyện tiền bạc trong gia đình thường dẫn tới điều gì?", "choices": ["Chẳng ảnh hưởng gì, vì tiền là chuyện riêng của từng người trong nhà", "Con cái học được cách quản lý tiền", "Gia đình tự khắc tiết kiệm được nhiều tiền hơn trước", "Vợ chồng thiếu minh bạch với nhau về tiền"], "answer": 3, "hard": False},
        {"id": "q101-12", "prompt": "Gắn nhãn «tư duy nghèo» hay «tư duy giàu» cho người khác có vấn đề gì?", "choices": ["Dễ thành phán xét và phản tác dụng", "Giúp người đó thay đổi suy nghĩ nhanh hơn hẳn", "Chẳng có vấn đề gì, nói thẳng mới là tốt", "Đó là cách chẩn đoán tâm lý chính xác, nên dùng thường xuyên"], "answer": 0, "hard": True},
    ],
    "N01-02": [
        {"id": "q102-01", "prompt": "Theo bài học, dòng tiền là gì?", "choices": ["Giá trị các khoản đầu tư", "Số dư còn lại vào cuối tháng", "Tổng tiền lương nhận được", "Mối quan hệ giữa thu nhập và chi tiêu trong cùng một khoảng thời gian"], "answer": 3, "hard": True},
        {"id": "q102-02", "prompt": "Khi nào dòng tiền được gọi là dương?", "choices": ["Khi số dư tài khoản lớn hơn 0 vào một ngày", "Khi thu nhập lớn hơn chi tiêu một cách bền vững qua nhiều tháng", "Khi vừa được tăng lương", "Khi nhận được thưởng Tết"], "answer": 1, "hard": True},
        {"id": "q102-03", "prompt": "Trong ẩn dụ bồn nước, các lỗ thoát nước tượng trưng cho điều gì?", "choices": ["Các khoản chi tiêu làm tiền chảy ra khỏi bồn mỗi tháng", "Các khoản đầu tư sinh lời", "Phần dư cuối kỳ", "Tiền lương hằng tháng"], "answer": 0, "hard": False},
        {"id": "q102-04", "prompt": "Vì sao chỉ mở to vòi (tăng thu nhập) mà bồn vẫn có thể cạn?", "choices": ["Vì vòi nước luôn bị rò rỉ", "Vì thu nhập tăng thì thuế luôn tăng gấp đôi, nên tiền còn lại bao giờ cũng ít hơn trước khi tăng lương", "Vì số dư chẳng quan trọng gì", "Vì các lỗ thoát (chi tiêu) cũng lớn dần mà mình không để ý"], "answer": 3, "hard": True},
        {"id": "q102-05", "prompt": "Nguyên tắc cốt lõi của bài học về dòng tiền là gì?", "choices": ["Cắt giảm chi tiêu là đủ", "Dồn sức tăng thu nhập, còn chi tiêu sẽ tự điều chỉnh theo thời gian mà không cần quan tâm", "Chỉ xem số dư cuối tháng", "Phải nhìn đồng thời cả hai phía: tiền vào và tiền ra"], "answer": 3, "hard": False},
        {"id": "q102-06", "prompt": "Ví dụ gia đình thu nhập 35 triệu/tháng trong bài cho thấy điều gì?", "choices": ["Gia đình thu nhập 35 triệu mỗi tháng thì chắc chắn luôn dư tiền để đầu tư dài hạn sau khi đã chi tiêu đủ", "35 triệu là quá thấp để sống", "Lương trông ổn nhưng tổng chi thực tế có thể chạm hoặc vượt 35 triệu", "Phải chuyển ngay sang thuê nhà rẻ hơn"], "answer": 2, "hard": False},
        {"id": "q102-07", "prompt": "Vì sao chi tiêu thường bị đánh giá thấp hơn thực tế?", "choices": ["Vì giá cả luôn giảm", "Chi bị chia thành nhiều khoản nhỏ, dễ quên", "Vì ngân hàng không gửi sao kê hằng tháng cho khách hàng có thu nhập trung bình", "Vì mọi khoản chi đều đã được ghi rõ trên phiếu lương hằng tháng của người lao động"], "answer": 1, "hard": True},
        {"id": "q102-08", "prompt": "Với thu nhập không ổn định (làm thêm, freelance), bài học lưu ý điều gì?", "choices": ["So sánh thu – chi càng khó nếu không ghi chép", "Thu nhập lên xuống thất thường thì số liệu chẳng có ý nghĩa, nên không cần theo dõi gì cả", "Nên vay thêm vào tháng thu thấp để giữ mức chi tiêu như những tháng cao điểm nhất", "Bỏ việc tự do cho chắc"], "answer": 0, "hard": True},
        {"id": "q102-09", "prompt": "Cắt giảm chi tiêu quá mức mà không có mục tiêu rõ có thể dẫn tới điều gì?", "choices": ["Giảm chất lượng sống và khó bền vững", "Giúp gia đình giàu lên rất nhanh chỉ trong vài tháng mà không cần làm gì thêm", "Chẳng ảnh hưởng gì", "Tạo dòng tiền dương vĩnh viễn, không bao giờ cần xem lại kế hoạch nữa"], "answer": 0, "hard": False},
        {"id": "q102-10", "prompt": "Dòng tiền dương có đồng nghĩa với giàu có không?", "choices": ["Đúng vậy, miễn là số dư cuối tháng lớn hơn tháng trước", "Chưa, đó chỉ là điều kiện cần", "Hai việc chẳng liên quan, vì giàu có chỉ phụ thuộc vào mức lương", "Có, dòng tiền dương nghĩa là bạn đã đạt tự do tài chính"], "answer": 1, "hard": True},
        {"id": "q102-11", "prompt": "Trong ẩn dụ bồn nước, số dư tương ứng với gì?", "choices": ["Tốc độ nước bốc hơi khỏi bồn những ngày trời nắng", "Kích thước các lỗ thoát nước dưới đáy bồn", "Mực nước còn lại trong bồn", "Lượng nước chảy vào từ vòi mỗi tháng"], "answer": 2, "hard": False},
        {"id": "q102-12", "prompt": "Bài học có đưa ra mức chi tiêu chuẩn cho mọi gia đình không?", "choices": ["Không, bài chỉ làm rõ khái niệm", "Bài khuyên chi bằng đúng thu nhập trung bình của cả nước", "Mỗi gia đình nên chi đúng 50% cho thiết yếu", "Mức chuẩn là chi tiêu không vượt quá 70% thu nhập trong mọi trường hợp"], "answer": 0, "hard": False},
    ],
    "N01-03": [
        {"id": "q103-01", "prompt": "Theo bài học, ngân sách là gì?", "choices": ["Bảng lương của cả gia đình", "Kế hoạch phân bổ thu nhập vào chi tiêu, tiết kiệm và mục tiêu trong một khoảng thời gian", "Sổ ghi nợ với ngân hàng", "Danh sách các món không được mua"], "answer": 1, "hard": True},
        {"id": "q103-02", "prompt": "Bài học nói ngân sách KHÔNG phải là gì, mà là gì?", "choices": ["Giúp vay thêm tiền dễ dàng hơn", "Là cách để tiêu hết tiền nhanh hơn", "Là bảng xếp hạng chi tiêu", "Không phải công cụ cấm tiêu tiền, mà để quyết định trước tiền sẽ đi đâu"], "answer": 3, "hard": True},
        {"id": "q103-03", "prompt": "Trong ẩn dụ lái xe, ngân sách giống với điều gì?", "choices": ["Người tài xế lái thay mình", "Vừa có bản đồ, vừa có đồng hồ báo xăng cho chuyến đi", "Một chiếc xe mới đắt tiền", "Biển cấm đi vào những đường lạ"], "answer": 1, "hard": False},
        {"id": "q103-04", "prompt": "Nguyên tắc trả cho mình trước (pay yourself first) nghĩa là gì?", "choices": ["Trả hết nợ của người khác trước", "Để lại phần cho tiết kiệm/mục tiêu trước khi tiêu phần còn lại", "Tự thưởng sau mỗi tháng", "Mua ngay món mình thích trước khi trả các hóa đơn sinh hoạt và tiền nhà trong tháng"], "answer": 1, "hard": True},
        {"id": "q103-05", "prompt": "Cách tiêu đến đâu hay đến đó dễ đổ vỡ khi nào?", "choices": ["Khi gia đình ít người", "Khi lãi suất tiết kiệm tăng", "Khi có khoản chi đột xuất, thu nhập không đều hoặc có trả góp", "Khi thu nhập dư dả, chi tiêu đều đặn mỗi tháng và gia đình chưa có khoản nợ hay trả góp nào"], "answer": 2, "hard": False},
        {"id": "q103-06", "prompt": "Ví dụ hộ thu nhập 30 triệu không lập ngân sách gặp khó khăn gì?", "choices": ["Họ luôn dư rất nhiều tiền nhưng không biết dùng vào việc gì nên để yên trong tài khoản", "Muốn xây quỹ hay trả nợ nhưng không biết lấy tiền từ đâu", "Không được ngân hàng cho mở tài khoản", "Bị phạt nộp thuế cao hơn"], "answer": 1, "hard": True},
        {"id": "q103-07", "prompt": "Ngân sách đơn giản trong bài gồm mấy nhóm lớn?", "choices": ["Khoảng 3–4 nhóm lớn", "Tận 12 nhóm", "Hơn 20 hạng mục chi tiết cho từng món nhỏ trong nhà", "Đúng một nhóm duy nhất: tiết kiệm thật nhiều"], "answer": 0, "hard": False},
        {"id": "q103-08", "prompt": "Ngân sách quá chi tiết và cứng nhắc thường dẫn tới điều gì?", "choices": ["Dễ bỏ cuộc sau vài tuần", "Gia đình sẽ không bao giờ phải điều chỉnh gì nữa", "Tiết kiệm được gấp đôi sau một tháng áp dụng", "Thu nhập tự tăng"], "answer": 0, "hard": True},
        {"id": "q103-09", "prompt": "Có ngân sách rồi, tài chính có tự động tốt lên không?", "choices": ["Có, chỉ cần lập ngân sách một lần là tài chính sẽ tự tốt lên mãi mãi", "Không cần làm gì", "Chưa, phải thực hiện và điều chỉnh", "Ngân sách tự khắc làm thu nhập tăng theo mỗi năm"], "answer": 2, "hard": False},
        {"id": "q103-10", "prompt": "Theo bài học, ngân sách là mục tiêu hay công cụ?", "choices": ["Là công cụ phục vụ mục tiêu", "Là bằng chứng để chứng minh mình giỏi quản lý tiền", "Là mục tiêu tối thượng của mọi gia đình", "Là thủ tục bắt buộc khi muốn vay ngân hàng"], "answer": 0, "hard": True},
        {"id": "q103-11", "prompt": "Không có ngân sách giống như lái xe thế nào?", "choices": ["Được người dẫn đường đi cùng suốt chặng", "Luôn đi đúng đường ngắn nhất", "Chỉ dựa vào cảm giác", "Đổ đầy xăng trước mỗi chuyến đi xa"], "answer": 2, "hard": False},
        {"id": "q103-12", "prompt": "Bài học có đưa ra mẫu ngân sách bắt buộc không?", "choices": ["Bắt buộc chia thành 4 nhóm bằng nhau", "Mọi gia đình phải theo cùng một mẫu", "Bài chỉ giải thích, không có mẫu", "Mẫu chuẩn là chi tối đa 30 triệu một tháng"], "answer": 2, "hard": False},
    ],
    "N01-04": [
        {"id": "q104-01", "prompt": "Lập ngân sách dựa trên chi tiêu thực tế nghĩa là gì?", "choices": ["Đặt ra các con số lý tưởng thật đẹp", "Chép ngân sách của nhà hàng xóm", "Đoán mức chi cho có", "Lấy dữ liệu chi đã xảy ra (sao kê, ghi chép, hóa đơn) làm cơ sở để phân bổ tiền"], "answer": 3, "hard": True},
        {"id": "q104-02", "prompt": "Vì sao cách làm này khả thi hơn ngân sách lý tưởng?", "choices": ["Vì không cần theo dõi gì sau đó", "Vì nó cấm hẳn mọi khoản chi linh hoạt", "Vì ngân hàng yêu cầu như vậy", "Vì xuất phát từ hành vi hiện tại rồi điều chỉnh dần từng bước"], "answer": 3, "hard": True},
        {"id": "q104-03", "prompt": "Trong ẩn dụ giảm cân, cách nào bền vững hơn?", "choices": ["Ép ăn 1.200 calo ngay từ hôm nay", "Đo xem hiện đang ăn bao nhiêu, rồi giảm dần từng bước có kiểm soát", "Không cần đo đếm gì cả", "Nhịn ăn hoàn toàn một tuần"], "answer": 1, "hard": False},
        {"id": "q104-04", "prompt": "Bước đầu tiên của quy trình trong bài là gì?", "choices": ["Chọn mục tiêu đầu tư ngay", "Cắt ngay một nửa mọi khoản chi linh hoạt từ ngày đầu tiên của tháng tới", "Thu thập dữ liệu chi tiêu trong 30 ngày", "Mở thẻ tín dụng mới"], "answer": 2, "hard": True},
        {"id": "q104-05", "prompt": "Khi tính tổng từng nhóm, nhóm nào thường gần như bằng không?", "choices": ["Nhóm chi cho tương lai (tiết kiệm, quỹ, trả nợ thêm)", "Nhóm giải trí, mua sắm", "Nhóm ăn ngoài", "Nhóm chi thiết yếu như tiền nhà, ăn uống cơ bản, đi lại và học phí của con hằng tháng"], "answer": 0, "hard": False},
        {"id": "q104-06", "prompt": "Đang chi linh hoạt 8 triệu, bài gợi ý đặt mục tiêu tháng tới thế nào?", "choices": ["Giảm còn 6 triệu và chuyển 2 triệu sang quỹ hoặc trả nợ", "Đưa hẳn về 0 đồng để dồn toàn bộ sang đầu tư chứng khoán ngay trong tháng tới", "Tăng lên 10 triệu", "Giữ nguyên 8 triệu"], "answer": 0, "hard": True},
        {"id": "q104-07", "prompt": "Theo bài học, ngân sách tốt là ngân sách như thế nào?", "choices": ["Ít", "Bạn có thể sống chung được", "Đẹp nhất trên giấy và không bao giờ phải sửa", "Giống hệt mẫu của chuyên gia nổi tiếng trên mạng"], "answer": 1, "hard": True},
        {"id": "q104-08", "prompt": "Ví dụ gia đình thu nhập 32 triệu: phần cho tương lai được hướng tới bao nhiêu?", "choices": ["Bằng 0", "Nâng lên 20 triệu ngay trong tháng đầu tiên", "Từ 2 lên khoảng 5–6 triệu", "Vẫn 2 triệu như hiện tại vì không thể tăng thêm"], "answer": 2, "hard": False},
        {"id": "q104-09", "prompt": "Bài học ví ngân sách như thế nào?", "choices": ["Bản nháp sống, không khắc đá", "Bảng điểm", "Một hợp đồng ký một lần dùng mãi không đổi", "Bản cam kết với ngân hàng không được sửa"], "answer": 0, "hard": False},
        {"id": "q104-10", "prompt": "Lấy số liệu chi tiêu chỉ trong vài ngày có vấn đề gì?", "choices": ["Không sao, vài ngày là đủ đại diện cho cả tháng", "Còn chính xác hơn số liệu của cả một tháng dài", "Dễ bị lệch", "Ngân hàng sẽ khóa tài khoản của bạn"], "answer": 2, "hard": True},
        {"id": "q104-11", "prompt": "Với học phí theo kỳ, bảo hiểm năm, Tết… nên làm gì?", "choices": ["Vay nóng khi đến hạn rồi trả dần sau", "Bỏ qua vì đó không phải chi tiêu hằng tháng", "Dùng hết quỹ khẩn cấp cho các khoản này", "Chia đều hoặc dự phòng riêng"], "answer": 3, "hard": False},
        {"id": "q104-12", "prompt": "Có một công thức phân bổ duy nhất đúng cho mọi gia đình không?", "choices": ["Chỉ cần chia đều thu nhập cho các nhóm", "Tỷ lệ đúng là do ngân hàng quy định", "Không có", "Có, mọi gia đình nên áp dụng cùng một tỷ lệ"], "answer": 2, "hard": False},
    ],
    "N01-05": [
        {"id": "q105-01", "prompt": "Mục đích chính của việc theo dõi chi tiêu là gì?", "choices": ["Có dữ liệu trung thực để lập ngân sách và ra quyết định tốt hơn", "Cho ngân hàng chấm điểm", "Khoe với bạn bè", "Để tự trách mỗi khi tiêu tiền"], "answer": 0, "hard": True},
        {"id": "q105-02", "prompt": "Trong ẩn dụ đồng hồ đo bước chân, công cụ theo dõi đóng vai trò gì?", "choices": ["Tăng thu nhập cho bạn", "Cấm mọi khoản chi không cần thiết", "Tự động trả hóa đơn thay bạn", "Cho bạn dữ liệu để quyết định, không cấm bạn tiêu"], "answer": 3, "hard": True},
        {"id": "q105-03", "prompt": "Vì sao cảm giác tiêu cũng bình thường không đáng tin?", "choices": ["Vì ai cũng tiêu giống nhau", "Vì giá cả luôn ổn định", "Do sao kê thường sai", "Vì cảm giác thường khác với con số thật trên sổ hay sao kê"], "answer": 3, "hard": False},
        {"id": "q105-04", "prompt": "Nguyên tắc «đủ rõ» khi theo dõi nghĩa là gì?", "choices": ["Ghi bằng mực đỏ", "Chỉ ghi các khoản trên 1 triệu", "Ghi chính xác đến từng đồng lẻ cho mọi giao dịch, dù nhỏ đến đâu, mỗi ngày", "Thấy được các nhóm lớn, chưa cần 20 hạng mục"], "answer": 3, "hard": True},
        {"id": "q105-05", "prompt": "Người còn dùng nhiều tiền mặt nên chọn cách theo dõi nào?", "choices": ["Chỉ xem sao kê ngân hàng cuối tháng vì mọi khoản tiền mặt đều tự hiện lên trong đó", "Đoán vào cuối năm", "Không cần theo dõi", "Ghi chép thủ công hoặc dùng một app đơn giản"], "answer": 3, "hard": False},
        {"id": "q105-06", "prompt": "Cách xem sao kê định kỳ phù hợp với ai nhất?", "choices": ["Người chỉ dùng tiền mặt, không có tài khoản ngân hàng hay ví điện tử nào", "Người không có thu nhập", "Trẻ em", "Người thanh toán không dùng tiền mặt nhiều"], "answer": 3, "hard": False},
        {"id": "q105-07", "prompt": "Mới bắt đầu, nên theo dõi bao nhiêu nhóm?", "choices": ["Một", "Ít nhất 20 nhóm để thật chi tiết ngay từ ngày đầu", "Chỉ 3–5 nhóm lớn", "Từng món riêng lẻ, không gộp nhóm nào cả"], "answer": 2, "hard": True},
        {"id": "q105-08", "prompt": "Theo dõi được khoảng 80–90% chi tiêu thì sao?", "choices": ["Phải bỏ và làm lại từ đầu vào tháng sau", "Sai", "Đã tốt hơn không theo dõi", "Vô ích, phải đủ 100% mới có giá trị sử dụng"], "answer": 2, "hard": True},
        {"id": "q105-09", "prompt": "Chị Mai phát hiện điều gì sau 3 tuần ghi 4 nhóm?", "choices": ["«Khác» và ăn ngoài chiếm nhiều", "Đi lại là khoản duy nhất chị cần cắt bỏ hoàn toàn", "Chị không chi gì cho ăn uống trong suốt ba tuần", "Ổn"], "answer": 0, "hard": False},
        {"id": "q105-10", "prompt": "Lý do phổ biến khiến nhiều người bỏ theo dõi sau 1–2 tuần?", "choices": ["Vì có quá ít khoản chi để ghi lại mỗi ngày", "Do ghi quá chi tiết", "Vì app theo dõi thường tính phí rất cao", "Vì sao kê ngân hàng luôn có sẵn mọi thông tin"], "answer": 1, "hard": True},
        {"id": "q105-11", "prompt": "Khoản nào dễ bị bỏ sót nếu chỉ nhìn theo tháng?", "choices": ["Bữa sáng mỗi ngày của cả nhà", "Tiền xăng xe đi làm hằng tuần", "Khoản chi theo chu kỳ dài", "Hóa đơn điện nước trả đều mỗi tháng"], "answer": 2, "hard": False},
        {"id": "q105-12", "prompt": "Bài học có khuyến nghị một app duy nhất cho mọi người không?", "choices": ["Sổ giấy mới là cách duy nhất hiệu quả", "Có, chỉ nên dùng app của ngân hàng", "Không", "Nên chọn app càng nhiều tính năng càng tốt"], "answer": 2, "hard": False},
    ],
    "N01-06": [
        {"id": "q106-01", "prompt": "Một mục tiêu tài chính đúng cách cần có những yếu tố nào?", "choices": ["Một ước mơ thật lớn", "Cảm hứng nhất thời", "Lời hứa của người bán", "Số tiền cụ thể, thời hạn và lý do rõ ràng"], "answer": 3, "hard": True},
        {"id": "q106-02", "prompt": "Mục tiêu «tiết kiệm 60 triệu» còn thiếu những gì theo bài học?", "choices": ["Thiếu một con số lớn hơn", "Thiếu tên ngân hàng", "Thiếu thời hạn hoàn thành và lý do để làm", "Không thiếu gì cả"], "answer": 2, "hard": True},
        {"id": "q106-03", "prompt": "Ví dụ mục tiêu tốt được nêu trong bài là gì?", "choices": ["Lãi 2% mỗi tháng", "Đủ quỹ 3 tháng chi thiết yếu trong 12 tháng", "Mua xe ngay tuần sau", "Giàu nhanh trong năm nay"], "answer": 1, "hard": False},
        {"id": "q106-04", "prompt": "Thứ tự ưu tiên mục tiêu theo bài học là gì?", "choices": ["Nợ → đầu tư → quỹ", "Quỹ → nợ nguy hiểm → tầng dài hạn", "Đầu tư dài hạn trước, sau đó mới tính đến quỹ dự phòng và các khoản nợ", "Tùy cảm hứng"], "answer": 1, "hard": True},
        {"id": "q106-05", "prompt": "Bạn được mời góp vốn với lời hứa lợi nhuận cố định 2%/tháng. Có nên đặt mục tiêu dựa trên con số đó?", "choices": ["Không — không đặt mục tiêu theo lời hứa lợi suất cố định", "Có, nếu ký hợp đồng", "Có, vì lợi nhuận cố định nghĩa là chắc chắn an toàn, nên tính luôn vào kế hoạch dài hạn của cả nhà", "Được, nếu người mời là bạn thân"], "answer": 0, "hard": True},
        {"id": "q106-06", "prompt": "Bài học khuyên nên có nhiều hay ít mục tiêu cùng lúc?", "choices": ["Theo mục tiêu của bạn bè", "Càng nhiều mục tiêu càng tốt, đặt mười mục tiêu một lúc để có động lực hơn", "Ưu tiên ít mục tiêu cùng lúc", "Không cần mục tiêu nào"], "answer": 2, "hard": False},
        {"id": "q106-07", "prompt": "Bao lâu nên đo tiến độ mục tiêu một lần?", "choices": ["Đo hàng tháng", "Chỉ cần xem lại một lần sau khi đã hết hạn mục tiêu", "Mỗi giờ", "Mười năm một lần là đủ"], "answer": 0, "hard": False},
        {"id": "q106-08", "prompt": "Thấy bạn bè rủ nhau mua vàng, bạn muốn đổi ngay mục tiêu. Bài học nhắc gì?", "choices": ["Đổi mục tiêu mỗi khi thị trường có tin nóng", "Cảm xúc không thay nguyên tắc", "Mượn tiền để mua", "Làm theo đám đông là an toàn nhất trong mọi thời điểm"], "answer": 1, "hard": True},
        {"id": "q106-09", "prompt": "Chưa có quỹ dự phòng nhưng đang nợ thẻ lãi cao và muốn đầu tư. Việc nào đứng đầu?", "choices": ["Bảo hiểm đầu tư trước", "Vay thêm để vừa đầu tư vừa trả nợ cùng lúc", "Xây quỹ trước", "Rót tiền đầu tư ngay để lấy lãi trả nợ thẻ tín dụng nhanh hơn"], "answer": 2, "hard": True},
        {"id": "q106-10", "prompt": "Đã có quỹ 3 tháng, còn nợ thẻ lãi cao. Ưu tiên tiếp theo là gì?", "choices": ["Mở thêm một thẻ tín dụng mới để có hạn mức chi tiêu", "Tiêu thoải mái hơn trước", "Xử lý nợ nguy hiểm", "Dồn toàn bộ phần tiền dư vào cổ phiếu"], "answer": 2, "hard": False},
        {"id": "q106-11", "prompt": "Đầu tư dài hạn nằm ở vị trí nào trong thứ tự ưu tiên?", "choices": ["Trước cả quỹ dự phòng vì càng sớm càng có lãi", "Đứng đầu tiên", "Song song với vay nóng để có thêm vốn ban đầu cho mình", "Sau cùng, khi quỹ và nợ nguy hiểm đã ổn"], "answer": 3, "hard": False},
        {"id": "q106-12", "prompt": "Mục tiêu «đủ quỹ 3 tháng trong 12 tháng» đã có thời hạn chưa?", "choices": ["Có", "Còn thiếu tên ngân hàng sẽ gửi tiền", "Thời hạn phải tính bằng tuần mới đúng", "Chưa, vì không ghi rõ ngày bắt đầu và ngày kết thúc"], "answer": 0, "hard": False},
    ],
    "N01-07": [
        {"id": "q107-01", "prompt": "Lãi kép là gì?", "choices": ["Phí phạt khi rút tiền sớm", "Lãi được trả gấp đôi mỗi năm", "Lãi chỉ tính trên số gốc ban đầu", "Lãi được cộng vào gốc, rồi chính khoản lãi đó lại tiếp tục sinh lãi ở các kỳ sau"], "answer": 3, "hard": True},
        {"id": "q107-02", "prompt": "Giá trị thời gian của tiền nói lên điều gì?", "choices": ["Tiền càng để lâu càng mất hết giá trị", "Một khoản tiền ở hiện tại thường có giá trị hơn cùng khoản đó trong tương lai", "Chỉ ngân hàng mới cần quan tâm", "Mọi thời điểm tiền đều như nhau"], "answer": 1, "hard": True},
        {"id": "q107-03", "prompt": "Trong ẩn dụ quả bóng tuyết, thời gian tương ứng với gì?", "choices": ["Lượng tuyết dính thêm", "Người đẩy quả bóng", "Quả bóng nhỏ ban đầu", "Chiều dài con dốc mà quả bóng có thể lăn qua để lớn dần"], "answer": 3, "hard": False},
        {"id": "q107-04", "prompt": "Vì sao bắt đầu sớm với số tiền nhỏ thường có lợi hơn bắt đầu muộn?", "choices": ["Vì người trẻ luôn được ngân hàng trả lãi suất cao hơn gấp nhiều lần so với người lớn tuổi", "Vì không có rủi ro", "Vì số tiền nhỏ không bị đánh thuế", "Vì lãi kép có nhiều thời gian hơn để phát huy tác dụng"], "answer": 3, "hard": True},
        {"id": "q107-05", "prompt": "Hai người cùng để dành 1 triệu/tháng; A bắt đầu từ 25 tuổi, B từ 35 tuổi. Bài học nói gì?", "choices": ["B chắc chắn hơn A vì người lớn tuổi có kinh nghiệm đầu tư và luôn chọn được kênh lãi cao nhất", "Tốt nhất B ngừng để dành", "Hai người như nhau", "A thường vẫn có lợi thế nhờ thời gian dài hơn"], "answer": 3, "hard": True},
        {"id": "q107-06", "prompt": "Minh họa A và B đúng trong điều kiện nào?", "choices": ["Cần vay thêm để góp", "Lãi suất phải cố định 10%", "Tỷ suất tương đương và không rút gốc giữa chừng", "Chỉ đúng khi cả hai cùng mua một loại cổ phiếu đang tăng giá mạnh trên thị trường hiện nay"], "answer": 2, "hard": False},
        {"id": "q107-07", "prompt": "Vì sao nợ thẻ tín dụng chỉ trả tối thiểu giảm rất chậm?", "choices": ["Vì trả quá nhiều", "Ngân hàng không ghi nhận các khoản trả tối thiểu của khách hàng", "Nợ thẻ không có lãi nên số dư không đổi", "Phần lớn tiền trả bị lãi ăn"], "answer": 3, "hard": True},
        {"id": "q107-08", "prompt": "Điều quan trọng nhất cần nắm về lãi suất tại Việt Nam là gì?", "choices": ["Nắm cơ chế, không phải một tỷ lệ cố định", "Tiết kiệm có lãi suất không bao giờ thay đổi theo thời kỳ", "Cứ chọn lãi cao nhất", "Ghi nhớ một tỷ lệ lãi cố định để áp dụng cho mọi sản phẩm mãi mãi"], "answer": 0, "hard": False},
        {"id": "q107-09", "prompt": "Lãi kép phát huy mạnh khi nào?", "choices": ["Gửi chừng một tuần", "Chọn kênh có lời hứa lợi nhuận cao nhất trên mạng", "Giữ đủ lâu, không rút sớm", "Khi rút ra thường xuyên để tiêu và gửi lại vào cuối năm"], "answer": 2, "hard": False},
        {"id": "q107-10", "prompt": "Có khoản đầu tư nào đảm bảo lợi nhuận kép ổn định mãi mãi?", "choices": ["Không có", "Có, nếu được người quen giới thiệu", "Các gói cam kết lợi nhuận hằng tháng đều đảm bảo", "Khoản nào gửi đủ 30 năm cũng chắc chắn"], "answer": 0, "hard": True},
        {"id": "q107-11", "prompt": "Hiểu lãi kép có nghĩa là nên chạy theo lợi nhuận cao?", "choices": ["Rủi ro sẽ tự biến mất theo thời gian", "Chưa chắc, rủi ro vẫn còn", "Nên, miễn là đầu tư thật lâu năm", "Đúng, vì lãi càng cao thì bóng tuyết càng lớn"], "answer": 1, "hard": False},
        {"id": "q107-12", "prompt": "Vì sao bài học nhắc nợ lãi cao để lâu rất nguy hiểm?", "choices": ["Để lâu ngày thì nợ sẽ được tự xóa", "Theo năm, lãi suất nợ luôn giảm dần đều", "Chuyện nợ không ảnh hưởng đến dòng tiền gia đình", "Do lãi đẻ lãi"], "answer": 3, "hard": False},
    ],
    "N02-01": [
        # GP P0b r2/r3 — mỗi câu 4 lựa chọn, độ dài cân bằng (đáp án đúng dài nhất / nhì / ba / ngắn nhất
        # đúng 3 câu mỗi loại); r3: cách mở đầu lựa chọn đa dạng (không còn mẫu «Không, trừ khi…»), không
        # có gợi ý kiểu «(15 × 3)» — mọi câu trả lời được bằng nội dung bài WA-02-01.
        {"id": "q01a", "prompt": "Quỹ khẩn cấp dùng để làm gì?", "choices": ["Trả các khoản chi tiêu thường ngày trong tháng", "Làm khoản đệm khi mất thu nhập hoặc có sự cố bất ngờ", "Chờ sẵn để mua cổ phiếu khi thị trường giảm", "Dành dụm cho chuyến du lịch cuối năm"], "answer": 1, "hard": False},
        {"id": "q01b", "prompt": "Cổng An Toàn của Welora cần quỹ tối thiểu bao nhiêu tháng chi tiêu thiết yếu?", "choices": ["Một tháng", "Khoảng hai tháng", "Ba tháng", "Mười hai tháng"], "answer": 2, "hard": True},
        {"id": "q01c", "prompt": "Có nên dùng quỹ khẩn cấp để mua đồ đang giảm giá?", "choices": ["Nên, miễn là tháng sau bù lại vào quỹ", "Không, mua sắm không phải sự cố bất ngờ", "Được, nếu món đó giảm hơn một nửa", "Hợp lý, vì mua lúc rẻ cũng là một cách tiết kiệm tiền"], "answer": 1, "hard": False},
        {"id": "q01d", "prompt": "Chi tiêu thiết yếu của bạn khoảng 15 triệu ₫ mỗi tháng. Quỹ tối thiểu để qua Cổng An Toàn là bao nhiêu?", "choices": ["5 triệu ₫", "22,5 triệu ₫", "45 triệu ₫", "150 triệu ₫"], "answer": 2, "hard": True},
        {"id": "q01e", "prompt": "Khoản nào nên tính vào chi tiêu thiết yếu khi đặt mục tiêu quỹ?", "choices": ["Du lịch và mua sắm mùa sale", "Số tiền bạn định đầu tư mỗi tháng", "Quà biếu và tiệc tùng theo sở thích", "Tiền nhà, ăn uống, điện nước, đi lại và học phí cần thiết"], "answer": 3, "hard": False},
        {"id": "q01f", "prompt": "Bắt đầu xây quỹ từ con số 0, cách nào dễ duy trì nhất?", "choices": ["Đợi có khoản thưởng lớn rồi gửi một lần cho đủ", "Tự động chuyển một khoản nhỏ ngay sau ngày nhận lương", "Cuối tháng còn dư bao nhiêu thì gửi bấy nhiêu, tháng nào hết thì thôi", "Vay người thân để có ngay đủ quỹ"], "answer": 1, "hard": False},
        {"id": "q01g", "prompt": "Vì sao nên để quỹ khẩn cấp ở một tài khoản riêng?", "choices": ["Lãi suất ở tài khoản riêng luôn cao nhất", "Quỹ không bị lẫn với tiền tiêu, khỏi lỡ tay tiêu mất", "Quy định bắt buộc phải mở tài khoản riêng cho quỹ", "Tiện rút ra đầu tư mỗi khi có cơ hội, khỏi phải chờ lâu"], "answer": 1, "hard": False},
        {"id": "q01h", "prompt": "Mục đích chính của quỹ khẩn cấp là gì?", "choices": ["Làm vốn đầu tư khi thị trường có cơ hội tốt, rồi nạp lại sau", "Sinh lời nhanh hơn gửi tiết kiệm ngân hàng thông thường", "Giúp bạn (và người phụ thuộc, nếu có) qua lúc có sự cố", "Để dành mua xe mới"], "answer": 2, "hard": True},
        {"id": "q01i", "prompt": "Bạn làm tự do, thu nhập lúc nhiều lúc ít, và quỹ vừa đủ 3 tháng chi thiết yếu. Bước tiếp theo hợp lý là gì?", "choices": ["Dừng góp, vì đã đủ mức của Cổng là xong", "Tiếp tục góp đều, hướng tới khoảng 6 tháng", "Rút bớt quỹ ra đầu tư cho sinh lời", "Chuyển toàn bộ quỹ sang tiêu dùng"], "answer": 1, "hard": True},
        {"id": "q01j", "prompt": "Nhà chỉ có một người tạo ra thu nhập chính. Mục tiêu quỹ khẩn cấp nên thế nào?", "choices": ["Chỉ cần nửa tháng là đủ", "Dày hơn mức 3 tháng", "Không cần quỹ, vì đã có người đi làm", "Đúng 3 tháng, không nên để dư thêm"], "answer": 1, "hard": False},
        {"id": "q01k", "prompt": "Đang xây quỹ thì có người rủ góp vốn «lời chắc 20% mỗi tháng». Bạn nên làm gì?", "choices": ["Góp ngay bằng tiền quỹ kẻo lỡ cơ hội", "Mượn thêm tiền để góp cho được nhiều hơn", "Giữ nguyên quỹ", "Chia đôi: nửa quỹ góp vốn, nửa giữ phòng thân"], "answer": 2, "hard": True},
        {"id": "q01l", "prompt": "Quỹ chưa đủ 3 tháng chi tiêu thiết yếu thì Cổng An Toàn thế nào?", "choices": ["Điểm sức khỏe tài chính cao thì Cổng vẫn ĐẠT", "Cổng chưa ĐẠT cho tới khi quỹ đủ 3 tháng", "Bạn tự xác nhận là ổn thì Cổng mở cho bạn", "Hai tháng là Cổng ĐẠT rồi"], "answer": 1, "hard": True},
    ],
    "N02-02": [
        # GP P0b r2/r3 — 4 lựa chọn, độ dài + cách mở đầu cân bằng; mọi câu trả lời được bằng bài WA-02-02.
        {"id": "q02a", "prompt": "Thấy cơ hội đầu tư ETF hấp dẫn, có được dùng quỹ khẩn cấp không?", "choices": ["Được, nếu chỉ dùng một phần nhỏ", "Cơ hội đầu tư không phải sự cố, nên giữ quỹ", "Nên tranh thủ lúc ETF đang giảm giá sâu", "Hợp lý, vì ETF phân tán rủi ro tốt hơn cổ phiếu riêng lẻ"], "answer": 1, "hard": True},
        {"id": "q02b", "prompt": "Quỹ khẩn cấp nên dùng khi nào?", "choices": ["Khi có cơ hội đầu tư tốt", "Khi mất việc, ốm đau hay sự cố bất ngờ", "Khi muốn đi du lịch", "Khi cửa hàng quen có đợt giảm giá lớn cuối năm"], "answer": 1, "hard": False},
        {"id": "q02c", "prompt": "Rút quỹ khẩn cấp để mua cổ phiếu thì sao?", "choices": ["Ổn, miễn là chắc chắn có lời", "Đó là phá lớp An Toàn", "Tranh thủ được khi giá đang giảm rất sâu", "Chấp nhận được nếu bán ra trong một tháng rồi nạp lại"], "answer": 1, "hard": True},
        {"id": "q02d", "prompt": "Tình huống nào phù hợp để rút quỹ khẩn cấp?", "choices": ["Đặt cọc chuyến du lịch Tết", "Bị cắt giảm thu nhập đột ngột", "Mua điện thoại đời mới khi máy cũ vẫn dùng tốt", "Góp tiền mừng đám cưới đã biết lịch từ lâu"], "answer": 1, "hard": True},
        {"id": "q02e", "prompt": "Theo bài học, trước khi rút quỹ nên tự hỏi hai câu nào?", "choices": ["Bạn bè có làm vậy không, và có đang giảm giá không?", "Việc này có bất ngờ không, và có cần thiết cho sinh hoạt hay đi làm không?", "Khoản này lời không, và có nhanh không?", "Ai sẽ cho mình vay, và lãi vay có cao không?"], "answer": 1, "hard": False},
        {"id": "q02f", "prompt": "Đám cưới của bạn đã lên lịch từ năm ngoái. Nên chuẩn bị tiền thế nào?", "choices": ["Rút quỹ khẩn cấp vì cưới là việc hệ trọng", "Lập quỹ mục tiêu riêng và góp dần", "Vay nóng rồi trả dần", "Dùng quỹ khẩn cấp trước, sau cưới nạp lại sau"], "answer": 1, "hard": False},
        {"id": "q02g", "prompt": "Vừa rút quỹ để lo một ca nằm viện. Việc nên làm tiếp theo là gì?", "choices": ["Đầu tư phần còn lại để gỡ lại nhanh", "Nạp lại cho đủ 3 tháng trước khi nghĩ đến đầu tư", "Khỏi nạp lại, vì quỹ đã dùng xong việc", "Giữ nguyên mức quỹ hiện tại và mở quyền đầu tư như cũ"], "answer": 1, "hard": True},
        {"id": "q02h", "prompt": "Xe máy hỏng nặng, không đi làm được. Dùng quỹ khẩn cấp để sửa thì sao?", "choices": ["Không được, quỹ chỉ dùng khi mất việc", "Dùng quỹ được, vì cần xe đi làm", "Đi vay nóng để giữ nguyên quỹ thì tốt hơn", "Chỉ được nếu sửa hết dưới một triệu đồng"], "answer": 1, "hard": False},
        {"id": "q02i", "prompt": "Tiền trong quỹ «nằm im» khiến bạn thấy tiếc. Cách nghĩ nào đúng?", "choices": ["Đổi ra vàng cho khỏi phí", "Quỹ nằm yên là đang làm đúng việc của nó", "Chuyển hết sang chứng khoán để tiền sinh lời mỗi ngày", "Cho bạn bè vay lấy lãi để tiền khỏi nằm im"], "answer": 1, "hard": False},
        {"id": "q02j", "prompt": "Thị trường giảm mạnh, ai cũng bảo «bắt đáy». Quỹ khẩn cấp thì sao?", "choices": ["Dùng quỹ bắt đáy, có lời thì nạp lại", "Không đụng tới quỹ", "Thử một ít thôi, không dùng hết", "Dồn toàn bộ quỹ vào vì giá đang rẻ hiếm thấy"], "answer": 1, "hard": True},
        {"id": "q02k", "prompt": "Bạn biết trước sang năm phải đóng một khoản học phí lớn. Nên chuẩn bị thế nào?", "choices": ["Đến lúc đóng thì rút quỹ khẩn cấp", "Mở quỹ mục tiêu riêng, góp dần từ bây giờ", "Tính sau, đến đâu hay đến đó", "Quẹt thẻ tín dụng"], "answer": 1, "hard": False},
        {"id": "q02l", "prompt": "Điểm sức khỏe tài chính cao có thay được việc quỹ phải đủ 3 tháng không?", "choices": ["Điểm cao là đủ rồi", "Cổng vẫn cần quỹ đủ 3 tháng, điểm không thay được", "Thay được nếu điểm trên 80", "Quỹ được 2 tháng là đủ"], "answer": 1, "hard": True},
    ],
    "N02-03": [
        {"id": "q203-01", "prompt": "Theo bài học, quỹ khẩn cấp cần hai đặc điểm chính nào?", "choices": ["Càng khó rút càng tốt", "Mức lợi tức càng cao càng tốt", "Thanh khoản cao và tách biệt khỏi tiền chi tiêu hằng ngày", "Nằm chung ví tiêu vặt hằng ngày"], "answer": 2, "hard": True},
        {"id": "q203-02", "prompt": "Nơi giữ quỹ nào phù hợp nhất theo bài học?", "choices": ["Danh mục cổ phiếu tăng trưởng", "Ví điện tử dùng đi chợ", "Một tài khoản riêng, rút được trong vài ngày, không dùng cho chi tiêu", "Sổ tiết kiệm kỳ hạn 5 năm"], "answer": 2, "hard": True},
        {"id": "q203-03", "prompt": "Vì sao không nên để quỹ chung với tiền tiêu hằng ngày?", "choices": ["Tiền sẽ mất giá nhanh hơn", "Ngân hàng cấm việc đó", "Sẽ bị đánh thuế thêm", "Dễ bị tiêu lẫn mất, đến lúc khẩn cấp thì quỹ không còn đủ"], "answer": 3, "hard": False},
        {"id": "q203-04", "prompt": "Có nên đặt quỹ khẩn cấp vào danh mục đầu tư cổ phiếu?", "choices": ["Nên, vì cổ phiếu tăng giá thì quỹ sẽ lớn nhanh hơn và đủ dùng cho mọi tình huống", "Không, quỹ không nằm trong danh mục đầu tư", "Có, nếu chọn mã tốt", "Tùy tâm trạng"], "answer": 1, "hard": True},
        {"id": "q203-05", "prompt": "Khi chọn nơi giữ quỹ, bài học ưu tiên điều gì?", "choices": ["Lợi suất cao nhất trên thị trường, kể cả khi phải chờ nhiều tháng mới rút được", "Gửi kỳ hạn dài", "Lãi suất thật cao", "An toàn và sẵn sàng dùng khi cần"], "answer": 3, "hard": False},
        {"id": "q203-06", "prompt": "Một người giữ quỹ bằng vàng miếng khó bán ở quê. Bài học nhận xét thế nào?", "choices": ["Tốt nhất là chôn vàng", "Chưa ổn: vàng khó bán thì khó dùng ngay khi cần", "Rất tốt, vì vàng luôn tăng giá nên quỹ được bảo vệ hoàn toàn trước mọi rủi ro trong tương lai", "Hợp lý, vì vàng là tài sản"], "answer": 1, "hard": False},
        {"id": "q203-07", "prompt": "Gửi toàn bộ quỹ vào kỳ hạn dài để được lãi cao hơn có ổn không?", "choices": ["Ổn hết", "Tuyệt, rút trước hạn cũng chẳng mất gì đáng kể", "Hoàn toàn ổn, vì lãi càng cao thì quỹ càng an toàn trước mọi biến cố", "Rút gấp sẽ khó khi kỳ hạn dài"], "answer": 3, "hard": True},
        {"id": "q203-08", "prompt": "Bài học nói gì về việc dùng quỹ để tìm lợi suất?", "choices": ["Chuyển quỹ sang kênh lãi cao nhất mỗi khi có cơ hội tốt", "Dùng một nửa quỹ để thử crypto cho vui", "Cứ thoải mái", "Đừng dùng quỹ để tìm lợi suất"], "answer": 3, "hard": True},
        {"id": "q203-09", "prompt": "Crypto có phải nơi giữ quỹ khẩn cấp phù hợp?", "choices": ["Phù hợp nếu chọn đồng đang tăng mạnh nhất", "Sai, không nhốt quỹ vào crypto", "Được, vì crypto giao dịch suốt 24 giờ mỗi ngày", "Chắc chắn"], "answer": 1, "hard": False},
        {"id": "q203-10", "prompt": "«Dễ rút vài ngày» nói về đặc điểm nào của quỹ?", "choices": ["Kỳ hạn gửi càng dài càng tốt", "Tính thanh khoản", "Độ rủi ro khi đầu tư", "Mức sinh lời hằng năm"], "answer": 1, "hard": True},
        {"id": "q203-11", "prompt": "Quỹ khẩn cấp nên được giữ thế nào so với tiền tiêu hằng ngày?", "choices": ["Tách riêng", "Ở thẻ tín dụng", "Trong ví điện tử đi chợ", "Chung ví tiêu vặt"], "answer": 0, "hard": False},
        {"id": "q203-12", "prompt": "Mục đích của quỹ khẩn cấp là sinh lời hay sẵn sàng dùng?", "choices": ["Sẵn sàng dùng", "Để khoe số dư lớn", "Sinh lời tối đa", "Cả hai quan trọng như nhau"], "answer": 0, "hard": False},
    ],
    "N02-05": [
        {"id": "q205-01", "prompt": "Theo bài học, dấu hiệu của nợ nguy hiểm là gì?", "choices": ["Lãi cao, kỳ hạn ngắn, dùng cho tiêu dùng hoặc đầu cơ", "Có hợp đồng rõ ràng", "Vay từ người thân", "Lãi thấp, kỳ hạn dài"], "answer": 0, "hard": True},
        {"id": "q205-02", "prompt": "Khoản nào dưới đây là ví dụ nợ nguy hiểm được nêu trong bài?", "choices": ["Tiền điện nước tháng này", "Mượn sách thư viện", "Hóa đơn internet", "Thẻ tín dụng quay vòng, vay nóng, vay để đầu tư"], "answer": 3, "hard": True},
        {"id": "q205-03", "prompt": "Khi cân nhắc một khoản vay, bài học nhắc dựa vào điều gì?", "choices": ["Lời mời của nhân viên tín dụng", "Bạn bè đều vay", "Hạn mức thẻ còn lại", "Khả năng trả nợ thực tế, không phải cảm xúc lúc đó"], "answer": 3, "hard": False},
        {"id": "q205-04", "prompt": "Cổng An Toàn chưa đạt, có nên vay thêm để đầu tư?", "choices": ["Nên, vì lợi nhuận đầu tư chắc chắn sẽ đủ để trả lãi vay và còn dư thêm rất nhiều", "Tùy cảm hứng", "Được, nếu lãi vay thấp", "Không vay thêm để đầu tư khi Cổng An Toàn chưa đạt"], "answer": 3, "hard": True},
        {"id": "q205-05", "prompt": "Theo bài học, nên ưu tiên giảm loại nợ nào?", "choices": ["Khoản nợ có lãi suất thấp nhất và kỳ hạn dài nhất, vì nó dễ trả xong nhất", "Nợ nguy hiểm, như thẻ quay vòng và vay nóng", "Bất kỳ khoản nào", "Nợ người thân"], "answer": 1, "hard": False},
        {"id": "q205-06", "prompt": "Vay nóng để mua điện thoại mới thuộc loại nợ gì?", "choices": ["Không phải nợ", "Nợ tốt, vì điện thoại là tài sản giúp làm việc và sẽ tăng giá trị theo thời gian", "Nợ an toàn", "Thuộc nợ nguy hiểm: lãi cao, dùng tiêu dùng"], "answer": 3, "hard": False},
        {"id": "q205-07", "prompt": "Mua sắm theo cảm xúc bằng thẻ, chỉ trả tối thiểu và để dư nợ quay vòng: đó là gì?", "choices": ["Chuyện bình thường", "Một dạng nợ nguy hiểm", "Đầu tư cho bản thân, rất đáng làm", "Cách dùng thẻ thông minh để tích điểm thưởng"], "answer": 1, "hard": True},
        {"id": "q205-08", "prompt": "Quyết định vay theo kiểu «thích là mua» có đúng tinh thần bài học?", "choices": ["Ổn nếu khoản vay đó nhỏ hơn một tháng lương", "Rất đúng", "Sai, cần xem khả năng trả", "Đúng, vì cảm xúc giúp ta nhận ra điều mình thật sự cần"], "answer": 2, "hard": True},
        {"id": "q205-09", "prompt": "Mục đích nào khiến một khoản vay bị xếp vào nhóm nguy hiểm?", "choices": ["Sửa nhà bằng khoản vay dài hạn lãi ưu đãi", "Học tập có kế hoạch trả rõ ràng và lãi suất thấp", "Tiêu dùng hoặc đầu cơ", "Đóng học"], "answer": 2, "hard": False},
        {"id": "q205-10", "prompt": "Vay nóng thường có lãi suất thế nào?", "choices": ["Rất cao", "Luôn ưu đãi cho mọi người", "Bằng 0 đồng", "Thấp hơn gửi tiết kiệm"], "answer": 0, "hard": True},
        {"id": "q205-11", "prompt": "Kỳ hạn của nợ nguy hiểm thường ra sao?", "choices": ["Rất dài", "Không có hạn", "Ngắn", "Từ hai mươi năm trở lên"], "answer": 2, "hard": False},
        {"id": "q205-12", "prompt": "Bài học không cho vay thêm để đầu tư khi điều gì chưa đạt?", "choices": ["Mức lương mong muốn", "Cổng An Toàn", "Điểm tín dụng cao nhất có thể", "Số dư thẻ tín dụng"], "answer": 1, "hard": False},
    ],
    "N02-04": [
        {"id": "q204-01", "prompt": "Theo bài học, hai cách trả nợ phổ biến là gì?", "choices": ["Trả món nhỏ trước, hoặc trả món lãi cao trước", "Trả món nào ngân hàng gọi trước", "Chỉ trả phần lãi", "Gom hết vào một khoản vay mới"], "answer": 0, "hard": True},
        {"id": "q204-02", "prompt": "Ưu điểm của cách trả món lãi cao trước là gì?", "choices": ["Giảm tổng chi phí lãi phải trả theo thời gian", "Giảm điểm tín dụng", "Xóa nợ ngay lập tức", "Ngân hàng tặng thưởng"], "answer": 0, "hard": True},
        {"id": "q204-03", "prompt": "Ưu điểm của cách trả món nhỏ trước là gì?", "choices": ["Dễ giữ thói quen nhờ sớm thấy từng khoản được xóa", "Tốn ít lãi nhất mọi lúc", "Không cần theo dõi", "Mở thêm hạn mức"], "answer": 0, "hard": False},
        {"id": "q204-04", "prompt": "Có phương pháp trả nợ nào đúng cho mọi người không?", "choices": ["Có, trả món lãi cao trước luôn là cách duy nhất đúng với tất cả mọi gia đình", "Chẳng có cách nào đúng cho mọi người", "Do ngân hàng quyết định", "Trả món to nhất trước"], "answer": 1, "hard": True},
        {"id": "q204-05", "prompt": "Sau khi chọn một phương pháp, điều quan trọng tiếp theo là gì?", "choices": ["Đổi sang phương pháp khác mỗi tuần để xem cách nào giúp hết nợ nhanh hơn hẳn", "Bỏ qua các khoản nhỏ", "Ngừng trả tối thiểu", "Theo dõi đều đặn và kiên trì với cách đã chọn"], "answer": 3, "hard": False},
        {"id": "q204-06", "prompt": "Vay một khoản mới để đảo nợ cũ khi chưa rõ khả năng trả thì sao?", "choices": ["Càng sớm càng tốt", "Tránh, vì chưa rõ khả năng trả nợ mới", "Tốt, cứ vay", "Rất nên, vì khoản vay mới luôn có lãi thấp hơn và giúp xóa sạch nợ cũ ngay"], "answer": 1, "hard": False},
        {"id": "q204-07", "prompt": "Có nên phá quỹ 3 tháng để đóng một khoản nợ không khẩn?", "choices": ["Nên, quỹ 3 tháng là để dùng cho bất kỳ việc gì", "Được, trả nợ xong rồi tính chuyện xây lại quỹ sau", "Giữ nguyên quỹ 3 tháng", "Phá ngay"], "answer": 2, "hard": True},
        {"id": "q204-08", "prompt": "Anh Hùng có 3 khoản nợ và hay nản. Cách nào giúp anh giữ động lực?", "choices": ["Ưu tiên món nhỏ trước", "Vay thêm một khoản lớn để trả hết một lần cho xong", "Trả tối thiểu rồi chờ thu nhập tăng", "Trốn nợ"], "answer": 0, "hard": True},
        {"id": "q204-09", "prompt": "Chị Lan muốn tốn ít tiền lãi nhất. Bài học gợi ý cách nào?", "choices": ["Mặc kệ", "Mượn khoản lãi cao để trả nợ cũ", "Món nhỏ nhất trước dù lãi thấp hơn nhiều", "Món lãi cao trước"], "answer": 3, "hard": False},
        {"id": "q204-10", "prompt": "Bài học gọi việc vay mới để trả nợ cũ là gì?", "choices": ["Tái đầu tư", "Đảo nợ", "Huy động vốn kinh doanh", "Tiết kiệm thông minh"], "answer": 1, "hard": True},
        {"id": "q204-11", "prompt": "Trả nợ theo cách nào thì cần theo dõi đều?", "choices": ["Khi trả món nhỏ trước thôi", "Một cách nào đó khác", "Cách nào cũng cần", "Riêng cách lãi cao trước"], "answer": 2, "hard": False},
        {"id": "q204-12", "prompt": "Quỹ 3 tháng có được dùng để đóng nợ không khẩn không?", "choices": ["Miễn lãi cao là được", "Không được", "Tùy nợ lớn hay nhỏ", "Dùng tùy ý mình"], "answer": 1, "hard": False},
    ],
    "N02-06": [
        {"id": "q206-01", "prompt": "Bước đầu tiên của kế hoạch trả nợ là gì?", "choices": ["Liệt kê đủ các khoản: số dư, lãi suất và mức trả tối thiểu", "Gom nợ bằng khoản vay mới", "Đổi sang ngân hàng mới", "Ngừng trả tối thiểu"], "answer": 0, "hard": True},
        {"id": "q206-02", "prompt": "Khi trả xong một khoản nợ, nên làm gì với phần tiền trả thêm?", "choices": ["Tiêu hết để tự thưởng", "Chuyển toàn bộ phần trả thêm sang khoản nợ tiếp theo", "Mở thêm thẻ tín dụng", "Giữ lại để mua sắm"], "answer": 1, "hard": True},
        {"id": "q206-03", "prompt": "Hai phương pháp ưu tiên được nhắc trong bài là gì?", "choices": ["Chỉ trả lãi hoặc chỉ trả gốc", "Snowball hoặc Avalanche, chọn một trong hai", "Đảo nợ hoặc vay nóng", "Trả đều mọi khoản"], "answer": 1, "hard": False},
        {"id": "q206-04", "prompt": "Trước khi dồn thêm tiền vào món ưu tiên, phải đảm bảo điều gì?", "choices": ["Đã có thẻ mới", "Đã phá quỹ khẩn cấp", "Vay được một khoản mới đủ lớn để trả hết tất cả các khoản nợ trong cùng một lần", "Đã trả đủ mức tối thiểu của mọi khoản"], "answer": 3, "hard": True},
        {"id": "q206-05", "prompt": "Bước «xác định số tiền trả thêm» nghĩa là gì?", "choices": ["Tính tiền lãi phạt", "Đếm số thẻ", "Ước lượng số tiền có thể vay thêm từ bạn bè và người thân để trả hết nợ ngay", "Tính số tiền có thể trả ngoài mức tối thiểu"], "answer": 3, "hard": False},
        {"id": "q206-06", "prompt": "Bước cuối cùng trong 5 bước là gì?", "choices": ["Đóng toàn bộ tài khoản ngân hàng để không còn tiêu được nữa", "Thôi ghi chép", "Vay mới", "Theo dõi và điều chỉnh định kỳ"], "answer": 3, "hard": False},
        {"id": "q206-07", "prompt": "Có nên phá quỹ khẩn cấp 3 tháng để đóng một khoản nợ không khẩn?", "choices": ["Giữ nguyên quỹ, không phá", "Phá hết", "Nên, trả được nợ sớm thì quỹ không còn cần thiết", "Có, miễn là sau đó cố gắng xây lại quỹ"], "answer": 0, "hard": True},
        {"id": "q206-08", "prompt": "Ai là người quyết định kế hoạch trả nợ của bạn?", "choices": ["Hàng xóm", "Nhân viên ngân hàng nơi bạn vay nhiều nhất", "Agent của Welora quyết thay để tránh sai lầm", "Bạn tự quyết"], "answer": 3, "hard": True},
        {"id": "q206-09", "prompt": "Vai trò của Agent trong kế hoạch trả nợ là gì?", "choices": ["Tự động chuyển tiền trả nợ thay bạn mỗi tháng", "Cho vay", "Chỉ giữ hàng rào An Toàn", "Quyết định khoản nào trả trước, bạn chỉ làm theo"], "answer": 2, "hard": False},
        {"id": "q206-10", "prompt": "Vay mới để đảo nợ khi chưa rõ khả năng trả thì sao?", "choices": ["Làm ngay đi", "Tránh", "Là cách tốt nhất", "Luôn có lợi hơn"], "answer": 1, "hard": True},
        {"id": "q206-11", "prompt": "Có nên dùng quỹ khẩn cấp để đầu tư trong lúc trả nợ?", "choices": ["Để lấy thêm lãi", "Dùng một nửa quỹ", "Được, nếu kênh lãi cao", "Không nên"], "answer": 3, "hard": False},
        {"id": "q206-12", "prompt": "Kế hoạch trả nợ trong bài gồm bao nhiêu bước?", "choices": ["Chỉ 1 bước", "Mười hai bước", "5 bước", "3 bước là đủ"], "answer": 2, "hard": False},
    ],
    "N02-07": [
        {"id": "q207-01", "prompt": "Thứ tự An Toàn giữa quỹ, nợ và đầu tư là gì?", "choices": ["Tùy lợi suất từng năm", "Quỹ 3 tháng → xử nợ nguy hiểm → đầu tư bằng tiền thừa", "Vừa trả nợ vừa vay đầu tư", "Đầu tư trước, quỹ để sau"], "answer": 1, "hard": True},
        {"id": "q207-02", "prompt": "Tiền dùng để đầu tư theo bài học phải là tiền nào?", "choices": ["Phần dành đóng học phí", "Tiền thừa, nằm ngoài quỹ khẩn cấp và ngoài phần trả nợ", "Khoản đang nằm trong quỹ khẩn cấp", "Tiền vay từ thẻ tín dụng"], "answer": 1, "hard": True},
        {"id": "q207-03", "prompt": "Đã có quỹ 3 tháng nhưng còn nợ thẻ quay vòng lãi cao. Bước tiếp theo là gì?", "choices": ["Vay thêm vốn để đầu tư", "Rút bớt quỹ ra đầu tư", "Mua cổ phiếu bằng khoản dư", "Xử lý nợ nguy hiểm trước khi nghĩ đến đầu tư"], "answer": 3, "hard": False},
        {"id": "q207-04", "prompt": "Có nên vay tiền để đầu tư không?", "choices": ["Không vay để đầu tư", "Nên, vì lợi nhuận đầu tư thường cao hơn lãi vay nên vay càng nhiều càng lời", "Hỏi ý bạn bè", "Có, vay ít"], "answer": 0, "hard": True},
        {"id": "q207-05", "prompt": "Một sản phẩm hứa lợi suất cố định 1,5%/tháng. Bài học nói gì?", "choices": ["Mượn tiền mua thêm", "Xuống tiền ngay kẻo lỡ", "Rất đáng tin, vì lợi suất cố định nghĩa là đã được bảo đảm an toàn tuyệt đối, không có rủi ro", "Cảnh giác: không ai được cam kết lợi suất cố định"], "answer": 3, "hard": False},
        {"id": "q207-06", "prompt": "Phá quỹ khẩn để đầu tư khi thấy thị trường tăng có ổn không?", "choices": ["Chưa ổn, không phá quỹ khẩn", "Quá ổn", "Ổn, vì thị trường đang tăng thì cơ hội có lời là rất cao và nhanh", "Phá luôn"], "answer": 0, "hard": False},
        {"id": "q207-07", "prompt": "Ai quyết định cuối cùng việc trả nợ hay đầu tư?", "choices": ["Chính bạn", "Người môi giới đầu tư", "Sếp", "Agent quyết thay bạn"], "answer": 0, "hard": True},
        {"id": "q207-08", "prompt": "Vai trò của Agent theo bài học là gì?", "choices": ["Chỉ giữ hàng rào", "Cho vay", "Quyết định thay bạn mọi việc", "Chọn kênh đầu tư cho bạn"], "answer": 0, "hard": True},
        {"id": "q207-09", "prompt": "Chưa có quỹ 3 tháng, việc nào cần làm đầu tiên?", "choices": ["Xây quỹ 3 tháng", "Đi vay nóng", "Trả hết mọi khoản nợ nhỏ", "Kiếm lời đầu tư rồi xây quỹ"], "answer": 0, "hard": False},
        {"id": "q207-10", "prompt": "Nợ nguy hiểm đứng ở vị trí nào trong thứ tự An Toàn?", "choices": ["Không cần xử lý", "Đứng đầu tiên", "Thứ hai", "Sau đầu tư"], "answer": 2, "hard": True},
        {"id": "q207-11", "prompt": "Đầu tư đứng ở vị trí nào trong thứ tự An Toàn?", "choices": ["Sau cùng", "Ngang với trả nợ", "Ưu tiên số một luôn", "Trước quỹ khẩn"], "answer": 0, "hard": False},
        {"id": "q207-12", "prompt": "Lợi suất cố định được hứa hẹn có nên tin?", "choices": ["Tin tuyệt đối", "Hợp đồng ký rồi thì tin", "Đừng tin", "Nghe là tin ngay"], "answer": 2, "hard": False},
    ],
    "N03-01": [
        # Follow-up item 5 — chuẩn N02 (P0b r2/r3): 12 câu × 4 lựa chọn, 6 câu trọng tâm; độ dài cân bằng (đáp án
        # đúng dài nhất / nhì / ba / ngắn nhất đúng 3 câu mỗi loại), mở đầu đáp án đúng không lặp; mọi câu trả lời
        # được bằng nội dung bài WP-03-01 (bài N03-01 hiển thị). Mỗi lượt KUAT bốc 5 câu (≥ 2 câu trọng tâm), xáo thứ tự lựa chọn.
        {"id": "q301-01", "prompt": "Theo bài học, cốt lõi của tự do tài chính là gì?", "choices": ["Phải nghỉ hưu sớm, không làm gì nữa", "Khả năng lựa chọn", "Đứng tên thật nhiều tài sản, càng nhiều càng tốt bất kể rủi ro", "Giàu có theo chuẩn của xã hội xung quanh"], "answer": 1, "hard": True},
        {"id": "q301-02", "prompt": "Định nghĩa nào đúng với tự do tài chính?", "choices": ["Có mức lương cao", "Vay được một khoản thật lớn từ ngân hàng để đầu tư cho nhanh giàu hơn người khác", "Thu nhập từ tài sản đủ trang trải mức sống bạn mong muốn", "Không bao giờ phải chi tiêu cho bất cứ việc gì"], "answer": 2, "hard": False},
        {"id": "q301-03", "prompt": "Trong ẩn dụ chiếc thuyền, thu nhập từ lao động giống điều gì?", "choices": ["Phải chèo liên tục, ngừng là dừng", "Cánh buồm căng gió đẩy thuyền đi xa", "Dòng nước tự đẩy thuyền đi mà bạn chẳng cần làm gì cả", "Động cơ gắn thêm cho thuyền chạy nhanh"], "answer": 0, "hard": False},
        {"id": "q301-04", "prompt": "Cũng trong ẩn dụ đó, thu nhập từ tài sản giống điều gì?", "choices": ["Cánh buồm hay động cơ giúp thuyền vẫn tiến khi bạn tạm nghỉ chèo", "Một chiếc thuyền khác chạy nhanh hơn rồi bỏ xa bạn", "Mái chèo thứ hai", "Chiếc phao cứu sinh"], "answer": 0, "hard": False},
        {"id": "q301-05", "prompt": "Ba yếu tố then chốt của tự do tài chính là gì?", "choices": ["Vàng, đất nền và các sổ tiết kiệm gửi ở nhiều ngân hàng khác nhau", "Lương, thưởng và phụ cấp", "Chi tiêu, tài sản sinh lời và khoảng cách giữa hai thứ đó", "May mắn, quen biết và một khoản thừa kế thật lớn từ gia đình"], "answer": 2, "hard": True},
        {"id": "q301-06", "prompt": "Mức 1 «An toàn cơ bản» gồm những gì?", "choices": ["Sở hữu vài căn nhà cho thuê", "Thu nhập thụ động đủ cho cả gia đình sống thật thoải mái suốt đời", "Có quỹ khẩn cấp, hết nợ lãi cao, chi tiêu trong tầm kiểm soát", "Đã nghỉ việc và sống hoàn toàn bằng tiền lãi từ một khoản đầu tư lớn"], "answer": 2, "hard": True},
        {"id": "q301-07", "prompt": "Thực tế, phần lớn mọi người tiến tới tự do tài chính như thế nào?", "choices": ["Vay thật nhiều để rút ngắn thời gian", "Đi từng mức một, an toàn trước", "Chờ một tấm vé số trúng độc đắc", "Nhảy thẳng lên nghỉ hưu sớm bằng một khoản đầu tư lớn duy nhất"], "answer": 1, "hard": True},
        {"id": "q301-08", "prompt": "Chưa có quỹ khẩn cấp, bạn được rủ vay tiền đầu tư «cho nhanh tự do». Bài học cảnh báo gì?", "choices": ["Cứ vay ngay kẻo lỡ mất cơ hội hiếm có trong đời", "Rủi ro quá lớn có thể đi ngược mục tiêu tự do", "Vay để đầu tư là con đường ngắn nhất tới tự do, cứ mạnh dạn làm", "Chỉ cần vay ít"], "answer": 1, "hard": True},
        {"id": "q301-09", "prompt": "Tự do tài chính có phải là đích đến đạt một lần rồi xong?", "choices": ["Chắc chắn rồi, vì tài sản luôn tăng giá", "Đúng, đạt rồi thì giữ được mãi", "Không, kế hoạch cần xem lại khi chi tiêu, thị trường hay sức khỏe thay đổi", "Phải, chỉ cần một lần chạm mức 4"], "answer": 2, "hard": True},
        {"id": "q301-10", "prompt": "Có nên lấy mức «đủ» của người khác làm thước đo cho mình?", "choices": ["Có, cứ lấy mức của bạn bè thân làm mục tiêu chung cho cả nhà mình", "Nên, vì chuẩn chung giúp phấn đấu", "Mỗi gia đình hiểu «đủ» khác nhau; so sánh dễ gây áp lực thừa", "Hãy chọn người giàu nhất mình biết để so"], "answer": 2, "hard": False},
        {"id": "q301-11", "prompt": "Một cặp vợ chồng chi khoảng 25 triệu ₫/tháng. Khi nào họ có nhiều lựa chọn hơn về việc làm toàn thời gian?", "choices": ["Khi có 25 triệu ₫ tiền mặt trong tay", "Khi thu từ tài sản, sau rủi ro và thuế, ổn định khoảng 25 triệu ₫ trở lên", "Khi lương tăng lên 30 triệu ₫", "Khi mua được ô tô"], "answer": 1, "hard": False},
        {"id": "q301-12", "prompt": "Mức 3 «Độc lập một phần» nghĩa là gì?", "choices": ["Lương đủ trả mọi khoản chi tiêu hằng tháng", "Toàn bộ chi tiêu của cả gia đình do tiền lãi đầu tư chi trả trong suốt nhiều năm", "Tiết kiệm, đầu tư, kinh doanh phụ gánh được một phần đáng kể chi tiêu", "Không cần làm việc nữa"], "answer": 2, "hard": False},
    ],
    "N03-02": [
        {"id": "q302-01", "prompt": "Theo bài học, tài sản (theo nghĩa tạo dòng tiền) là gì?", "choices": ["Những thứ bỏ tiền vào túi bạn: tạo thu nhập, tăng giá trị hoặc giảm chi phí bền vững", "Vật dụng mới mua gần đây", "Những gì hàng xóm khen", "Mọi thứ đắt tiền bạn đang có"], "answer": 0, "hard": True},
        {"id": "q302-02", "prompt": "Nợ / trách nhiệm (liabilities) được hiểu thế nào trong bài?", "choices": ["Tài sản đứng tên vợ chồng", "Khoản tiền người khác nợ mình", "Món đã trả hết tiền", "Các thứ lấy tiền ra khỏi túi bạn, đòi chi định kỳ hoặc mất giá nhanh"], "answer": 3, "hard": True},
        {"id": "q302-03", "prompt": "Cách phân loại trong bài khác cách kế toán thuần túy ở điểm nào?", "choices": ["Trọng tâm là tác động lên dòng tiền và khả năng lựa chọn dài hạn", "Chỉ tính theo giá mua", "Dựa vào giấy tờ pháp lý", "Bỏ qua hoàn toàn dòng tiền"], "answer": 0, "hard": False},
        {"id": "q302-04", "prompt": "Câu hỏi then chốt bài học đặt ra với mỗi thứ bạn sở hữu là gì?", "choices": ["Giá mua lúc đầu?", "Tôi đang sở hữu bao nhiêu thứ?", "Món đồ này có đắt hơn của bạn bè hay không và có giúp mình được mọi người nể phục?", "Thứ này đưa tiền vào túi tôi, hay đang lấy tiền ra?"], "answer": 3, "hard": True},
        {"id": "q302-05", "prompt": "Trong ẩn dụ hai loại máy, máy loại A giống với gì?", "choices": ["Một chiếc máy chỉ tiêu thụ điện mà không tạo ra gì thêm, càng chạy càng tốn kém hơn", "Khoản nợ tiêu dùng", "Đồ trang trí", "Tài sản tạo thu nhập: càng chạy càng có lợi"], "answer": 3, "hard": False},
        {"id": "q302-06", "prompt": "Chiếc điện thoại mới thường được xếp vào đâu?", "choices": ["Bất động sản", "Khoản tiêu dùng: mất giá nhanh, không tạo dòng tiền", "Tài sản sinh lời, vì điện thoại đời mới luôn bán lại được với giá cao hơn lúc mua ban đầu", "Khoản đầu tư sinh lãi"], "answer": 1, "hard": False},
        {"id": "q302-07", "prompt": "Ngôi nhà để ở có thể đồng thời là tài sản khi nào?", "choices": ["Luôn luôn, vì mọi bất động sản đều là tài sản tạo thu nhập bất kể vay bao nhiêu", "Khi cho thuê một phần hoặc tăng giá trị dài hạn", "Không bao giờ, vì nhà ở chỉ tạo chi phí và chẳng thể nào tăng giá trị được", "Khi sơn lại"], "answer": 1, "hard": True},
        {"id": "q302-08", "prompt": "Xe mua trả góp chỉ để đi lại cá nhân thường nghiêng về phía nào?", "choices": ["Tài sản sinh lời", "Lấy tiền ra: khấu hao, lãi và bảo dưỡng", "Đưa tiền vào túi, vì xe giúp đi làm nhanh hơn nên chắc chắn tăng thu nhập", "Trung lập, vì trả góp lãi 0% thì không tốn thêm đồng nào cả"], "answer": 1, "hard": True},
        {"id": "q302-09", "prompt": "Hai người cùng thu nhập 30 triệu: A trả nợ thẻ rồi tích lũy, B nâng cấp xe và đồ công nghệ. Sau vài năm thường thế nào?", "choices": ["A nghèo hơn", "Cấu trúc tài chính hai người khác biệt rõ", "Hai người như nhau, vì thu nhập ban đầu giống nhau hoàn toàn", "B giàu hơn vì đồ công nghệ mới luôn tăng giá trị theo thời gian"], "answer": 1, "hard": False},
        {"id": "q302-10", "prompt": "Mọi thứ được gọi là «đầu tư» có tự động là tài sản tạo thu nhập không?", "choices": ["Không tự động", "Có, đã gọi là đầu tư là sinh lời", "Đúng, nếu bỏ nhiều tiền", "Chắc chắn là vậy"], "answer": 0, "hard": True},
        {"id": "q302-11", "prompt": "Chi cho sức khỏe, giáo dục, công cụ làm việc có phải luôn «xấu»?", "choices": ["Xấu nếu tốn nhiều tiền", "Lúc nào cũng xấu", "Chưa hẳn", "Đều là nợ cả"], "answer": 2, "hard": False},
        {"id": "q302-12", "prompt": "Cách phân loại tài sản – nợ trong bài là gì?", "choices": ["Mẫu tờ khai thuế bắt buộc", "Bảng kế toán pháp lý", "Quy định của ngân hàng", "Công cụ tư duy"], "answer": 3, "hard": False},
    ],
    "N03-03": [
        {"id": "q303-01", "prompt": "Thu nhập chủ động là gì theo bài học?", "choices": ["Lãi từ sổ tiết kiệm", "Phần cổ tức được chia", "Khoản thuê nhà mỗi tháng", "Thu nhập đòi hỏi trao đổi thời gian và công sức trực tiếp, liên tục"], "answer": 3, "hard": True},
        {"id": "q303-02", "prompt": "Thu nhập thụ động được định nghĩa thế nào?", "choices": ["Khoản thu cần ít tham gia trực tiếp hơn sau giai đoạn xây dựng ban đầu", "Lương làm thêm buổi tối", "Món tiền tự đến mà không cần vốn", "Thưởng cuối năm"], "answer": 0, "hard": True},
        {"id": "q303-03", "prompt": "«Thụ động» có nghĩa là không cần làm gì và không có rủi ro?", "choices": ["Đúng, cứ ngồi không là có tiền", "Chỉ rủi ro khi lười", "Không — hầu hết vẫn cần vốn, thời gian xây dựng, kiến thức và chịu biến động", "Có, nếu chọn đúng kênh"], "answer": 2, "hard": False},
        {"id": "q303-04", "prompt": "Trong ẩn dụ lấy nước, thu nhập thụ động giống điều gì?", "choices": ["Nước đóng chai", "Xách xô ra sông múc nước mỗi ngày, ngừng xách là hết nước dùng cho cả nhà ngay lập tức", "Trận mưa lớn", "Hệ thống dẫn nước: tốn công lúc đầu, sau vẫn cần bảo trì"], "answer": 3, "hard": True},
        {"id": "q303-05", "prompt": "Vì sao không có hệ thống thu nhập nào «bật là quên»?", "choices": ["Thị trường đổi, tài sản hư, khách thuê có thể bỏ đi", "Bởi vì pháp luật Việt Nam cấm mọi hình thức thu nhập không cần làm việc trực tiếp hằng ngày", "Do máy móc hay hỏng", "Vì ai cũng lười"], "answer": 0, "hard": False},
        {"id": "q303-06", "prompt": "Cho thuê nhà được tính là thụ động hơn sau khi trừ những gì?", "choices": ["Chẳng cần trừ gì, tiền thuê nhận được bao nhiêu thì đó chính là thu nhập thụ động bấy nhiêu", "Hóa đơn điện của khách", "Trống phòng, sửa chữa, thuế và công quản lý", "Tiền cọc"], "answer": 2, "hard": False},
        {"id": "q303-07", "prompt": "Hoạt động nào thường bị nhầm là thụ động nhưng thực chất rất chủ động?", "choices": ["Bán online phải livestream, chốt đơn mỗi ngày", "Bản quyền một khóa học đã làm xong, chỉ cần cập nhật nội dung định kỳ", "Gửi tiết kiệm", "Cổ tức từ quỹ đầu tư đã nắm giữ nhiều năm mà không cần theo dõi hằng ngày"], "answer": 0, "hard": True},
        {"id": "q303-08", "prompt": "Lời mời «thu nhập thụ động đảm bảo, không cần vốn, không cần làm gì» nên được nhìn thế nào?", "choices": ["Lựa chọn an toàn nhất vì đã được người giới thiệu cam đoan", "Cơ hội hiếm có, nên tham gia ngay trước khi hết suất ưu đãi", "Dấu hiệu cần hết sức thận trọng", "Rất tốt"], "answer": 2, "hard": True},
        {"id": "q303-09", "prompt": "Trước khi xây nguồn thu thụ động, nền tảng nào thường cần có?", "choices": ["Thật nhiều thời gian rảnh và một nhóm chat chia sẻ mã cổ phiếu hằng ngày", "Xe đời mới", "Một khoản vay lớn để có vốn ngay, càng nhiều đòn bẩy thì càng nhanh có thu nhập", "Quỹ khẩn cấp, kiểm soát nợ, dòng tiền dương"], "answer": 3, "hard": False},
        {"id": "q303-10", "prompt": "Cách nhìn lành mạnh về thu nhập thụ động là gì?", "choices": ["Ngồi không mà vẫn có tiền đều đặn mỗi tháng", "Bỏ việc chính để tập trung săn các nguồn thu nhập dễ", "Xóa sạch mọi nỗ lực làm việc ngay trong năm đầu", "Giảm dần phụ thuộc vào bán giờ lao động"], "answer": 3, "hard": True},
        {"id": "q303-11", "prompt": "Cổ tức từ cổ phiếu / quỹ có được đảm bảo không?", "choices": ["Đảm bảo tăng đều mỗi năm", "Pháp luật luôn bảo đảm", "Có thể giảm hoặc mất", "Được nhà nước bảo hiểm toàn bộ"], "answer": 2, "hard": False},
        {"id": "q303-12", "prompt": "Lãi tiền gửi / trái phiếu sau lạm phát và thuế thường thế nào?", "choices": ["Thấp hơn", "Luôn vượt lạm phát", "Không đổi", "Cao gấp đôi"], "answer": 0, "hard": False},
    ],
    "N03-04": [
        {"id": "q304-01", "prompt": "Theo bài học, đầu tư là gì?", "choices": ["Săn đồ giảm giá", "Dùng tiền hiện tại kỳ vọng tạo giá trị tương lai, kèm khả năng mất một phần hoặc toàn bộ", "Gửi tiết kiệm có lãi cố định", "Cho bạn bè vay lấy lãi"], "answer": 1, "hard": True},
        {"id": "q304-02", "prompt": "Đầu tư khác tiết kiệm ở điểm nào?", "choices": ["Đầu tư luôn an toàn hơn", "Tiết kiệm có rủi ro cao hơn", "Chấp nhận rủi ro để đổi lấy khả năng sinh lời cao hơn trong dài hạn", "Hai việc giống hệt nhau thôi"], "answer": 2, "hard": True},
        {"id": "q304-03", "prompt": "Nguyên tắc 1 nói nên đầu tư bằng tiền nào?", "choices": ["Phần quỹ khẩn cấp", "Hạn mức thẻ tín dụng", "Chỉ tiền có thể chấp nhận biến động hoặc mất, không phải quỹ khẩn cấp hay học phí", "Khoản học phí sắp đóng"], "answer": 2, "hard": False},
        {"id": "q304-04", "prompt": "Nguyên tắc «hiểu cái mình đang mua» nghĩa là gì?", "choices": ["Biết giá mua vào", "Đọc qua tên sản phẩm", "Nắm cơ chế tạo ra lợi nhuận và rủi ro của sản phẩm", "Chọn theo mã được nhiều người trong nhóm chat nhắc đến nhất tuần này để không bỏ lỡ cơ hội"], "answer": 2, "hard": True},
        {"id": "q304-05", "prompt": "Vì sao thời gian có thể là «đối thủ» của nhà đầu tư?", "choices": ["Vì càng giữ lâu thì tài sản nào cũng chắc chắn mất giá và không bao giờ hồi phục được nữa", "Khi bị buộc phải bán đúng lúc giá đang xuống", "Do lãi suất cố định", "Đồng hồ chạy nhanh"], "answer": 1, "hard": False},
        {"id": "q304-06", "prompt": "Lời hứa «lãi cao, không rủi ro» nên được xem thế nào?", "choices": ["Mua ngay", "Xem xét hết sức thận trọng", "Rất đáng tin", "Tin tưởng ngay, vì rủi ro và lợi nhuận không liên quan gì đến nhau"], "answer": 1, "hard": False},
        {"id": "q304-07", "prompt": "Anh Nam có 100 triệu: 40 triệu quỹ khẩn cấp, 30 triệu học phí 8 tháng tới, 30 triệu dài hạn. Phần nào có thể xem xét cho kênh biến động?", "choices": ["Lấy 40 triệu quỹ vì đang nằm yên", "Toàn bộ 100 triệu để tối đa lợi nhuận", "70 triệu", "Riêng 30 triệu dài hạn"], "answer": 3, "hard": True},
        {"id": "q304-08", "prompt": "Vay tiền để đầu tư với kỳ vọng «lãi cao hơn lãi vay» là hành vi gì?", "choices": ["Hành vi cần thận trọng", "Cách đầu tư được bài học khuyến khích mạnh mẽ", "Chiến lược khôn ngoan giúp giàu nhanh không rủi ro", "Bình thường"], "answer": 0, "hard": True},
        {"id": "q304-09", "prompt": "Nguyên tắc 5 nói gì về việc phân bổ tiền đầu tư?", "choices": ["Giữ hết tiền mặt", "Đổi kênh liên tục theo tin tức hằng ngày trên mạng", "Dồn toàn bộ vào một kênh tốt nhất để tối đa lợi nhuận", "Không bỏ tất cả vào một chỗ"], "answer": 3, "hard": False},
        {"id": "q304-10", "prompt": "Lịch sử lợi nhuận có đảm bảo kết quả tương lai?", "choices": ["Có, lãi năm ngoái sẽ lặp lại", "Luôn đúng với cổ phiếu lớn", "Chẳng đảm bảo", "Đảm bảo nếu giữ đủ lâu"], "answer": 2, "hard": True},
        {"id": "q304-11", "prompt": "Mức rủi ro của bài học về đầu tư được ghi là gì?", "choices": ["Cao", "Thấp lắm", "Trung bình thấp", "Bằng không"], "answer": 0, "hard": False},
        {"id": "q304-12", "prompt": "Bài học có khuyến nghị mã cổ phiếu hay kênh cụ thể nào?", "choices": ["Khuyên mua bất động sản", "Một vài mã ngân hàng lớn", "Hoàn toàn không", "Gợi ý vàng và crypto"], "answer": 2, "hard": False},
    ],
    "N03-05": [
        {"id": "q305-01", "prompt": "Đa dạng hóa nhằm mục đích chính gì?", "choices": ["Tránh phải đóng thuế thu nhập", "Chắc chắn lãi cao hơn", "Sở hữu được nhiều mã hot", "Giảm rủi ro tập trung, để một sự kiện xấu không làm tổn hại toàn bộ số tiền"], "answer": 3, "hard": True},
        {"id": "q305-02", "prompt": "Đa dạng hóa có đảm bảo lãi hay loại bỏ hết rủi ro không?", "choices": ["Không, nó chỉ giúp tránh cảnh một cây đổ, cả vườn không còn gì", "Có, chia nhỏ là hết rủi ro", "Bảo đảm không lỗ", "Đảm bảo lãi nếu đủ 10 mã"], "answer": 0, "hard": True},
        {"id": "q305-03", "prompt": "Trong ẩn dụ vận chuyển trứng, đa dạng hóa giống cách nào?", "choices": ["Giao một người chở hết", "Để trứng ở nhà", "Dồn hết vào một giỏ", "Chia trứng vào nhiều giỏ, đi nhiều đường khác nhau"], "answer": 3, "hard": False},
        {"id": "q305-04", "prompt": "Khi nào việc chia nhỏ chỉ là đa dạng hóa trên hình thức?", "choices": ["Mua quá ít mã", "Gửi qua app", "Khi các «giỏ» cùng chung một loại rủi ro", "Lúc số tiền đầu tư dưới 100 triệu vì khi đó chia nhỏ hay không cũng chẳng khác gì nhau"], "answer": 2, "hard": True},
        {"id": "q305-05", "prompt": "Nhiều gói tiết kiệm nhưng cùng một ngân hàng, cùng kỳ hạn thì sao?", "choices": ["Lãi gấp đôi", "Đã đa dạng hóa hoàn hảo vì có nhiều sổ tiết kiệm khác nhau với nhiều số tài khoản riêng", "Rủi ro bằng 0", "Vẫn tập trung, chỉ giảm rủi ro có hạn"], "answer": 3, "hard": False},
        {"id": "q305-06", "prompt": "Bài học khuyên xem xét điều gì khi đa dạng hóa?", "choices": ["Màu biểu đồ", "Sự khác biệt về loại rủi ro, không chỉ khác tên", "Chọn càng nhiều sản phẩm có tên gọi khác nhau càng tốt, bất kể chúng phụ thuộc vào cùng một thứ", "Logo của sản phẩm"], "answer": 1, "hard": False},
        {"id": "q305-07", "prompt": "Quỹ khẩn cấp có nên «đa dạng hóa» vào kênh biến động?", "choices": ["Cứ thế làm", "Giữ riêng, an toàn và thanh khoản", "Nên chia đều quỹ vào cổ phiếu, vàng và crypto", "Được, vì đa dạng hóa giúp quỹ tăng nhanh hơn"], "answer": 1, "hard": True},
        {"id": "q305-08", "prompt": "Chị H. có 200 triệu dùng dài hạn. Chị làm gì theo tinh thần bài học?", "choices": ["Phân thành nhiều phần với mức rủi ro khác nhau", "Vay thêm 200 triệu để dồn toàn bộ vào một dự án lớn", "Gộp hết vào cơ hội đang nóng để không bỏ lỡ thời điểm", "Ngồi yên"], "answer": 0, "hard": True},
        {"id": "q305-09", "prompt": "Đa dạng hóa quá mức có thể gây ra điều gì?", "choices": ["Luôn tốt hơn, càng nhiều khoản nhỏ càng an toàn tuyệt đối", "Tăng chi phí, khó theo dõi", "Không ảnh hưởng gì vì mọi khoản tự quản lý được", "Tiền lãi tăng"], "answer": 1, "hard": False},
        {"id": "q305-10", "prompt": "Vay nợ lớn để tập trung vào một kênh duy nhất là gì?", "choices": ["Đa dạng hóa thông minh", "Chiến lược an toàn tuyệt đối", "Cách giảm rủi ro hiệu quả", "Rủi ro tập trung"], "answer": 3, "hard": True},
        {"id": "q305-11", "prompt": "Nghe nhiều người bảo «đa dạng» có thay được việc hiểu danh mục của mình?", "choices": ["Nghe theo số đông là đủ", "Chẳng thể thay", "Thay được hoàn toàn", "Đúng, nghe nhiều là hiểu"], "answer": 1, "hard": False},
        {"id": "q305-12", "prompt": "Bài học có đưa ra tỷ lệ phân bổ chuẩn?", "choices": ["Chia đều cho năm kênh", "Năm mươi phần trăm cổ phiếu", "Bài không đưa ra", "Tỷ lệ chuẩn là 60/40"], "answer": 2, "hard": False},
    ],
    "N03-06": [
        {"id": "q306-01", "prompt": "Lập kế hoạch hướng tới tự do tài chính gồm những gì?", "choices": ["Vay để đầu tư sớm", "Chọn kênh lãi cao nhất", "Tính một con số nghỉ hưu", "Xác định mức sống mong muốn, ước lượng nguồn lực, đánh giá khoảng cách, rồi đi từng bước"], "answer": 3, "hard": True},
        {"id": "q306-02", "prompt": "Theo bài học, một kế hoạch tốt là gì?", "choices": ["Con số tuyệt đối không đổi", "Mục tiêu càng cao thì càng tốt", "Một lộ trình có thể điều chỉnh, gắn với hoàn cảnh và khẩu vị rủi ro thực tế", "Bản tính sẵn trên mạng"], "answer": 2, "hard": True},
        {"id": "q306-03", "prompt": "Vì sao kế hoạch tự do tài chính thường thất bại?", "choices": ["Bỏ qua bước chuẩn bị hoặc chọn đỉnh quá cao so với nền tảng hiện có", "Không có app riêng", "Thiếu tham vọng", "Đặt mục tiêu quá thấp"], "answer": 0, "hard": False},
        {"id": "q306-04", "prompt": "Trong ẩn dụ leo núi, «giày, nước, bản đồ» tương ứng với gì?", "choices": ["Những món đồ đắt tiền cần mua sắm trước để thể hiện quyết tâm leo lên tới đỉnh núi cao nhất", "Tương ứng quỹ khẩn cấp, kiểm soát nợ, dòng tiền và kiến thức", "Kế hoạch nghỉ hưu", "Một danh mục cổ phiếu"], "answer": 1, "hard": True},
        {"id": "q306-05", "prompt": "Ví dụ mục tiêu giai đoạn 12–24 tháng trong bài là gì?", "choices": ["Đạt mức an toàn vững và bắt đầu đệm linh hoạt", "Nhảy thẳng lên mức độc lập hoàn toàn để có thể nghỉ việc ngay trong năm tới", "Mua nhà ngay", "Nghỉ hưu thật sớm"], "answer": 0, "hard": False},
        {"id": "q306-06", "prompt": "Bao lâu nên review kế hoạch một lần theo khung trong bài?", "choices": ["Mỗi 6–12 tháng, xem lại chi tiêu, thu nhập và giả định", "Chỉ cần xem lại đúng một lần khi đã nghỉ hưu, vì kế hoạch đã lập thì không bao giờ phải thay đổi", "Mười năm", "Mỗi ngày một lần"], "answer": 0, "hard": False},
        {"id": "q306-07", "prompt": "Chưa có quỹ khẩn cấp, còn nợ lãi rất cao mà đã «tính số để nghỉ hưu» thì sao?", "choices": ["Đảo ngược thứ tự ưu tiên", "Hoàn toàn hợp lý nếu dùng công cụ tính trên mạng", "Đúng hướng, vì nghĩ đến nghỉ hưu càng sớm càng tốt", "Rất tốt"], "answer": 0, "hard": True},
        {"id": "q306-08", "prompt": "Các kênh đầu tư phức tạp hơn chỉ nên mở rộng khi nào?", "choices": ["Nền đã vững và hiểu rõ rủi ro", "Ngay khi có người rủ tham gia nhóm đầu tư mới", "Khi thu nhập vừa tăng dù còn nợ lãi rất cao", "Tháng sau"], "answer": 0, "hard": True},
        {"id": "q306-09", "prompt": "Gia đình anh B. theo dõi mỗi quý 3 chỉ số nào?", "choices": ["Quỹ, nợ lãi cao, tỷ lệ tiết kiệm/đầu tư", "Số lượt thích bài đăng khoe tài sản của bạn bè", "Giá vàng, tỷ giá đô la và chỉ số chứng khoán mỗi ngày", "Lương sếp"], "answer": 0, "hard": False},
        {"id": "q306-10", "prompt": "Công cụ tính «bao nhiêu thì đủ» trên mạng có giá trị gì?", "choices": ["Chỉ để minh họa", "Dự báo chính xác cho bạn", "Thay thế hoàn toàn kế hoạch", "Là con số bắt buộc phải đạt được"], "answer": 0, "hard": True},
        {"id": "q306-11", "prompt": "Mọi kế hoạch dài hạn đều dựa trên điều gì có thể sai?", "choices": ["Sự may mắn", "Lời khuyên của bạn bè", "Luật pháp", "Giả định"], "answer": 3, "hard": False},
        {"id": "q306-12", "prompt": "Mục tiêu 5 năm của gia đình anh B. là gì?", "choices": ["Giàu nhất trong cả họ hàng", "Về hưu sớm ngay lập tức", "Sở hữu thêm căn nhà thứ hai", "Linh hoạt nghề nghiệp"], "answer": 3, "hard": False},
    ],
    "N03-07": [
        {"id": "q307-01", "prompt": "Theo bài học, rủi ro khi theo đuổi tự do tài chính là gì?", "choices": ["Thiếu một app quản lý tiền", "Các khả năng khiến kế hoạch bị chậm, bị đảo lộn hoặc đi ngược mục tiêu", "Việc lãi suất tăng nhẹ", "Chỉ là chuyện thua lỗ cổ phiếu"], "answer": 1, "hard": True},
        {"id": "q307-02", "prompt": "Mục đích của việc nhận diện rủi ro là gì?", "choices": ["Làm mình nản và bỏ cuộc", "Tìm kênh lãi cao nhất", "Thiết kế kế hoạch chịu đựng được khi mọi thứ không đúng giả định", "Tránh đầu tư mãi mãi"], "answer": 2, "hard": True},
        {"id": "q307-03", "prompt": "Theo bài học, rủi ro lớn nhất thường là gì?", "choices": ["Bị buộc phải dừng cuộc chơi đúng lúc bất lợi, như bán lúc giá xuống", "Phí giao dịch cao", "Lãi suất tiết kiệm thấp", "Không kiếm đủ tiền lời"], "answer": 0, "hard": False},
        {"id": "q307-04", "prompt": "Người lái xe khôn ngoan trong ẩn dụ lên đèo làm gì?", "choices": ["Đi thật nhanh", "Chọn xe đắt tiền", "Mang xăng dự phòng, không phóng hết tốc lực, biết khi nào dừng", "Tin rằng chuyến đi chắc chắn sẽ không có sự cố nào nên cứ chạy hết tốc lực ở mọi khúc cua cho nhanh"], "answer": 2, "hard": True},
        {"id": "q307-05", "prompt": "FOMO, bán tháo khi sợ, tin «lãi cao không rủi ro» thuộc nhóm rủi ro nào?", "choices": ["Rủi ro thanh khoản của ngân hàng nơi gửi tiền", "Lạm phát", "Pháp lý", "Rủi ro hành vi"], "answer": 3, "hard": False},
        {"id": "q307-06", "prompt": "Tiền nằm ở bất động sản khó bán, kỳ hạn dài thuộc rủi ro nào?", "choices": ["Không rủi ro", "Thanh khoản: khó rút đúng lúc cần", "Rủi ro lạm phát vì bất động sản luôn mất giá nhanh hơn tiền mặt trong mọi giai đoạn", "Rủi ro hành vi"], "answer": 1, "hard": False},
        {"id": "q307-07", "prompt": "Chưa có quỹ khẩn cấp mà đã dồn tiền vào kênh biến động dẫn tới điều gì?", "choices": ["Lợi nhuận nhanh hơn vì không có tiền nằm yên trong quỹ", "Ổn thôi", "Sự cố nhỏ cũng có thể buộc bán lỗ", "An toàn hơn vì tiền đã được đầu tư hết vào thị trường"], "answer": 2, "hard": True},
        {"id": "q307-08", "prompt": "Anh C. rút gần hết đệm an toàn để «tối ưu lợi nhuận». Chuyện gì đã xảy ra?", "choices": ["Gia đình an toàn hơn vì tiền đã sinh lời nhiều hơn trước", "Gặp việc y tế, kế hoạch lùi nhiều năm", "Anh nghỉ hưu sớm hơn dự kiến nhờ lợi nhuận được tối ưu", "Giàu nhanh"], "answer": 1, "hard": True},
        {"id": "q307-09", "prompt": "Kế hoạch giả định thu nhập ổn định mãi, rồi mất việc hoặc ốm đau: đó là rủi ro gì?", "choices": ["Rủi ro từ việc có quá nhiều quỹ khẩn cấp", "Thuế", "Rủi ro tập trung vào một mã cổ phiếu duy nhất", "Thu nhập và sức khỏe"], "answer": 3, "hard": False},
        {"id": "q307-10", "prompt": "Tham gia sản phẩm không hiểu rõ hợp đồng, bên phát hành là rủi ro gì?", "choices": ["Giá vàng giảm", "Tập trung ngành", "Pháp lý", "Sức khỏe gia đình"], "answer": 2, "hard": True},
        {"id": "q307-11", "prompt": "Bài học có muốn bạn sợ hãi và không đầu tư gì cả?", "choices": ["Không", "Có, an toàn là trên hết", "Nên ngừng hết mọi kế hoạch", "Đúng vậy, tránh xa mọi kênh"], "answer": 0, "hard": False},
        {"id": "q307-12", "prompt": "Phần lớn tài sản phụ thuộc một kênh, một ngành là rủi ro gì?", "choices": ["Thanh khoản tốt", "Đa dạng hóa", "Hành vi tích cực", "Tập trung"], "answer": 3, "hard": False},
    ],
    "N04-01": [
        # Follow-up item 5 — chuẩn N02 (P0b r2/r3): 12 câu × 4 lựa chọn, 6 câu trọng tâm; độ dài cân bằng (đáp án
        # đúng dài nhất / nhì / ba / ngắn nhất đúng 3 câu mỗi loại), mở đầu đáp án đúng không lặp; mọi câu trả lời
        # được bằng nội dung bài WP-04-01 (bài N04-01 hiển thị). Mỗi lượt KUAT bốc 5 câu (≥ 2 câu trọng tâm), xáo thứ tự lựa chọn.
        {"id": "q401-01", "prompt": "Theo bài học, bền vững tài chính là gì?", "choices": ["Việc riêng của người đã giàu", "Đạt tự do tài chính tại một thời điểm rồi dừng mọi kế hoạch về sau", "Gom góp thật nhiều trong vài năm đầu", "Khả năng giữ tài chính ổn định qua nhiều giai đoạn của cuộc đời"], "answer": 3, "hard": False},
        {"id": "q401-02", "prompt": "Bền vững khác việc chỉ tập trung tích lũy ở điểm nào?", "choices": ["Chỉ quan tâm đến số dư tài khoản vào cuối mỗi năm tài chính", "Nhấn mạnh khả năng chịu đựng và thích ứng lâu dài", "Bỏ qua mọi kế hoạch cho tuổi già để dồn tiền đầu tư ngay hôm nay", "Không khác gì, chỉ là một cách gọi khác cho hay hơn"], "answer": 1, "hard": True},
        {"id": "q401-03", "prompt": "Ba trụ cột bền vững trong bài học là gì?", "choices": ["Sắm nhà, sắm xe và gửi tiết kiệm thật nhiều trước tuổi bốn mươi", "Lương, thưởng và các khoản phụ cấp", "Tích lũy, đầu tư và tiêu dùng hằng ngày", "Bảo vệ, duy trì và chuyển giao"], "answer": 3, "hard": True},
        {"id": "q401-04", "prompt": "Trụ cột «Bảo vệ» nhằm làm gì?", "choices": ["Giảm thiệt hại từ rủi ro lớn như ốm đau, tai nạn, mất thu nhập", "Giữ tiền khỏi bị người nhà tiêu", "Tìm ra kênh đầu tư có mức lãi cao nhất thị trường để dồn tiền vào", "Bảo đảm tài sản chỉ tăng giá, không bao giờ giảm trong bất kỳ hoàn cảnh nào"], "answer": 0, "hard": False},
        {"id": "q401-05", "prompt": "Trụ cột «Duy trì» chuẩn bị cho giai đoạn nào?", "choices": ["Mùa mua sắm giảm giá", "Lúc vừa được tăng lương", "Kỳ nghỉ cuối năm", "Lúc không còn hoặc giảm thu nhập từ lao động"], "answer": 3, "hard": False},
        {"id": "q401-06", "prompt": "«Chuyển giao» trong bài học gồm những gì?", "choices": ["Kiến thức, giá trị và tài sản, truyền lại có chủ đích", "Tiền mặt để lại sau cùng, không cần trao đổi gì với gia đình", "Số nợ chưa trả", "Riêng phần tài sản đang đứng tên bố mẹ, ngoài ra không có gì khác"], "answer": 0, "hard": True},
        {"id": "q401-07", "prompt": "Trong ẩn dụ khu vườn, An toàn tài chính (Module 02) giống điều gì?", "choices": ["Hàng rào và hệ thống tưới cơ bản", "Một vụ thu hoạch lớn rồi bỏ đất", "Những cây ăn quả mới trồng", "Người sẽ tiếp quản khu vườn"], "answer": 0, "hard": False},
        {"id": "q401-08", "prompt": "Vì sao một khu vườn chỉ lo thu hoạch thật nhiều vài năm rồi bỏ mặc đất là không bền?", "choices": ["Vườn cần sống được qua nhiều mùa, cả khi người làm vườn đã già", "Cây ăn quả sẽ chẳng bao giờ ra trái", "Đất tốt thì tự sinh ra tiền mà chẳng cần ai chăm sóc hay để tâm tới", "Thu hoạch nhiều vốn là việc sai"], "answer": 0, "hard": False},
        {"id": "q401-09", "prompt": "Có cần giàu rồi mới bắt đầu bền vững tài chính?", "choices": ["Phải đợi nghỉ hưu rồi mới bắt đầu tính đến chuyện bền vững", "Cần, vì bền vững là việc của người giàu", "Có, phải có nhà và xe trước đã", "Không, chỉ cần nhìn xa hơn chu kỳ lương tháng này"], "answer": 3, "hard": True},
        {"id": "q401-10", "prompt": "Gia đình đang nuôi con và lo cho cha mẹ già. Việc nào là một bước bền vững thực tế?", "choices": ["Chờ con lớn", "Có bảo hiểm y tế, bảo hiểm phù hợp với rủi ro lớn nhất của nhà mình", "Dồn hết tiết kiệm vào một kênh lãi cao", "Mua ngay căn nhà thứ hai"], "answer": 1, "hard": True},
        {"id": "q401-11", "prompt": "Dạy con về tiền theo tinh thần bền vững nghĩa là gì?", "choices": ["Con xin bao nhiêu thì cho bấy nhiêu, miễn là con thấy vui vẻ", "Để con tự xoay xở khi lớn, vì bố mẹ không cần nói gì về chuyện tiền nong cả", "Dạy thói quen tiền bạc cơ bản thay vì chỉ cho tiền khi cần", "Giấu con mọi chuyện tiền bạc"], "answer": 2, "hard": False},
        {"id": "q401-12", "prompt": "Quyết định về bảo hiểm, thừa kế, chăm sóc dài hạn nên được đưa ra thế nào?", "choices": ["Cứ làm theo đúng lời người bán bảo hiểm tư vấn cho mình", "Quyết thật nhanh cho xong, càng nghĩ lâu càng thêm rối", "Cân nhắc với đủ thông tin, khi cần thì hỏi chuyên gia", "Chép nguyên cách làm của một người quen mà không cần tìm hiểu hoàn cảnh nhà mình"], "answer": 2, "hard": True},
    ],
    "N04-02": [
        {"id": "q402-01", "prompt": "Theo bài học, bảo hiểm là gì?", "choices": ["Sổ tiết kiệm bắt buộc", "Cách để vay tiền dễ hơn", "Công cụ chuyển giao một phần rủi ro tài chính sang tổ chức bảo hiểm, qua việc đóng phí định kỳ", "Một kênh đầu tư sinh lời cao"], "answer": 2, "hard": True},
        {"id": "q402-02", "prompt": "Mục tiêu cốt lõi của bảo hiểm là gì?", "choices": ["Giảm thuế thu nhập hằng năm", "Sinh lời nhiều hơn gửi tiết kiệm", "Tránh để một rủi ro lớn phá hủy toàn bộ kế hoạch tài chính và đời sống gia đình", "Nhận quà tặng khi ký hợp đồng"], "answer": 2, "hard": True},
        {"id": "q402-03", "prompt": "Trong ẩn dụ cơn bão, bảo hiểm giúp được gì?", "choices": ["Báo trước ngày có bão", "Khi bão đến, bạn không mất trắng và không phải bắt đầu lại từ đầu", "Xây nhà chắc hơn", "Làm cơn bão biến mất"], "answer": 1, "hard": False},
        {"id": "q402-04", "prompt": "Nguyên tắc «bảo vệ trước» nói nên ưu tiên rủi ro nào?", "choices": ["Hỏng xe đạp", "Tất cả mọi rủi ro dù nhỏ đến đâu, mua càng nhiều hợp đồng thì gia đình càng an toàn tuyệt đối", "Rủi ro có thể phá hủy, không phải mọi rủi ro nhỏ", "Rủi ro mất điện thoại"], "answer": 2, "hard": True},
        {"id": "q402-05", "prompt": "Trước khi tham gia một sản phẩm, bài học nhắc đọc kỹ những gì?", "choices": ["Quyền lợi, điều khoản loại trừ, thời gian chờ và khả năng đóng phí dài hạn", "Màu sắc tờ rơi", "Tên công ty", "Chỉ cần nghe tư vấn viên nói tóm tắt là đủ, vì hợp đồng bảo hiểm nào cũng giống nhau về quyền lợi và điều khoản"], "answer": 0, "hard": True},
        {"id": "q402-06", "prompt": "Có nên dùng bảo hiểm thay cho quỹ khẩn cấp hay đầu tư?", "choices": ["Có, luôn luôn", "Không, mỗi công cụ một vai trò riêng", "Nên, vì bảo hiểm vừa bảo vệ vừa sinh lời nên có thể thay thế hoàn toàn quỹ và đầu tư", "Tùy công ty"], "answer": 1, "hard": False},
        {"id": "q402-07", "prompt": "Phí bảo hiểm nên được nhìn như thế nào?", "choices": ["Chi càng lớn càng chứng tỏ gia đình an toàn", "Chi phí bảo vệ, nằm trong ngân sách", "Khoản đầu tư chắc chắn có lãi sau mười năm đóng", "Tiền mất"], "answer": 1, "hard": True},
        {"id": "q402-08", "prompt": "Bài học khuyên mua bảo hiểm vì lý do gì?", "choices": ["Được tư vấn viên thuyết phục mạnh mẽ trong buổi gặp đầu tiên", "Đã xác định rõ rủi ro cần chuyển giao", "Bạn bè đều mua nên mình cũng mua cho yên tâm hơn", "Vì quà"], "answer": 1, "hard": True},
        {"id": "q402-09", "prompt": "Gia đình có một trụ cột nuôi 2 con nhỏ: rủi ro nào có thể để lại gánh nặng rất lớn?", "choices": ["Con cái đòi mua đồ chơi mới mỗi tháng", "Mất ví", "Trụ cột mất khả năng lao động", "Giá điện tăng nhẹ vào mùa hè năm nay"], "answer": 2, "hard": False},
        {"id": "q402-10", "prompt": "«Mua càng nhiều bảo hiểm càng an toàn» có luôn đúng?", "choices": ["Đúng nếu còn trẻ", "Chưa chắc", "Càng mua càng lời", "Luôn đúng tuyệt đối"], "answer": 1, "hard": False},
        {"id": "q402-11", "prompt": "Lớp bảo vệ cơ bản bài học nhắc duy trì trước tiên là gì?", "choices": ["Gói đầu tư", "BHYT", "Bảo hiểm xe máy", "Thẻ tín dụng"], "answer": 1, "hard": False},
        {"id": "q402-12", "prompt": "Với sản phẩm kết hợp bảo vệ và tích lũy, cần làm gì?", "choices": ["Bỏ qua phần bảo vệ đi", "Coi tất cả là đầu tư", "Tách bạch hai phần", "Không cần đọc hợp đồng"], "answer": 2, "hard": False},
    ],
    "N04-03": [
        {"id": "q403-01", "prompt": "Chuẩn bị tài chính cho tuổi già là gì?", "choices": ["Mua thật nhiều vàng cất giữ", "Đầu tư một lần cho xong", "Xây nguồn lực để trang trải chi tiêu khi thu nhập lao động giảm hoặc dừng, tính cả y tế và chăm sóc", "Chờ con cái lo hết"], "answer": 2, "hard": True},
        {"id": "q403-02", "prompt": "Mục tiêu của việc chuẩn bị tuổi già theo bài học là gì?", "choices": ["Có nhiều tiền hơn hàng xóm", "Giảm phụ thuộc hoàn toàn vào con cháu và giữ mức sống tối thiểu chấp nhận được", "Nghỉ hưu giàu có theo chuẩn cố định", "Để lại thật nhiều tài sản"], "answer": 1, "hard": True},
        {"id": "q403-03", "prompt": "Vì sao bắt đầu sớm hơn thì gánh nhẹ hơn?", "choices": ["Lúc trẻ thì tiêu ít hơn", "Do lương hưu tăng theo tuổi", "Người trẻ được ưu đãi thuế", "Nhờ thời gian và lãi kép, khoản để dành nhỏ hôm nay có nhiều năm để lớn dần"], "answer": 3, "hard": False},
        {"id": "q403-04", "prompt": "Chi tiêu lúc về già có thể thay đổi thế nào?", "choices": ["Mọi khoản chi đều giảm về gần bằng không vì người già không cần tiêu gì nhiều nữa cả", "Y tế có thể tăng, một số khoản khác có thể giảm", "Tăng gấp mười", "Không đổi gì"], "answer": 1, "hard": True},
        {"id": "q403-05", "prompt": "Bài học nói gì về việc dựa vào một nguồn duy nhất?", "choices": ["Đừng dựa 100% vào lương hưu, con cái hay một khoản", "Chỉ cần lương hưu", "Nên dựa hoàn toàn vào con cái vì đó là truyền thống tốt đẹp và an toàn nhất của mọi gia đình", "Chọn một nguồn tốt nhất"], "answer": 0, "hard": False},
        {"id": "q403-06", "prompt": "Vì sao lương hưu / BHXH không nên là chỗ dựa duy nhất?", "choices": ["Không phải ai cũng có và không phải lúc nào cũng đủ", "Bởi vì lương hưu luôn cao hơn mức chi tiêu thực tế nên chẳng cần chuẩn bị gì thêm", "Thủ tục khó", "Vì nhận chậm"], "answer": 0, "hard": False},
        {"id": "q403-07", "prompt": "Khoản để dành cho «giai đoạn sau 55–60» nên được dùng thế nào?", "choices": ["Giữ lại, không rút cho chi tiêu ngắn hạn", "Rút ra mỗi dịp Tết để mua sắm rồi bù lại sau nếu còn dư", "Dùng trả góp điện thoại mới vì đó cũng là nhu cầu cần thiết", "Tiêu dần"], "answer": 0, "hard": True},
        {"id": "q403-08", "prompt": "Vợ chồng anh/chị H. 42 tuổi đã làm gì?", "choices": ["Vay thêm", "Để dành 2 triệu/tháng, tách khỏi quỹ khác", "Gộp chung khoản để dành với quỹ tiêu dùng cho tiện theo dõi", "Đợi biết chính xác con số cần bao nhiêu rồi mới bắt đầu để dành"], "answer": 1, "hard": True},
        {"id": "q403-09", "prompt": "Tuổi thọ tăng có ý nghĩa gì với kế hoạch tuổi già?", "choices": ["Ít ý nghĩa", "Không cần chuẩn bị vì sẽ làm việc được lâu hơn mãi", "Chi phí y tế chắc chắn giảm mạnh nhờ y học hiện đại", "Giai đoạn sau lao động dài hơn"], "answer": 3, "hard": False},
        {"id": "q403-10", "prompt": "Bao lâu nên review kế hoạch tuổi già?", "choices": ["Không bao giờ cần", "Mỗi vài năm", "Một lần trong cả đời", "Khi đã 70 tuổi"], "answer": 1, "hard": True},
        {"id": "q403-11", "prompt": "Mọi ước tính cho 15–30 năm sau mang tính gì?", "choices": ["Chính xác", "Giả định", "Được bảo đảm", "Bắt buộc đúng"], "answer": 1, "hard": False},
        {"id": "q403-12", "prompt": "Dựa hoàn toàn vào con cái hoặc hoàn toàn vào thị trường thì sao?", "choices": ["Riêng con cái là đủ", "An toàn tuyệt đối", "Đều có rủi ro", "Là cách tốt nhất"], "answer": 2, "hard": False},
    ],
    "N04-04": [
        {"id": "q404-01", "prompt": "Giáo dục tài chính cho con là gì theo bài học?", "choices": ["Dạy con đầu tư cổ phiếu sớm", "Cấm con chạm vào tiền", "Đưa con thật nhiều tiền", "Giúp trẻ hình thành nhận thức, thói quen và kỹ năng về kiếm, tiêu, tiết kiệm, chia sẻ tiền"], "answer": 3, "hard": True},
        {"id": "q404-02", "prompt": "Vì sao dạy con về tiền là một phần của di sản phi vật chất?", "choices": ["Do luật bắt buộc như vậy", "Gia đình để lại khả năng quản lý tiền và tư duy lành mạnh, không chỉ để lại tiền", "Tiền là di sản duy nhất", "Vì trẻ sẽ được thừa kế nhà"], "answer": 1, "hard": True},
        {"id": "q404-03", "prompt": "Trong ẩn dụ dạy đi xe đạp, cách hiệu quả là gì?", "choices": ["Đợi con 18 tuổi mới cho tập", "Không bao giờ cho tập xe", "Cho trẻ 4 tuổi tự đi đường dài", "Bắt đầu với xe nhỏ có bánh phụ, rồi dần bỏ bánh phụ khi con sẵn sàng"], "answer": 3, "hard": False},
        {"id": "q404-04", "prompt": "Trẻ học về tiền nhiều nhất từ đâu?", "choices": ["Từ tivi", "Từ những bài giảng thật dài vào cuối tuần mà cha mẹ chuẩn bị kỹ để giải thích về tiền", "Sách giáo khoa", "Từ việc người lớn làm, không chỉ từ lời nói"], "answer": 3, "hard": True},
        {"id": "q404-05", "prompt": "Với trẻ nhỏ (mầm non – tiểu học sớm), cách nào phù hợp?", "choices": ["Cho chọn một trong hai món trong ngân sách nhỏ", "Giao cho con tự quản lý toàn bộ tiền chợ của gia đình trong một tháng để học cách chi tiêu", "Học về cổ tức", "Mở thẻ tín dụng"], "answer": 0, "hard": False},
        {"id": "q404-06", "prompt": "Với trẻ cuối tiểu học – THCS, bài học gợi ý gì?", "choices": ["Không cho đồng nào", "Cho con vay tiền có tính lãi như ngân hàng để con hiểu cảm giác mắc nợ từ sớm và sợ nợ suốt đời", "Cho tiền khi xin", "Tiền tiêu vặt định kỳ kèm thỏa thuận rõ phạm vi tự quyết"], "answer": 3, "hard": False},
        {"id": "q404-07", "prompt": "Với teen, bài học gợi ý cho con tham gia việc gì?", "choices": ["Đi làm thêm", "Một phần quyết định chi tiêu gia đình đơn giản", "Toàn bộ quyết định đầu tư và vay nợ lớn của cả gia đình từ nay về sau", "Ký thay cha mẹ các hợp đồng vay ngân hàng để con quen dần với giấy tờ pháp lý"], "answer": 1, "hard": True},
        {"id": "q404-08", "prompt": "Nhiều gia đình Việt ngại nói chuyện tiền với con. Bài học khuyên gì?", "choices": ["Chờ con trưởng thành rồi giải thích một lần cho đầy đủ", "Im lặng", "Chỉ đưa tiền khi con xin mà không cần giải thích gì", "Mở lời sớm, ngắn và đều đặn"], "answer": 3, "hard": True},
        {"id": "q404-09", "prompt": "Dùng tiền để thưởng/phạt liên tục có rủi ro gì?", "choices": ["Là cách dạy tài chính tốt nhất được bài học khuyến khích", "Dễ làm lệch động lực nội tại", "Giúp con ngoan ngoãn mãi mãi mà không có tác dụng phụ", "Không gì"], "answer": 1, "hard": False},
        {"id": "q404-10", "prompt": "Đưa áp lực «phải giỏi tiền» quá sớm có thể gây ra gì?", "choices": ["Con giàu nhanh hơn bạn bè", "Chắc chắn giỏi toán hơn", "Tự lập tài chính ngay lập tức", "Lo âu không cần thiết"], "answer": 3, "hard": True},
        {"id": "q404-11", "prompt": "Có một độ tuổi hay cách dạy duy nhất đúng cho mọi nhà không?", "choices": ["Theo sách giáo khoa là đúng", "Không có", "Có, từ 10 tuổi", "Đúng là có một cách"], "answer": 1, "hard": False},
        {"id": "q404-12", "prompt": "Heo đất / lọ tiết kiệm phù hợp với mục tiêu nào của trẻ nhỏ?", "choices": ["Trả nợ cho cha mẹ", "Mua nhà khi lớn", "Mục tiêu ngắn", "Đầu tư dài hạn"], "answer": 2, "hard": False},
    ],
    "N04-05": [
        {"id": "q405-01", "prompt": "Theo bài học, chuẩn bị di sản cần ba việc nào?", "choices": ["Chờ đến khi về già mới tính", "Chia đều tiền cho hàng xóm", "Liệt kê tài sản và nghĩa vụ, ghi rõ người thụ hưởng, để lại hướng dẫn rõ ràng", "Giữ kín mọi thứ trong đầu"], "answer": 2, "hard": True},
        {"id": "q405-02", "prompt": "Câu «di sản không tự xảy ra» nhắc điều gì?", "choices": ["Không cần làm gì cả", "Di sản luôn tự chia đều", "Phải chuẩn bị hướng dẫn rõ ràng trước khi cần đến, không để mặc định", "Nhà nước sẽ lo hết"], "answer": 2, "hard": True},
        {"id": "q405-03", "prompt": "Hướng dẫn rõ ràng về di sản có thể ở dạng nào theo bài học?", "choices": ["Di chúc hoặc thỏa thuận gia đình được ghi rõ ràng", "Tin nhắn trên mạng xã hội", "Ghi chú trong chiếc điện thoại riêng", "Một lời dặn miệng với hàng xóm"], "answer": 0, "hard": False},
        {"id": "q405-04", "prompt": "Cách bắt đầu đơn giản mà bài học gợi ý là gì?", "choices": ["Thuê ngay một công ty luật lớn soạn bộ hồ sơ hàng trăm trang dù tài sản hiện tại còn rất nhỏ và đơn giản", "Chụp ảnh sổ đỏ đăng lên mạng", "Lập danh sách tài khoản và giấy tờ quan trọng, để ở nơi người tin cậy biết", "Giấu giấy tờ thật kỹ"], "answer": 2, "hard": True},
        {"id": "q405-05", "prompt": "Giấy tờ quan trọng nên được để ở đâu?", "choices": ["Trong một chiếc két mà chỉ mình bạn biết mật mã, không ai khác được biết đến bao giờ", "Ở nơi người tin cậy biết và tìm được", "Ngăn kéo bất kỳ", "Trên mạng"], "answer": 1, "hard": False},
        {"id": "q405-06", "prompt": "Khi nào nên cập nhật danh sách tài sản và người thụ hưởng?", "choices": ["Mỗi khi đi chợ", "Không bao giờ cần cập nhật vì danh sách đã lập một lần thì có giá trị mãi mãi về sau", "Mười năm một lần", "Khi có thay đổi lớn: mua nhà, kết hôn, có con"], "answer": 3, "hard": False},
        {"id": "q405-07", "prompt": "Bài học về di sản có phải tư vấn pháp lý không?", "choices": ["Có, có thể dùng thay luật sư trong mọi tình huống", "Đúng, bài học đủ để tự soạn di chúc có hiệu lực", "Chỉ một phần thôi", "Không, đây không phải tư vấn pháp lý"], "answer": 3, "hard": True},
        {"id": "q405-08", "prompt": "Tài sản lớn hoặc tình huống phức tạp thì nên làm gì?", "choices": ["Hỏi ý kiến trong nhóm chat gia đình rồi cứ làm theo", "Để sau", "Tự viết tay một tờ giấy là đủ cho mọi trường hợp", "Gặp luật sư hoặc công chứng"], "answer": 3, "hard": True},
        {"id": "q405-09", "prompt": "Ai quyết định cách sắp xếp di sản của bạn?", "choices": ["Người họ hàng lớn tuổi nhất trong gia đình", "Agent của Welora quyết thay cho chắc chắn", "Ngân hàng", "Bạn tự quyết định"], "answer": 3, "hard": False},
        {"id": "q405-10", "prompt": "Agent đóng vai trò gì trong chủ đề di sản?", "choices": ["Làm chứng trước công chứng", "Giữ nguyên lý An Toàn", "Soạn di chúc thay cho bạn", "Phân chia tài sản cho người thân"], "answer": 1, "hard": True},
        {"id": "q405-11", "prompt": "Ai cần được ghi rõ khi lập kế hoạch di sản?", "choices": ["Nhân viên ngân hàng", "Bạn bè trên mạng", "Những người hàng xóm thân", "Người thụ hưởng"], "answer": 3, "hard": False},
        {"id": "q405-12", "prompt": "Bên cạnh tài sản, cần liệt kê thêm gì?", "choices": ["Nghĩa vụ", "Món ăn yêu thích", "Sở thích riêng", "Lịch sử du lịch"], "answer": 0, "hard": False},
    ],
    "N04-06": [
        {"id": "q406-01", "prompt": "Di sản phi tài chính là gì?", "choices": ["Sổ tiết kiệm đứng tên con", "Vàng cất trong két sắt ở nhà", "Những gì truyền qua thế hệ không đo bằng tiền: giá trị, thói quen, kỹ năng, câu chuyện, uy tín", "Nhà đất để lại cho con"], "answer": 2, "hard": True},
        {"id": "q406-02", "prompt": "Vì sao di sản phi tài chính có thể ảnh hưởng lâu dài hơn một khoản tiền?", "choices": ["Vì nó được miễn thuế", "Nó định hình cách con cháu kiếm, tiêu, tiết kiệm và đối xử với nhau quanh tiền", "Do nó tăng giá theo năm", "Dễ chia đều hơn"], "answer": 1, "hard": True},
        {"id": "q406-03", "prompt": "Trong ẩn dụ túi tiền và la bàn, la bàn giúp con điều gì?", "choices": ["Biết giá vàng mỗi ngày", "Tìm đường tới ngân hàng gần nhất", "Tự định hướng được dù túi tiền có lúc đầy, có lúc vơi", "Tiêu hết tiền nhanh hơn"], "answer": 2, "hard": False},
        {"id": "q406-04", "prompt": "Khi tiền mất hay thị trường đổi, điều gì giúp thế hệ sau xây lại được?", "choices": ["Lời hứa suông", "Một khoản tiền thật lớn gửi ngân hàng mà con cháu không bao giờ được rút ra dùng", "May mắn", "Cách nghĩ và thói quen được truyền tốt"], "answer": 3, "hard": True},
        {"id": "q406-05", "prompt": "Tư duy về tiền như «giữ chữ tín» nên được truyền thế nào?", "choices": ["Treo khẩu hiệu", "Phạt khi sai", "Viết lên tường thật to rồi nhắc đi nhắc lại mỗi bữa cơm cho con thuộc lòng", "Được sống hàng ngày, không chỉ nói"], "answer": 3, "hard": True},
        {"id": "q406-06", "prompt": "Kỹ năng như nấu ăn, sửa chữa, thương lượng giúp gì cho tài chính?", "choices": ["Chẳng liên quan gì đến tiền bạc nên không cần dạy cho con trong gia đình hiện đại", "Giảm chi phí và tăng khả năng tự chủ", "Để khoe", "Tăng lãi suất"], "answer": 1, "hard": False},
        {"id": "q406-07", "prompt": "Theo ví dụ hai gia đình, vì sao con nhà A thường tự chủ tài chính tốt hơn?", "choices": ["Gặp thời", "Con nhà A được học trường quốc tế đắt đỏ hơn", "Nhà A để lại cho con số tiền lớn hơn hẳn nhà B", "Nhà A nói chuyện cởi mở về ngân sách"], "answer": 3, "hard": True},
        {"id": "q406-08", "prompt": "«Chỉ cần dạy con giỏi là đủ, không cần để lại gì» được bài học đánh giá thế nào?", "choices": ["Rất hay", "Hoàn toàn đúng, mọi gia đình nên làm theo như vậy", "Là một cực đoan, thường cần cả hai", "Chính xác tuyệt đối trong mọi hoàn cảnh"], "answer": 2, "hard": True},
        {"id": "q406-09", "prompt": "Đầu tư vào học vấn / nghề nghiệp của con là gì theo bài học?", "choices": ["Khoản chi tiêu lãng phí nên cắt giảm tối đa", "Chuyển giao năng lực tạo thu nhập", "Cách chắc chắn để con giàu có sau khi ra trường", "Món nợ"], "answer": 1, "hard": False},
        {"id": "q406-10", "prompt": "Có nên biến việc truyền giá trị thành áp lực đạo đức nặng nề?", "choices": ["Nên, càng nặng càng tốt", "Tùy theo độ tuổi của con", "Đúng, để con nghe lời", "Tránh điều đó"], "answer": 3, "hard": False},
        {"id": "q406-11", "prompt": "Di sản phi tài chính có thay thế hoàn toàn chuẩn bị tài chính vật chất?", "choices": ["Có, thay thế hoàn toàn", "Không thay thế", "Chỉ khi giàu có", "Thay được một nửa"], "answer": 1, "hard": False},
        {"id": "q406-12", "prompt": "Khi có xung đột quanh tiền, bài học gợi ý mẫu ứng xử nào?", "choices": ["Im lặng rồi giận nhau lâu", "Trách móc thật nặng cho nhớ", "Mỗi người tự xử lý riêng", "Nói rõ, cùng tìm hướng"], "answer": 3, "hard": False},
    ],
    "N04-07": [
        {"id": "q407-01", "prompt": "Sống bền vững với tiền là gì theo bài học?", "choices": ["Tiết kiệm tối đa mọi lúc", "Vừa xây lớp an toàn và mục tiêu dài hạn, vừa không đánh đổi hết sức khỏe, quan hệ, niềm vui hiện tại", "Tiêu hết cho hôm nay", "Đầu tư toàn bộ thu nhập"], "answer": 1, "hard": True},
        {"id": "q407-02", "prompt": "Theo bài học, «bền vững» nằm ở đâu?", "choices": ["Phía tiêu xài thoải mái", "Tùy cảm hứng mỗi ngày", "Ở cực tiết kiệm tối đa", "Vùng giữa có chủ đích: biết mình tối ưu gì và đánh đổi tỉnh táo"], "answer": 3, "hard": True},
        {"id": "q407-03", "prompt": "Trong ẩn dụ balo, balo quá nặng dẫn đến gì?", "choices": ["An toàn tuyệt đối", "Đi nhanh hơn mọi người", "Thiếu nước giữa đường", "Lưng đau, không còn sức ngắm cảnh, thậm chí bỏ cuộc giữa chừng"], "answer": 3, "hard": False},
        {"id": "q407-04", "prompt": "Câu hỏi then chốt bài học đặt ra khi tiết kiệm là gì?", "choices": ["Ai giàu hơn?", "Làm sao để tiết kiệm được nhiều hơn tất cả bạn bè và đồng nghiệp xung quanh trong năm nay", "Mình tiết kiệm vì mục tiêu rõ ràng hay vì sợ hãi?", "Lãi suất bao nhiêu?"], "answer": 2, "hard": True},
        {"id": "q407-05", "prompt": "Phần chi cho trải nghiệm / sức khỏe / mối quan hệ nên được xử lý thế nào?", "choices": ["Ghi thành ngân sách, không phải phần còn lại", "Xài tùy hứng", "Cắt bỏ hết", "Chỉ chi khi cuối tháng còn dư tiền một cách may mắn, còn không thì bỏ qua hoàn toàn"], "answer": 0, "hard": True},
        {"id": "q407-06", "prompt": "«Tận hưởng hôm nay» có phải lý do để phá quỹ khẩn cấp hay tạo nợ lãi cao?", "choices": ["Có, vì sống cho hiện tại quan trọng hơn mọi kế hoạch dài hạn của gia đình mình", "Không, ưu tiên nền vẫn phải giữ vững", "Thỉnh thoảng", "Nên thử"], "answer": 1, "hard": False},
        {"id": "q407-07", "prompt": "Vợ chồng chị K. dành bao nhiêu thu nhập cho tương lai?", "choices": ["5%", "20% thu nhập, vẫn giữ quỹ khẩn cấp", "Không để dành gì vì muốn tận hưởng tuổi trẻ trước", "Toàn bộ thu nhập, không chi cho bất kỳ trải nghiệm nào"], "answer": 1, "hard": True},
        {"id": "q407-08", "prompt": "Ngoài phần cho tương lai, chị K. còn dành khoản cố định cho gì?", "choices": ["Chuyến đi ngắn mỗi quý với cả nhà", "Vé số", "Mua sắm hàng hiệu mỗi tháng để tự thưởng cho bản thân", "Rót thêm tiền vào một mã cổ phiếu đang được bàn tán"], "answer": 0, "hard": True},
        {"id": "q407-09", "prompt": "Bài học khuyên tránh so sánh với ai?", "choices": ["Đồng nghiệp", "Những người chỉ thích khoe tích lũy hay khoe trải nghiệm trên mạng xã hội", "Người chỉ khoe tích lũy hoặc trải nghiệm trên mạng", "Bất kỳ ai, kể cả chính mình của năm ngoái khi đặt mục tiêu"], "answer": 2, "hard": False},
        {"id": "q407-10", "prompt": "Có tỷ lệ vàng cân bằng đúng cho mọi người không?", "choices": ["Tùy hoàn cảnh", "Chia đôi 50/50 là chuẩn", "Theo chuyên gia là có", "Luôn luôn là tỷ lệ 80/20"], "answer": 0, "hard": False},
        {"id": "q407-11", "prompt": "Review định kỳ nên hỏi lại điều gì?", "choices": ["Ứng dụng nào đang hot nhất", "Mục tiêu còn hợp không", "Giá vàng hôm nay ra sao", "Hàng xóm giàu hơn bao nhiêu"], "answer": 1, "hard": False},
        {"id": "q407-12", "prompt": "«Tiết kiệm tối đa» có phải lý do để bỏ bê sức khỏe?", "choices": ["Phải, tiền quan trọng hơn", "Đúng, khi còn trẻ", "Riêng trong vài năm đầu", "Chẳng phải"], "answer": 3, "hard": False},
    ],
    "N05-01": [
        {"id": "q501-01", "prompt": "«Knowing–doing gap» là gì?", "choices": ["Ghét học về tiền bạc", "Thiếu kiến thức tài chính", "Không có thu nhập ổn định hàng tháng", "Đã hiểu nguyên tắc tài chính nhưng vẫn trì hoãn, bỏ dở hoặc không làm nhất quán"], "answer": 3, "hard": True},
        {"id": "q501-02", "prompt": "Theo bài học, hành động tài chính bền vững cần thêm gì ngoài thông tin?", "choices": ["Một khoản vốn lớn ban đầu", "Học thêm thật nhiều sách", "Tải thêm vài ứng dụng", "Mục tiêu đủ rõ, bước đầu đủ nhỏ, môi trường hỗ trợ và cơ chế phản hồi"], "answer": 3, "hard": True},
        {"id": "q501-03", "prompt": "Trong ẩn dụ bơi lội, hành động giống việc gì?", "choices": ["Đọc sách hướng dẫn bơi", "Xem video kỹ thuật bơi lội", "Mua đồ bơi thật đắt", "Xuống hồ, bắt đầu ở vũng nông, có phao nếu cần, lặp lại thành thói quen"], "answer": 3, "hard": False},
        {"id": "q501-04", "prompt": "Cầu nối từ biết sang làm thường là gì?", "choices": ["Nghe thêm podcast", "Một kế hoạch tài chính hoàn hảo cho cả mười năm tới được lập xong ngay trong một buổi tối", "Một hành động nhỏ, rõ, lặp lại được trong 7–14 ngày", "Ý chí sắt đá"], "answer": 2, "hard": True},
        {"id": "q501-05", "prompt": "Ba lý do phổ biến khiến «biết mà không làm» gồm gì?", "choices": ["Mơ hồ mục tiêu, ma sát cao và thiếu phản hồi", "Hết tiền", "Quá bận", "Người đó lười biếng, thiếu ý chí và không thật sự muốn thay đổi cuộc sống tài chính của mình"], "answer": 0, "hard": True},
        {"id": "q501-06", "prompt": "«Ma sát quá cao» trong bài học nghĩa là gì?", "choices": ["Thị trường biến động mạnh khiến giá cổ phiếu đi lên đi xuống thất thường mỗi ngày", "Phí ngân hàng", "Lãi suất cao", "Quy trình phức tạp, nhiều app, đòi hoàn hảo ngay"], "answer": 3, "hard": False},
        {"id": "q501-07", "prompt": "Với mục tiêu «quản lý tài chính tốt hơn», bước thu hẹp khoảng cách thực tế là gì?", "choices": ["Tuần này xem sao kê, ghi 3 nhóm chi lớn", "Tự hứa từ nay sẽ chi tiêu cẩn thận hơn trước nhiều", "Lập ngay bảng tính chi tiết mọi khoản chi trong năm qua", "Đợi đầu năm"], "answer": 0, "hard": True},
        {"id": "q501-08", "prompt": "Thay vì «xây quỹ khẩn cấp 6 tháng» ngay, bước nhỏ là gì?", "choices": ["Vay một khoản đủ sáu tháng chi tiêu để lập quỹ ngay", "Tháng này chuyển 500.000 vào một chỗ riêng", "Chờ đến khi có đủ tiền sáu tháng rồi mới gửi một lần", "Bỏ qua"], "answer": 1, "hard": True},
        {"id": "q501-09", "prompt": "Thay vì tải 3 app cùng lúc, bài học gợi ý gì?", "choices": ["Xóa hết", "Cài thêm app thứ tư để so sánh và chọn cái tốt nhất", "Chọn một cách ghi đơn giản, giữ 2 tuần", "Ghi chép thật chi tiết từng đồng bằng cả ba app"], "answer": 2, "hard": False},
        {"id": "q501-10", "prompt": "Thêm kiến thức khi đã «biết đủ để bắt đầu» đôi khi là gì?", "choices": ["Cách học thông minh nhất", "Bước bắt buộc trước khi làm", "Dấu hiệu sắp giàu", "Trì hoãn tinh vi"], "answer": 3, "hard": False},
        {"id": "q501-11", "prompt": "Welora hỗ trợ bước từ kiến thức sang hành động theo chuỗi nào?", "choices": ["Học hết mọi thứ rồi mới làm", "Đăng ký khóa học đầu tư đắt tiền", "Học, thực hành, áp dụng", "Thấy quảng cáo là đầu tư luôn ngay"], "answer": 2, "hard": False},
        {"id": "q501-12", "prompt": "Không phải mọi trì hoãn đều do «lười». Bài học khuyên gì?", "choices": ["Buông xuôi luôn cho xong", "Trách bản thân thật nhiều", "Nhìn thực tế", "Ép mình làm ngay"], "answer": 2, "hard": False},
    ],
    "N05-02": [
        {"id": "q502-01", "prompt": "Thói quen tài chính là gì theo bài học?", "choices": ["Một lần quyết tâm thật lớn", "Hành vi về tiền lặp lại đủ nhiều trong ngữ cảnh ổn định, ít phụ thuộc vào quyết tâm từng lần", "Ghi chép mọi khoản chi tiêu", "Sở thích đi mua sắm cuối tuần"], "answer": 1, "hard": True},
        {"id": "q502-02", "prompt": "Theo bài học, xây thói quen tài chính dựa vào điều gì?", "choices": ["Phạt bản thân khi quên", "Ý chí vô hạn mỗi ngày", "Ứng dụng đắt tiền nhất nhì", "Thiết kế hành vi: đủ nhỏ, có neo thời điểm, có phản hồi và giảm ma sát"], "answer": 3, "hard": True},
        {"id": "q502-03", "prompt": "Ẩn dụ đánh răng cho thấy điều gì về thói quen?", "choices": ["Gắn vào thời điểm có sẵn và lặp lại để não bớt phải quyết định từ đầu", "Riêng trẻ em mới cần thói quen", "Cần người nhắc suốt đời", "Phải họp nội tâm mỗi tối"], "answer": 0, "hard": False},
        {"id": "q502-04", "prompt": "«Neo» (cue) trong thói quen là gì?", "choices": ["Số dư tài khoản", "Mức phạt thật nặng mà bạn tự đặt ra cho mình nếu lỡ quên không làm đúng kế hoạch", "Lãi suất", "Thời điểm hoặc sự kiện kích hoạt, ví dụ lúc nhận lương"], "answer": 3, "hard": True},
        {"id": "q502-05", "prompt": "Thói quen «quản lý tài chính hoàn hảo» hình thành thế nào?", "choices": ["Gần như không trực tiếp; thói quen nhỏ xếp chồng thì có", "Chỉ cần quyết tâm thật cao trong một tuần đầu tiên là thói quen lớn sẽ tự hình thành mãi mãi", "Ngay lập tức", "Sau một tháng"], "answer": 0, "hard": True},
        {"id": "q502-06", "prompt": "Với thói quen «xem lại chi tiêu», phiên bản đủ nhỏ là gì?", "choices": ["Hỏi bạn bè", "Xem số dư", "Kê lại thật chi tiết từng khoản chi nhỏ nhất mỗi ngày, không được bỏ sót một đồng nào", "Chỉ phân 3 nhóm lớn, trong 15–20 phút"], "answer": 3, "hard": False},
        {"id": "q502-07", "prompt": "Chị H. đặt thói quen nào thay cho «ghi mọi khoản chi mỗi ngày»?", "choices": ["Tối Chủ nhật mở app, ghi nhanh 3 nhóm", "Thuê người khác theo dõi toàn bộ chi tiêu giúp mình", "Bỏ hẳn", "Nhập đầy đủ mọi khoản chi ngay khi vừa trả tiền xong"], "answer": 0, "hard": True},
        {"id": "q502-08", "prompt": "Cố xây quá nhiều thói quen cùng lúc dễ dẫn đến gì?", "choices": ["Giàu", "Thành công nhanh gấp nhiều lần", "Thất bại đồng loạt", "Tiết kiệm được gấp đôi tiền"], "answer": 2, "hard": True},
        {"id": "q502-09", "prompt": "Thói quen dựa trên cảm giác tội lỗi thường thế nào?", "choices": ["Hiệu quả hơn mọi phương pháp khác trong mọi trường hợp", "Rất tốt", "Bền nhất vì nỗi sợ là động lực mạnh mẽ nhất của con người", "Kém bền hơn thói quen gắn mục tiêu rõ"], "answer": 3, "hard": False},
        {"id": "q502-10", "prompt": "Công cụ (app, nhắc nhở) có thay thế việc chọn hành vi đủ nhỏ và có neo?", "choices": ["Thay thế hoàn toàn", "Có, app làm hết", "Miễn có app thật tốt", "Không thay thế"], "answer": 3, "hard": False},
        {"id": "q502-11", "prompt": "Neo gợi ý cho thói quen trả nợ / hóa đơn đúng hạn là gì?", "choices": ["Vào dịp cuối năm âm lịch", "Khi có tin nhắn đòi nợ", "Đợi sau khi quá hạn", "2–3 ngày trước hạn"], "answer": 3, "hard": False},
        {"id": "q502-12", "prompt": "Có một bộ thói quen bắt buộc cho mọi hộ gia đình không?", "choices": ["Theo chuyên gia là có", "Đúng, ba thói quen chuẩn", "Tùy từng nhà", "Bắt buộc với mọi người dân"], "answer": 2, "hard": False},
    ],
    "N05-03": [
        {"id": "q503-01", "prompt": "Theo dõi kế hoạch tài chính là gì?", "choices": ["Đọc tin tức thị trường", "Định kỳ so sánh thực tế thu, chi, số dư quỹ, tiến độ trả nợ và Goal với dự kiến", "Xem số dư mỗi giờ", "Ghi nhật ký cảm xúc"], "answer": 1, "hard": True},
        {"id": "q503-02", "prompt": "Điều chỉnh kế hoạch khác bỏ cuộc ở chỗ nào?", "choices": ["Không có gì khác nhau", "Thay đổi mức đóng góp, thứ tự ưu tiên hoặc mục tiêu khi dữ liệu cho thấy đang lệch", "Bỏ cuộc thì nhẹ nhàng hơn", "Điều chỉnh là giả vờ ổn"], "answer": 1, "hard": True},
        {"id": "q503-03", "prompt": "Theo bài học, theo dõi để làm gì?", "choices": ["Khoe với bạn bè", "Có thông tin kịp thời trước khi lệch trở thành đổ vỡ, không phải để tự trách", "Đủ chỉ tiêu ngân hàng", "Tự trách khi chi sai"], "answer": 1, "hard": False},
        {"id": "q503-04", "prompt": "Trong ẩn dụ lái xe, khi tắc đường bạn làm gì?", "choices": ["Bấm còi liên tục", "Chọn đi đường khác, nghỉ, hoặc chấp nhận đến muộn hơn", "Ngủ trên xe", "Vứt xe lại giữa đường rồi quay về nhà vì kế hoạch ban đầu đã thất bại hoàn toàn"], "answer": 1, "hard": True},
        {"id": "q503-05", "prompt": "Điều chỉnh nên dựa trên điều gì?", "choices": ["Tin đồn", "Lời khuyên mạng", "Vị trí thực tế, không phải vị trí trên giấy", "Cảm xúc của bạn trong ngày hôm đó, càng thay đổi nhiều thì kế hoạch càng linh hoạt"], "answer": 2, "hard": True},
        {"id": "q503-06", "prompt": "Review «hàng tuần (nhẹ)» nên hỏi gì?", "choices": ["Lương bao giờ về?", "Cổ phiếu nào đang tăng mạnh nhất tuần này để mua thêm cho kịp người khác?", "Ai tiêu nhiều nhất?", "Chi tiêu có đang vượt nhóm linh hoạt không?"], "answer": 3, "hard": False},
        {"id": "q503-07", "prompt": "Anh T. bị giảm thu nhập ở tháng thứ 3. Anh đã làm gì?", "choices": ["Vay thêm tiền để vẫn chuyển đủ 2 triệu như kế hoạch cũ", "Giả vờ ổn", "Tạm hạ còn 1 triệu, cắt bớt chi linh hoạt", "Dẹp luôn kế hoạch quỹ khẩn cấp vì không thể đạt như ban đầu"], "answer": 2, "hard": True},
        {"id": "q503-08", "prompt": "Kết quả kế hoạch của anh T. ra sao?", "choices": ["Thất bại hoàn toàn và phải bắt đầu lại từ đầu", "Bị hủy", "Chậm hơn dự kiến nhưng không chết", "Vượt mục tiêu gấp đôi nhờ cắt giảm thật mạnh"], "answer": 2, "hard": True},
        {"id": "q503-09", "prompt": "Theo dõi quá dày và quá chi tiết có thể gây ra gì?", "choices": ["Giàu nhanh hơn người theo dõi thưa", "Vui", "Mệt mỏi và bỏ cuộc", "Kế hoạch chắc chắn thành công hơn"], "answer": 2, "hard": False},
        {"id": "q503-10", "prompt": "Bao lâu nên xem lại mục tiêu còn phù hợp hoàn cảnh không?", "choices": ["Mỗi ngày một lần", "Mười năm mới một lần", "Chỉ khi gặp biến cố", "3–6 tháng"], "answer": 3, "hard": False},
        {"id": "q503-11", "prompt": "Không điều chỉnh gì khi hoàn cảnh đã đổi là gì?", "choices": ["Cứng nhắc có hại", "Cách làm an toàn nhất", "Kỷ luật đáng khen", "Dấu hiệu thành công"], "answer": 0, "hard": False},
        {"id": "q503-12", "prompt": "Điều chỉnh liên tục theo cảm xúc dễ dẫn đến gì?", "choices": ["Linh hoạt tốt hơn nhiều", "Dao động vô hướng", "Đạt mục tiêu sớm hơn", "Tiết kiệm nhanh hơn"], "answer": 1, "hard": False},
    ],
    "N05-04": [
        {"id": "q504-01", "prompt": "Ra quyết định tài chính hàng ngày là gì theo bài học?", "choices": ["Một quyết định đầu tư lớn", "Tập hợp lựa chọn nhỏ về chi tiêu, mua sắm, dùng nợ, chuyển tiền, tích lại quyết định ngân sách", "Việc chọn ngân hàng gửi tiền", "Lập kế hoạch cho mười năm tới"], "answer": 1, "hard": True},
        {"id": "q504-02", "prompt": "Kế hoạch lớn thường thành hoặc bại ở đâu?", "choices": ["Ở tầng quyết định nhỏ lặp lại, không chỉ ở một quyết định lớn hiếm hoi", "Ở lần chọn sản phẩm đầu tư", "Chỉ ở mức lương mỗi tháng", "Do may rủi hoàn toàn"], "answer": 0, "hard": True},
        {"id": "q504-03", "prompt": "Trong ẩn dụ cái xô, một khoản chi nhỏ 20–50 nghìn lặp lại giống gì?", "choices": ["Lỗ thủng nhỏ ở đáy, có thể làm xô không bao giờ đầy dù vẫn đổ thêm", "Không ảnh hưởng gì đến xô", "Nắp đậy giữ nước lại", "Gáo nước đổ vào xô"], "answer": 0, "hard": False},
        {"id": "q504-04", "prompt": "«Có quy tắc trước» trong bài học gồm ví dụ nào?", "choices": ["Hỏi người bán", "Tùy hứng", "Chờ 24–48 giờ với món không cần thiết", "Mua ngay khi thấy sale để không bỏ lỡ, rồi tính lại ngân sách vào cuối tháng sau"], "answer": 2, "hard": True},
        {"id": "q504-05", "prompt": "Cách giảm quyết định lúc mệt / FOMO là gì?", "choices": ["Chiều theo cảm xúc", "Hạn chế xem livestream khi buồn, tắt thông báo sale", "Bật thông báo", "Xem thật nhiều livestream để quen dần và tự nhiên sẽ không còn muốn mua gì nữa cả"], "answer": 1, "hard": True},
        {"id": "q504-06", "prompt": "Theo bài học, quyết định tốt hàng ngày thường đến từ đâu?", "choices": ["Lời khuyên bạn bè", "May mắn", "Ý chí thật mạnh mẽ ở từng khoảnh khắc mà không cần bất kỳ quy tắc hay hỗ trợ nào", "Môi trường và quy tắc, không chỉ ý chí"], "answer": 3, "hard": False},
        {"id": "q504-07", "prompt": "Câu hỏi ngắn nào giúp tách «muốn ngay» và «cần thật»?", "choices": ["Người khác có đang mua món này nhiều trên mạng xã hội không?", "Giá bao nhiêu?", "Món này có đang được giảm giá sâu nhất trong năm hay không?", "Nếu chờ 48 giờ, mình vẫn muốn mua chứ?"], "answer": 3, "hard": True},
        {"id": "q504-08", "prompt": "Anh P. đặt hạn mức chi linh hoạt và kết quả là gì?", "choices": ["Hết tiền", "Chi tiêu tăng vì luôn thấy còn tiền trong app", "Anh từ chối tất cả mọi khoản chi ngoài dự kiến", "Số lần «mua xong rồi hối» giảm rõ"], "answer": 3, "hard": True},
        {"id": "q504-09", "prompt": "Kiểm soát quá mức từng đồng có thể gây ra gì?", "choices": ["Không gì", "Mệt và phản tác dụng", "Sống thoải mái hơn mọi người xung quanh", "Giàu nhanh nhất có thể trong vài năm"], "answer": 1, "hard": False},
        {"id": "q504-10", "prompt": "Mọi khoản chi nhỏ có phải là «lỗ thủng»?", "choices": ["Đúng, tất cả đều là", "Riêng cà phê thôi", "Không hẳn", "Có, phải cắt hết"], "answer": 2, "hard": False},
        {"id": "q504-11", "prompt": "Chuyển tiền giúp người thân ngoài kế hoạch nên được xử lý thế nào?", "choices": ["Vay tiền để giúp", "Giúp hết khả năng", "Từ chối toàn bộ", "Cân nhắc riêng"], "answer": 3, "hard": False},
        {"id": "q504-12", "prompt": "Bài học có đưa danh sách «được phép / cấm» chi tiêu cho mọi người?", "choices": ["Đưa một danh sách chuẩn", "Rất chi tiết từng món", "Chỉ đưa khung", "Cấm hết trừ ăn uống"], "answer": 2, "hard": False},
    ],
    "N05-05": [
        {"id": "q505-01", "prompt": "Cộng đồng tài chính lành mạnh theo bài học là gì?", "choices": ["Sàn bán khóa học làm giàu", "Nhóm cùng mua một mã cổ phiếu", "Nơi khoe lợi nhuận mỗi ngày", "Nhóm cùng chia sẻ kiến thức, kinh nghiệm, câu hỏi và hỗ trợ tinh thần, không phải nơi khoe thu nhập"], "answer": 3, "hard": True},
        {"id": "q505-02", "prompt": "Học hỏi cùng nhau mang lại lợi ích gì?", "choices": ["Được chia lãi từ nhóm", "Không phải tự quyết định", "Chắc chắn giàu nhanh hơn người", "Giảm cô đơn khi đổi thói quen, có góc nhìn mới và duy trì trách nhiệm nhẹ"], "answer": 3, "hard": True},
        {"id": "q505-03", "prompt": "Trong ẩn dụ chạy bộ, nhóm chạy độc hại thường làm gì?", "choices": ["Chạy chậm cùng người mới", "Chia sẻ lịch chạy cùng một giờ", "Khích lệ nhau khi trời mưa", "Chê bai người chậm, ép chạy quá sức, khoe thành tích gây áp lực"], "answer": 3, "hard": False},
        {"id": "q505-04", "prompt": "Cộng đồng lành mạnh chia sẻ kinh nghiệm thế nào?", "choices": ["Khoe lương", "Kể thật cả thất bại, không chỉ khoe chiến thắng", "Giấu thất bại", "Chỉ đăng những khoản lãi lớn nhất để truyền cảm hứng mạnh mẽ cho các thành viên mới vào nhóm"], "answer": 1, "hard": True},
        {"id": "q505-05", "prompt": "Dấu hiệu nào cho thấy một cộng đồng cần thận trọng?", "choices": ["Mọi người hỏi thăm nhau về tiến độ quỹ khẩn cấp mỗi tháng một cách nhẹ nhàng và tôn trọng", "Liên tục khoe lợi nhuận ngắn hạn, giục «all-in»", "Trao đổi sổ tay", "Người mới hỏi bài"], "answer": 1, "hard": True},
        {"id": "q505-06", "prompt": "Lời khuyên từ người lạ trên mạng có phải tư vấn chuyên nghiệp?", "choices": ["Không, không phải tư vấn chuyên nghiệp", "Đúng, nếu người đó có nhiều người theo dõi và hay khoe lợi nhuận cao trên mạng xã hội", "Luôn luôn", "Thường là có"], "answer": 0, "hard": False},
        {"id": "q505-07", "prompt": "Trong nhóm chị N. tham gia, mọi người trao đổi gì?", "choices": ["Tháng này để dành được không, vướng gì", "Giá vàng", "Lương mỗi người bao nhiêu và ai có tài sản lớn nhất nhóm", "Mã cổ phiếu nào sẽ tăng mạnh trong tuần sau để cùng mua"], "answer": 0, "hard": True},
        {"id": "q505-08", "prompt": "Kết quả của chị N. khi tham gia nhóm là gì?", "choices": ["Bỏ quỹ khẩn cấp để chuyển sang đầu tư theo cả nhóm", "Duy trì thói quen lâu hơn tự làm một mình", "Nợ nhiều hơn", "Thu nhập tăng gấp đôi sau ba tháng nhờ tip của nhóm"], "answer": 1, "hard": True},
        {"id": "q505-09", "prompt": "Cộng đồng có thay thế trách nhiệm cá nhân với quyết định tài chính?", "choices": ["Mỗi người vẫn tự chịu trách nhiệm", "Có, nhóm sẽ chịu trách nhiệm thay cho từng thành viên", "Thay thế hoàn toàn nếu nhóm đủ đông và đủ uy tín", "Một phần"], "answer": 0, "hard": False},
        {"id": "q505-10", "prompt": "So sánh thu nhập, tài sản trên mạng xã hội dễ thế nào?", "choices": ["Phản ánh đúng thực tế", "Rất có ích", "Chính xác tuyệt đối", "Méo mó"], "answer": 3, "hard": False},
        {"id": "q505-11", "prompt": "Bán khóa học dưới danh nghĩa «chia sẻ kinh nghiệm» mà thiếu minh bạch là gì?", "choices": ["Cách học nhanh nhất", "Cần thận trọng", "Hoàn toàn bình thường", "Đáng ủng hộ ngay"], "answer": 1, "hard": False},
        {"id": "q505-12", "prompt": "Cộng đồng lành mạnh nhìn hoàn cảnh mỗi người thế nào?", "choices": ["Tôn trọng khác biệt", "So sánh xem ai giỏi hơn", "Ép theo một công thức", "Xấu hổ hóa người đang trả nợ"], "answer": 0, "hard": False},
    ],
    "N05-06": [
        {"id": "q506-01", "prompt": "Công cụ hỗ trợ tài chính cá nhân dùng để làm gì?", "choices": ["Thay bạn ra mọi quyết định", "Khoe thành tích với bạn bè thân", "Tự động làm giàu cho bạn", "Ghi nhận dữ liệu, theo dõi mục tiêu, giảm gánh nặng ghi nhớ và phản hồi kịp thời"], "answer": 3, "hard": True},
        {"id": "q506-02", "prompt": "Hệ thống tốt giúp được gì theo bài học?", "choices": ["Loại bỏ hoàn toàn kỷ luật", "Bảo đảm lợi nhuận đều", "Giảm ma sát và giảm phụ thuộc vào ý chí từng lúc, nhờ đó thói quen dễ duy trì hơn", "Không cần học nguyên tắc"], "answer": 2, "hard": True},
        {"id": "q506-03", "prompt": "Trong ẩn dụ tưới cây, chuông báo và bình nước sẵn giúp gì?", "choices": ["Việc tưới trở thành phản xạ nhẹ nhàng, không phải nhớ và chuẩn bị mỗi lần", "Khỏi cần tưới nữa", "Cây tự lớn nhanh hơn", "Tốn thêm nhiều nước"], "answer": 0, "hard": False},
        {"id": "q506-04", "prompt": "Trong hệ sinh thái Welora, Welorademy đóng vai trò gì?", "choices": ["Nơi luyện tập kiến thức, có cổng KUAT", "Mạng xã hội", "Ví điện tử", "Nơi đầu tư trực tiếp vào cổ phiếu và quỹ được Welora chọn sẵn cho người dùng mới"], "answer": 0, "hard": True},
        {"id": "q506-05", "prompt": "Nguyên tắc chọn công cụ đầu tiên bài học nêu là gì?", "choices": ["Đủ đơn giản để dùng được ngay cả khi mệt", "Được quảng cáo nhiều", "Càng nhiều tính năng càng tốt, kể cả khi bạn không bao giờ dùng đến phần lớn trong số đó", "Đắt nhất"], "answer": 0, "hard": True},
        {"id": "q506-06", "prompt": "Khi nản, có nên nhảy sang công cụ mới?", "choices": ["Có, ngay", "Không, thường là vấn đề thói quen, không phải app", "Tùy app", "Nên, vì mỗi lần đổi app sẽ tạo động lực mới và giải quyết được hết mọi khó khăn cũ"], "answer": 1, "hard": False},
        {"id": "q506-07", "prompt": "Anh K. từng tải 4 app rồi bỏ. Sau đó anh làm gì?", "choices": ["Mua sổ mới", "Tải thêm 3 app khác để so sánh xem cái nào nhiều tính năng hơn hết", "Bỏ hẳn việc theo dõi vì cho rằng mình không hợp với công cụ nào", "Chỉ dùng WeloraOS đặt 2 Goal, review tháng một lần"], "answer": 3, "hard": True},
        {"id": "q506-08", "prompt": "Kết quả của anh K. ra sao?", "choices": ["Giàu lên nhanh chóng nhờ dùng đúng ứng dụng hàng đầu", "Dừng lại sau một tuần vì WeloraOS quá ít tính năng so với bốn app trước", "Thất bại", "Ít tính năng hơn nhưng duy trì được 5 tháng"], "answer": 3, "hard": True},
        {"id": "q506-09", "prompt": "Công cụ có tự làm giàu cho bạn không?", "choices": ["Chắc chắn có nếu chọn được ứng dụng đắt tiền và nổi tiếng nhất", "Dữ liệu đẹp mà thiếu hành vi thì vẫn đứng yên", "Thường có", "Đúng, chỉ cần nhập đủ dữ liệu là tài sản sẽ tự tăng lên theo thời gian"], "answer": 1, "hard": False},
        {"id": "q506-10", "prompt": "Về bảo mật, bài học nhắc gì?", "choices": ["Lưu mật khẩu lên trên mạng", "Dùng chung tài khoản app", "Gửi OTP cho người thân", "Giữ kín OTP, mật khẩu"], "answer": 3, "hard": False},
        {"id": "q506-11", "prompt": "Phụ thuộc quá nhiều vào một app mà không hiểu nguyên tắc dẫn đến gì?", "choices": ["Tiết kiệm thời gian", "An toàn tuyệt đối", "Khó thích ứng", "Lãi suất cao hơn"], "answer": 2, "hard": False},
        {"id": "q506-12", "prompt": "Theo bài học, ai phục vụ ai?", "choices": ["Bạn phải phục vụ công cụ", "Công cụ phục vụ bạn", "Ứng dụng quyết định tất cả", "Hai bên cùng phục vụ lẫn nhau"], "answer": 1, "hard": False},
    ],
    "N05-07": [
        {"id": "q507-01", "prompt": "Duy trì động lực dài hạn trong tài chính là gì?", "choices": ["Không bao giờ nghỉ ngơi", "Khả năng tiếp tục hành vi có ích qua nhiều tháng năm, kể cả khi hứng khởi ban đầu đã hết", "Đạt mục tiêu thật nhanh chóng", "Luôn hào hứng mỗi ngày"], "answer": 1, "hard": True},
        {"id": "q507-02", "prompt": "Theo bài học, động lực thường là gì?", "choices": ["Một cú nước rút thật mạnh", "Áp lực từ người xung quanh", "Hệ thống, ý nghĩa và phản hồi đủ thường xuyên giúp quay lại sau mỗi lần đứt quãng", "Cảm xúc cao trào liên tục mãi"], "answer": 2, "hard": True},
        {"id": "q507-03", "prompt": "Trong ẩn dụ marathon, người về đích thường là ai?", "choices": ["Người có lý do rõ, chia chặng, biết đứng dậy sau khi chậm hoặc nghỉ", "Ai chạy nhanh nhất ở chặng đầu", "Vận động viên hứng khởi nhất lúc đầu", "Bất kỳ ai không bao giờ nghỉ"], "answer": 0, "hard": False},
        {"id": "q507-04", "prompt": "Trụ «chặng nhỏ» khuyên đặt mốc thế nào?", "choices": ["Mốc mỗi giờ", "Chỉ đặt một mốc duy nhất là tự do tài chính hoàn toàn, rồi cố gắng hết sức cho đến khi đạt được", "Bỏ hết mốc", "Mốc 30 ngày, 3 tháng thay vì chỉ mốc tự do tài chính"], "answer": 3, "hard": True},
        {"id": "q507-05", "prompt": "Trụ «quay lại được» nói gì về đứt quãng?", "choices": ["Tự phạt nặng", "Giấu đi", "Coi là bình thường; lần review tới vẫn mở app ra", "Đứt quãng một lần nghĩa là đã thất bại, nên dừng lại và chờ năm sau bắt đầu lại từ đầu"], "answer": 2, "hard": True},
        {"id": "q507-06", "prompt": "Bài học liệt kê điều gì là thực tế làm mất động lực?", "choices": ["So sánh với người khoe trên mạng", "Viết câu vì sao", "Ăn mừng các mốc nhỏ như quỹ đạt một tháng chi tiêu hoặc trả hết một khoản nợ", "Lịch review cố định"], "answer": 0, "hard": False},
        {"id": "q507-07", "prompt": "Khi nản, cách giữ lửa thực dụng là gì?", "choices": ["Ép bản thân làm gấp đôi kế hoạch để bù lại", "Xóa hết mục tiêu cũ và chờ cảm hứng mới tự đến", "Mua sắm", "Đọc lại 1–2 câu «vì sao» đã viết"], "answer": 3, "hard": True},
        {"id": "q507-08", "prompt": "Theo bài học, tốc độ 70% kế hoạch gốc so với bỏ cuộc thế nào?", "choices": ["Bằng nhau", "Vẫn tốt hơn tốc độ 0% vì bỏ cuộc", "Kém hơn vì thà bỏ hẳn còn hơn làm nửa vời", "Tệ như nhau vì đều không đạt kế hoạch ban đầu"], "answer": 1, "hard": True},
        {"id": "q507-09", "prompt": "Lần thứ 4 xây quỹ khẩn cấp, anh V. đã thay đổi gì?", "choices": ["Ngừng review", "Vay một khoản lớn để lập quỹ ngay trong một lần", "Đặt mục tiêu 6 tháng chi tiêu chỉ trong 1 năm cho nhanh", "Đặt mốc 1 tháng chi tiêu trong 4 tháng"], "answer": 3, "hard": False},
        {"id": "q507-10", "prompt": "Động lực có thay được thu nhập thấp đột ngột hay khủng hoảng lớn?", "choices": ["Lúc nào cũng thay được", "Thay được hoàn toàn luôn", "Có, chỉ cần cố thêm", "Không thay được"], "answer": 3, "hard": False},
        {"id": "q507-11", "prompt": "Tự trách nặng sau mỗi lần lệch thường làm gì?", "choices": ["Giúp giữ kỷ luật tốt hơn nhiều", "Tăng động lực thật mạnh mẽ", "Giảm khả năng quay lại", "Chẳng ảnh hưởng gì đáng kể cả"], "answer": 2, "hard": False},
        {"id": "q507-12", "prompt": "Nếu trì hoãn và tuyệt vọng kéo dài ảnh hưởng nặng, bài học khuyên gì?", "choices": ["Tìm hỗ trợ chuyên môn", "Im lặng với tất cả mọi người", "Cố gắng thêm thật nhiều", "Âm thầm chịu đựng một mình"], "answer": 0, "hard": False},
    ],

}

_PROFILES: dict[str, dict[str, Any]] = {}
_REVS: dict[str, int] = {}  # DB revision each cached profile was loaded from / saved as
# follow-up #244/#245 item 10: the DB row's updated_at next to its rev — (rev, updated_at) is the
# version a cached copy is checked against on EVERY read. rev alone was not enough: the demo seed
# (on any worker) deletes / rewrites rows and a re-created row starts again at rev 1, so another
# worker holding "rev 1" kept its stale copy. A row that disappeared (demo seed / «reset tiến độ
# demo») drops the cached copy as well.
_STAMPS: dict[str, Optional[str]] = {}
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
    _STAMPS.clear()
    _BACKFILL_CHECKED.clear()
    _SESSION_LRU.clear()


def _forget(key: str) -> None:
    """Drop every in-process copy of one profile (the next read loads the DB row, if any)."""
    _PROFILES.pop(key, None)
    _REVS.pop(key, None)
    _STAMPS.pop(key, None)
    _BACKFILL_CHECKED.discard(key)
    with _LRU_LOCK:
        _SESSION_LRU.pop(key, None)


def _remember_saved(key: str, rev: Optional[int]) -> None:
    from welora import academy_store as store

    if rev is None:
        return
    _REVS[key] = int(rev)
    ver = store.profile_version(key)
    # a concurrent save in between → keep no stamp, so the next read reloads the newer row
    _STAMPS[key] = ver[1] if ver and ver[0] == int(rev) else None


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
    ver = store.profile_version(user_id)
    if ver is None:
        if user_id in _REVS:  # was persisted, the row is gone (demo seed / reset on any worker)
            _forget(user_id)
        return
    if user_id in _PROFILES and _REVS.get(user_id) == ver[0] and _STAMPS.get(user_id) == ver[1]:
        return
    loaded = store.load_profile_v(user_id)
    if loaded:
        _PROFILES[user_id], _REVS[user_id], _STAMPS[user_id] = loaded


# --- follow-up ticket item 1: demo persona progress per login session ------------------------------
# The partner demo personas P1–P6 are ONE public login shared by every tester. While
# WELORA_GUEST_DEMO is on, a persona's Academy progress (read lessons, KUAT results, XP, badges) is
# kept per login session — the same ``scope_key`` as its open KUAT attempts (#243 / migration 019:
# a hash of the bearer token, never the token) — so a tester never sees another tester's mastery.
# Each session starts from the persona's demo seed (P2 / P3 / P6: N02-01 + N02-02 mastered, from
# the trusted seeded mastery; P1 / P4 / P5: an empty tree). A new login = a fresh seed state.
# Storage: the same ``academy_profiles`` table under the key ``<user_id>#<scope>`` (no migration);
# a row is only written once the session makes progress (views never write), and the persona's
# session rows are dropped whenever the demo seed runs (every deploy). A demo session never writes
# the persona's shared gate mastery (user_flags) — that stays the seeded state for every tester.
# Regular accounts (and every account with WELORA_GUEST_DEMO=0): key = user_id, unchanged.
SESSION_KEY_SEP = "#"


def profile_key(user_id: str, *, session: Optional[str] = None, ip: Optional[str] = None) -> str:
    """Key of the Academy profile a request reads / writes (see above)."""
    from welora import academy_store as store
    from welora.auth import guest_demo_enabled

    if not user_id or SESSION_KEY_SEP in user_id or not guest_demo_enabled():
        return user_id
    scope = store.attempt_scope(user_id, session=session, ip=ip)
    return f"{user_id}{SESSION_KEY_SEP}{scope}" if scope else user_id


def _base_uid(key: str) -> str:
    return key.split(SESSION_KEY_SEP, 1)[0]


def is_session_key(key: str) -> bool:
    return SESSION_KEY_SEP in (key or "")


def _demo_start_state(user_id: str) -> dict[str, Any]:
    """The persona's demo seed state (as ``seed_profile`` writes it): gate path mastered when the
    persona's server-written mastery is ≥ apply, else an empty tree."""
    from welora.goals_api import effective_mastery_state
    from welora.mastery import _RANK, GATE_MIN

    p = _normalise({})
    if _RANK.get(str(effective_mastery_state(user_id) or ""), 0) >= _RANK[GATE_MIN]:
        _mark_gate_path_mastered(p)
    else:
        _refresh_locks(p)
    return p


# --- follow-up #244/#245 item 9: bounded cache of demo SESSION profiles -----------------------------
# Every demo login is its own profile key, so the in-process cache would grow with every tester
# session. Session keys are kept in an LRU of WELORA_ACADEMY_SESSION_CACHE_MAX entries (default 512,
# min 16); the least recently used one is evicted. Safe because a session's progress is saved to the
# DB on every change (and a never-saved session is just the persona's seed state, rebuilt on demand);
# the in-memory store (no DB, local dev only) never evicts. Regular accounts are not affected.
import threading as _threading
from collections import OrderedDict as _OrderedDict

_SESSION_LRU: "_OrderedDict[str, None]" = _OrderedDict()
_LRU_LOCK = _threading.Lock()


def session_cache_max() -> int:
    import os

    try:
        v = int(str(os.environ.get("WELORA_ACADEMY_SESSION_CACHE_MAX", "")).strip() or 512)
    except ValueError:
        v = 512
    return max(16, v)


def _touch_session(key: str) -> None:
    from welora import academy_store as store

    if not is_session_key(key):
        return
    evict: list[str] = []
    with _LRU_LOCK:
        _SESSION_LRU[key] = None
        _SESSION_LRU.move_to_end(key)
        if store.use_db_profiles():
            while len(_SESSION_LRU) > session_cache_max():
                old, _ = _SESSION_LRU.popitem(last=False)
                evict.append(old)
    for old in evict:
        _PROFILES.pop(old, None)
        _REVS.pop(old, None)
        _STAMPS.pop(old, None)
        _BACKFILL_CHECKED.discard(old)


def session_cache_size() -> int:
    return sum(1 for k in list(_PROFILES) if is_session_key(k))


def _profile(user_id: str) -> dict[str, Any]:
    _sync_from_db(user_id)
    if is_session_key(user_id) and user_id not in _PROFILES:
        _PROFILES[user_id] = _demo_start_state(_base_uid(user_id))  # saved on the first progress
        _BACKFILL_CHECKED.add(user_id)
    p = _normalise(_PROFILES.setdefault(user_id, {}))
    if user_id not in _BACKFILL_CHECKED:
        p = _backfill_from_mastery(user_id, p)
    _touch_session(user_id)
    return p


# --- migration-019 ticket items 4 + 6: Academy progress consistent with the gate mastery ----------
# The gate mastery (user_flags.mastery_no_efund_invest ≥ apply) is earned by passing N02-02, which
# needs N02-01 passed first. Users who passed before migration 017 (progress was in memory only) and
# the seeded demo personas have the mastery but an empty Academy profile (xp 0, N02-01 not_started).
# Read-time backfill (DB store only, once per process per user): a TRUSTED server-written mastery
# (source academy or seed — never a legacy self-set row) ≥ apply → N02-01 + N02-02 mastered with
# their XP and badges, as a pass would have done. It only ever ADDS progress (never lowers a node,
# never touches the mastery flag) and writes with an optimistic revision check, so a concurrent
# save on another instance is never overwritten. Idempotent: a backfilled profile has both nodes
# mastered and is left alone.
GATE_PATH_NODES = ("N02-01", "N02-02")
BACKFILL_SOURCES = ("academy", "seed")
_BACKFILL_CHECKED: set[str] = set()


def _mark_gate_path_mastered(p: dict[str, Any]) -> bool:
    from welora.mastery import _RANK, GATE_MIN

    changed = False
    for nid in GATE_PATH_NODES:
        st = p["nodes"][nid]
        if st.get("status") != STATUS_MASTERED:
            st["status"] = STATUS_MASTERED
            changed = True
        if _RANK.get(str(st.get("mastery_level") or "not_started"), 0) < _RANK[GATE_MIN]:
            st["mastery_level"] = GATE_MIN
            changed = True
        if nid not in p["awarded_xp"]:
            p["xp"] = int(p["xp"]) + XP_PER_PASS
            p["awarded_xp"].append(nid)
            changed = True
    _refresh_locks(p)
    _refresh_badges(p)
    return changed


def _gate_path_mastered(p: dict[str, Any]) -> bool:
    return all(p["nodes"][nid].get("status") == STATUS_MASTERED for nid in GATE_PATH_NODES)


def _trusted_gate_mastery(user_id: str) -> bool:
    from welora.db.repos import get_user_flags_db
    from welora.mastery import _RANK, GATE_MIN

    f = get_user_flags_db(user_id)
    return (f.get("mastery_source") in BACKFILL_SOURCES
            and _RANK.get(str(f.get("mastery_no_efund_invest") or ""), 0) >= _RANK[GATE_MIN])


def _backfill_from_mastery(user_id: str, p: dict[str, Any]) -> dict[str, Any]:
    from welora import academy_store as store

    if not store.use_db_profiles() or _gate_path_mastered(p):
        _BACKFILL_CHECKED.add(user_id)
        return p
    for _round in range(3):
        if not _trusted_gate_mastery(_base_uid(user_id)):
            _BACKFILL_CHECKED.add(user_id)
            return p
        _mark_gate_path_mastered(p)
        p["backfilled_at"] = _now()
        rev = store.save_profile_if_rev(user_id, p, _REVS.get(user_id))
        if rev is not None:
            _remember_saved(user_id, rev)
            _BACKFILL_CHECKED.add(user_id)
            return p
        # another request / instance saved first → reload its profile and re-apply on top of it
        _PROFILES.pop(user_id, None)
        _REVS.pop(user_id, None)
        _STAMPS.pop(user_id, None)
        _sync_from_db(user_id)
        p = _normalise(_PROFILES.setdefault(user_id, {}))
        if _gate_path_mastered(p):
            _BACKFILL_CHECKED.add(user_id)
            return p
    return p  # still racing: retried on the next request (not marked checked)


def seed_profile(user_id: str, *, gate_passed: bool) -> dict[str, Any]:
    """Demo seed (item 4): a fresh Academy profile that matches the persona's seeded mastery —
    N02-01 + N02-02 mastered (XP + badges) when the persona has passed the gate (mastery apply),
    else an empty one. Written in the caller's transaction (demo seed: ambient transaction +
    advisory lock); calling it again yields the same profile (idempotent)."""
    from welora import academy_store as store

    p = _normalise({})
    if gate_passed:
        _mark_gate_path_mastered(p)
    else:
        _refresh_locks(p)
    _PROFILES[user_id] = p
    _BACKFILL_CHECKED.discard(user_id)
    # item 1: every tester session of this persona restarts from the new seed state
    prefix = user_id + SESSION_KEY_SEP
    for k in [k for k in list(_PROFILES) if k.startswith(prefix)]:
        _forget(k)
    if store.use_db_profiles():
        store.delete_session_profiles(user_id)
        _remember_saved(user_id, store.save_profile(user_id, p))
    else:
        _REVS.pop(user_id, None)
        _STAMPS.pop(user_id, None)
    return p


def _save(user_id: str, p: Optional[dict[str, Any]] = None) -> None:
    """Persist one profile. ``p``: the copy the caller changed — saved even if the LRU (item 9)
    evicted that key from the cache meanwhile (another thread), so no progress is ever lost."""
    from welora import academy_store as store

    prof = p if p is not None else _PROFILES.get(user_id)
    if store.use_db_profiles() and prof is not None:
        if p is not None and user_id not in _PROFILES:
            _PROFILES[user_id] = p
        _remember_saved(user_id, store.save_profile(user_id, prof))


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


def served_valid(node_id: str, served: Any) -> bool:
    """True when every served slot still maps to a question of the node's CURRENT bank with the same
    number of options (an attempt issued before a bank update is not)."""
    by_id = {q["id"]: q for q in QUESTIONS.get(node_id, [])}
    if not isinstance(served, list) or not served:
        return False
    for slot in served:
        q = by_id.get((slot or {}).get("q")) if isinstance(slot, dict) else None
        perm = (slot or {}).get("perm") if isinstance(slot, dict) else None
        if q is None or not isinstance(perm, list) or sorted(perm) != list(range(len(q["choices"]))):
            return False
    return True


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


def get_tree(user_id: str, *, key: Optional[str] = None) -> dict[str, Any]:
    """``key``: the profile key (``profile_key``; demo persona session) — default the user id."""
    p = _profile(key or user_id)
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
        "pass_rule": PASS_RULE_VI,  # item 6: the header copy comes from the real rule
        # follow-up #244/#245 item 13: «reset tiến độ demo của tôi» is offered only to a demo session
        "demo_session": is_session_key(key or user_id),
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


def get_node(user_id: str, node_id: str, *, issue_attempt: bool = True, ip: Optional[str] = None,
             session: Optional[str] = None) -> dict[str, Any] | None:
    """Lesson + (when the node is open and the learner is not cooling down) the learner's server-held
    KUAT attempt — the OPEN one if still valid (same questions / option order in every tab), a new one
    only when none is open: ``kuat.attempt_id`` and the shuffled ``questions`` (no answers, no verdicts)."""
    from welora import academy_store as store

    if node_id not in _NODE_BY_ID:
        return None
    p = _profile(profile_key(user_id, session=session, ip=ip))
    _refresh_locks(p)
    n = dict(_NODE_BY_ID[node_id])
    st = p["nodes"][node_id]
    body = _lesson_body_markdown(str(n.get("lesson_id") or ""), str(n.get("principle_key") or ""))
    kuat: dict[str, Any] = kuat_info(node_id)
    questions: list[dict[str, Any]] = []
    if st["status"] != STATUS_LOCKED and issue_attempt and QUESTIONS.get(node_id):
        try:
            att = start_attempt(user_id, node_id, ip=ip, session=session)
            questions = att["questions"]
            kuat.update({"attempt_id": att["attempt_id"], "expires_at": att["expires_at"]})
        except store.KuatCooldown as e:
            kuat.update({"cooldown": cooldown_payload(e, node_id)})
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


def mark_read(user_id: str, node_id: str, *, key: Optional[str] = None) -> dict[str, Any]:
    if node_id not in _NODE_BY_ID:
        return {"error": "unknown node"}
    key = key or user_id
    p = _profile(key)
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
    _save(key, p)
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


def _apply_result(user_id: str, node_id: str, passed: bool, *, key: Optional[str] = None) -> dict[str, Any]:
    key = key or user_id
    p = _profile(key)
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
        if node_id == GATE_NODE and not is_session_key(key):
            # item 1: a demo tester session never flips the persona's shared gate mastery
            _wire_mastery(user_id)
        _refresh_locks(p)
        _refresh_badges(p)
    else:
        st["status"] = STATUS_KUAT_PENDING
        st["mastery_level"] = "familiar"
        st["last_kuat"] = attempt
        _refresh_locks(p)
    _save(key, p)
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
        "tree": get_tree(user_id, key=key),
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


def start_attempt(user_id: str, node_id: str, *, ip: Optional[str] = None,
                  session: Optional[str] = None) -> dict[str, Any]:
    """The learner's KUAT attempt for this node: the open one if still valid, else a new draw
    (raises academy_store.KuatCooldown while cooling down / too many new attempts). ``session`` =
    the request's bearer token: demo personas keep one open attempt per login session (019)."""
    from welora import academy_store as store

    store.check_kuat_allowed(user_id, node_id, ip)
    scope = store.attempt_scope(user_id, session=session, ip=ip)
    att = store.open_or_create_attempt(user_id, node_id, lambda: _draw(node_id), ip=ip, scope=scope)
    if not att.get("created") and not served_valid(node_id, att["served"]):
        # an attempt issued from an older bank (follow-up item 5 replaced three banks): retire it
        # and draw from the current bank
        store.expire_attempt(att["attempt_id"])
        att = store.open_or_create_attempt(user_id, node_id, lambda: _draw(node_id), ip=ip, scope=scope)
    return {**kuat_info(node_id), "attempt_id": att["attempt_id"], "expires_at": att["expires_at"],
            "node_id": node_id, "questions": _served_public(node_id, att["served"])}


_SLOT_RE = re.compile(r"^k([1-9][0-9]?)$")


def submit_kuat_attempt(user_id: str, node_id: str, attempt_id: Optional[str], answers: list[dict[str, Any]],
                        *, ip: Optional[str] = None, session: Optional[str] = None) -> dict[str, Any]:
    """Grade one server-held attempt. Order (round 2): validate (old tab → "reload", nothing
    counted) → consume the attempt atomically (only one concurrent submit continues) → RESERVE a
    failed-KUAT slot in every limit bucket BEFORE grading (429 if any is full; the attempt is
    re-opened, nothing graded) → grade → keep the reserved fail, or release it on pass."""
    from welora import academy_store as store

    if node_id not in _NODE_BY_ID:
        return {"error": "unknown node"}
    key = profile_key(user_id, session=session, ip=ip)
    p = _profile(key)
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
    scope = store.attempt_scope(user_id, session=session, ip=ip)  # demo persona: this login session only
    aid = (attempt_id or "").strip() or store.latest_open_attempt_id(user_id, node_id, scope=scope)
    served = store.peek_attempt(aid, user_id, node_id, scope=scope) if aid else None
    if not served:
        return {"error": "attempt_invalid"}
    if not served_valid(node_id, served):  # issued from an older bank → nothing graded / counted
        store.expire_attempt(aid)
        return {"error": "attempt_invalid"}
    if any(int(_SLOT_RE.match(i).group(1)) > len(served) for i in ids):
        return {"error": "reload"}  # answers for questions this attempt never showed
    served = store.consume_attempt(aid, user_id, node_id, scope=scope)  # atomic: one concurrent submit wins
    if not served:
        return {"error": "attempt_invalid"}
    try:
        reservation = store.reserve_kuat_fail(user_id, node_id, ip)
    except store.KuatCooldown:
        store.reopen_attempt(aid, user_id, node_id, scope=scope)  # not graded → the learner keeps the attempt
        raise
    try:
        _score, passed = _grade_served(node_id, served, answers)
        store.finish_attempt(aid, passed=passed)
    except Exception:
        reservation.release()
        raise
    if passed:
        reservation.release()
    return _apply_result(user_id, node_id, passed, key=key)


def _wait_vi(seconds: int) -> str:
    m = max(1, math.ceil(seconds / 60))
    if m < 60:
        return f"{m} phút"
    h, mm = divmod(m, 60)
    return f"{h} giờ" + (f" {mm} phút" if mm else "")


# Round 4: every message carries the retry time in Vietnam time ({at}, UTC+7 — no DST) next to the
# duration; the payload also has retry_at (ISO, UTC) and a link back to the lesson. The network
# messages never ask for an OTP / verification: a password-registered account has no way to verify
# today (e-mail OTP is admin-listed only, phone OTP creates a separate account) — and (migration-019
# ticket item 2) never ask to log in either: a password login does not lift a gate-node limit.
_RETRY = "sau khoảng {wait} (từ {at}, giờ Việt Nam)"
_REVIEW = " Trong lúc chờ, mời bạn ôn lại bài «{lesson}» — nắm vững nội dung bài là cách chắc chắn nhất để đạt."
COOLDOWN_MSG_VI = {
    "fails": "Bạn đã làm bài KUAT này chưa đạt vài lần liền. Hãy ôn lại bài học rồi thử lại " + _RETRY + ".",
    "daily": "Hôm nay bạn đã làm bài KUAT này chưa đạt nhiều lần. Hãy nghỉ ngơi, ôn lại bài và quay lại " + _RETRY + ".",
    "ip": "Có quá nhiều lượt KUAT chưa đạt từ mạng này. Vui lòng thử lại " + _RETRY + ".",
    "ip_day": "Hôm nay mạng này đã có quá nhiều lượt KUAT chưa đạt. Vui lòng thử lại " + _RETRY + ".",
    "unverified_ip": ("Bài KUAT này tạm dừng trên mạng bạn đang dùng vì đã có nhiều lượt chưa đạt từ mạng này "
                      "trong 24 giờ qua. Bạn có thể làm lại " + _RETRY + "." + _REVIEW),
    "unverified_device": ("Bạn đã làm bài KUAT này chưa đạt nhiều lần trong 24 giờ qua. Bạn có thể làm lại "
                          + _RETRY + "." + _REVIEW),
    "demo_ip": ("Bài KUAT này tạm dừng cho tài khoản demo trên mạng bạn đang dùng vì đã có nhiều lượt chưa đạt từ "
                "mạng này trong 24 giờ qua. Bạn có thể làm lại " + _RETRY + "." + _REVIEW),
    # migration-019 ticket item 2: no login / OTP nudge — logging in does not lift a gate-node limit
    "guest_ip": ("Bài KUAT này tạm dừng trên mạng bạn đang dùng vì đã có nhiều lượt chưa đạt từ mạng này "
                 "trong 24 giờ qua. Bạn có thể làm lại " + _RETRY + "." + _REVIEW),
    "device": ("Thiết bị này đã làm bài KUAT này chưa đạt nhiều lần trong 24 giờ qua. Bạn có thể làm lại "
               + _RETRY + "." + _REVIEW),
    "starts": "Bạn đã mở bài KUAT này quá nhiều lần. Vui lòng thử lại " + _RETRY + ".",
    # item 3: too many NEW attempts on non-gate nodes from one network
    "ip_starts": ("Mạng bạn đang dùng đã mở quá nhiều lượt bài KUAT trong thời gian ngắn. Bạn có thể mở bài "
                  "mới " + _RETRY + "." + _REVIEW),
    # follow-up item 4: too many NEW non-gate attempts by this account
    "user_starts": ("Bạn đã mở quá nhiều lượt bài KUAT mới trong thời gian ngắn. Bạn có thể mở bài mới "
                    + _RETRY + "." + _REVIEW),
}
VN_TZ = timezone(timedelta(hours=7), "ICT")
ATTEMPT_INVALID_MSG_VI = "Lượt KUAT này đã hết hạn hoặc đã được nộp. Hãy tải lại bài để làm lượt mới."
RELOAD_MSG_VI = "Bài KUAT trên trang này đã cũ. Vui lòng tải lại trang để làm lượt mới."
NO_ANSWERS_MSG_VI = "Bạn chưa chọn câu trả lời nào."


def _vn_time(at: datetime) -> str:
    """'05:12' today (Vietnam time), else '05:12 ngày 03/10'."""
    local, today = at.astimezone(VN_TZ), datetime.now(VN_TZ).date()
    return local.strftime("%H:%M") + ("" if local.date() == today else local.strftime(" ngày %d/%m"))


def cooldown_payload(e: Any, node_id: Optional[str] = None) -> dict[str, Any]:
    retry_at = datetime.fromtimestamp(datetime.now(timezone.utc).timestamp() + e.retry_after, tz=timezone.utc)
    n = _NODE_BY_ID.get(node_id or "") or {}
    lesson = str(n.get("title") or "học")
    at_vn = _vn_time(retry_at)
    out = {
        "error_code": "KUAT_COOLDOWN",
        "reason": e.reason,
        "message": COOLDOWN_MSG_VI.get(e.reason, COOLDOWN_MSG_VI["fails"]).format(
            wait=_wait_vi(e.retry_after), at=at_vn, lesson=lesson),
        "retry_after": int(e.retry_after),
        "retry_at": retry_at.isoformat(),
        "retry_at_vn": at_vn,
    }
    if n:
        out.update({"lesson_title": lesson, "lesson_href": lesson_href(str(n["node_id"]))})
    return out


def lesson_href(node_id: str) -> str:
    """Follow-up item 2: the «ôn lại bài» link of a KUAT notice opens the lesson IN the Academy
    (/app/academy?node=…), which follows the Academy guest gate (open to device guests only while
    WELORA_GUEST_DEMO is on; login required otherwise). The page keeps the address in sync with
    history.pushState (follow-up #244/#245 item 11)."""
    return "/app/academy?node=" + node_id


# --- follow-up #244/#245 item 13: «reset tiến độ demo của tôi» -----------------------------------
DEMO_RESET_ONLY_MSG_VI = "Chỉ phiên dùng thử tài khoản demo mới đặt lại được tiến độ."
DEMO_RESET_OK_MSG_VI = "Đã đặt lại tiến độ học của phiên demo này về trạng thái ban đầu."


def reset_demo_session(user_id: str, *, ip: Optional[str] = None, session: Optional[str] = None) -> Optional[dict]:
    """Back to the persona's demo seed for THIS login session only (drops its session profile; other
    testers, the persona's own profile and its shared gate mastery are untouched; the KUAT start /
    fail budgets are NOT reset — they are per persona + network). None when the caller is not a
    demo session (regular account, WELORA_GUEST_DEMO off)."""
    from welora import academy_store as store

    key = profile_key(user_id, session=session, ip=ip)
    if not is_session_key(key):
        return None
    if store.use_db_profiles():
        store.delete_profile(key)
    _forget(key)
    return get_tree(user_id, key=key)


def service_reset_demo(user_id: str, *, ip: Optional[str] = None, session: Optional[str] = None) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    tree = reset_demo_session(user_id, ip=ip, session=session)
    if tree is None:
        return 403, {"error_code": "DEMO_RESET_NOT_ALLOWED", "message": DEMO_RESET_ONLY_MSG_VI}
    return 200, {"ok": True, "message": DEMO_RESET_OK_MSG_VI, "tree": tree}


# --- follow-up #244/#245 item 14: Safety Gate + mastery per demo session --------------------------
# A demo tester's gate follows THEIR session: passing N02-02 in the session opens the mastery part of
# the Safety Gate (and everything that reads it: /safety-gate, mastery, Health Score, the Pre-Rule
# context) for that session only. The persona's shared gate mastery (user_flags) is never written by
# a session (item 1) and every other tester keeps seeing their own state. Only RAISES the shared
# state (a failed retake never closes a gate, same as for regular accounts). The request's login
# session comes from REQUEST_SESSION (set per request by the API middleware: bearer token + client
# IP); regular accounts / WELORA_GUEST_DEMO=0 → no change at all.
import contextvars as _contextvars

REQUEST_SESSION: "_contextvars.ContextVar[Optional[tuple[str, str]]]" = _contextvars.ContextVar(
    "welora_academy_request_session", default=None)


def session_gate_mastery(user_id: str) -> Optional[str]:
    """"apply" when the CURRENT request is a demo login session of ``user_id`` whose session profile
    has the gate node mastered, else None."""
    from welora.auth import guest_demo_enabled, resolve_token

    ctx = REQUEST_SESSION.get()
    if not ctx or not user_id or not guest_demo_enabled():
        return None
    token, ip = ctx
    if not token or resolve_token(token) != user_id:
        return None
    key = profile_key(user_id, session=token, ip=ip)
    if not is_session_key(key):
        return None
    p = _profile(key)
    return "apply" if p["nodes"][GATE_NODE].get("status") == STATUS_MASTERED else None


def overlay_session_mastery(user_id: str, state: str) -> str:
    """Shared gate mastery ``state`` → the one this request's demo session sees (item 14)."""
    from welora.mastery import _RANK

    try:
        sess = session_gate_mastery(user_id)
    except Exception:  # never breaks a gate read
        return state
    if sess and _RANK.get(sess, 0) > _RANK.get(str(state or "not_started"), 0):
        return sess
    return state


def service_get_tree(user_id: str, *, ip: Optional[str] = None, session: Optional[str] = None) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    return 200, get_tree(user_id, key=profile_key(user_id, session=session, ip=ip))


def service_get_node(user_id: str, node_id: str, *, ip: Optional[str] = None,
                     session: Optional[str] = None) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    n = get_node(user_id, node_id, ip=ip, session=session)
    if not n:
        return 404, {"error": "unknown node"}
    return 200, n


def service_mark_read(body: dict, *, ip: Optional[str] = None, session: Optional[str] = None) -> tuple[int, dict]:
    user_id = (body or {}).get("user_id") or ""
    node_id = (body or {}).get("node_id") or ""
    if not user_id or not node_id:
        return 400, {"error": "user_id and node_id required"}
    out = mark_read(user_id, node_id, key=profile_key(user_id, session=session, ip=ip))
    if out.get("error"):
        return 400, out
    return 200, out


def service_start_kuat(body: dict, *, ip: Optional[str] = None, session: Optional[str] = None) -> tuple[int, dict]:
    from welora import academy_store as store

    user_id = (body or {}).get("user_id") or ""
    node_id = (body or {}).get("node_id") or ""
    if not user_id or not node_id:
        return 400, {"error": "user_id and node_id required"}
    if node_id not in _NODE_BY_ID or not QUESTIONS.get(node_id):
        return 404, {"error": "unknown node"}
    p = _profile(profile_key(user_id, session=session, ip=ip))
    _refresh_locks(p)
    if p["nodes"][node_id]["status"] == STATUS_LOCKED:
        return 403, {"error": "locked"}
    try:
        return 200, start_attempt(user_id, node_id, ip=ip, session=session)
    except store.KuatCooldown as e:
        return 429, cooldown_payload(e, node_id)


def service_submit_kuat(body: dict, *, ip: Optional[str] = None, session: Optional[str] = None) -> tuple[int, dict]:
    from welora import academy_store as store

    user_id = (body or {}).get("user_id") or ""
    node_id = (body or {}).get("node_id") or ""
    answers = (body or {}).get("answers") or []
    if not user_id or not node_id:
        return 400, {"error": "user_id and node_id required"}
    try:
        out = submit_kuat_attempt(user_id, node_id, (body or {}).get("attempt_id"), answers, ip=ip, session=session)
    except store.KuatCooldown as e:
        return 429, cooldown_payload(e, node_id)
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
