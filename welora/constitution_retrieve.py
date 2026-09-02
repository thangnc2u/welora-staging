"""P0 — Agent bắt buộc retrieve Hiến pháp Cốt lõi + Hiến pháp Cá nhân.

Load TRƯỚC evaluate_pre_rules và TRƯỚC LLM.
Không đổi rule_id / detect R01–R09.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Map Hard Deny → CORE (title Cốt lõi ưu tiên hơn SAFE/DEBT khi render).
RULE_TO_CORE: dict[str, list[str]] = {
    "R01": ["CORE-07"],
    "R02": ["CORE-07"],
    "R03": ["CORE-07"],
    "R04": ["CORE-01"],
    "R05": ["CORE-05"],
    "R06": ["CORE-07"],
    "R07": ["CORE-07", "CORE-03"],
    "R08": ["CORE-07"],
    "R09": ["CORE-07"],
}

CONSTRAINT_RANK = {"hard_ban": 0, "soft_limit": 1, "priority_guidance": 2}
ADVISORY_TOP_N = 4


class CoreConstitutionMissing(RuntimeError):
    """Cốt lõi trống / không load được — Agent không được im lặng bỏ retrieve."""


@dataclass
class ConstitutionBundle:
    ok: bool
    error: str = ""
    constitution_version: str = ""
    constitution_id: str = ""
    core_articles: list[dict[str, Any]] = field(default_factory=list)
    personal_codes: list[str] = field(default_factory=list)
    personal_articles: list[dict[str, Any]] = field(default_factory=list)

    @property
    def personal_codes_count(self) -> int:
        return len(self.personal_codes)

    @property
    def core_articles_count(self) -> int:
        return len(self.core_articles)


def _core_index() -> dict[str, dict[str, Any]]:
    from welora.core_constitution import get_core_constitution

    core = get_core_constitution()
    articles = list(core.get("articles") or [])
    if not articles:
        raise CoreConstitutionMissing(
            "Hiến pháp Cốt lõi trống — Agent dừng để bảo vệ An Toàn."
        )
    by_code = {str(a.get("code")): a for a in articles if a.get("code")}
    if not by_code:
        raise CoreConstitutionMissing(
            "Hiến pháp Cốt lõi không có mã CORE — Agent dừng."
        )
    return {
        "version": str(core.get("version") or ""),
        "constitution_id": str(core.get("constitution_id") or ""),
        "articles": articles,
        "by_code": by_code,
    }


def load_core_or_raise() -> dict[str, Any]:
    return _core_index()


def retrieve_constitution(
    *,
    personal_codes: Optional[list[str]] = None,
    personal_articles: Optional[list[dict[str, Any]]] = None,
    user_id: Optional[str] = None,
) -> ConstitutionBundle:
    """Load Cốt lõi + (tuỳ chọn) Hiến pháp Cá nhân. Không im lặng khi Cốt lõi thiếu."""
    codes = [str(c) for c in (personal_codes or []) if c]
    articles_personal = list(personal_articles or [])
    if user_id and not (codes or articles_personal):
        try:
            from welora.onboarding import get_constitution

            personal = get_constitution(user_id) or {}
            articles_personal = list(personal.get("articles") or [])
            codes = [str(a.get("code")) for a in articles_personal if a.get("code")]
        except Exception:
            articles_personal = []
            codes = list(codes)

    try:
        core = load_core_or_raise()
    except CoreConstitutionMissing as exc:
        return ConstitutionBundle(ok=False, error=str(exc), personal_codes=codes)
    except Exception as exc:
        return ConstitutionBundle(
            ok=False,
            error=f"Không tải được Hiến pháp Cốt lõi: {exc}",
            personal_codes=codes,
        )

    slim = []
    for a in core["articles"]:
        slim.append(
            {
                "code": a.get("code"),
                "title": a.get("title"),
                "principle": a.get("principle"),
                "constraint_type": a.get("constraint_type"),
                "priority": a.get("priority"),
            }
        )
    return ConstitutionBundle(
        ok=True,
        constitution_version=core["version"],
        constitution_id=core["constitution_id"],
        core_articles=slim,
        personal_codes=codes,
        personal_articles=articles_personal,
    )


def core_label(code: str, bundle: Optional[ConstitutionBundle] = None) -> str:
    art = None
    if bundle and bundle.ok:
        art = next((a for a in bundle.core_articles if a.get("code") == code), None)
    if art is None:
        try:
            art = load_core_or_raise()["by_code"].get(code)
        except Exception:
            art = None
    if not art:
        return code
    title = str(art.get("title") or "").strip()
    return f"{code} · {title}" if title else code


def labels_for_rule(rule_id: str, bundle: Optional[ConstitutionBundle] = None) -> list[str]:
    return [core_label(c, bundle) for c in RULE_TO_CORE.get(rule_id, [])]


def enrich_deny_reply(rule_id: str, body: str, bundle: Optional[ConstitutionBundle] = None) -> str:
    labels = labels_for_rule(rule_id, bundle)
    if not labels:
        return body
    header = "Nguyên lý Cốt lõi: " + " · ".join(labels)
    if header.split("Nguyên lý Cốt lõi: ", 1)[-1] and any(
        lab.split(" · ", 1)[0] in body for lab in labels
    ):
        return header + "\n" + body
    return header + "\n" + body


def top_core_articles(
    bundle: ConstitutionBundle, *, n: int = ADVISORY_TOP_N
) -> list[dict[str, Any]]:
    ranked = sorted(
        bundle.core_articles,
        key=lambda a: (
            CONSTRAINT_RANK.get(str(a.get("constraint_type") or ""), 9),
            int(a.get("priority") or 9),
            str(a.get("code") or ""),
        ),
    )
    return ranked[: max(1, n)]


def advisory_system_prefix(bundle: ConstitutionBundle) -> str:
    """Khối context bắt buộc cho advisory LLM. hard_ban trước."""
    if not bundle.ok:
        return (
            "DỬNG. Không tải được Hiến pháp Cốt lõi. Không tư vấn cá nhân hóa.\n"
        )
    lines = [
        "Welora Agent Stage 1 — An Toàn trước. Trụ giáo dục: Welorademy.",
        f"Hiến pháp Cốt lõi version={bundle.constitution_version}.",
        "Nguyên lý bắt buộc (ưu tiên hard_ban):",
    ]
    for a in top_core_articles(bundle):
        lines.append(
            f"- {a.get('code')} · {a.get('title')} [{a.get('constraint_type')}]: "
            f"{a.get('principle')}"
        )
    if bundle.personal_codes:
        lines.append(
            "Hiến pháp Cá nhân (mã): " + ", ".join(bundle.personal_codes)
        )
    lines.append("Không cam kết lợi suất. Không quyết định thay user.")
    return "\n".join(lines) + "\n"


def retrieve_missing_deny_reply(error: str) -> str:
    return (
        "Không tải được Hiến pháp Cốt lõi — Agent dừng để bảo vệ An Toàn. "
        f"{error} Quyết định cuối cùng thuộc về bạn."
    )


def audit_fields(bundle: ConstitutionBundle, *, llm_called: bool = False) -> dict[str, Any]:
    return {
        "constitution_version": bundle.constitution_version,
        "personal_codes_count": bundle.personal_codes_count,
        "core_articles_count": bundle.core_articles_count,
        "retrieve_ok": bundle.ok,
        "llm_called": llm_called,
    }


def os_nudge_for(node_id: str, *, first_pass: bool = True) -> dict[str, Any] | None:
    """Re-export — map node → Goal nudge sống ở welora.academy."""
    from welora.academy import os_nudge_for as _academy_nudge

    return _academy_nudge(node_id, first_pass=first_pass)
