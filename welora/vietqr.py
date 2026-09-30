"""VietQR (NAPAS EMVCo) payload builder — used for the UNDERPAID remainder QR (mục 8).

Builds a dynamic QR for bank transfer to account (bin, account_number) with a
fixed amount and transfer description. Pure function, no network.
"""

from __future__ import annotations

NAPAS_GUID = "A000000727"
SERVICE_TO_ACCOUNT = "QRIBFTTA"


def _tlv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def crc16_ccitt(data: str) -> str:
    crc = 0xFFFF
    for ch in data.encode("utf-8"):
        crc ^= ch << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
            crc &= 0xFFFF
    return f"{crc:04X}"


def build_payload(*, bin_code: str, account_number: str, amount: int, description: str) -> str:
    if not bin_code or not account_number:
        raise ValueError("bin and account_number required")
    if int(amount) <= 0:
        raise ValueError("amount must be positive")
    beneficiary = _tlv("00", str(bin_code)) + _tlv("01", str(account_number))
    merchant = _tlv("00", NAPAS_GUID) + _tlv("01", beneficiary) + _tlv("02", SERVICE_TO_ACCOUNT)
    body = (
        _tlv("00", "01")
        + _tlv("01", "12")  # dynamic QR (has amount)
        + _tlv("38", merchant)
        + _tlv("53", "704")
        + _tlv("54", str(int(amount)))
        + _tlv("58", "VN")
        + _tlv("62", _tlv("08", str(description)[:25]))
        + "6304"
    )
    return body + crc16_ccitt(body)
