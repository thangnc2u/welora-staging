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


def pick_phone_row(rows: Iterable[Any], e164: str) -> Optional[Any]:
    """Exact E.164 row wins; one legacy-format row is accepted; several legacy rows for the same
    number (an unresolved migration collision) are ambiguous → None (caller refuses)."""
    rows = list(rows)
    exact = [r for r in rows if r["phone"] == e164]
    if exact:
        return exact[0]
    return rows[0] if len(rows) == 1 else None


def find_user_by_phone(conn, e164: str, cols: str = "*") -> Optional[Any]:
    cands = lookup_candidates(e164)
    rows = conn.execute(
        f"SELECT {cols} FROM users WHERE phone IN (" + ",".join("?" * len(cands)) + ")", tuple(cands)
    ).fetchall()
    return pick_phone_row(rows, e164)


def phone_taken(conn, e164: str) -> bool:
    cands = lookup_candidates(e164)
    return conn.execute(
        "SELECT 1 FROM users WHERE phone IN (" + ",".join("?" * len(cands)) + ") LIMIT 1", tuple(cands)
    ).fetchone() is not None
