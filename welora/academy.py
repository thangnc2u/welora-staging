"""Welorademy M02 An Toàn — cây ngữ nghĩa + cổng KUAT."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

KUAT_PASS_THRESHOLD = 0.70
MODULE_ID = "M02"
MODULE_TITLE = "An Toàn Tài Chính"
XP_PER_PASS = 20
GATE_NODE = "N02-02"
MASTERY_NODE = "no_efund_invest"

STATUS_LOCKED = "locked"
STATUS_AVAILABLE = "available"
STATUS_LEARNING = "learning"
STATUS_KUAT_PENDING = "kuat_pending"
STATUS_MASTERED = "mastered"

NODES: list[dict[str, Any]] = [
    {
        "node_id": "N02-01",
        "module_id": MODULE_ID,
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
        "title": "Ưu tiên trả nợ vs đầu tư",
        "lesson_id": "WA-02-07",
        "principle_key": "DEBT-03",
        "core_map": ["CORE-07", "CORE-01"],
        "prereq_node_ids": ["N02-06"],
        "order": 7,
    },
]

_NODE_BY_ID = {n["node_id"]: n for n in NODES}

QUESTIONS: dict[str, list[dict[str, Any]]] = {
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
    fund = all(p["nodes"][i]["status"] == STATUS_MASTERED for i in ("N02-01", "N02-02", "N02-03"))
    debt = all(p["nodes"][i]["status"] == STATUS_MASTERED for i in ("N02-04", "N02-05", "N02-06", "N02-07"))
    if fund and "An Toàn — Quỹ" not in p["badges"]:
        p["badges"].append("An Toàn — Quỹ")
    if debt and "An Toàn — Nợ" not in p["badges"]:
        p["badges"].append("An Toàn — Nợ")


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
    return {
        "module_id": MODULE_ID,
        "title": MODULE_TITLE,
        "threshold": KUAT_PASS_THRESHOLD,
        "xp": p["xp"],
        "badges": list(p["badges"]),
        "nodes": nodes,
    }


def get_node(user_id: str, node_id: str) -> dict[str, Any] | None:
    if node_id not in _NODE_BY_ID:
        return None
    p = _profile(user_id)
    _refresh_locks(p)
    n = dict(_NODE_BY_ID[node_id])
    st = p["nodes"][node_id]
    n.update(
        {
            "status": st["status"],
            "mastery_level": st["mastery_level"],
            "last_kuat": st["last_kuat"],
            "questions": _public_questions(node_id),
            "content_href": "/app/content?key=" + n["principle_key"],
            "lesson_stub": n["title"] + " · " + n["principle_key"],
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
    return {
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
    }


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
