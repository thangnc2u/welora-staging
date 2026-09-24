"""WeloraOS P0 — Categories first-class (Fixed / Variable / Goals + tags).

Ticket 3/4 WeloraOS parity (staging). Soft-disable + reassign history when
txs/splits reference the category name. Keep tx.category as free-string for
now (resolve by display name). No Budget envelopes (ticket 4). No Open Banking.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

KIND_FIXED = "fixed"
KIND_VARIABLE = "variable"
KIND_GOALS = "goals"

CATEGORY_KINDS = frozenset({KIND_FIXED, KIND_VARIABLE, KIND_GOALS})

KIND_LABEL_VI = {
    KIND_FIXED: "Cố định",
    KIND_VARIABLE: "Biến đổi",
    KIND_GOALS: "Mục tiêu",
}

STATUS_ACTIVE = "active"
STATUS_DISABLED = "disabled"

# Persona budget_tags P1–P6 union (latin slugs).
PERSONA_BUDGET_TAGS_UNION: frozenset[str] = frozenset({
    "an_uong",
    "bao_hiem",
    "di_chuyen",
    "giai_tri",
    "ho-tro-gia-dinh",
    "hoc_phi",
    "hoc_phi_con",
    "nha_o",
    "pyf",
    "tra_no",
})

# Sensible aliases from CATEGORY_HINTS_VI (os_transactions) not already in persona set.
CATEGORY_HINT_ALIAS_TAGS: frozenset[str] = frozenset({
    "dien_nuoc",  # Điện nước
    "luong",      # Lương
    "sieu_thi",   # Siêu thị
    "mua_sam",    # Mua sắm
    "khac",       # Khác
    "quy_khan_cap",  # Quỹ khẩn cấp / mục tiêu
})

ALL_KNOWN_TAGS: frozenset[str] = PERSONA_BUDGET_TAGS_UNION | CATEGORY_HINT_ALIAS_TAGS

# Seed matching PRD intent — Fixed / Variable / Goals + P1–P6 tags.
# names VI; tags latin slug.
DEFAULT_CATEGORIES: list[dict[str, Any]] = [
    # --- Fixed (Cố định) ---
    {"name": "Nhà ở", "kind": KIND_FIXED, "tags": ["nha_o"], "note": None},
    {"name": "Bảo hiểm", "kind": KIND_FIXED, "tags": ["bao_hiem"], "note": None},
    {"name": "Học phí", "kind": KIND_FIXED, "tags": ["hoc_phi"], "note": None},
    {"name": "Học phí con", "kind": KIND_FIXED, "tags": ["hoc_phi_con"], "note": None},
    {"name": "Trả nợ", "kind": KIND_FIXED, "tags": ["tra_no"], "note": None},
    {
        "name": "Hỗ trợ gia đình",
        "kind": KIND_FIXED,
        "tags": ["ho-tro-gia-dinh"],
        "note": None,
    },
    {"name": "Điện nước", "kind": KIND_FIXED, "tags": ["dien_nuoc"], "note": None},
    # --- Variable (Biến đổi) ---
    {"name": "Ăn uống", "kind": KIND_VARIABLE, "tags": ["an_uong"], "note": None},
    {"name": "Di chuyển", "kind": KIND_VARIABLE, "tags": ["di_chuyen"], "note": None},
    {"name": "Giải trí", "kind": KIND_VARIABLE, "tags": ["giai_tri"], "note": None},
    {"name": "Siêu thị", "kind": KIND_VARIABLE, "tags": ["sieu_thi"], "note": None},
    {"name": "Mua sắm", "kind": KIND_VARIABLE, "tags": ["mua_sam"], "note": None},
    {"name": "Lương", "kind": KIND_VARIABLE, "tags": ["luong"], "note": "Thu nhập (hint CSV)"},
    {"name": "Khác", "kind": KIND_VARIABLE, "tags": ["khac"], "note": None},
    # --- Goals (Mục tiêu) ---
    {"name": "PYF", "kind": KIND_GOALS, "tags": ["pyf"], "note": "Trả cho mình trước"},
    {
        "name": "Quỹ khẩn cấp",
        "kind": KIND_GOALS,
        "tags": ["quy_khan_cap"],
        "note": "Mục tiêu / quỹ khẩn cấp",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


_SLUG_RE = re.compile(r"[^a-z0-9_\-]+")


def normalize_tag(raw: Any) -> Optional[str]:
    """Normalize to latin slug (underscore / hyphen). Empty → None."""
    if raw is None:
        return None
    s = str(raw).strip().lower().replace(" ", "_")
    s = _SLUG_RE.sub("", s.replace("__", "_"))
    s = s.strip("_-")
    return s or None


def normalize_tags(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        # comma / space separated
        parts = re.split(r"[,;\s]+", raw.strip())
        items = parts
    elif isinstance(raw, (list, tuple, set)):
        items = list(raw)
    else:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        t = normalize_tag(item)
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def persona_budget_tags_union() -> list[str]:
    """Sorted unique budget_tags from personas P1–P6."""
    try:
        from welora.personas import PERSONAS

        tags: set[str] = set()
        for p in PERSONAS.values():
            for t in p.get("budget_tags") or []:
                nt = normalize_tag(t)
                if nt:
                    tags.add(nt)
        return sorted(tags)
    except Exception:
        return sorted(PERSONA_BUDGET_TAGS_UNION)


@dataclass
class Category:
    category_id: str
    user_id: str
    name: str
    kind: str
    tags: list[str] = field(default_factory=list)
    note: Optional[str] = None
    status: str = STATUS_ACTIVE
    disabled_at: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind_label_vi"] = KIND_LABEL_VI.get(self.kind, self.kind)
        d["tags"] = list(self.tags or [])
        return d


class InMemoryCategoryStore:
    def __init__(self) -> None:
        self._by_id: dict[str, Category] = {}

    def clear(self) -> None:
        self._by_id.clear()

    def save(self, category: Category) -> Category:
        self._by_id[category.category_id] = category
        return category

    def get(self, category_id: str) -> Optional[Category]:
        return self._by_id.get(category_id)

    def list_for_user(
        self, user_id: str, *, include_disabled: bool = False
    ) -> list[Category]:
        rows = [c for c in self._by_id.values() if c.user_id == user_id]
        if not include_disabled:
            rows = [c for c in rows if c.status != STATUS_DISABLED]
        kind_order = {KIND_FIXED: 0, KIND_VARIABLE: 1, KIND_GOALS: 2}
        rows.sort(key=lambda c: (kind_order.get(c.kind, 9), c.name.lower(), c.created_at))
        return rows

    def find_by_name(
        self, user_id: str, name: str, *, include_disabled: bool = True
    ) -> Optional[Category]:
        target = (name or "").strip().lower()
        if not target:
            return None
        for c in self.list_for_user(user_id, include_disabled=include_disabled):
            if c.name.strip().lower() == target:
                return c
        return None

    def delete_hard(self, category_id: str) -> None:
        self._by_id.pop(category_id, None)


def _use_db_store() -> bool:
    store = (os.environ.get("WELORA_STORE") or "memory").strip().lower()
    url = (os.environ.get("WELORA_DB_URL") or "").strip()
    if store in ("sqlite", "postgres", "db"):
        return True
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return True
    if url.startswith("sqlite:"):
        return True
    return False


def _make_store():
    if _use_db_store():
        try:
            from welora.db.repos import SqliteCategoryStore

            return SqliteCategoryStore(os.environ.get("WELORA_DB_URL") or None)
        except Exception:
            return InMemoryCategoryStore()
    return InMemoryCategoryStore()


STORE = _make_store()


def use_store(store) -> None:
    global STORE
    STORE = store


def reset_category_store() -> None:
    if hasattr(STORE, "clear"):
        STORE.clear()
    elif hasattr(STORE, "_by_id"):
        STORE._by_id.clear()


def _validate_kind(kind: str) -> Optional[str]:
    if kind not in CATEGORY_KINDS:
        return (
            "kind không hợp lệ — chọn: fixed (Cố định), "
            "variable (Biến đổi), goals (Mục tiêu)"
        )
    return None


def _tx_store():
    try:
        from welora import os_transactions as tx_mod

        return tx_mod.STORE
    except Exception:
        return None


def _category_name_in_use(user_id: str, name: str) -> tuple[int, list[str]]:
    """Count active+hidden txs/splits referencing category display name.

    Returns (count, sample_tx_ids).
    """
    store = _tx_store()
    if store is None:
        return 0, []
    target = (name or "").strip()
    if not target:
        return 0, []
    target_l = target.lower()
    count = 0
    samples: list[str] = []
    try:
        rows = store.list_for_user(user_id, include_hidden=True)
    except TypeError:
        rows = store.list_for_user(user_id)
    for tx in rows:
        hit = False
        cat = (getattr(tx, "category", None) or "").strip()
        if cat.lower() == target_l:
            hit = True
        for split in getattr(tx, "splits", None) or []:
            sc = (
                split.get("category")
                if isinstance(split, dict)
                else getattr(split, "category", None)
            )
            if (sc or "").strip().lower() == target_l:
                hit = True
                break
        if hit:
            count += 1
            tid = getattr(tx, "transaction_id", None) or ""
            if tid and len(samples) < 5:
                samples.append(tid)
    return count, samples


def _reassign_tx_category_strings(
    user_id: str, from_name: str, to_name: str
) -> int:
    """Rewrite tx.category / split.category from_name → to_name. Returns migrated count."""
    store = _tx_store()
    if store is None:
        return 0
    from_l = (from_name or "").strip().lower()
    to_n = (to_name or "").strip()
    if not from_l or not to_n:
        return 0
    migrated = 0
    try:
        rows = store.list_for_user(user_id, include_hidden=True)
    except TypeError:
        rows = store.list_for_user(user_id)
    for tx in rows:
        changed = False
        cat = (getattr(tx, "category", None) or "").strip()
        if cat.lower() == from_l:
            tx.category = to_n
            changed = True
        new_splits = []
        for split in getattr(tx, "splits", None) or []:
            if isinstance(split, dict):
                sc = (split.get("category") or "").strip()
                if sc.lower() == from_l:
                    split = dict(split)
                    split["category"] = to_n
                    changed = True
                new_splits.append(split)
            else:
                sc = (getattr(split, "category", None) or "").strip()
                if sc.lower() == from_l:
                    split.category = to_n
                    changed = True
                new_splits.append(split)
        if changed:
            tx.splits = new_splits
            if hasattr(tx, "updated_at"):
                tx.updated_at = _now()
            store.save(tx)
            migrated += 1
    return migrated


def service_defaults() -> tuple[int, dict]:
    items = []
    for d in DEFAULT_CATEGORIES:
        kind = d["kind"]
        items.append({
            "name": d["name"],
            "kind": kind,
            "kind_label_vi": KIND_LABEL_VI.get(kind, kind),
            "tags": list(d.get("tags") or []),
            "note": d.get("note"),
        })
    return 200, {
        "defaults": items,
        "count": len(items),
        "kinds": {
            KIND_FIXED: KIND_LABEL_VI[KIND_FIXED],
            KIND_VARIABLE: KIND_LABEL_VI[KIND_VARIABLE],
            KIND_GOALS: KIND_LABEL_VI[KIND_GOALS],
        },
        "persona_budget_tags": persona_budget_tags_union(),
        "hint_alias_tags": sorted(CATEGORY_HINT_ALIAS_TAGS),
    }


def service_create_category(body: dict) -> tuple[int, dict]:
    user_id = (body.get("user_id") or "").strip()
    if not user_id:
        return 400, {"error": "user_id is required"}
    name = (body.get("name") or "").strip()
    if not name:
        return 400, {"error": "name is required"}
    kind = (body.get("kind") or KIND_VARIABLE).strip().lower()
    err = _validate_kind(kind)
    if err:
        return 400, {"error": err}

    existing = STORE.find_by_name(user_id, name, include_disabled=True)
    if existing and existing.status == STATUS_ACTIVE:
        return 409, {
            "error": f"Danh mục '{name}' đã tồn tại",
            "category_id": existing.category_id,
        }

    tags = normalize_tags(body.get("tags"))
    note = body.get("note")
    if note is not None:
        note = str(note).strip() or None

    now = _now()
    # Re-activate disabled same-name if present
    if existing and existing.status == STATUS_DISABLED:
        existing.name = name
        existing.kind = kind
        existing.tags = tags
        existing.note = note
        existing.status = STATUS_ACTIVE
        existing.disabled_at = None
        existing.updated_at = now
        STORE.save(existing)
        return 201, existing.to_dict()

    cat = Category(
        category_id=str(uuid4()),
        user_id=user_id,
        name=name,
        kind=kind,
        tags=tags,
        note=note,
        status=STATUS_ACTIVE,
        created_at=now,
        updated_at=now,
    )
    STORE.save(cat)
    return 201, cat.to_dict()


def service_list_categories(
    user_id: str, *, include_disabled: bool = False
) -> tuple[int, dict]:
    if not (user_id or "").strip():
        return 400, {"error": "user_id is required"}
    items = [
        c.to_dict()
        for c in STORE.list_for_user(user_id, include_disabled=include_disabled)
    ]
    return 200, {
        "categories": items,
        "items": items,
        "user_id": user_id,
        "count": len(items),
        "kinds": {
            KIND_FIXED: KIND_LABEL_VI[KIND_FIXED],
            KIND_VARIABLE: KIND_LABEL_VI[KIND_VARIABLE],
            KIND_GOALS: KIND_LABEL_VI[KIND_GOALS],
        },
        "persona_budget_tags": persona_budget_tags_union(),
    }


def service_get_category(category_id: str) -> tuple[int, dict]:
    cat = STORE.get(category_id)
    if not cat:
        return 404, {"error": "category not found"}
    return 200, cat.to_dict()


def service_update_category(category_id: str, body: dict) -> tuple[int, dict]:
    cat = STORE.get(category_id)
    if not cat:
        return 404, {"error": "category not found"}

    old_name = cat.name

    if "name" in body and body["name"] is not None:
        name = str(body["name"]).strip()
        if not name:
            return 400, {"error": "name cannot be empty"}
        other = STORE.find_by_name(cat.user_id, name, include_disabled=True)
        if other and other.category_id != cat.category_id and other.status == STATUS_ACTIVE:
            return 409, {"error": f"Danh mục '{name}' đã tồn tại"}
        cat.name = name

    if "kind" in body and body["kind"] is not None:
        kind = str(body["kind"]).strip().lower()
        err = _validate_kind(kind)
        if err:
            return 400, {"error": err}
        cat.kind = kind

    if "tags" in body and body["tags"] is not None:
        cat.tags = normalize_tags(body["tags"])

    if "note" in body:
        note = body["note"]
        cat.note = (str(note).strip() or None) if note is not None else None

    if body.get("reactivate") or body.get("status") == STATUS_ACTIVE:
        cat.status = STATUS_ACTIVE
        cat.disabled_at = None

    cat.updated_at = _now()
    STORE.save(cat)

    # If renamed, migrate tx/split category strings to new display name.
    if cat.name != old_name:
        _reassign_tx_category_strings(cat.user_id, old_name, cat.name)

    return 200, cat.to_dict()


def service_reassign_category(
    category_id: str, body: Optional[dict] = None
) -> tuple[int, dict]:
    """Migrate txs/splits from this category name to target; does not disable."""
    body = body or {}
    cat = STORE.get(category_id)
    if not cat:
        return 404, {"error": "category not found"}
    target_id = (body.get("reassign_to") or body.get("target_category_id") or "").strip()
    if not target_id:
        return 400, {"error": "reassign_to (target category id) is required"}
    if target_id == category_id:
        return 400, {"error": "reassign_to must be a different category"}
    target = STORE.get(target_id)
    if not target:
        return 404, {"error": "target category not found"}
    if target.user_id != cat.user_id:
        return 400, {"error": "target category belongs to a different user"}
    if target.status == STATUS_DISABLED:
        return 400, {"error": "target category is disabled — chọn danh mục đang hoạt động"}

    migrated = _reassign_tx_category_strings(cat.user_id, cat.name, target.name)
    return 200, {
        "category_id": category_id,
        "from_name": cat.name,
        "reassign_to": target_id,
        "to_name": target.name,
        "migrated": migrated,
    }


def service_disable_category(
    category_id: str, body: Optional[dict] = None
) -> tuple[int, dict]:
    """Soft-disable. If history references this name, reassign_to is required."""
    body = body or {}
    cat = STORE.get(category_id)
    if not cat:
        return 404, {"error": "category not found"}
    if cat.status == STATUS_DISABLED:
        out = cat.to_dict()
        out["disabled"] = True
        return 200, out

    ref_count, samples = _category_name_in_use(cat.user_id, cat.name)
    reassign_to = (body.get("reassign_to") or body.get("target_category_id") or "").strip()

    migrated = 0
    if ref_count > 0:
        if not reassign_to:
            return 400, {
                "error": (
                    "Danh mục đang được dùng trong giao dịch — "
                    "cần reassign_to (id danh mục đích) trước khi vô hiệu hoá"
                ),
                "reassign_required": True,
                "referencing_count": ref_count,
                "sample_transaction_ids": samples,
                "category_id": category_id,
                "name": cat.name,
            }
        if reassign_to == category_id:
            return 400, {"error": "reassign_to must be a different category"}
        target = STORE.get(reassign_to)
        if not target:
            return 404, {"error": "target category not found"}
        if target.user_id != cat.user_id:
            return 400, {"error": "target category belongs to a different user"}
        if target.status == STATUS_DISABLED:
            return 400, {
                "error": "target category is disabled — chọn danh mục đang hoạt động"
            }
        migrated = _reassign_tx_category_strings(cat.user_id, cat.name, target.name)
    elif reassign_to:
        # Optional reassign even with no refs
        target = STORE.get(reassign_to)
        if target and target.user_id == cat.user_id and target.status != STATUS_DISABLED:
            migrated = _reassign_tx_category_strings(cat.user_id, cat.name, target.name)

    now = _now()
    cat.status = STATUS_DISABLED
    cat.disabled_at = now
    cat.updated_at = now
    STORE.save(cat)
    out = cat.to_dict()
    out["disabled"] = True
    out["migrated"] = migrated
    if reassign_to:
        out["reassign_to"] = reassign_to
    return 200, out


def service_seed_defaults(user_id: str) -> tuple[int, dict]:
    """Idempotent seed from DEFAULT_CATEGORIES (skip names already present)."""
    user_id = (user_id or "").strip()
    if not user_id:
        return 400, {"error": "user_id is required"}
    created: list[dict] = []
    skipped: list[str] = []
    existing = {
        c.name.strip().lower(): c
        for c in STORE.list_for_user(user_id, include_disabled=True)
    }
    for tmpl in DEFAULT_CATEGORIES:
        name = (tmpl.get("name") or "").strip()
        if not name:
            continue
        key = name.lower()
        if key in existing:
            # If disabled, reactivate + refresh tags/kind
            prev = existing[key]
            if prev.status == STATUS_DISABLED:
                code, out = service_create_category({
                    "user_id": user_id,
                    "name": name,
                    "kind": tmpl.get("kind") or KIND_VARIABLE,
                    "tags": list(tmpl.get("tags") or []),
                    "note": tmpl.get("note"),
                })
                if code == 201:
                    created.append(out)
                    existing[key] = STORE.get(out["category_id"])  # type: ignore
                else:
                    skipped.append(name)
            else:
                skipped.append(name)
            continue
        code, out = service_create_category({
            "user_id": user_id,
            "name": name,
            "kind": tmpl.get("kind") or KIND_VARIABLE,
            "tags": list(tmpl.get("tags") or []),
            "note": tmpl.get("note"),
        })
        if code == 201:
            created.append(out)
            existing[key] = STORE.get(out["category_id"])  # type: ignore
        else:
            return code, out
    return 200, {
        "user_id": user_id,
        "created": created,
        "skipped": skipped,
        "count": len(created),
        "defaults_total": len(DEFAULT_CATEGORIES),
        "persona_budget_tags": persona_budget_tags_union(),
    }
