"""P1 G1 — OS Flow 3: Pedia inline cho Goal WeloraOS.

Canonical keys sống ở content_map.CONTENT_BY_KEY.
Không auto-navigate; excerpt + deep-link khi user bấm.
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


def keys_for_goal_type(goal_type: str) -> list[str]:
    return list(GOAL_PEDIA_KEYS.get(str(goal_type or ""), []))


def excerpt_body(md: str, limit: int = EXCERPT_LIMIT) -> str:
    text = (md or "").replace("\r\n", "\n")
    text = re.sub(r"^#+\s*", "", text, flags=re.M)
    text = re.sub(r"[*_`]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]).rstrip(".,:;") + "…"


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
