"""User-facing percent — max 1 decimal, Vietnamese comma. Mirrors WeloraMoney.formatPct."""

from __future__ import annotations


def format_pct(n: object) -> str:
    try:
        x = float(n)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "0%"
    if x != x or x in (float("inf"), float("-inf")):
        return "0%"
    r = round(x * 10) / 10.0
    if abs(r - round(r)) < 1e-9:
        return f"{int(round(r))}%"
    s = f"{r:.1f}".replace(".", ",")
    return s + "%"
