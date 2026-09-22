"""WeloraOS P0 — Accounts CRUD + manual balance + minimal consent.

Ticket 1/4 WeloraOS parity (staging). Manual source only — no Open Banking,
no bank aggregator. Soft-delete = hide (status=hidden). CSV import must not
replace this CRUD (parser stays separate).
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

ACCOUNT_TYPES = frozenset({
    "chi_tieu_hang_ngay",
    "tiet_kiem",
    "no",
    "dau_tu",
    "tai_san_dai_han",
})

SOURCE_MANUAL = "manual"
STATUS_ACTIVE = "active"
STATUS_HIDDEN = "hidden"

CONSENT_REQUIRED_VI = (
    "Cần xác nhận đồng ý trước khi thêm nguồn dữ liệu thủ công "
    "(không kết nối ngân hàng)."
)
CONSENT_TEXT_VI = (
    "Tôi đồng ý lưu số dư / tên tài khoản này trên Welora (nhập thủ công). "
    "Không kết nối Open Banking hay thu thập dữ liệu ngân hàng."
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class Account:
    account_id: str
    user_id: str
    name: str
    type: str
    balance: float = 0.0
    source: str = SOURCE_MANUAL
    consent_ack: bool = False
    consent_at: Optional[str] = None
    status: str = STATUS_ACTIVE
    hidden_at: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class InMemoryAccountStore:
    def __init__(self) -> None:
        self._by_id: dict[str, Account] = {}

    def clear(self) -> None:
        self._by_id.clear()

    def save(self, account: Account) -> Account:
        self._by_id[account.account_id] = account
        return account

    def get(self, account_id: str) -> Optional[Account]:
        return self._by_id.get(account_id)

    def list_for_user(
        self, user_id: str, *, include_hidden: bool = False
    ) -> list[Account]:
        rows = [a for a in self._by_id.values() if a.user_id == user_id]
        if not include_hidden:
            rows = [a for a in rows if a.status != STATUS_HIDDEN]
        rows.sort(key=lambda a: a.created_at)
        return rows

    def delete_hard(self, account_id: str) -> None:
        self._by_id.pop(account_id, None)


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
            from welora.db.repos import SqliteAccountStore
            return SqliteAccountStore(os.environ.get("WELORA_DB_URL") or None)
        except Exception:
            return InMemoryAccountStore()
    return InMemoryAccountStore()


STORE = _make_store()


def use_store(store) -> None:
    global STORE
    STORE = store


def reset_account_store() -> None:
    if hasattr(STORE, "clear"):
        STORE.clear()
    elif hasattr(STORE, "_by_id"):
        STORE._by_id.clear()


def _validate_type(atype: str) -> Optional[str]:
    if atype not in ACCOUNT_TYPES:
        return f"type không hợp lệ — chọn: {', '.join(sorted(ACCOUNT_TYPES))}"
    return None


def service_create_account(body: dict) -> tuple[int, dict]:
    user_id = (body.get("user_id") or "").strip()
    if not user_id:
        return 400, {"error": "user_id is required"}
    name = (body.get("name") or "").strip()
    if not name:
        return 400, {"error": "name is required"}
    atype = (body.get("type") or "chi_tieu_hang_ngay").strip()
    err = _validate_type(atype)
    if err:
        return 400, {"error": err}

    source = (body.get("source") or SOURCE_MANUAL).strip().lower()
    if source != SOURCE_MANUAL:
        return 400, {
            "error": (
                "Chỉ hỗ trợ nguồn thủ công (manual) — "
                "không Open Banking / aggregator trong MVP."
            ),
            "consent_text": CONSENT_TEXT_VI,
        }

    consent = body.get("consent_ack")
    if consent is True or consent is False:
        consent_ok = bool(consent)
    elif isinstance(consent, str):
        consent_ok = consent.strip().lower() in ("1", "true", "yes", "y", "on")
    else:
        consent_ok = False
    if not consent_ok:
        return 400, {
            "error": CONSENT_REQUIRED_VI,
            "consent_required": True,
            "consent_text": CONSENT_TEXT_VI,
            "source": SOURCE_MANUAL,
        }

    try:
        balance = float(body.get("balance", body.get("opening_balance", 0)) or 0)
    except (TypeError, ValueError):
        return 400, {"error": "balance / opening_balance must be a number"}

    now = _now()
    account = Account(
        account_id=str(uuid4()),
        user_id=user_id,
        name=name,
        type=atype,
        balance=balance,
        source=SOURCE_MANUAL,
        consent_ack=True,
        consent_at=now,
        status=STATUS_ACTIVE,
        created_at=now,
        updated_at=now,
    )
    STORE.save(account)
    return 201, account.to_dict()


def service_list_accounts(
    user_id: str, *, include_hidden: bool = False
) -> tuple[int, dict]:
    if not (user_id or "").strip():
        return 400, {"error": "user_id is required"}
    items = [a.to_dict() for a in STORE.list_for_user(user_id, include_hidden=include_hidden)]
    return 200, {
        "accounts": items,
        "items": items,
        "user_id": user_id,
        "count": len(items),
        "source_policy": "manual_only",
        "consent_text": CONSENT_TEXT_VI,
    }


def service_get_account(account_id: str) -> tuple[int, dict]:
    acc = STORE.get(account_id)
    if not acc:
        return 404, {"error": "account not found"}
    return 200, acc.to_dict()


def service_update_account(account_id: str, body: dict) -> tuple[int, dict]:
    acc = STORE.get(account_id)
    if not acc:
        return 404, {"error": "account not found"}
    if acc.status == STATUS_HIDDEN and not body.get("unhide"):
        # Allow update of hidden only if explicitly unhiding or patching while include
        pass

    if "name" in body and body["name"] is not None:
        name = str(body["name"]).strip()
        if not name:
            return 400, {"error": "name cannot be empty"}
        acc.name = name

    if "type" in body and body["type"] is not None:
        atype = str(body["type"]).strip()
        err = _validate_type(atype)
        if err:
            return 400, {"error": err}
        acc.type = atype

    if "balance" in body and body["balance"] is not None:
        try:
            acc.balance = float(body["balance"])
        except (TypeError, ValueError):
            return 400, {"error": "balance must be a number"}

    if "opening_balance" in body and body["opening_balance"] is not None and "balance" not in body:
        try:
            acc.balance = float(body["opening_balance"])
        except (TypeError, ValueError):
            return 400, {"error": "opening_balance must be a number"}

    if body.get("unhide") or body.get("status") == STATUS_ACTIVE:
        acc.status = STATUS_ACTIVE
        acc.hidden_at = None

    acc.updated_at = _now()
    STORE.save(acc)
    return 200, acc.to_dict()


def service_set_balance(account_id: str, body: dict) -> tuple[int, dict]:
    acc = STORE.get(account_id)
    if not acc:
        return 404, {"error": "account not found"}
    if acc.status == STATUS_HIDDEN:
        return 409, {"error": "account is hidden — unhide before editing balance"}
    raw = body.get("balance", body.get("set_amount"))
    if raw is None:
        return 400, {"error": "balance is required"}
    try:
        acc.balance = float(raw)
    except (TypeError, ValueError):
        return 400, {"error": "balance must be a number"}
    acc.updated_at = _now()
    STORE.save(acc)
    return 200, acc.to_dict()


def service_hide_account(account_id: str, body: Optional[dict] = None) -> tuple[int, dict]:
    """Soft-delete / hide — does not hard-delete rows."""
    acc = STORE.get(account_id)
    if not acc:
        return 404, {"error": "account not found"}
    if acc.status == STATUS_HIDDEN:
        return 200, acc.to_dict()
    now = _now()
    acc.status = STATUS_HIDDEN
    acc.hidden_at = now
    acc.updated_at = now
    STORE.save(acc)
    out = acc.to_dict()
    out["hidden"] = True
    return 200, out


def service_seed_from_persona(user_id: str, persona_id: str) -> tuple[int, dict]:
    """Seed os_accounts from P1–P6 persona templates (opening_balance None → 0).

    Idempotent per (user_id, name): skips names already present (active or hidden).
    Requires consent_ack path — seeds mark consent as demo ack.
    """
    from welora.personas import get_persona

    try:
        persona = get_persona(persona_id)
    except Exception as exc:
        return 400, {"error": f"persona not found: {exc}"}
    templates = list(persona.get("os_accounts") or [])
    created: list[dict] = []
    skipped: list[str] = []
    existing = {
        a.name: a
        for a in STORE.list_for_user(user_id, include_hidden=True)
    }
    for tmpl in templates:
        name = (tmpl.get("name") or "").strip()
        if not name:
            continue
        if name in existing:
            skipped.append(name)
            continue
        bal = tmpl.get("opening_balance")
        code, out = service_create_account({
            "user_id": user_id,
            "name": name,
            "type": tmpl.get("type") or "chi_tieu_hang_ngay",
            "opening_balance": 0.0 if bal is None else float(bal),
            "consent_ack": True,
            "source": SOURCE_MANUAL,
        })
        if code == 201:
            created.append(out)
            existing[name] = out
        else:
            return code, out
    return 200, {
        "user_id": user_id,
        "persona_id": persona_id,
        "created": created,
        "skipped": skipped,
        "count": len(created),
    }
