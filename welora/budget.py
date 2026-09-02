"""WeloraOS — ngân sách từ CSV thật. Không ghi đè Goal quỹ. Không silent overwrite."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

_BUDGETS: dict[str, dict[str, Any]] = {}


def reset_budget_store() -> None:
    _BUDGETS.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _outflow_by_category(txs: list[dict[str, Any]]) -> dict[str, float]:
    from welora.csv_parser import vn_category_label

    out: dict[str, float] = {}
    for t in txs or []:
        amt = t.get("amount")
        try:
            n = float(amt)
        except (TypeError, ValueError):
            continue
        desc = str(t.get("description") or t.get("raw") or "")
        lab = vn_category_label(desc)
        if n < 0:
            out[lab] = out.get(lab, 0.0) + abs(n)
        elif lab != "Lương":
            out[lab] = out.get(lab, 0.0) + abs(n)
    return out


def budget_draft_from_parse(parse_out: dict[str, Any]) -> dict[str, Any]:
    counts = dict(parse_out.get("category_counts") or {})
    outflow = _outflow_by_category(list(parse_out.get("transactions") or []))
    cats = list(counts.keys()) or list(outflow.keys())
    lines = []
    for cat in cats:
        lines.append(
            {
                "category": cat,
                "count": int(counts.get(cat) or 0),
                "outflow": float(outflow.get(cat) or 0.0),
            }
        )
    return {
        "kind": "budget_draft",
        "auto_overwrite": False,
        "source": "csv_parse",
        "lines": lines,
        "total_outflow": float(sum(l["outflow"] for l in lines)),
    }


def attach_budget_draft(out: dict[str, Any]) -> dict[str, Any]:
    if out.get("ok"):
        out["budget_draft"] = budget_draft_from_parse(out)
    else:
        out["budget_draft"] = None
    out.setdefault("auto_overwrite", False)
    return out


def get_budget(user_id: str) -> Optional[dict[str, Any]]:
    return _BUDGETS.get(user_id)


def apply_budget(
    user_id: str,
    *,
    confirm: bool,
    replace_existing: bool = False,
    draft: Optional[dict[str, Any]] = None,
    lines: Optional[list[dict[str, Any]]] = None,
) -> tuple[int, dict[str, Any]]:
    if not user_id:
        return 400, {"error": "user_id is required", "auto_overwrite": False}
    if not confirm:
        return 400, {
            "error": "confirm required",
            "auto_overwrite": False,
            "hint": "User phải xác nhận trước khi lưu ngân sách.",
        }
    payload = dict(draft or {})
    use_lines = list(lines or payload.get("lines") or [])
    if not use_lines:
        return 400, {"error": "draft.lines required", "auto_overwrite": False}

    existing = _BUDGETS.get(user_id)
    if existing and not replace_existing:
        return 409, {
            "error": "budget_exists",
            "auto_overwrite": False,
            "budget": existing,
            "hint": "Ngân sách đã có · không ghi đè im lặng. Gửi replace_existing=true để cập nhật.",
        }

    record = {
        "user_id": user_id,
        "kind": "budget",
        "status": "applied",
        "lines": use_lines,
        "total_outflow": float(
            payload.get("total_outflow")
            or sum(float(x.get("outflow") or 0) for x in use_lines)
        ),
        "source": payload.get("source") or "csv_parse",
        "auto_overwrite": False,
        "applied_at": _now(),
        "replaced": bool(existing),
    }
    _BUDGETS[user_id] = record
    return 200, {"ok": True, "budget": record, "replaced": bool(existing), "auto_overwrite": False}


def service_get(user_id: str) -> tuple[int, dict[str, Any]]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    b = get_budget(user_id)
    return 200, {"ok": True, "budget": b, "status": (b or {}).get("status") or "none"}


def service_apply(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    body = body or {}
    return apply_budget(
        str(body.get("user_id") or ""),
        confirm=bool(body.get("confirm")),
        replace_existing=bool(body.get("replace_existing")),
        draft=body.get("draft") if isinstance(body.get("draft"), dict) else None,
        lines=body.get("lines") if isinstance(body.get("lines"), list) else None,
    )
