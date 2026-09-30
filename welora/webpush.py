"""Web Push adapter (W3C Push API · RFC 8291 aes128gcm · RFC 8292 VAPID).

Real transport for renewal reminders (PAY-05: email + push). Browser flow:
``/app/sw.js`` service worker + ``PushManager.subscribe`` with our VAPID public
key → ``POST /api/push/v1/subscriptions``. The server encrypts each message for
the subscription (ECDH P-256 + HKDF + AES-128-GCM) and POSTs it to the browser
vendor's push service with a VAPID JWT (ES256).

Default SAFE: nothing is sent unless ``WELORA_PUSH_PROVIDER=webpush`` AND
``WELORA_VAPID_PUBLIC_KEY`` / ``WELORA_VAPID_PRIVATE_KEY`` / ``WELORA_VAPID_SUBJECT``
are set (and ``cryptography`` is installed). Otherwise welora.push stays log-only.
Keys live in env only; generate locally:  ``python -m welora.webpush gen-vapid``.
Endpoints are restricted to known push-service hosts (no SSRF). Tests replace
``set_transport`` — no network.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
import sys
import time
import uuid
from typing import Any, Callable, Optional
from urllib.parse import urlparse

log = logging.getLogger("welora.webpush")

RECORD_SIZE = 4096
DEFAULT_TTL_S = 24 * 3600
MAX_FAILURES = 3
PUSH_HOST_SUFFIXES = (
    "fcm.googleapis.com",              # Chrome / Edge / Android
    "updates.push.services.mozilla.com",  # Firefox
    "push.services.mozilla.com",
    "notify.windows.com",              # legacy Edge / Windows
    "push.apple.com",                  # Safari (web.push.apple.com)
)

Transport = Callable[[str, dict[str, str], bytes], int]  # (url, headers, body) -> HTTP status


def b64u(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def b64u_decode(s: str) -> bytes:
    s = (s or "").strip()
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


# ---------------------------------------------------------------------------
# config
# ---------------------------------------------------------------------------


def crypto_available() -> bool:
    try:
        import cryptography  # noqa: F401

        return True
    except ImportError:
        return False


def config() -> dict[str, str]:
    return {
        "provider": (os.environ.get("WELORA_PUSH_PROVIDER") or "log").strip().lower(),
        "public_key": (os.environ.get("WELORA_VAPID_PUBLIC_KEY") or "").strip(),
        "private_key": (os.environ.get("WELORA_VAPID_PRIVATE_KEY") or "").strip(),
        "subject": (os.environ.get("WELORA_VAPID_SUBJECT") or "").strip(),
    }


def enabled() -> bool:
    c = config()
    return (
        c["provider"] == "webpush"
        and bool(c["public_key"] and c["private_key"])
        and c["subject"].startswith(("mailto:", "https://"))
        and crypto_available()
    )


def public_key() -> Optional[str]:
    return config()["public_key"] if enabled() else None


# ---------------------------------------------------------------------------
# crypto (RFC 8291 / RFC 8292)
# ---------------------------------------------------------------------------


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def _pub_bytes(pub) -> bytes:
    from cryptography.hazmat.primitives import serialization

    return pub.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def _private_from_raw(raw32: bytes):
    from cryptography.hazmat.primitives.asymmetric import ec

    return ec.derive_private_key(int.from_bytes(raw32, "big"), ec.SECP256R1())


def encrypt(
    plaintext: bytes, *, ua_public_b64: str, auth_secret_b64: str, salt: Optional[bytes] = None, as_private_raw: Optional[bytes] = None,
) -> bytes:
    """aes128gcm body for one record (RFC 8291 §3.4 / RFC 8188). salt/as key injectable for test vectors."""
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ua_pub_raw = b64u_decode(ua_public_b64)
    auth = b64u_decode(auth_secret_b64)
    if len(ua_pub_raw) != 65 or len(auth) < 16:
        raise ValueError("invalid subscription keys")
    ua_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub_raw)
    as_priv = _private_from_raw(as_private_raw) if as_private_raw else ec.generate_private_key(ec.SECP256R1())
    as_pub_raw = _pub_bytes(as_priv.public_key())
    ecdh = as_priv.exchange(ec.ECDH(), ua_pub)
    ikm = _hkdf(auth, ecdh, b"WebPush: info\x00" + ua_pub_raw + as_pub_raw, 32)
    salt = salt or os.urandom(16)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    if len(plaintext) + 1 + 16 > RECORD_SIZE:
        raise ValueError("payload too large for one record")
    ct = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    return salt + struct.pack(">I", RECORD_SIZE) + bytes([len(as_pub_raw)]) + as_pub_raw + ct


def vapid_headers(endpoint: str, *, now: Optional[float] = None) -> dict[str, str]:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

    c = config()
    u = urlparse(endpoint)
    claims = {"aud": f"{u.scheme}://{u.netloc}", "exp": int((now or time.time()) + 12 * 3600), "sub": c["subject"]}
    head = b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode())
    body = b64u(json.dumps(claims, separators=(",", ":")).encode())
    signing = f"{head}.{body}".encode("ascii")
    key = _private_from_raw(b64u_decode(c["private_key"]))
    r, s = decode_dss_signature(key.sign(signing, ec.ECDSA(hashes.SHA256())))
    jwt = f"{head}.{body}.{b64u(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
    return {"Authorization": f"vapid t={jwt}, k={c['public_key']}"}


def generate_vapid() -> tuple[str, str]:
    from cryptography.hazmat.primitives.asymmetric import ec

    k = ec.generate_private_key(ec.SECP256R1())
    raw = k.private_numbers().private_value.to_bytes(32, "big")
    return b64u(_pub_bytes(k.public_key())), b64u(raw)


# ---------------------------------------------------------------------------
# subscriptions (DB)
# ---------------------------------------------------------------------------


def endpoint_allowed(endpoint: str) -> bool:
    try:
        u = urlparse(endpoint or "")
    except ValueError:
        return False
    host = (u.hostname or "").lower()
    return u.scheme == "https" and any(host == h or host.endswith("." + h) for h in PUSH_HOST_SUFFIXES)


def _conn():
    from welora import checkout as co

    return co._conn()


def _iso(ts: Optional[float] = None) -> str:
    from welora import checkout as co

    return co._iso(time.time() if ts is None else ts)


def save_subscription(user_id: str, sub: dict[str, Any], *, user_agent: str = "") -> dict[str, Any]:
    endpoint = str((sub or {}).get("endpoint") or "").strip()
    keys = (sub or {}).get("keys") or {}
    p256dh, auth = str(keys.get("p256dh") or "").strip(), str(keys.get("auth") or "").strip()
    if not endpoint_allowed(endpoint) or len(endpoint) > 1000:
        raise ValueError("PUSH_ENDPOINT_NOT_ALLOWED")
    try:
        if len(b64u_decode(p256dh)) != 65 or len(b64u_decode(auth)) < 16:
            raise ValueError
    except (ValueError, TypeError):
        raise ValueError("PUSH_KEYS_INVALID")
    conn = _conn()
    try:
        conn.execute("DELETE FROM push_subscriptions WHERE endpoint=?", (endpoint,))
        conn.execute(
            "INSERT INTO push_subscriptions(id, user_id, endpoint, p256dh, auth, user_agent, created_at, failures) "
            "VALUES (?,?,?,?,?,?,?,0)",
            (uuid.uuid4().hex, user_id, endpoint, p256dh, auth, (user_agent or "")[:200], _iso()),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


def delete_subscription(user_id: str, endpoint: str) -> bool:
    conn = _conn()
    try:
        cur = conn.execute("DELETE FROM push_subscriptions WHERE user_id=? AND endpoint=?", (user_id, endpoint))
        conn.commit()
        return (cur.rowcount or 0) > 0
    finally:
        conn.close()


def subscriptions_for(user_id: str) -> list[dict[str, Any]]:
    conn = _conn()
    try:
        return [
            {k: r[k] for k in r.keys()}
            for r in conn.execute(
                "SELECT * FROM push_subscriptions WHERE user_id=? AND disabled_at IS NULL", (user_id,)
            ).fetchall()
        ]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# transport + sender
# ---------------------------------------------------------------------------


def _httpx_transport(url: str, headers: dict[str, str], body: bytes) -> int:
    import httpx

    return httpx.post(url, headers=headers, content=body, timeout=10.0).status_code


_transport: Transport = _httpx_transport


def set_transport(fn: Optional[Transport]) -> None:
    global _transport
    _transport = fn or _httpx_transport


def _mark(sub_id: str, *, ok: bool, gone: bool = False) -> None:
    conn = _conn()
    try:
        if ok:
            conn.execute("UPDATE push_subscriptions SET failures=0, last_success_at=? WHERE id=?", (_iso(), sub_id))
        elif gone:
            conn.execute("UPDATE push_subscriptions SET disabled_at=? WHERE id=?", (_iso(), sub_id))
        else:
            conn.execute(
                "UPDATE push_subscriptions SET failures=failures+1, "
                "disabled_at=CASE WHEN failures+1 >= ? THEN ? ELSE disabled_at END WHERE id=?",
                (MAX_FAILURES, _iso(), sub_id),
            )
        conn.commit()
    finally:
        conn.close()


def send_to_user(user_id: str, title: str, body: str, data: Optional[dict[str, Any]] = None) -> int:
    """Encrypt + deliver to every active subscription of the user. Returns #delivered."""
    if not enabled():
        return 0
    payload = json.dumps(
        {"title": title[:120], "body": body[:300], "url": (data or {}).get("url") or "/app/my-plan", "data": data or {}},
        ensure_ascii=False,
    ).encode("utf-8")
    delivered = 0
    for s in subscriptions_for(user_id):
        try:
            enc = encrypt(payload, ua_public_b64=s["p256dh"], auth_secret_b64=s["auth"])
            headers = {
                **vapid_headers(s["endpoint"]),
                "Content-Encoding": "aes128gcm",
                "Content-Type": "application/octet-stream",
                "TTL": str(DEFAULT_TTL_S),
                "Urgency": "normal",
            }
            status = int(_transport(s["endpoint"], headers, enc))
        except Exception as e:
            log.warning("webpush error sub=%s err=%s", s["id"][:8], type(e).__name__)
            _mark(s["id"], ok=False)
            continue
        if 200 <= status < 300:
            delivered += 1
            _mark(s["id"], ok=True)
        elif status in (404, 410):  # subscription expired / unsubscribed
            _mark(s["id"], ok=False, gone=True)
        else:
            log.warning("webpush status=%s sub=%s", status, s["id"][:8])
            _mark(s["id"], ok=False)
    return delivered


def _main(argv: list[str]) -> int:
    if argv[:1] == ["gen-vapid"]:
        pub, priv = generate_vapid()
        print("# Set on Render (never commit):")
        print("WELORA_PUSH_PROVIDER=webpush")
        print(f"WELORA_VAPID_PUBLIC_KEY={pub}")
        print(f"WELORA_VAPID_PRIVATE_KEY={priv}")
        print("WELORA_VAPID_SUBJECT=mailto:<ops-email>")
        return 0
    print("usage: python -m welora.webpush gen-vapid")
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
