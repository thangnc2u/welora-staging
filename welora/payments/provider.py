"""PaymentProvider abstraction (Phụ lục Checkout VietQR mục 5).

create / get / cancel / verify_webhook (+ confirm_webhook for payOS).

Provider selection (env, never hard-coded keys):
  PAYMENT_PROVIDER = payos | mock | sepay
  default: payos when PAYOS_CLIENT_ID + PAYOS_API_KEY + PAYOS_CHECKSUM_KEY
           are all set, otherwise mock.

payOS has NO separate sandbox host: a non-prod "test channel" is simply a
different set of PAYOS_* keys against the same base URL.

Keys are read from env only and are never logged (see ``redact``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

log = logging.getLogger("welora.payments")

PAYOS_BASE_URL = "https://api-merchant.payos.vn"
PAYOS_ENV_KEYS = ("PAYOS_CLIENT_ID", "PAYOS_API_KEY", "PAYOS_CHECKSUM_KEY")
HTTP_TIMEOUT_S = 10.0


class ProviderError(Exception):
    """Provider call failed (network / non-00 code / bad response signature)."""

    def __init__(self, message: str, *, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class PaymentLink:
    order_code: int
    amount: int
    description: str
    provider_link_id: str
    checkout_url: str
    qr_code: str
    status: str = "PENDING"
    account_number: str = ""
    account_name: str = ""
    bin: str = ""
    expired_at: Optional[int] = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaymentTransaction:
    reference: str
    amount: int
    transaction_datetime: str = ""
    description: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class PaymentStatus:
    order_code: int
    status: str  # PENDING | PAID | UNDERPAID | CANCELLED | EXPIRED | PROCESSING
    amount: int
    amount_paid: int
    amount_remaining: int
    transactions: list[PaymentTransaction] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Signature (mục 5) — HMAC_SHA256 with Checksum Key
# ---------------------------------------------------------------------------


def _value_to_str(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    if isinstance(value, list):
        items = [
            {k: v[k] for k in sorted(v)} if isinstance(v, dict) else v for v in value
        ]
        return json.dumps(items, separators=(",", ":"), ensure_ascii=False)
    if value in ("undefined", "null"):
        return ""
    return str(value)


def signature_payment_request(
    *,
    amount: int,
    cancel_url: str,
    description: str,
    order_code: int,
    return_url: str,
    checksum_key: str,
) -> str:
    """Create-link signature over the alphabetical string (mục 5):
    amount=…&cancelUrl=…&description=…&orderCode=…&returnUrl=…"""
    data = (
        f"amount={amount}&cancelUrl={cancel_url}&description={description}"
        f"&orderCode={order_code}&returnUrl={return_url}"
    )
    return hmac.new(checksum_key.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()


def signature_from_data(data: dict[str, Any], checksum_key: str) -> str:
    """Webhook / response signature: keys sorted alphabetically, key=value&…"""
    parts = [f"{k}={_value_to_str(data[k])}" for k in sorted(data.keys())]
    msg = "&".join(parts)
    return hmac.new(checksum_key.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_data_signature(data: Any, signature: Any, checksum_key: str) -> bool:
    if not isinstance(data, dict) or not isinstance(signature, str) or not signature:
        return False
    if not checksum_key:
        return False
    expected = signature_from_data(data, checksum_key)
    return hmac.compare_digest(expected, signature.strip().lower())


def redact(value: Optional[str]) -> str:
    """Never print keys — keep last 2 chars only for debugging."""
    v = value or ""
    if len(v) <= 4:
        return "***"
    return "***" + v[-2:]


# ---------------------------------------------------------------------------
# Abstract provider
# ---------------------------------------------------------------------------


class PaymentProvider(ABC):
    """Checkout flow depends only on this interface (payOS / SePay / MoMo / VNPAY)."""

    name: str = "abstract"

    @abstractmethod
    def create_payment(
        self,
        *,
        order_code: int,
        amount: int,
        description: str,
        return_url: str,
        cancel_url: str,
        expired_at: int,
    ) -> PaymentLink: ...

    @abstractmethod
    def get_payment(self, order_code: int) -> PaymentStatus: ...

    @abstractmethod
    def cancel_payment(self, order_code: int, reason: str = "") -> dict[str, Any]: ...

    @abstractmethod
    def verify_webhook(self, payload: dict[str, Any]) -> bool:
        """True only if payload['signature'] matches payload['data']."""

    def confirm_webhook(self, webhook_url: str) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError(f"{self.name}: confirm_webhook not supported")


# ---------------------------------------------------------------------------
# payOS
# ---------------------------------------------------------------------------


class PayOSProvider(PaymentProvider):
    name = "payos"

    def __init__(
        self,
        *,
        client_id: Optional[str] = None,
        api_key: Optional[str] = None,
        checksum_key: Optional[str] = None,
        http_client: Any = None,
    ) -> None:
        self._client_id = client_id if client_id is not None else os.environ.get("PAYOS_CLIENT_ID", "")
        self._api_key = api_key if api_key is not None else os.environ.get("PAYOS_API_KEY", "")
        self._checksum_key = (
            checksum_key if checksum_key is not None else os.environ.get("PAYOS_CHECKSUM_KEY", "")
        )
        if not (self._client_id and self._api_key and self._checksum_key):
            raise ProviderError("payOS keys missing (PAYOS_CLIENT_ID / PAYOS_API_KEY / PAYOS_CHECKSUM_KEY)")
        self._http = http_client

    def __repr__(self) -> str:  # never leak keys via repr/logging
        return f"PayOSProvider(client_id={redact(self._client_id)})"

    def _headers(self) -> dict[str, str]:
        return {
            "x-client-id": self._client_id,
            "x-api-key": self._api_key,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, body: Optional[dict] = None) -> dict[str, Any]:
        import httpx

        url = f"{PAYOS_BASE_URL}{path}"
        client = self._http or httpx.Client(timeout=HTTP_TIMEOUT_S)
        try:
            resp = client.request(method, url, headers=self._headers(), json=body)
        except httpx.HTTPError as e:
            raise ProviderError(f"payOS {method} {path} network error: {type(e).__name__}") from None
        finally:
            if self._http is None:
                client.close()
        try:
            out = resp.json()
        except ValueError:
            raise ProviderError(f"payOS {method} {path} HTTP {resp.status_code} non-JSON") from None
        code = str(out.get("code", ""))
        if resp.status_code != 200 or code != "00":
            raise ProviderError(
                f"payOS {method} {path} HTTP {resp.status_code} code={code} desc={out.get('desc')}",
                code=code,
            )
        return out

    def _verified_data(self, out: dict[str, Any], path: str) -> dict[str, Any]:
        data = out.get("data") or {}
        sig = out.get("signature")
        if sig is not None and not verify_data_signature(data, sig, self._checksum_key):
            raise ProviderError(f"payOS {path} response signature mismatch", code="DATA_NOT_INTEGRITY")
        return data

    def create_payment(
        self,
        *,
        order_code: int,
        amount: int,
        description: str,
        return_url: str,
        cancel_url: str,
        expired_at: int,
    ) -> PaymentLink:
        sig = signature_payment_request(
            amount=amount,
            cancel_url=cancel_url,
            description=description,
            order_code=order_code,
            return_url=return_url,
            checksum_key=self._checksum_key,
        )
        body = {
            "orderCode": int(order_code),
            "amount": int(amount),
            "description": description,
            "returnUrl": return_url,
            "cancelUrl": cancel_url,
            "expiredAt": int(expired_at),
            "signature": sig,
        }
        out = self._request("POST", "/v2/payment-requests", body)
        data = self._verified_data(out, "/v2/payment-requests")
        return PaymentLink(
            order_code=int(data.get("orderCode") or order_code),
            amount=int(data.get("amount") or amount),
            description=str(data.get("description") or description),
            provider_link_id=str(data.get("paymentLinkId") or ""),
            checkout_url=str(data.get("checkoutUrl") or ""),
            qr_code=str(data.get("qrCode") or ""),
            status=str(data.get("status") or "PENDING"),
            account_number=str(data.get("accountNumber") or ""),
            account_name=str(data.get("accountName") or ""),
            bin=str(data.get("bin") or ""),
            expired_at=data.get("expiredAt") or expired_at,
            raw=data,
        )

    def get_payment(self, order_code: int) -> PaymentStatus:
        path = f"/v2/payment-requests/{int(order_code)}"
        out = self._request("GET", path)
        data = self._verified_data(out, path)
        return _status_from_payos(data, order_code)

    def cancel_payment(self, order_code: int, reason: str = "") -> dict[str, Any]:
        path = f"/v2/payment-requests/{int(order_code)}/cancel"
        body = {"cancellationReason": reason} if reason else None
        out = self._request("POST", path, body)
        return self._verified_data(out, path)

    def verify_webhook(self, payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        return verify_data_signature(payload.get("data"), payload.get("signature"), self._checksum_key)

    def confirm_webhook(self, webhook_url: str) -> dict[str, Any]:
        out = self._request("POST", "/confirm-webhook", {"webhookUrl": webhook_url})
        return {"ok": True, "desc": out.get("desc"), "webhook_url": webhook_url}


def _status_from_payos(data: dict[str, Any], order_code: int) -> PaymentStatus:
    txns = []
    for t in data.get("transactions") or []:
        if not isinstance(t, dict):
            continue
        ref = str(t.get("reference") or "")
        if not ref:
            continue
        txns.append(
            PaymentTransaction(
                reference=ref,
                amount=int(t.get("amount") or 0),
                transaction_datetime=str(t.get("transactionDateTime") or ""),
                description=str(t.get("description") or ""),
                raw=t,
            )
        )
    amount = int(data.get("amount") or 0)
    paid = int(data.get("amountPaid") or 0)
    return PaymentStatus(
        order_code=int(data.get("orderCode") or order_code),
        status=str(data.get("status") or "PENDING").upper(),
        amount=amount,
        amount_paid=paid,
        amount_remaining=int(data.get("amountRemaining") or max(0, amount - paid)),
        transactions=txns,
        raw=data,
    )


# ---------------------------------------------------------------------------
# Mock (tests / CI / non-prod without keys) — in-process, no network
# ---------------------------------------------------------------------------


class MockPaymentProvider(PaymentProvider):
    """In-process fake payOS. Signs with its own checksum key.

    Key: MOCK_PAYMENT_CHECKSUM_KEY env, else a random per-process key so
    nobody outside the process can forge a valid webhook.
    """

    name = "mock"

    def __init__(self, checksum_key: Optional[str] = None) -> None:
        self.checksum_key = (
            checksum_key
            or (os.environ.get("MOCK_PAYMENT_CHECKSUM_KEY") or "").strip()
            or secrets.token_hex(32)
        )
        self._lock = threading.RLock()
        self.links: dict[int, dict[str, Any]] = {}
        self.calls: list[tuple[str, int]] = []

    def create_payment(
        self,
        *,
        order_code: int,
        amount: int,
        description: str,
        return_url: str,
        cancel_url: str,
        expired_at: int,
    ) -> PaymentLink:
        link_id = f"mock{secrets.token_hex(12)}"
        with self._lock:
            self.calls.append(("create", int(order_code)))
            self.links[int(order_code)] = {
                "orderCode": int(order_code),
                "amount": int(amount),
                "description": description,
                "paymentLinkId": link_id,
                "status": "PENDING",
                "transactions": [],
                "expiredAt": int(expired_at),
                "signature_sent": signature_payment_request(
                    amount=amount,
                    cancel_url=cancel_url,
                    description=description,
                    order_code=order_code,
                    return_url=return_url,
                    checksum_key=self.checksum_key,
                ),
            }
        return PaymentLink(
            order_code=int(order_code),
            amount=int(amount),
            description=description,
            provider_link_id=link_id,
            checkout_url=f"/app/checkout/return?orderCode={int(order_code)}&mock=1",
            qr_code=f"MOCKVIETQR|970422|0000000000|{int(amount)}|{description}",
            status="PENDING",
            account_number="0000000000",
            account_name="WELORA MOCK",
            bin="970422",
            expired_at=int(expired_at),
            raw={"paymentLinkId": link_id, "mock": True},
        )

    def get_payment(self, order_code: int) -> PaymentStatus:
        with self._lock:
            self.calls.append(("get", int(order_code)))
            link = self.links.get(int(order_code))
            if not link:
                raise ProviderError(f"mock: order {order_code} not found", code="101")
            data = json.loads(json.dumps({k: v for k, v in link.items() if k != "signature_sent"}))
        paid = sum(int(t["amount"]) for t in data["transactions"])
        data["amountPaid"] = paid
        data["amountRemaining"] = max(0, data["amount"] - paid)
        return _status_from_payos(data, order_code)

    def cancel_payment(self, order_code: int, reason: str = "") -> dict[str, Any]:
        with self._lock:
            self.calls.append(("cancel", int(order_code)))
            link = self.links.get(int(order_code))
            if link and link["status"] in ("PENDING", "UNDERPAID"):
                link["status"] = "CANCELLED"
            return {"orderCode": int(order_code), "status": (link or {}).get("status", "CANCELLED")}

    def verify_webhook(self, payload: dict[str, Any]) -> bool:
        if not isinstance(payload, dict):
            return False
        return verify_data_signature(payload.get("data"), payload.get("signature"), self.checksum_key)

    def confirm_webhook(self, webhook_url: str) -> dict[str, Any]:
        return {"ok": True, "mock": True, "webhook_url": webhook_url}

    # --- test helpers -----------------------------------------------------
    def simulate_transfer(
        self, order_code: int, amount: int, *, reference: Optional[str] = None
    ) -> dict[str, Any]:
        """Record a bank transfer on the fake link; returns signed webhook payload."""
        ref = reference or f"MOCKTF{secrets.token_hex(6).upper()}"
        with self._lock:
            link = self.links.get(int(order_code))
            if not link:
                raise ProviderError(f"mock: order {order_code} not found")
            if not any(t["reference"] == ref for t in link["transactions"]):
                link["transactions"].append(
                    {
                        "reference": ref,
                        "amount": int(amount),
                        "description": link["description"],
                        "transactionDateTime": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
            paid = sum(int(t["amount"]) for t in link["transactions"])
            link["status"] = "PAID" if paid >= link["amount"] else "UNDERPAID"
            desc = link["description"]
            link_id = link["paymentLinkId"]
        return self.signed_webhook(
            {
                "orderCode": int(order_code),
                "amount": int(amount),
                "description": desc,
                "accountNumber": "0000000000",
                "reference": ref,
                "transactionDateTime": time.strftime("%Y-%m-%d %H:%M:%S"),
                "currency": "VND",
                "paymentLinkId": link_id,
                "code": "00",
                "desc": "success",
                "counterAccountBankId": "",
                "counterAccountBankName": "",
                "counterAccountName": "",
                "counterAccountNumber": "",
                "virtualAccountName": "",
                "virtualAccountNumber": "",
            }
        )

    def signed_webhook(self, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "code": "00",
            "desc": "success",
            "success": True,
            "data": data,
            "signature": signature_from_data(data, self.checksum_key),
        }


# ---------------------------------------------------------------------------
# SePay — backup gateway slot (NOT implemented in P0)
# ---------------------------------------------------------------------------


class SePayProvider(PaymentProvider):
    """Reserved slot for SePay (phương án dự phòng). Not implemented in P0."""

    name = "sepay"

    def _todo(self) -> None:
        raise NotImplementedError("SePayProvider chưa triển khai (P0 chỉ payOS)")

    def create_payment(self, **kwargs: Any) -> PaymentLink:  # type: ignore[override]
        self._todo()
        raise AssertionError  # pragma: no cover

    def get_payment(self, order_code: int) -> PaymentStatus:
        self._todo()
        raise AssertionError  # pragma: no cover

    def cancel_payment(self, order_code: int, reason: str = "") -> dict[str, Any]:
        self._todo()
        raise AssertionError  # pragma: no cover

    def verify_webhook(self, payload: dict[str, Any]) -> bool:
        return False


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------

_provider: Optional[PaymentProvider] = None
_provider_lock = threading.RLock()


def payos_keys_present() -> bool:
    return all((os.environ.get(k) or "").strip() for k in PAYOS_ENV_KEYS)


def provider_name_from_env() -> str:
    raw = (os.environ.get("PAYMENT_PROVIDER") or "").strip().lower()
    if raw in ("payos", "mock", "sepay"):
        return raw
    return "payos" if payos_keys_present() else "mock"


def get_provider() -> PaymentProvider:
    global _provider
    with _provider_lock:
        if _provider is not None:
            return _provider
        name = provider_name_from_env()
        if name == "payos":
            _provider = PayOSProvider()
        elif name == "sepay":
            _provider = SePayProvider()
        else:
            _provider = MockPaymentProvider()
        log.info("payment provider selected: %s", _provider.name)
        return _provider


def set_provider(provider: Optional[PaymentProvider]) -> None:
    global _provider
    with _provider_lock:
        _provider = provider


def reset_provider() -> None:
    set_provider(None)
