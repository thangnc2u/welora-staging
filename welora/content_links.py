"""
Welora — content link helpers (CTA / Deny deep-links)
Thin wrapper around content_map for chat responses.
"""

from __future__ import annotations

from typing import Any

from welora.content_map import CTA_CONTENT, enrich_cta, resolve_keys


def links_for_principle_keys(keys: list[str]) -> list[dict[str, Any]]:
    return resolve_keys(keys)


def links_for_cta(codes: list[str]) -> list[dict[str, str]]:
    return enrich_cta(codes)


def primary_learn_href(principle_keys: list[str]) -> str | None:
    links = resolve_keys(principle_keys)
    if not links:
        return None
    return links[0].get("href")
