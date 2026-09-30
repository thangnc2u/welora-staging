"""Renewal reminders + grace + downgrade (Phụ lục Checkout mục 7 · PAY-04 · PAY-05).

VietQR cannot auto-debit, so each period is a new order. This job:
- sends reminders per config ``checkout_rules.renewal.schedule`` (month: D-3, D0,
  D+3, D+7 · year: D-14, D-3, D0, D+3, D+7) via email (welora.mailer) and push
  (welora.push, pluggable, log-only by default). No SMS / Zalo (PAY-05).
- moves subscriptions active → grace after period end (full access, banner) and
  grace → expired after 7 days: downgrade to FREE via entitlements. User data
  (budgets, learning progress) is NOT touched — kept ≥ 12 months.
- is idempotent: UNIQUE(subscription_id, period_end, step). If the job was down,
  only the latest due step is sent; skipped earlier steps are recorded.
- runs in-process (same FastAPI process, no new Render service); ``run_once(now=)``
  is a plain function for tests and the admin "run now" button.

Copy describes the plan only — no promise of financial outcomes (Firewall).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from typing import Any, Optional

from welora import checkout as co
from welora import checkout_pricing as cp
from welora import entitlements as ent
from welora import mailer, push

log = logging.getLogger("welora.renewal")

DEFAULT_INTERVAL_S = 3600


def schedule(cycle: str) -> list[dict[str, Any]]:
    sch = ((cp.rules().get("renewal") or {}).get("schedule") or {}).get(cycle) or []
    return sorted((dict(x) for x in sch), key=lambda x: float(x.get("offset_days") or 0))


def _vnd(n: int) -> str:
    return f"{int(n):,}".replace(",", ".") + "đ"


def reminder_text(*, step: dict[str, Any], plan_id: str, cycle: str, period_end: float, link: str) -> tuple[str, str]:
    info = ent.plan_by_code(plan_id) or {}
    name = info.get("name") or plan_id
    off = float(step.get("offset_days") or 0)
    grace_end = period_end + ent.GRACE_DAYS * 86400
    if step.get("final"):
        subject = f"Welora · {name} đã chuyển về gói Free"
        lead = (
            f"Thời gian ân hạn {ent.GRACE_DAYS} ngày của gói {name} đã kết thúc nên tài khoản đã chuyển về gói Free. "
            "Dữ liệu của bạn (ngân sách, tiến độ học) vẫn được giữ nguyên. Gia hạn bất cứ lúc nào để mở lại gói."
        )
    elif off < 0:
        subject = f"Welora · {name} hết hạn sau {int(-off)} ngày"
        lead = f"Gói {name} hết hạn vào {co._ict(period_end)}. Gia hạn sớm không mất ngày còn lại: kỳ mới nối tiếp ngày hết hạn."
    elif off == 0:
        subject = f"Welora · {name} hết hạn hôm nay"
        lead = f"Gói {name} hết hạn hôm nay. Bạn có {ent.GRACE_DAYS} ngày ân hạn, vẫn dùng đầy đủ đến {co._ict(grace_end)}."
    else:
        subject = f"Welora · Còn {int(ent.GRACE_DAYS - off)} ngày ân hạn cho {name}"
        lead = f"Gói {name} đang trong thời gian ân hạn đến {co._ict(grace_end)}. Sau đó tài khoản chuyển về gói Free."
    body = lead + f"\n\nGia hạn một chạm (link hết hạn sau 24 giờ): {link}\n"
    if cycle == "month":
        m = ent.price_amount(plan_id, "month") or 0
        y = ent.price_amount(plan_id, "year") or 0
        if m and y and m * 12 > y:
            body += (
                f"\nGợi ý: chuyển sang gói năm — {_vnd(m)} × 12 = {_vnd(m * 12)} so với {_vnd(y)}/năm "
                f"(tiết kiệm {_vnd(m * 12 - y)}).\n"
            )
    body += "\nWelora cung cấp thông tin và công cụ quản lý tài chính cá nhân, không tư vấn đầu tư.\n"
    return subject, body


def _record(conn: Any, sub_id: str, period_end: str, step: str, channels: list[str], status: str, now: float) -> bool:
    try:
        conn.execute(
            "INSERT INTO renewal_reminders(id, subscription_id, period_end, step, channels, status, sent_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, sub_id, period_end, step, json.dumps(channels), status, co._iso(now)),
        )
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        if co._is_unique_violation(e):
            return False
        raise


def run_once(*, now: Optional[float] = None) -> dict[str, Any]:
    if not co.checkout_enabled():
        return {"skipped": "checkout_disabled"}
    t = co._now(now)
    summary = {"checked": 0, "reminders": 0, "emails": 0, "pushes": 0, "grace": 0, "downgraded": 0, "skipped_steps": 0}
    conn = co._conn()
    try:
        rows = [
            co._row(r)
            for r in conn.execute(
                "SELECT s.*, o.billing_cycle AS last_cycle FROM subscriptions s "
                "LEFT JOIN orders o ON o.id = s.last_order_id WHERE s.status IN ('active','grace')"
            ).fetchall()
        ]
        for sub in rows:
            summary["checked"] += 1
            uid, plan = sub["user_id"], sub["plan_id"]
            cycle = sub.get("last_cycle") or "month"
            end_iso = sub["current_period_end"]
            end = co._ts(end_iso)
            grace_end = end + ent.GRACE_DAYS * 86400

            # --- reminders (latest due step only; earlier missed steps recorded as skipped)
            steps = schedule(cycle)
            due = [s for s in steps if t >= end + float(s.get("offset_days") or 0) * 86400]
            if due:
                latest = due[-1]
                for s in due[:-1]:
                    if _record(conn, sub["id"], end_iso, str(s["step"]), list(s.get("channels") or []), "skipped", t):
                        summary["skipped_steps"] += 1
                chans = list(latest.get("channels") or ["email"])
                if _record(conn, sub["id"], end_iso, str(latest["step"]), chans, "sent", t):
                    summary["reminders"] += 1
                    link = co.create_renewal_link(conn, user_id=uid, plan_id=plan, billing_cycle=cycle, now=t)
                    subject, body = reminder_text(step=latest, plan_id=plan, cycle=cycle, period_end=end, link=link)
                    if "email" in chans:
                        email = co._user_email(conn, uid)
                        if email:
                            mailer.enqueue(email, subject, body)
                            summary["emails"] += 1
                    if "push" in chans:
                        push.send(uid, subject, body.split("\n", 1)[0], {"type": "renewal", "plan": plan, "step": latest["step"]})
                        summary["pushes"] += 1
                    ent.emit_event("renewal_reminder", {"plan": plan, "step": latest["step"], "channels": chans})

            # --- status: active → grace → expired (downgrade to FREE, data kept)
            if t > grace_end:
                cur = conn.execute(
                    "UPDATE subscriptions SET status='expired' WHERE id=? AND status IN ('active','grace')", (sub["id"],)
                )
                conn.commit()
                if (cur.rowcount or 0) == 1:
                    summary["downgraded"] += 1
                    co._refresh_entitlement(uid, reason="grace_ended")
                    ent.emit_event("subscription_downgraded_free", {"plan": plan, "reason": "grace_ended"})
            elif t > end and sub["status"] == "active":
                conn.execute("UPDATE subscriptions SET status='grace' WHERE id=? AND status='active'", (sub["id"],))
                conn.commit()
                summary["grace"] += 1
                co._refresh_entitlement(uid, reason="grace")
        return summary
    finally:
        conn.close()


_stop = threading.Event()
_thread: Optional[threading.Thread] = None


def start_loop(interval_s: Optional[float] = None) -> Optional[threading.Thread]:
    """In-process loop (no new Render service). WELORA_RENEWAL_JOB=0 disables."""
    global _thread
    if (os.environ.get("WELORA_RENEWAL_JOB") or "1").strip() == "0":
        return None
    if _thread and _thread.is_alive():
        return _thread
    try:
        iv = float(interval_s or os.environ.get("WELORA_RENEWAL_INTERVAL_S") or DEFAULT_INTERVAL_S)
    except ValueError:
        iv = DEFAULT_INTERVAL_S
    _stop.clear()

    def _loop() -> None:
        while not _stop.wait(iv):
            try:
                if co.checkout_enabled():
                    run_once()
            except Exception as e:
                log.warning("renewal loop error: %s", type(e).__name__)

    _thread = threading.Thread(target=_loop, name="welora-renewal", daemon=True)
    _thread.start()
    return _thread


def stop_loop() -> None:
    _stop.set()
