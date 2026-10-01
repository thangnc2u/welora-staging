"""Data step 014_phone_e164_data (run by welora.db.migrate after 014_phone_e164.sql).

* users.phone: each row whose E.164 form is unique among all rows is rewritten to E.164. When two
  or more rows normalise to the same number (e.g. '0900012095' and '+84900012095' on two
  accounts) NONE of them is changed or merged: the group is recorded in phone_e164_conflicts
  and logged for manual review. Lookups stay safe for such rows (exact E.164 wins; several legacy
  matches → refused).
* otp_challenges.phone: rewritten per raw value, unless the variants of one number belong to
  different phone-OTP users (that would silently merge two accounts) → recorded + skipped.
* Unparseable values are left as they are. Idempotent: a re-run changes nothing new and does
  not duplicate conflict rows (deterministic id).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any

from welora.phone import try_normalize

log = logging.getLogger("welora.phone_migration")


def _record_conflict(conn, table: str, norm: str, user_ids: list[str], raws: list[str]) -> None:
    uids = sorted({u for u in user_ids if u})
    cid = hashlib.sha256(f"{table}|{norm}|{'|'.join(uids)}".encode("utf-8")).hexdigest()[:32]
    if conn.execute("SELECT 1 FROM phone_e164_conflicts WHERE id=?", (cid,)).fetchone():
        return
    conn.execute(
        "INSERT INTO phone_e164_conflicts(id, table_name, normalized, user_ids, raw_values, detected_at) "
        "VALUES (?,?,?,?,?,?)",
        (cid, table, norm, json.dumps(uids), json.dumps(sorted(set(raws))), datetime.now(timezone.utc).isoformat()),
    )
    log.warning("phone E.164 collision skipped: table=%s accounts=%d (see phone_e164_conflicts id=%s)",
                table, len(uids), cid)


def normalize_existing_phones(conn, dialect: str = "sqlite") -> dict[str, Any]:
    report = {"users_updated": 0, "users_conflicts": 0, "otp_updated": 0, "otp_conflicts": 0}

    groups: dict[str, list[Any]] = {}
    for r in conn.execute("SELECT user_id, phone FROM users WHERE phone IS NOT NULL AND phone <> ''").fetchall():
        norm = try_normalize(r["phone"])
        if norm:
            groups.setdefault(norm, []).append(r)
    for norm, rows in groups.items():
        if len(rows) > 1:
            _record_conflict(conn, "users", norm, [r["user_id"] for r in rows], [r["phone"] for r in rows])
            report["users_conflicts"] += 1
            continue
        r = rows[0]
        if r["phone"] != norm:
            cur = conn.execute("UPDATE users SET phone=? WHERE user_id=? AND phone=?", (norm, r["user_id"], r["phone"]))
            report["users_updated"] += int(cur.rowcount or 0)

    otp: dict[str, dict[str, set]] = {}
    for r in conn.execute(
        "SELECT phone, user_id, consumed FROM otp_challenges WHERE phone IS NOT NULL AND phone <> ''"
    ).fetchall():
        norm = try_normalize(r["phone"])
        if not norm:
            continue
        g = otp.setdefault(norm, {})
        owners = g.setdefault(r["phone"], set())
        if r["consumed"] and r["user_id"]:
            owners.add(str(r["user_id"]))
    for norm, variants in otp.items():
        owners_all = set().union(*variants.values())
        if len(variants) > 1 and len(owners_all) > 1:
            _record_conflict(conn, "otp_challenges", norm, list(owners_all), list(variants))
            report["otp_conflicts"] += 1
            continue
        for raw in variants:
            if raw != norm:
                cur = conn.execute("UPDATE otp_challenges SET phone=? WHERE phone=?", (norm, raw))
                report["otp_updated"] += int(cur.rowcount or 0)
    conn.commit()
    if any(report.values()):
        log.info("phone E.164 migration: %s", report)
    return report
