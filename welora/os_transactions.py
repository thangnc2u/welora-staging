"""WeloraOS P0 — Manual transactions + split (supplement CSV parser).

Ticket 2/4 WeloraOS parity (staging). Manual OS records only — CSV parser
stays parse-only and untouched. No Open Banking / aggregator. Categories
remain free-string (ticket 3 later). Budget parity is ticket 4.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional
from uuid import uuid4

SOURCE_MANUAL = "manual"
STATUS_ACTIVE = "active"
STATUS_HIDDEN = "hidden"
SPLIT_TOLERANCE = 0.01

CONSENT_REQUIRED_VI = (
    "Cần xác nhận đồng ý trước khi thêm giao dịch thủ công "
    "(không kết nối ngân hàng)."
)
CONSENT_TEXT_VI = (
    "Tôi đồng ý lưu giao dịch này trên Welora (nhập thủ công). "
    "Không kết nối Open Banking hay thu thập dữ liệu ngân hàng."
)

# Docs-only label hints (reuse parser heuristics; no Categories CRUD).
CATEGORY_HINTS_VI = (
    "Nhà ở",
    "Điện nước",
    "Lương",
    "Siêu thị",
    "Học phí",
    "Khác",
    "Ăn uống",
    "Di chuyển",
    "Mua sắm",
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_bool(raw: Any) -> bool:
    if raw is True or raw is False:
        return bool(raw)
    if isinstance(raw, str):
        return raw.strip().lower() in ("1", "true", "yes", "y", "on")
    return False


def _parse_iso_date(raw: Any) -> Optional[str]:
    """Accept YYYY-MM-DD (or datetime prefix). Return normalized ISO date string."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if "T" in s:
        s = s.split("T", 1)[0]
    try:
        d = date.fromisoformat(s)
    except ValueError:
        return None
    return d.isoformat()


@dataclass
class SplitLine:
    split_id: str
    amount: float
    category: str
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Transaction:
    transaction_id: str
    user_id: str
    account_id: str
    amount: float
    category: str
    date: str
    note: Optional[str] = None
    merchant: Optional[str] = None
    source: str = SOURCE_MANUAL
    consent_ack: bool = False
    consent_at: Optional[str] = None
    is_split: bool = False
    splits: list[SplitLine] = field(default_factory=list)
    status: str = STATUS_ACTIVE
    hidden_at: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["splits"] = [s if isinstance(s, dict) else s for s in d.get("splits") or []]
        # asdict already converts SplitLine; ensure list of dicts
        out_splits = []
        for s in self.splits:
            out_splits.append(s.to_dict() if hasattr(s, "to_dict") else dict(s))
        d["splits"] = out_splits
        d["is_split"] = bool(self.is_split or len(out_splits) > 0)
        return d


class InMemoryTransactionStore:
    def __init__(self) -> None:
        self._by_id: dict[str, Transaction] = {}

    def clear(self) -> None:
        self._by_id.clear()

    def save(self, tx: Transaction) -> Transaction:
        self._by_id[tx.transaction_id] = tx
        return tx

    def get(self, transaction_id: str) -> Optional[Transaction]:
        return self._by_id.get(transaction_id)

    def list_for_user(
        self,
        user_id: str,
        *,
        account_id: Optional[str] = None,
        include_hidden: bool = False,
    ) -> list[Transaction]:
        rows = [t for t in self._by_id.values() if t.user_id == user_id]
        if account_id:
            rows = [t for t in rows if t.account_id == account_id]
        if not include_hidden:
            rows = [t for t in rows if t.status != STATUS_HIDDEN]
        rows.sort(key=lambda t: (t.date, t.created_at), reverse=True)
        return rows

    def delete_hard(self, transaction_id: str) -> None:
        self._by_id.pop(transaction_id, None)


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
            from welora.db.repos import SqliteTransactionStore
            return SqliteTransactionStore(os.environ.get("WELORA_DB_URL") or None)
        except Exception:
            return InMemoryTransactionStore()
    return InMemoryTransactionStore()


STORE = _make_store()


def use_store(store) -> None:
    global STORE
    STORE = store


def reset_transaction_store() -> None:
    if hasattr(STORE, "clear"):
        STORE.clear()
    elif hasattr(STORE, "_by_id"):
        STORE._by_id.clear()


def _normalize_splits(raw: Any) -> tuple[Optional[list[SplitLine]], Optional[str]]:
    if raw is None:
        return [], None
    if not isinstance(raw, list):
        return None, "splits must be an array"
    lines: list[SplitLine] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            return None, f"splits[{i}] must be an object"
        try:
            amt = float(item.get("amount"))
        except (TypeError, ValueError):
            return None, f"splits[{i}].amount must be a number"
        cat = (item.get("category") or "").strip()
        if not cat:
            return None, f"splits[{i}].category is required"
        note = item.get("note")
        note_s = str(note).strip() if note is not None and str(note).strip() else None
        sid = (item.get("split_id") or "").strip() or str(uuid4())
        lines.append(SplitLine(split_id=sid, amount=amt, category=cat, note=note_s))
    return lines, None


def _validate_split_sum(amount: float, splits: list[SplitLine]) -> Optional[str]:
    if not splits:
        return None
    total = sum(s.amount for s in splits)
    if abs(total - amount) > SPLIT_TOLERANCE:
        return (
            f"Tổng split ({total}) phải bằng amount ({amount}) "
            f"(dung sai ±{SPLIT_TOLERANCE})"
        )
    return None


def _resolve_account(user_id: str, account_id: str) -> tuple[Optional[Any], Optional[tuple[int, dict]]]:
    """Return (account, None) or (None, error_response)."""
    from welora import os_accounts as accounts_svc

    acc = accounts_svc.STORE.get(account_id)
    if not acc:
        return None, (400, {"error": "account_id không tồn tại — tạo qua /os/accounts trước"})
    if acc.user_id != user_id:
        return None, (400, {"error": "account_id không thuộc user_id"})
    if getattr(acc, "status", None) == accounts_svc.STATUS_HIDDEN:
        return None, (400, {"error": "account is hidden — không thể gắn giao dịch"})
    return acc, None


def service_create_transaction(body: dict) -> tuple[int, dict]:
    user_id = (body.get("user_id") or "").strip()
    if not user_id:
        return 400, {"error": "user_id is required"}
    account_id = (body.get("account_id") or "").strip()
    if not account_id:
        return 400, {"error": "account_id is required"}

    _acc, err = _resolve_account(user_id, account_id)
    if err:
        return err

    try:
        amount = float(body.get("amount"))
    except (TypeError, ValueError):
        return 400, {"error": "amount must be a number"}
    if body.get("amount") is None:
        return 400, {"error": "amount is required"}

    category = (body.get("category") or "").strip()
    if not category:
        return 400, {"error": "category is required"}

    iso_date = _parse_iso_date(body.get("date"))
    if not iso_date:
        return 400, {"error": "date is required (ISO YYYY-MM-DD)"}

    consent_ok = _parse_bool(body.get("consent_ack"))
    # Soft gate: if client sends consent_ack explicitly false, reject;
    # if omitted, allow (manual txs are first-class; accounts already gated).
    if "consent_ack" in body and body.get("consent_ack") is not None and not consent_ok:
        return 400, {
            "error": CONSENT_REQUIRED_VI,
            "consent_required": True,
            "consent_text": CONSENT_TEXT_VI,
            "source": SOURCE_MANUAL,
        }

    splits, split_err = _normalize_splits(body.get("splits"))
    if split_err:
        return 400, {"error": split_err}
    assert splits is not None
    sum_err = _validate_split_sum(amount, splits)
    if sum_err:
        return 400, {"error": sum_err}

    note = body.get("note")
    note_s = str(note).strip() if note is not None and str(note).strip() else None
    merchant = body.get("merchant")
    merchant_s = (
        str(merchant).strip() if merchant is not None and str(merchant).strip() else None
    )

    now = _now()
    tx = Transaction(
        transaction_id=str(uuid4()),
        user_id=user_id,
        account_id=account_id,
        amount=amount,
        category=category,
        date=iso_date,
        note=note_s,
        merchant=merchant_s,
        source=SOURCE_MANUAL,
        consent_ack=True if consent_ok or "consent_ack" not in body else consent_ok,
        consent_at=now if (consent_ok or "consent_ack" not in body) else None,
        is_split=len(splits) > 0,
        splits=splits,
        status=STATUS_ACTIVE,
        created_at=now,
        updated_at=now,
    )
    # If consent omitted, still mark ack for manual OS create (account already consented)
    if "consent_ack" not in body or body.get("consent_ack") is None:
        tx.consent_ack = True
        tx.consent_at = now

    STORE.save(tx)
    return 201, tx.to_dict()


def service_list_transactions(
    user_id: str,
    *,
    account_id: Optional[str] = None,
    include_hidden: bool = False,
) -> tuple[int, dict]:
    if not (user_id or "").strip():
        return 400, {"error": "user_id is required"}
    items = [
        t.to_dict()
        for t in STORE.list_for_user(
            user_id,
            account_id=(account_id or None) or None,
            include_hidden=include_hidden,
        )
    ]
    return 200, {
        "transactions": items,
        "items": items,
        "user_id": user_id,
        "account_id": account_id or None,
        "count": len(items),
        "source_policy": "manual_only",
        "category_hints": list(CATEGORY_HINTS_VI),
        "csv_parser_separate": True,
    }


def service_get_transaction(transaction_id: str) -> tuple[int, dict]:
    tx = STORE.get(transaction_id)
    if not tx:
        return 404, {"error": "transaction not found"}
    return 200, tx.to_dict()


def service_update_transaction(transaction_id: str, body: dict) -> tuple[int, dict]:
    tx = STORE.get(transaction_id)
    if not tx:
        return 404, {"error": "transaction not found"}

    if "account_id" in body and body["account_id"] is not None:
        new_aid = str(body["account_id"]).strip()
        if not new_aid:
            return 400, {"error": "account_id cannot be empty"}
        _acc, err = _resolve_account(tx.user_id, new_aid)
        if err:
            return err
        tx.account_id = new_aid

    if "amount" in body and body["amount"] is not None:
        try:
            tx.amount = float(body["amount"])
        except (TypeError, ValueError):
            return 400, {"error": "amount must be a number"}

    if "category" in body and body["category"] is not None:
        cat = str(body["category"]).strip()
        if not cat:
            return 400, {"error": "category cannot be empty"}
        tx.category = cat

    if "date" in body and body["date"] is not None:
        iso_date = _parse_iso_date(body["date"])
        if not iso_date:
            return 400, {"error": "date must be ISO YYYY-MM-DD"}
        tx.date = iso_date

    if "note" in body:
        note = body["note"]
        tx.note = str(note).strip() if note is not None and str(note).strip() else None

    if "merchant" in body:
        merchant = body["merchant"]
        tx.merchant = (
            str(merchant).strip() if merchant is not None and str(merchant).strip() else None
        )

    if "splits" in body:
        splits, split_err = _normalize_splits(body.get("splits"))
        if split_err:
            return 400, {"error": split_err}
        assert splits is not None
        # Empty list clears splits
        if splits:
            sum_err = _validate_split_sum(tx.amount, splits)
            if sum_err:
                return 400, {"error": sum_err}
            tx.splits = splits
            tx.is_split = True
        else:
            tx.splits = []
            tx.is_split = False
    elif tx.splits:
        # Re-validate if amount changed without replacing splits
        sum_err = _validate_split_sum(tx.amount, tx.splits)
        if sum_err:
            return 400, {"error": sum_err}

    if body.get("unhide") or body.get("status") == STATUS_ACTIVE:
        tx.status = STATUS_ACTIVE
        tx.hidden_at = None

    tx.updated_at = _now()
    STORE.save(tx)
    return 200, tx.to_dict()


def service_split_transaction(transaction_id: str, body: dict) -> tuple[int, dict]:
    """Replace split lines on an existing transaction (POST …/split)."""
    tx = STORE.get(transaction_id)
    if not tx:
        return 404, {"error": "transaction not found"}
    if tx.status == STATUS_HIDDEN:
        return 409, {"error": "transaction is hidden — unhide before splitting"}

    raw = body.get("splits", body.get("lines"))
    if raw is None:
        return 400, {"error": "splits is required"}
    splits, split_err = _normalize_splits(raw)
    if split_err:
        return 400, {"error": split_err}
    assert splits is not None
    if not splits:
        return 400, {"error": "splits must contain at least one line"}
    # Optional parent amount override when re-splitting
    if body.get("amount") is not None:
        try:
            tx.amount = float(body["amount"])
        except (TypeError, ValueError):
            return 400, {"error": "amount must be a number"}
    sum_err = _validate_split_sum(tx.amount, splits)
    if sum_err:
        return 400, {"error": sum_err}

    if body.get("merchant") is not None:
        m = str(body["merchant"]).strip()
        tx.merchant = m or None
    if body.get("category") is not None:
        c = str(body["category"]).strip()
        if c:
            tx.category = c

    tx.splits = splits
    tx.is_split = True
    tx.updated_at = _now()
    STORE.save(tx)
    return 200, tx.to_dict()


def service_hide_transaction(transaction_id: str, body: Optional[dict] = None) -> tuple[int, dict]:
    """Soft-delete / hide — does not hard-delete rows."""
    tx = STORE.get(transaction_id)
    if not tx:
        return 404, {"error": "transaction not found"}
    if tx.status == STATUS_HIDDEN:
        return 200, tx.to_dict()
    now = _now()
    tx.status = STATUS_HIDDEN
    tx.hidden_at = now
    tx.updated_at = now
    STORE.save(tx)
    out = tx.to_dict()
    out["hidden"] = True
    return 200, out
