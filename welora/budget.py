"""WeloraOS — ngân sách từ CSV thật + trung bình chi tiêu 3–6 tháng + rollover + Goal contrib.

Không ghi đè Goal quỹ. Không silent overwrite (confirm / replace_existing).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

_BUDGETS: dict[str, dict[str, Any]] = {}
# Closed / historical periods: key = f"{user_id}:{period}"
_BUDGET_PERIODS: dict[str, dict[str, Any]] = {}


def reset_budget_store() -> None:
    _BUDGETS.clear()
    _BUDGET_PERIODS.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _period_key(user_id: str, period: str) -> str:
    return f"{user_id}:{period}"


def _clamp_months(months: Any) -> tuple[Optional[int], Optional[str]]:
    try:
        m = int(months)
    except (TypeError, ValueError):
        return None, "months must be an integer 3..6"
    if m < 3 or m > 6:
        return None, "months must be between 3 and 6 (inclusive)"
    return m, None


def _parse_period(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip()
    if len(s) >= 7 and s[4] == "-":
        try:
            y = int(s[0:4])
            m = int(s[5:7])
            if 1 <= m <= 12:
                return f"{y:04d}-{m:02d}"
        except ValueError:
            return None
    return None


def _next_period(period: str) -> str:
    y, m = int(period[0:4]), int(period[5:7])
    if m == 12:
        return f"{y + 1:04d}-01"
    return f"{y:04d}-{m + 1:02d}"


def _tx_ymd(raw: Any) -> Optional[str]:
    """Normalize transaction date to YYYY-MM-DD."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if "T" in s:
        s = s.split("T", 1)[0]
    # CSV style DD/MM/YYYY
    if "/" in s and len(s) >= 8:
        parts = s.split("/")
        if len(parts) == 3:
            try:
                d, mo, y = int(parts[0]), int(parts[1]), int(parts[2])
                if y < 100:
                    y += 2000
                return date(y, mo, d).isoformat()
            except ValueError:
                pass
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return None


def _outflow_by_category(txs: list[dict[str, Any]]) -> dict[str, float]:
    from welora.csv_parser import vn_category_label

    out: dict[str, float] = {}
    for t in txs or []:
        amt = t.get("amount")
        try:
            n = float(amt)
        except (TypeError, ValueError):
            continue
        desc = str(t.get("description") or t.get("raw") or t.get("note") or "")
        cat = (t.get("category") or "").strip()
        if not cat:
            cat = vn_category_label(desc)
        if n < 0:
            out[cat] = out.get(cat, 0.0) + abs(n)
        elif cat != "Lương":
            out[cat] = out.get(cat, 0.0) + abs(n)
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
        "goal_contrib_lines": [],
    }


def attach_budget_draft(out: dict[str, Any]) -> dict[str, Any]:
    if out.get("ok"):
        out["budget_draft"] = budget_draft_from_parse(out)
    else:
        out["budget_draft"] = None
    out.setdefault("auto_overwrite", False)
    return out


def _kind_hint_for_category(user_id: str, category: str) -> Optional[str]:
    try:
        from welora import os_categories as cats_svc

        found = cats_svc.STORE.find_by_name(user_id, category, include_disabled=True)
        if found is not None:
            return getattr(found, "kind", None) or None
    except Exception:
        return None
    return None


def _goal_contrib_lines(user_id: str) -> list[dict[str, Any]]:
    """Read-only pull from active EF / debt_payoff goals. Never mutates goal stores."""
    lines: list[dict[str, Any]] = []
    try:
        from welora import goals_api

        code, body = goals_api.service_list_goals(user_id, type=None)
        if code >= 400:
            return lines
        items = list(body.get("items") or [])
    except Exception:
        return lines

    for g in items:
        gtype = str(g.get("type") or "")
        if gtype not in ("emergency_fund", "debt_payoff"):
            continue
        status = str(g.get("status") or "active")
        if status not in ("active", "in_progress", ""):
            # still include if status missing; skip clearly closed/cancelled
            if status in ("closed", "cancelled", "completed", "archived"):
                continue
        plan = g.get("plan") if isinstance(g.get("plan"), dict) else {}
        amount = plan.get("monthly_contribution")
        if amount is None:
            amount = g.get("monthly_contribution")
        try:
            amt = float(amount or 0)
        except (TypeError, ValueError):
            amt = 0.0
        if amt <= 0:
            continue
        title = (g.get("title") or "").strip()
        if gtype == "emergency_fund":
            label = title or "Quỹ khẩn cấp"
        else:
            label = title or "Trả nợ"
        lines.append(
            {
                "goal_id": g.get("goal_id"),
                "goal_type": gtype,
                "label": label,
                "amount": amt,
                "kind": "goal_contrib",
            }
        )
    return lines


def _collect_os_txs(
    user_id: str, *, account_id: Optional[str] = None
) -> list[dict[str, Any]]:
    from welora import os_transactions as tx_svc

    code, body = tx_svc.service_list_transactions(
        user_id, account_id=account_id, include_hidden=False
    )
    if code >= 400:
        return []
    return list(body.get("transactions") or body.get("items") or [])


def _expand_tx_outflows(txs: list[dict[str, Any]]) -> list[tuple[str, str, float]]:
    """Return list of (YYYY-MM-DD, category, outflow_amount>0). Handles splits."""
    rows: list[tuple[str, str, float]] = []
    for t in txs or []:
        ymd = _tx_ymd(t.get("date"))
        if not ymd:
            continue
        splits = t.get("splits") or []
        if t.get("is_split") and splits:
            for s in splits:
                try:
                    amt = float(s.get("amount"))
                except (TypeError, ValueError):
                    continue
                cat = (s.get("category") or t.get("category") or "Khác").strip() or "Khác"
                if amt < 0:
                    rows.append((ymd, cat, abs(amt)))
                elif cat != "Lương":
                    # split lines may be positive outflow portions
                    if amt > 0:
                        rows.append((ymd, cat, abs(amt)))
            continue
        try:
            amt = float(t.get("amount"))
        except (TypeError, ValueError):
            continue
        cat = (t.get("category") or "").strip()
        if not cat:
            from welora.csv_parser import vn_category_label

            cat = vn_category_label(str(t.get("note") or t.get("description") or t.get("merchant") or ""))
        if amt < 0:
            rows.append((ymd, cat, abs(amt)))
        elif cat != "Lương" and amt > 0:
            # Manual OS convention: negative = outflow. Positive non-salary treated as outflow only for CSV-like.
            # For OS manual, positive usually means income/credit — skip non-negative OS amounts.
            # Keep CSV path separate; for OS avg we only count amount < 0 (and split abs).
            pass
    return rows


def budget_draft_from_avg(
    user_id: str,
    *,
    months: int = 3,
    account_id: Optional[str] = None,
    txs: Optional[list[dict[str, Any]]] = None,
) -> tuple[int, dict[str, Any]]:
    """Draft budget from real average monthly outflow over 3..6 calendar months."""
    if not (user_id or "").strip():
        return 400, {"error": "user_id is required", "auto_overwrite": False}
    m, err = _clamp_months(months if months is not None else 3)
    if err:
        return 400, {"error": err, "auto_overwrite": False}
    assert m is not None

    raw_txs = list(txs) if txs is not None else _collect_os_txs(user_id, account_id=account_id)
    rows = _expand_tx_outflows(raw_txs)
    if not rows:
        return 400, {
            "error": "no_outflow_history",
            "auto_overwrite": False,
            "hint": "Không có giao dịch chi tiêu thật để tính trung bình. Thêm giao dịch OS (hoặc CSV đã lưu) trước.",
        }

    # Calendar months present in history (sorted ascending).
    month_set: set[str] = set()
    for ymd, _cat, _amt in rows:
        month_set.add(ymd[:7])
    available_months = sorted(month_set)
    if not available_months:
        return 400, {
            "error": "no_outflow_history",
            "auto_overwrite": False,
            "hint": "Không có tháng lịch sử chi tiêu.",
        }

    # Clamp window to available history: take last up-to-m months.
    months_used = min(m, len(available_months))
    window = available_months[-months_used:]
    window_set = set(window)

    # Aggregate per category over window.
    cat_sum: dict[str, float] = {}
    cat_count: dict[str, int] = {}
    for ymd, cat, amt in rows:
        if ymd[:7] not in window_set:
            continue
        cat_sum[cat] = cat_sum.get(cat, 0.0) + float(amt)
        cat_count[cat] = cat_count.get(cat, 0) + 1

    if not cat_sum:
        return 400, {
            "error": "no_outflow_history",
            "auto_overwrite": False,
            "hint": "Cửa sổ tháng không có chi tiêu.",
        }

    lines: list[dict[str, Any]] = []
    for cat in sorted(cat_sum.keys()):
        total = float(cat_sum[cat])
        avg = total / float(months_used)
        kind = _kind_hint_for_category(user_id, cat)
        line: dict[str, Any] = {
            "category": cat,
            "avg_monthly": round(avg, 2),
            "outflow": round(avg, 2),  # allocated hint — monthly average
            "allocated": round(avg, 2),
            "months_used": months_used,
            "count": int(cat_count.get(cat) or 0),
            "rollover_in": 0.0,
            "spent": 0.0,
            "remaining": round(avg, 2),
            "rollover_out": 0.0,
        }
        if kind:
            line["kind"] = kind
        lines.append(line)

    goal_lines = _goal_contrib_lines(user_id)
    draft = {
        "kind": "budget_draft",
        "auto_overwrite": False,
        "source": "avg_spend",
        "months_requested": m,
        "months_used": months_used,
        "window_months": window,
        "lines": lines,
        "total_outflow": float(sum(float(x["avg_monthly"]) for x in lines)),
        "goal_contrib_lines": goal_lines,
        "fictional_estimate": False,
    }
    return 200, {"ok": True, "draft": draft, "auto_overwrite": False}


def get_budget(user_id: str) -> Optional[dict[str, Any]]:
    return _BUDGETS.get(user_id)


def get_budget_period(user_id: str, period: str) -> Optional[dict[str, Any]]:
    return _BUDGET_PERIODS.get(_period_key(user_id, period))


def apply_budget(
    user_id: str,
    *,
    confirm: bool,
    replace_existing: bool = False,
    draft: Optional[dict[str, Any]] = None,
    lines: Optional[list[dict[str, Any]]] = None,
    period: Optional[str] = None,
    goal_contrib_lines: Optional[list[dict[str, Any]]] = None,
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

    # Normalize lines with rollover fields (preserve CSV shape).
    norm_lines: list[dict[str, Any]] = []
    for x in use_lines:
        row = dict(x)
        allocated = row.get("allocated")
        if allocated is None:
            allocated = row.get("avg_monthly")
        if allocated is None:
            allocated = row.get("outflow")
        try:
            alloc_f = float(allocated or 0)
        except (TypeError, ValueError):
            alloc_f = 0.0
        try:
            rin = float(row.get("rollover_in") or 0)
        except (TypeError, ValueError):
            rin = 0.0
        try:
            spent = float(row.get("spent") or 0)
        except (TypeError, ValueError):
            spent = 0.0
        remaining = max(0.0, alloc_f + rin - spent)
        row.setdefault("allocated", alloc_f)
        row["rollover_in"] = rin
        row["spent"] = spent
        row["remaining"] = remaining
        row.setdefault("rollover_out", 0.0)
        norm_lines.append(row)

    g_lines = goal_contrib_lines
    if g_lines is None:
        g_lines = payload.get("goal_contrib_lines")
    if g_lines is None:
        # Always attach current goal contribs (read-only) when applying from avg or missing.
        g_lines = _goal_contrib_lines(user_id)
    g_lines = list(g_lines or [])

    use_period = _parse_period(period or payload.get("period")) or datetime.now(timezone.utc).strftime("%Y-%m")

    record = {
        "user_id": user_id,
        "kind": "budget",
        "status": "applied",
        "period": use_period,
        "lines": norm_lines,
        "goal_contrib_lines": g_lines,
        "total_outflow": float(
            payload.get("total_outflow")
            or sum(float(x.get("outflow") or x.get("avg_monthly") or x.get("allocated") or 0) for x in norm_lines)
        ),
        "source": payload.get("source") or "csv_parse",
        "months_used": payload.get("months_used"),
        "window_months": payload.get("window_months"),
        "auto_overwrite": False,
        "applied_at": _now(),
        "replaced": bool(existing),
    }
    # Snapshot goals at apply time for audit — do NOT write back to goal stores.
    record["goals_touched"] = False
    _BUDGETS[user_id] = record
    _BUDGET_PERIODS[_period_key(user_id, use_period)] = dict(record)
    return 200, {"ok": True, "budget": record, "replaced": bool(existing), "auto_overwrite": False}


def close_budget_period(
    user_id: str,
    *,
    period: str,
    confirm: bool,
    spent_by_category: Optional[dict[str, Any]] = None,
) -> tuple[int, dict[str, Any]]:
    """Close a budget period: remaining carries to next as rollover_in (non-negative)."""
    if not (user_id or "").strip():
        return 400, {"error": "user_id is required", "auto_overwrite": False}
    if not confirm:
        return 400, {
            "error": "confirm required",
            "auto_overwrite": False,
            "hint": "User phải xác nhận trước khi đóng kỳ ngân sách.",
        }
    per = _parse_period(period)
    if not per:
        return 400, {"error": "period required (YYYY-MM)", "auto_overwrite": False}

    current = get_budget_period(user_id, per) or (
        _BUDGETS.get(user_id) if (_BUDGETS.get(user_id) or {}).get("period") == per else None
    )
    if not current:
        # Allow closing the active budget if period omitted match
        active = _BUDGETS.get(user_id)
        if active and (not active.get("period") or active.get("period") == per):
            current = active
            current = dict(current)
            current["period"] = per
        else:
            return 404, {
                "error": "budget_period_not_found",
                "auto_overwrite": False,
                "hint": f"Không tìm thấy ngân sách kỳ {per}.",
            }

    spent_map: dict[str, float] = {}
    if isinstance(spent_by_category, dict):
        for k, v in spent_by_category.items():
            try:
                spent_map[str(k)] = float(v)
            except (TypeError, ValueError):
                continue

    closed_lines: list[dict[str, Any]] = []
    for line in list(current.get("lines") or []):
        row = dict(line)
        cat = str(row.get("category") or "")
        try:
            alloc = float(row.get("allocated") if row.get("allocated") is not None else (row.get("avg_monthly") if row.get("avg_monthly") is not None else row.get("outflow") or 0))
        except (TypeError, ValueError):
            alloc = 0.0
        try:
            rin = float(row.get("rollover_in") or 0)
        except (TypeError, ValueError):
            rin = 0.0
        if cat in spent_map:
            spent = spent_map[cat]
        else:
            try:
                spent = float(row.get("spent") or 0)
            except (TypeError, ValueError):
                spent = 0.0
        remaining = max(0.0, alloc + rin - spent)
        row["allocated"] = alloc
        row["rollover_in"] = rin
        row["spent"] = spent
        row["remaining"] = remaining
        row["rollover_out"] = remaining  # carry forward
        closed_lines.append(row)

    closed = dict(current)
    closed["lines"] = closed_lines
    closed["period"] = per
    closed["status"] = "closed"
    closed["closed_at"] = _now()
    closed["auto_overwrite"] = False
    _BUDGET_PERIODS[_period_key(user_id, per)] = closed

    nxt = _next_period(per)
    next_lines: list[dict[str, Any]] = []
    for row in closed_lines:
        alloc = float(row.get("allocated") or 0)
        rin = float(row.get("rollover_out") or 0)
        next_lines.append(
            {
                "category": row.get("category"),
                "allocated": alloc,
                "avg_monthly": row.get("avg_monthly", alloc),
                "outflow": row.get("outflow", alloc),
                "months_used": row.get("months_used"),
                "count": row.get("count"),
                "kind": row.get("kind"),
                "rollover_in": rin,  # previous remaining — never silently wiped
                "spent": 0.0,
                "remaining": alloc + rin,
                "rollover_out": 0.0,
            }
        )

    next_record = {
        "user_id": user_id,
        "kind": "budget",
        "status": "applied",
        "period": nxt,
        "lines": next_lines,
        "goal_contrib_lines": list(current.get("goal_contrib_lines") or _goal_contrib_lines(user_id)),
        "total_outflow": float(sum(float(x.get("allocated") or 0) for x in next_lines)),
        "source": current.get("source") or "rollover",
        "auto_overwrite": False,
        "applied_at": _now(),
        "rolled_from": per,
        "replaced": False,
        "goals_touched": False,
    }
    _BUDGET_PERIODS[_period_key(user_id, nxt)] = next_record
    _BUDGETS[user_id] = next_record

    return 200, {
        "ok": True,
        "closed": closed,
        "next": next_record,
        "auto_overwrite": False,
    }


def service_get(user_id: str) -> tuple[int, dict[str, Any]]:
    if not user_id:
        return 400, {"error": "user_id is required"}
    b = get_budget(user_id)
    return 200, {
        "ok": True,
        "budget": b,
        "status": (b or {}).get("status") or "none",
        "auto_overwrite": False,
    }


def service_apply(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    body = body or {}
    return apply_budget(
        str(body.get("user_id") or ""),
        confirm=bool(body.get("confirm")),
        replace_existing=bool(body.get("replace_existing")),
        draft=body.get("draft") if isinstance(body.get("draft"), dict) else None,
        lines=body.get("lines") if isinstance(body.get("lines"), list) else None,
        period=body.get("period"),
        goal_contrib_lines=(
            body.get("goal_contrib_lines")
            if isinstance(body.get("goal_contrib_lines"), list)
            else None
        ),
    )


def service_draft_from_avg(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    body = body or {}
    months_raw = body.get("months", 3)
    try:
        months_i = int(months_raw) if months_raw is not None else 3
    except (TypeError, ValueError):
        months_i = -1
    account_id = body.get("account_id")
    account_s = str(account_id).strip() if account_id else None
    return budget_draft_from_avg(
        str(body.get("user_id") or ""),
        months=months_i,
        account_id=account_s or None,
    )


def service_close_period(body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    body = body or {}
    spent = body.get("spent_by_category")
    return close_budget_period(
        str(body.get("user_id") or ""),
        period=str(body.get("period") or ""),
        confirm=bool(body.get("confirm")),
        spent_by_category=spent if isinstance(spent, dict) else None,
    )


# Alias used by some callers / docs
service_rollover = service_close_period

