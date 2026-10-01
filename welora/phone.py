"""Phone numbers in E.164 (P0 follow-up 2, item 9).

Saved form: ``+<country><national>`` with Vietnam (+84) as the default country:
  0900012095 / 0900 012 095 / 84900012095 / +84 900 012 095 / 0084900012095 / +840900012095
  → +84900012095. Any other ``+``/``00`` international number is kept (digits only).
Old rows may still hold the local form (written before migration 014, or skipped as a collision),
so lookups use ``lookup_candidates`` and prefer the exact E.164 row (``pick_phone_row``).
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

DEFAULT_CC = "84"
_E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")
PHONE_INVALID_MSG = "số điện thoại không hợp lệ"


def normalize_phone_e164(phone: Optional[str]) -> Optional[str]:
    """E.164 string, None for empty input, ValueError (VI message) when not a phone number."""
    if phone is None:
        return None
    p = re.sub(r"[\s\-().]", "", str(phone).strip())
    if not p:
        return None
    if p.startswith("00"):
        p = "+" + p[2:]
    if p.startswith("+"):
        digits = p[1:]
        if not digits.isdigit():
            raise ValueError(PHONE_INVALID_MSG)
        if digits.startswith(DEFAULT_CC + "0"):  # +84 0900… (trunk 0 kept by mistake)
            digits = DEFAULT_CC + digits[len(DEFAULT_CC) + 1:]
    elif p.isdigit():
        if p.startswith("0"):
            digits = DEFAULT_CC + p[1:]
        elif p.startswith(DEFAULT_CC) and len(p) >= 11:
            digits = p
        else:
            digits = DEFAULT_CC + p  # national number typed without the trunk 0
    else:
        raise ValueError(PHONE_INVALID_MSG)
    e = "+" + digits
    if not _E164.match(e):
        raise ValueError(PHONE_INVALID_MSG)
    return e


def try_normalize(phone: Optional[str]) -> Optional[str]:
    try:
        return normalize_phone_e164(phone)
    except ValueError:
        return None


def lookup_candidates(e164: str) -> list[str]:
    """Stored forms that denote this number: E.164 first, then legacy local / bare forms."""
    out = [e164]
    if e164.startswith("+" + DEFAULT_CC):
        national = e164[1 + len(DEFAULT_CC):]
        out += ["0" + national, DEFAULT_CC + national]
    else:
        out.append(e164[1:])
    return list(dict.fromkeys(out))


PHONE_CONFLICT_MSG = (
    "Số điện thoại này đang gắn với nhiều tài khoản (dữ liệu cũ) nên tạm thời không dùng được để "
    "đăng nhập hoặc đặt lại mật khẩu. Vui lòng đăng nhập bằng email; nếu tài khoản chưa có email, "
    "hãy liên hệ hỗ trợ Welora."
)


class PhoneConflictError(Exception):
    """The number is ambiguous (several accounts) — phone login / OTP / reset are refused."""

    def __init__(self, message: str = PHONE_CONFLICT_MSG) -> None:
        super().__init__(message)


def pick_phone_row(rows: Iterable[Any], e164: str) -> Optional[Any]:
    """Exactly one row for the number → that row. Several rows (e.g. legacy '0900…' AND '+84900…'
    = two accounts, an unresolved migration collision) are AMBIGUOUS → None — no account is
    preferred (CoS review #239: the +84 row no longer wins; callers refuse the phone path)."""
    rows = list(rows)
    return rows[0] if len(rows) == 1 else None


def candidate_rows(conn, e164: str, cols: str = "*") -> list[Any]:
    cands = lookup_candidates(e164)
    return list(conn.execute(
        f"SELECT {cols} FROM users WHERE phone IN (" + ",".join("?" * len(cands)) + ")", tuple(cands)
    ).fetchall())


def phone_conflicted(conn, e164: str) -> bool:
    """True when this number cannot identify ONE account: it is recorded in
    ``phone_e164_conflicts`` (migration 014 collision report, any table) or more than one user row
    currently matches its stored forms. Resolution is manual (fix the rows, delete the report row)."""
    if not e164:
        return False
    if len(candidate_rows(conn, e164, "user_id")) > 1:
        return True
    row = conn.execute("SELECT 1 FROM phone_e164_conflicts WHERE normalized=? LIMIT 1", (e164,)).fetchone()
    return row is not None


def find_user_by_phone(conn, e164: str, cols: str = "*") -> Optional[Any]:
    """The single account for this number, or None (unknown OR conflicted — callers that need to
    tell the owner apart check ``phone_conflicted`` themselves without leaking existence)."""
    if phone_conflicted(conn, e164):
        return None
    if "phone" not in cols and cols.strip() != "*":
        cols = cols + ", phone"
    return pick_phone_row(candidate_rows(conn, e164, cols), e164)


def phone_taken(conn, e164: str) -> bool:
    cands = lookup_candidates(e164)
    return conn.execute(
        "SELECT 1 FROM users WHERE phone IN (" + ",".join("?" * len(cands)) + ") LIMIT 1", tuple(cands)
    ).fetchone() is not None
