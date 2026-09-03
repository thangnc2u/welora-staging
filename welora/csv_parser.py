"""
Welora P1-E7 — CSV bank export parser
Suggests essential_expense_monthly without auto-overwrite.
Text fields (description / raw / filename) are HTML-stripped before JSON.
"""

from __future__ import annotations

import csv
import html
import io
import re
from typing import Any, Optional

_SCRIPT_RE = re.compile(r"(?is)<script[^>]*>.*?</script>")
_STYLE_RE = re.compile(r"(?is)<style[^>]*>.*?</style>")
_TAG_RE = re.compile(r"<[^>]*>")


def sanitize_csv_text(value: Any) -> str:
    """Strip dangerous HTML from CSV text. Amounts stay numeric elsewhere.

    Unescape entities first so ``<script>`` is treated as a real tag,
    then strip. Do not unescape again after strip.
    """
    if value is None:
        return ""
    t = html.unescape(str(value))
    t = _SCRIPT_RE.sub("", t)
    t = _STYLE_RE.sub("", t)
    t = _TAG_RE.sub("", t)
    t = t.replace("<", "").replace(">", "")
    return t.strip()


def _sanitize_tx(tx: dict[str, Any]) -> dict[str, Any]:
    out = dict(tx)
    for key in ("description", "raw", "memo", "detail", "category"):
        if key in out and out[key] is not None:
            out[key] = sanitize_csv_text(out[key])
    return out


def _parse_amount(raw: str) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip().replace(",", "").replace(" ", "")
    s = re.sub(r"[^0-9.+-]", "", s)
    if not s or s in (".", "+", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def vn_category_label(desc: str) -> str:
    """Heuristic danh mục tiếng Việt từ mô tả. Không LLM."""
    d = (desc or "").lower()
    if "thuê nhà" in d or "thue nha" in d or "nhà" in d:
        return "Nhà ở"
    if any(k in d for k in ("điện", "dien", "evn", "nước", "nuoc")):
        return "Điện nước"
    if "lương" in d or "luong" in d or "salary" in d:
        return "Lương"
    if "winmart" in d or "siêu thị" in d or "sieu thi" in d or "grocer" in d:
        return "Siêu thị"
    if "học phí" in d or "hoc phi" in d or "học" in d or "hoc" in d:
        return "Học phí"
    return "Khác"


def attach_goal_draft(out: dict) -> dict:
    from welora.safety_gate import TARGET_MONTHS

    suggestion = out.get("suggestion") or {}
    sug = suggestion.get("essential_expense_monthly") if isinstance(suggestion, dict) else None
    draft = None
    if sug:
        essential = float(sug)
        draft = {
            "type": "emergency_fund",
            "essential_expense_monthly": essential,
            "target_amount": essential * int(TARGET_MONTHS),
            "target_months": int(TARGET_MONTHS),
            "auto_overwrite": False,
        }
    out["goal_draft"] = draft
    out["auto_overwrite"] = False
    return out


def parse_csv_text(text: str, filename: str = "") -> dict[str, Any]:
    text = text or ""
    filename = sanitize_csv_text(filename)
    if not text.strip():
        return {"ok": False, "error": "empty csv", "transactions": [], "suggestion": None}

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        lines = [ln for ln in text.splitlines() if ln.strip()]
        txs = []
        for ln in lines[:200]:
            parts = re.split(r"[,;\t]", ln)
            amt = None
            for p in reversed(parts):
                amt = _parse_amount(p)
                if amt is not None:
                    break
            if amt is not None:
                safe = sanitize_csv_text(ln[:120])
                txs.append({"amount": amt, "description": safe, "raw": safe})
        return _summarize(txs, filename)

    fields = [f.strip().lower() for f in reader.fieldnames]
    amount_keys = [k for k in fields if any(x in k for x in ("amount", "số tiền", "so tien", "value", "debit", "credit"))]
    desc_keys = [k for k in fields if any(x in k for x in ("desc", "nội dung", "noi dung", "memo", "detail"))]

    txs = []
    for row in reader:
        raw_map = {k.strip().lower(): v for k, v in row.items() if k}
        amt = None
        for ak in amount_keys:
            amt = _parse_amount(raw_map.get(ak))
            if amt is not None:
                break
        if amt is None:
            continue
        desc = ""
        for dk in desc_keys:
            if raw_map.get(dk):
                desc = sanitize_csv_text(str(raw_map[dk])[:240])[:120]
                break
        txs.append({"amount": amt, "description": desc})

    return _summarize(txs, filename)


def _summarize(txs: list[dict], filename: str) -> dict[str, Any]:
    txs = [_sanitize_tx(t) for t in txs]
    debits = [abs(t["amount"]) for t in txs if t.get("amount") is not None and t["amount"] < 0]
    if not debits:
        debits = [abs(t["amount"]) for t in txs if t.get("amount")]
    suggestion = None
    if debits:
        sorted_d = sorted(debits)
        median = sorted_d[len(sorted_d) // 2]
        suggestion = {
            "essential_expense_monthly": round(median * 20, -3),
            "method": "heuristic_median_outflow",
            "note": "Gợi ý — không tự ghi đè Goal. User xác nhận trước khi apply.",
            "sample_size": len(debits),
        }
    counts: dict[str, int] = {}
    for t in txs:
        desc = str(t.get("description") or t.get("raw") or "")
        lab = vn_category_label(desc)
        counts[lab] = counts.get(lab, 0) + 1
    out = {
        "ok": True,
        "filename": sanitize_csv_text(filename),
        "transaction_count": len(txs),
        "transactions": txs[:100],
        "suggestion": suggestion,
        "auto_overwrite": False,
        "category_counts": counts,
    }
    out = attach_goal_draft(out)
    from welora.budget import attach_budget_draft

    return attach_budget_draft(out)


def service_parse_csv(*, text: str, filename: str = "") -> tuple[int, dict]:
    out = parse_csv_text(text, filename)
    if not out.get("ok"):
        return 400, out
    return 200, out
