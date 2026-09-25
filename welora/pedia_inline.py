"""P1 G1 — OS Flow 3: Pedia inline cho Goal WeloraOS.

Canonical keys sống ở content_map.CONTENT_BY_KEY.
Không auto-navigate; excerpt + deep-link khi user bấm.
Display-layer strips editorial frontmatter + CORE/SAFE/DEBT codes
from user-facing excerpt (keys remain internal for fetch/href).
"""

from __future__ import annotations

import re
from typing import Any, Optional

from welora.content_map import get_article

EXCERPT_LIMIT = 220

GOAL_PEDIA_KEYS: dict[str, list[str]] = {
    "emergency_fund": ["SAFE-01"],
    "debt_payoff": ["DEBT-01", "DEBT-02", "DEBT-03"],
}

_INTERNAL_KEY_RE = re.compile(r"\b(?:CORE|SAFE|DEBT)-\d+\b")
_META_LABEL_RE = re.compile(
    r"(?i)\*{0,2}\s*(?:principle[_ ]?key|secondary[_ ]?keys)\s*:\s*"
    r"[A-Z0-9*_,\s\u2014\u2013\-]+\*{0,2}"
)


def strip_frontmatter(md: str) -> str:
    """Drop Welorapedia editorial head (WP-*, Module, principle_key, ---)."""
    s = (md or "").replace("\ufeff", "")
    m = re.search(r"\n---\s*\n", s)
    if m:
        head = s[: m.start()]
        if re.search(
            r"principle_key|Module:|Mức rủi ro|Version:|Status:|^#\s*W[AP]-",
            head,
            flags=re.M,
        ):
            s = s[m.end() :]
    lines = s.split("\n")
    while lines:
        t = lines[0].strip()
        if not t:
            lines.pop(0)
            continue
        if re.match(r"^#\s*W[AP]-", t):
            lines.pop(0)
            continue
        if re.match(
            r"^\*\*(Module|Mức rủi ro|Version|Status|principle_key|secondary_keys):",
            t,
            flags=re.I,
        ):
            lines.pop(0)
            continue
        break
    return "\n".join(lines).lstrip()


def scrub_internal_codes(text: str) -> str:
    """Remove leftover CORE-/SAFE-/DEBT- tokens from learner-facing copy."""
    out = _META_LABEL_RE.sub(" ", text or "")
    out = _INTERNAL_KEY_RE.sub("", out)
    out = re.sub(r"\s{2,}", " ", out).strip(" .,;:-")
    return out


def keys_for_goal_type(goal_type: str) -> list[str]:
    return list(GOAL_PEDIA_KEYS.get(str(goal_type or ""), []))


def excerpt_body(md: str, limit: int = EXCERPT_LIMIT) -> str:
    text = strip_frontmatter(md or "").replace("\r\n", "\n")
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = scrub_internal_codes(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return scrub_internal_codes((cut or text[:limit]).rstrip(".,:;") + "…")


def pedia_card(key: str) -> Optional[dict[str, Any]]:
    art = get_article(key)
    if not art.get("ok"):
        return None
    wp = list(art.get("wp") or [])
    module = str(art.get("module") or "")
    return {
        "principle_key": art.get("principle_key") or key,
        "title": art.get("title") or key,
        "excerpt": excerpt_body(str(art.get("body_markdown") or "")),
        "href": art.get("href") or f"/app/content?key={key}",
        "academy_href": f"/app/academy?from=pedia&key={key}",
        "academy_label": "Học sâu hơn · Welorademy",
        "linked_module_id": "M02" if module == "02" else (f"M{module.zfill(2)}" if module.isdigit() else None),
        "linked_article_id": wp[0] if wp else None,
    }


def pedia_cards_for_goal(goal_type: str) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for key in keys_for_goal_type(goal_type):
        card = pedia_card(key)
        if card:
            cards.append(card)
    return cards
