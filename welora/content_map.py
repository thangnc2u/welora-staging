"""
Welora P1-E8 — Content deep-link from principle_key / Deny CTA
P1 Pedia ship An Toàn: full WP-02 + governance + CTA Welorademy.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

GOVERNANCE_DEFAULT = {
    "version": "1.0.0",
    "last_reviewed_at": "2026-09-02",
    "status": "published",
}

RISK_VI = {"low": "Thấp", "medium": "Trung bình", "high": "Cao"}

FALLBACK_BODY: dict[str, str] = {
    "SAFE-01": (
        "## Quỹ khẩn cấp là lớp sống còn\n\n"
        "Quỹ khẩn cấp không phải tiền để đầu tư. Đó là lớp đệm khi thu nhập gián đoạn "
        "hoặc chi phí bất ngờ (ốm, mất việc, sửa chữa cần thiết).\n\n"
        "Welora yêu cầu quỹ đủ tối thiểu 3 tháng chi tiêu thiết yếu trước khi nói đến đầu tư. "
        "Không cam kết lợi suất. Không rút quỹ để all-in."
    ),
    "SAFE-02": (
        "## Chỉ dùng quỹ cho sự cố bất ngờ\n\n"
        "Quỹ khẩn cấp chỉ dùng khi sự cố bất ngờ và cần thiết: bệnh, mất việc, "
        "hỏng việc phải sửa để sống hoặc làm việc.\n\n"
        "Không dùng quỹ để du lịch, mua sắm, hay cơ hội đầu tư. Nếu rút quỹ, "
        "ưu tiên xây lại đủ 3 tháng trước khi mở quyền đầu tư."
    ),
    "DEBT-03": (
        "## An Toàn trước đầu tư\n\n"
        "Nợ nguy hiểm (lãi cao, tín dụng tiêu dùng, vay để đầu cơ) cần xử lý "
        "trước khi tăng rủi ro đầu tư.\n\n"
        "Không vay để đầu tư. Không phá quỹ khẩn cấp để trả nợ không khẩn. "
        "Đầu tư chỉ bằng tiền thừa ngoài quỹ 3 tháng và ngoài nghĩa vụ nợ nguy hiểm."
    ),
    "CORE-07": (
        "## Phòng thủ đi trước tăng trưởng\n\n"
        "Tăng trưởng đứng sau phòng thủ: quỹ 3 tháng, không nợ nguy hiểm, hiểu rõ rủi ro.\n\n"
        "Cổng An Toàn không bị Health Score hay cảm xúc bypass. "
        "Agent từ chối đề xuất phá quỹ hoặc cam kết chắc lời."
    ),
    "SAFE-03": (
        "## Quỹ thanh khoản cao và tách biệt\n\n"
        "Quỹ khẩn cấp cần dễ rút khi sự cố xảy ra. Nên để ở nơi tách biệt khỏi tài khoản chi tiêu hàng ngày và khỏi tiền đầu tư.\n\n"
        "Ưu tiên giữ quỹ an toàn, đủ 3 tháng chi tiêu thiết yếu. Không dùng quỹ này để tìm lợi suất."
    ),
    "DEBT-01": (
        "## Phân biệt nợ tốt và nợ xấu\n\n"
        "Nợ nguy hiểm thường có lãi suất cao, kỳ hạn ngắn, hoặc dùng để tiêu dùng và đầu cơ. Cần xem khả năng trả, không quyết theo cảm xúc.\n\n"
        "Ưu tiên giảm nợ nguy hiểm. Không vay thêm để đầu tư khi Cổng An Toàn chưa đạt."
    ),
    "DEBT-02": (
        "## Chọn cách trả nợ phù hợp\n\n"
        "Có thể trả khoản nhỏ nhất trước để giảm số món, hoặc trả khoản lãi cao trước để giảm chi phí lãi. Chọn một cách và theo dõi đều.\n\n"
        "Không có phương pháp nào luôn đúng mọi trường hợp. Không vay mới để đảo nợ nếu chưa rõ khả năng trả."
    ),
    "CORE-01": (
        "## Trách nhiệm với quyết định tiền bạc\n\n"
        "Bạn chịu trách nhiệm cho lựa chọn chi tiêu, vay, và đầu tư của mình. Agent chỉ hỗ trợ theo nguyên tắc An Toàn, không quyết định thay bạn.\n\n"
        "Hãy xem rõ thu nhập, chi tiêu thiết yếu, và quỹ khẩn cấp trước khi nhận thêm rủi ro."
    ),
    "CORE-05": (
        "## Cảm xúc không thay cho nguyên tắc\n\n"
        "Sợ hãi hoặc hưng phấn dễ đẩy tới quyết định vội: rút quỹ, vay nóng, all-in. Giữ nguyên tắc An Toàn dù thị trường biến động.\n\n"
        "Không dùng cảm xúc để phá quỹ 3 tháng hay nhận lời hứa lợi suất cố định."
    ),
    "CORE-10": (
        "## Tiền phục vụ cuộc đời\n\n"
        "Di sản không tự xảy ra: liệt kê tài sản và nghĩa vụ, ghi người thụ hưởng, "
        "để lại hướng dẫn rõ trước khi cần đến.\n\n"
        "Không phải tư vấn pháp lý. Quyết định thuộc về bạn; Agent giữ An Toàn và Hiến pháp."
    ),
}

CONTENT_BY_KEY: dict[str, dict[str, Any]] = {
    "SAFE-01": {
        "title": "Quỹ khẩn cấp là lớp sống còn",
        "module": "02",
        "module_title": "An Toàn Tài Chính",
        "wp": ["WP-02-01", "WP-02-02"],
        "wa": ["WA-02-01"],
        "path_wp": "WP-02-01-quy-khan-cap-la-gi.md",
        "path_wp_extra": ["WP-02-02-cach-xay-dung-quy-khan-cap.md"],
        "path_wa": "WA-02-01-xay-dung-quy-khan-cap.md",
        "risk_level": "medium",
        "academy_href": "/app/academy",
    },
    "SAFE-02": {
        "title": "Chỉ dùng quỹ cho sự cố bất ngờ",
        "module": "02",
        "module_title": "An Toàn Tài Chính",
        "wp": ["WP-02-03"],
        "wa": ["WA-02-02"],
        "path_wp": "WP-02-03-khi-nao-duoc-dung-quy-khan-cap.md",
        "path_wa": "WA-02-02-nguyen-tac-su-dung-quy-khan-cap.md",
        "risk_level": "medium",
        "academy_href": "/app/academy",
    },
    "SAFE-03": {
        "title": "Quỹ thanh khoản cao & tách biệt",
        "module": "02",
        "module_title": "An Toàn Tài Chính",
        "wp": ["WP-02-04"],
        "wa": ["WA-02-03"],
        "path_wp": "WP-02-04-nen-de-quy-khan-cap-o-dau.md",
        "path_wa": "WA-02-03-lua-chon-noi-giu-quy-khan-cap.md",
        "risk_level": "medium",
        "academy_href": "/app/academy",
    },
    "DEBT-01": {
        "title": "Nợ tốt vs Nợ xấu",
        "module": "02",
        "module_title": "An Toàn Tài Chính",
        "wp": ["WP-02-06"],
        "wa": ["WA-02-05"],
        "path_wp": "WP-02-06-no-tot-va-no-xau.md",
        "path_wa": "WA-02-05-nhan-dien-no-tot-no-xau.md",
        "risk_level": "high",
        "academy_href": "/app/academy",
    },
    "DEBT-02": {
        "title": "Phương pháp trả nợ",
        "module": "02",
        "module_title": "An Toàn Tài Chính",
        "wp": ["WP-02-05", "WP-02-07"],
        "wa": ["WA-02-04", "WA-02-06"],
        "path_wp": "WP-02-05-snowball-va-avalanche.md",
        "path_wp_extra": ["WP-02-07-cach-lap-ke-hoach-tra-no.md"],
        "path_wa": "WA-02-04-chon-phuong-phap-tra-no.md",
        "risk_level": "high",
        "academy_href": "/app/academy",
    },
    "DEBT-03": {
        "title": "An Toàn trước đầu tư",
        "module": "02",
        "module_title": "An Toàn Tài Chính",
        "wp": ["WP-02-08"],
        "wa": ["WA-02-07"],
        "path_wp": "WP-02-08-co-nen-tra-het-no-truoc-khi-dau-tu.md",
        "path_wa": "WA-02-07-sap-xep-uu-tien-tra-no-va-dau-tu.md",
        "risk_level": "high",
        "academy_href": "/app/academy",
    },
    "CORE-01": {
        "title": "Trách nhiệm tuyệt đối",
        "module": "01",
        "wp": ["WP-01-01"],
        "wa": ["WA-01-01"],
        "path_wp": "WP-01-01-tu-duy-ve-tien-la-gi.md",
        "path_wa": "WA-01-01-xay-dung-tu-duy-ve-tien.md",
        "risk_level": "low",
        "academy_href": "/app/academy",
    },
    "CORE-05": {
        "title": "Cảm xúc không ra quyết định",
        "module": "01",
        "wp": ["WP-01-07"],
        "wa": ["WA-01-06"],
        "path_wp": "WP-01-07-muc-tieu-tai-chinh.md",
        "path_wa": "WA-01-06-dat-muc-tieu-tai-chinh.md",
        "risk_level": "medium",
        "academy_href": "/app/academy",
    },
    "CORE-07": {
        "title": "Phòng thủ đi trước tăng trưởng",
        "module": "02",
        "module_title": "An Toàn Tài Chính",
        "wp": ["WP-02-01", "WP-02-08"],
        "wa": ["WA-02-01", "WA-02-07"],
        "path_wp": "WP-02-01-quy-khan-cap-la-gi.md",
        "path_wa": "WA-02-01-xay-dung-quy-khan-cap.md",
        "risk_level": "medium",
        "academy_href": "/app/academy",
    },
    "CORE-10": {
        "title": "Tiền phục vụ cuộc đời",
        "module": "04",
        "module_title": "Bền Vững & Di Sản",
        "wp": ["WP-04-06"],
        "wa": ["WA-04-05"],
        "path_wp": "WP-04-06-di-san-thua-ke.md",
        "path_wa": "WA-04-05-di-san-thua-ke.md",
        "risk_level": "medium",
        "academy_href": "/app/academy",
    },
}

CTA_CONTENT: dict[str, dict[str, str]] = {
    "keep_emergency_fund": {
        "principle_key": "SAFE-02",
        "href": "/app/content?key=SAFE-02",
        "label": "Đọc: Khi nào được dùng quỹ",
    },
    "create_emergency_fund_goal": {
        "principle_key": "SAFE-01",
        "href": "/app/safety",
        "label": "Tạo Goal quỹ 3 tháng",
    },
    "create_invest_goal_surplus_only": {
        "principle_key": "DEBT-03",
        "href": "/app/content?key=DEBT-03",
        "label": "Học: Chỉ đầu tư tiền thừa ngoài quỹ",
    },
    "view_safety_gate": {
        "principle_key": "CORE-07",
        "href": "/app/safety",
        "label": "Xem checklist Cổng An Toàn",
    },
    "create_debt_payoff_goal": {
        "principle_key": "DEBT-01",
        "href": "/app/content?key=DEBT-01",
        "label": "Học: Nợ tốt vs Nợ xấu",
    },
    "create_savings_goal": {
        "principle_key": "SAFE-02",
        "href": "/app/safety",
        "label": "Tạo Goal tiết kiệm riêng",
    },
    "view_options_framework": {
        "principle_key": "CORE-01",
        "href": "/app/content?key=CORE-01",
        "label": "Đọc: Bạn chịu trách nhiệm quyết định",
    },
}

_CTA_LABELS = {
    "keep_emergency_fund": "Giữ nguyên quỹ khẩn cấp",
    "create_emergency_fund_goal": "Tạo Goal quỹ khẩn cấp 3 tháng",
    "create_invest_goal_surplus_only": "Tạo Goal đầu tư (tiền ngoài quỹ)",
    "view_safety_gate": "Xem checklist Cổng An Toàn",
    "create_debt_payoff_goal": "Tạo plan trả nợ",
    "create_savings_goal": "Tạo Goal tiết kiệm riêng",
    "view_options_framework": "Xem khung lựa chọn",
}


def content_root() -> Path:
    env = os.environ.get("WELORA_CONTENT_ROOT")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[1] / "content"


def _gov(meta: dict[str, Any]) -> dict[str, str]:
    level = meta.get("risk_level") or "medium"
    return {
        "risk_level": level,
        "risk_label": RISK_VI.get(level, level),
        "version": GOVERNANCE_DEFAULT["version"],
        "last_reviewed_at": GOVERNANCE_DEFAULT["last_reviewed_at"],
        "status": GOVERNANCE_DEFAULT["status"],
    }


def _read_rel(root: Path, rel: Optional[str]) -> tuple[str, Optional[str]]:
    if not rel:
        return "", None
    path = root / rel
    if path.is_file():
        return path.read_text(encoding="utf-8", errors="replace"), path.name
    return "", None


def resolve_keys(keys: list[str]) -> list[dict[str, Any]]:
    out = []
    seen = set()
    for k in keys:
        if k in seen or k not in CONTENT_BY_KEY:
            continue
        seen.add(k)
        meta = dict(CONTENT_BY_KEY[k])
        meta["principle_key"] = k
        meta["href"] = f"/app/content?key={k}"
        out.append(meta)
    return out


def enrich_cta(codes: list[str]) -> list[dict[str, str]]:
    items = []
    for c in codes:
        label = _CTA_LABELS.get(c, c)
        row: dict[str, str] = {"code": c, "label": label}
        extra = CTA_CONTENT.get(c)
        if extra:
            row["href"] = extra.get("href") or ""
            row["principle_key"] = extra.get("principle_key") or ""
            if extra.get("label"):
                row["label"] = extra["label"]
        items.append(row)
    return items


def get_article(key: str) -> dict[str, Any]:
    meta = CONTENT_BY_KEY.get(key)
    if not meta:
        return {"ok": False, "error": "unknown principle_key", "principle_key": key}
    root = content_root()
    body, path_used = _read_rel(root, meta.get("path_wp"))
    extras = []
    for rel in meta.get("path_wp_extra") or []:
        extra, extra_name = _read_rel(root, rel)
        if extra.strip():
            extras.append(extra)
            if extra_name:
                extras_name = extra_name
    if extras:
        body = (body.rstrip() + "\n\n---\n\n" + "\n\n---\n\n".join(extras)).strip()
    if not (body or "").strip():
        wa_body, wa_name = _read_rel(root, meta.get("path_wa"))
        if wa_body.strip():
            body, path_used = wa_body, wa_name
    if not (body or "").strip():
        body = FALLBACK_BODY.get(key) or ""
        if body:
            path_used = path_used or "fallback"
    preview = body
    truncated = False
    if len(preview) > 20000:
        preview = preview[:20000] + "\n\n… (truncated)"
        truncated = True
    gov = _gov(meta)
    return {
        "ok": True,
        "principle_key": key,
        "title": meta["title"],
        "module": meta["module"],
        "module_title": meta.get("module_title") or "",
        "wp": meta.get("wp"),
        "wa": meta.get("wa"),
        "source_file": path_used,
        "body_markdown": preview,
        "truncated": truncated,
        "href": f"/app/content?key={key}",
        "risk_level": gov["risk_level"],
        "risk_label": gov["risk_label"],
        "version": gov["version"],
        "last_reviewed_at": gov["last_reviewed_at"],
        "status": gov["status"],
        "cta_academy": {"label": "Học sâu hơn", "href": meta.get("academy_href") or "/app/academy"},
        "cta_constitution": {"label": "Xây Hiến pháp Cá nhân", "href": "/app/constitution"},
    }


def service_get_content(key: str) -> tuple[int, dict]:
    if not key:
        return 400, {"error": "key is required"}
    art = get_article(key.strip().upper() if "-" in key else key.strip())
    if not art.get("ok"):
        art = get_article(key.strip())
    if not art.get("ok"):
        art = get_article(key.strip().upper())
    if not art.get("ok"):
        return 404, art
    return 200, art


def service_list_content_keys() -> tuple[int, dict]:
    items = []
    an_toan = []
    for k, v in CONTENT_BY_KEY.items():
        row = {
            "principle_key": k,
            "title": v["title"],
            "module": v.get("module"),
            "module_title": v.get("module_title") or "",
            "href": f"/app/content?key={k}",
            "wp": v.get("wp") or [],
        }
        items.append(row)
        if v.get("module") == "02":
            an_toan.append(row)
    return 200, {"items": items, "modules": {"02": {"title": "An Toàn Tài Chính", "items": an_toan}}}
