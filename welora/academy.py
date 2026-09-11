"""Welorademy M01 Rễ Cục + M02 An Toàn + M03 Tự Do + M04 Bền Vững & Di Sản + M05 Kết Nối & Thực Hành — cây ngữ nghĩa + cổng KUAT."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
        {"id": "q01a", "prompt": "Quỹ khẩn cấp dùng để làm gì?", "choices": ["Chi tiêu thường ngày", "Đệm khi mất thu nhập / sốc", "All-in cổ phiếu"], "answer": 1, "hard": False},
        {"id": "q01b", "prompt": "Mục tiêu tối thiểu của Cổng An Toàn là bao nhiêu tháng chi thiết yếu?", "choices": ["1 tháng", "3 tháng", "12 tháng"], "answer": 1, "hard": True},
        {"id": "q01c", "prompt": "Có nên dùng quỹ khẩn cấp để mua sắm sale?", "choices": ["Có", "Không"], "answer": 1, "hard": False},
    ],
    "N02-02": [
        {"id": "q02a", "prompt": "Được dùng quỹ khẩn cấp để all-in ETF khi thấy cơ hội?", "choices": ["Có", "Không"], "answer": 1, "hard": True},
        {"id": "q02b", "prompt": "Quỹ khẩn cấp nên dùng khi nào?", "choices": ["Mất việc / y tế / sốc", "Cơ hội đầu tư", "Du lịch"], "answer": 0, "hard": False},
        {"id": "q02c", "prompt": "Rút quỹ khẩn cấp để đầu tư cổ phiếu?", "choices": ["Được nếu lời", "Không — phá An Toàn"], "answer": 1, "hard": True},
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


def reset_academy_store() -> None:
    _PROFILES.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _profile(user_id: str) -> dict[str, Any]:
    p = _PROFILES.setdefault(
        user_id,
        {
            "xp": 0,
            "badges": [],
            "awarded_xp": [],
            "nodes": {},
            "attempts": [],
            "read": [],
        },
    )
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
    return p


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


def _public_questions(node_id: str) -> list[dict[str, Any]]:
    out = []
    for q in QUESTIONS.get(node_id, []):
        out.append({"id": q["id"], "prompt": q["prompt"], "choices": list(q["choices"]), "hard": bool(q["hard"])})
    return out


def get_tree(user_id: str) -> dict[str, Any]:
    p = _profile(user_id)
    _refresh_locks(p)
    nodes = []
    for n in NODES:
        st = p["nodes"][n["node_id"]]
        item = dict(n)
        item.update({"status": st["status"], "mastery_level": st["mastery_level"], "last_kuat": st["last_kuat"]})
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


def get_node(user_id: str, node_id: str) -> dict[str, Any] | None:
    if node_id not in _NODE_BY_ID:
        return None
    p = _profile(user_id)
    _refresh_locks(p)
    n = dict(_NODE_BY_ID[node_id])
    st = p["nodes"][node_id]
    body = _lesson_body_markdown(str(n.get("lesson_id") or ""), str(n.get("principle_key") or ""))
    n.update(
        {
            "status": st["status"],
            "mastery_level": st["mastery_level"],
            "last_kuat": st["last_kuat"],
            "questions": _public_questions(node_id),
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
    return {"ok": True, "xp": p["xp"], "status": st["status"], "awarded_xp": False}


def _grade(node_id: str, answers: list[dict[str, Any]]) -> tuple[float, bool, list[dict[str, Any]]]:
    qs = QUESTIONS.get(node_id, [])
    by_id = {q["id"]: q for q in qs}
    picked = {str(a.get("question_id") or a.get("id")): a.get("choice") for a in answers or []}
    correct = 0
    detail = []
    hard_ok = True
    for q in qs:
        raw = picked.get(q["id"])
        try:
            choice = int(raw)
        except (TypeError, ValueError):
            choice = -1
        ok = choice == q["answer"]
        if ok:
            correct += 1
        elif q["hard"]:
            hard_ok = False
        detail.append({"id": q["id"], "correct": ok, "hard": q["hard"]})
    score = (correct / len(qs)) if qs else 0.0
    passed = score >= KUAT_PASS_THRESHOLD and hard_ok
    return score, passed, detail


def _wire_mastery(user_id: str) -> None:
    from welora.mastery import STATES, get_node as mget, service_patch_mastery

    rank = {s: i for i, s in enumerate(STATES)}
    cur = mget(user_id, MASTERY_NODE)
    if rank.get(cur.state, 0) >= rank["apply"]:
        return
    service_patch_mastery(user_id, {"state": "apply", "node_id": MASTERY_NODE})


def submit_kuat(user_id: str, node_id: str, answers: list[dict[str, Any]]) -> dict[str, Any]:
    if node_id not in _NODE_BY_ID:
        return {"error": "unknown node"}
    p = _profile(user_id)
    _refresh_locks(p)
    st = p["nodes"][node_id]
    if st["status"] == STATUS_LOCKED:
        return {"error": "locked", "passed": False, "xp": p["xp"]}
    score, passed, detail = _grade(node_id, answers)
    attempt = {
        "node_id": node_id,
        "score": score,
        "passed": passed,
        "answers": detail,
        "ts": _now(),
        "principle_keys": [_NODE_BY_ID[node_id]["principle_key"]],
    }
    p["attempts"].append(attempt)
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
    payload: dict[str, Any] = {
        "kuat_result": {
            "passed": passed,
            "score": score,
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
    return payload


def service_get_tree(user_id: str) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    return 200, get_tree(user_id)


def service_get_node(user_id: str, node_id: str) -> tuple[int, dict]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    n = get_node(user_id, node_id)
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


def service_submit_kuat(body: dict) -> tuple[int, dict]:
    user_id = (body or {}).get("user_id") or ""
    node_id = (body or {}).get("node_id") or ""
    answers = (body or {}).get("answers") or []
    if not user_id or not node_id:
        return 400, {"error": "user_id and node_id required"}
    out = submit_kuat(user_id, node_id, answers)
    if out.get("error") and out.get("error") != "locked":
        return 400, out
    if out.get("error") == "locked":
        return 403, out
    return 200, out
