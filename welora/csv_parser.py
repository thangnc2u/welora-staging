"""
Welora P1-E7 — CSV bank export parser
Suggests essential_expense_monthly without auto-overwrite.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any, Optional


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


def parse_csv_text(text: str, filename: str = "") -> dict[str, Any]:
    text = text or ""
    if not text.strip():
        return {"ok": False, "error": "empty csv", "transactions": [], "suggestion": None}

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        # try simple rows
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
                txs.append({"amount": amt, "raw": ln[:120]})
        return _summarize(txs, filename)

    # normalize headers
    fields = [f.strip().lower() for f in reader.fieldnames]
    amount_keys = [k for k in fields if any(x in k for x in ("amount", "số tiền", "so tien", "value", "debit", "credit"))]
    desc_keys = [k for k in fields if any(x in k for x in ("desc", "nội dung", "noi dung", "memo", "detail"))]

    txs = []
    for row in reader:
        # map original keys
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
                desc = str(raw_map[dk])[:120]
                break
        txs.append({"amount": amt, "description": desc})

    return _summarize(txs, filename)


def _summarize(txs: list[dict], filename: str) -> dict[str, Any]:
    debits = [abs(t["amount"]) for t in txs if t.get("amount") is not None and t["amount"] < 0]
    if not debits:
        debits = [abs(t["amount"]) for t in txs if t.get("amount")]
    suggestion = None
    if debits:
        # crude monthly essential estimate: median of absolute outflows * conservative factor
        sorted_d = sorted(debits)
        median = sorted_d[len(sorted_d) // 2]
        suggestion = {
            "essential_expense_monthly": round(median * 20, -3),  # rough monthly scale
            "method": "heuristic_median_outflow",
            "note": "Gợi ý — không tự ghi đè Goal. User xác nhận trước khi apply.",
            "sample_size": len(debits),
        }
    return {
        "ok": True,
        "filename": filename,
        "transaction_count": len(txs),
        "transactions": txs[:100],
        "suggestion": suggestion,
        "auto_overwrite": False,
    }


def service_parse_csv(*, text: str, filename: str = "") -> tuple[int, dict]:
    out = parse_csv_text(text, filename)
    if not out.get("ok"):
        return 400, out
    return 200, out
