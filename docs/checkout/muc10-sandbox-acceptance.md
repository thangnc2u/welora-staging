# Checkout VietQR — mục 10 acceptance run guide (test channel, non-prod)

payOS has **no separate sandbox host**. "Sandbox" = a separate payOS **test channel** with its
own `PAYOS_CLIENT_ID` / `PAYOS_API_KEY` / `PAYOS_CHECKSUM_KEY`, run on a **non-prod** Render
service against the same base URL `https://api-merchant.payos.vn`. CI never calls payOS
(MockPaymentProvider only).

## 0. Setup (non-prod service only)

| Env | Value |
|---|---|
| `WELORA_ENV` | `staging` (never `production` for this run) |
| `WELORA_CHECKOUT_ENABLED` | `1` (non-prod only; production stays unset) |
| `PAYMENT_PROVIDER` | `payos` |
| `PAYOS_CLIENT_ID` / `PAYOS_API_KEY` / `PAYOS_CHECKSUM_KEY` | test-channel keys (Render secret) |
| `WELORA_PUBLIC_BASE_URL` | the non-prod HTTPS URL |
| `WELORA_ADMIN_TOTP_SECRETS` | `<admin_user_id>:<BASE32>` from `python -m welora.admin_2fa gen <admin_user_id>` |
| `WELORA_CHECKOUT_TEST_HOOKS` | `1` (enables grace time-travel; refused when `WELORA_ENV=production`) |
| `WELORA_SMTP_*` / `WELORA_MAIL_FROM` | real SMTP so receipts/reminders arrive |

1. Admin logs in (OTP/device flow, role in `ADMIN_ROLES`) → `/app/admin/checkout` → enter the TOTP code.
2. Register the webhook once for this channel: `POST /api/admin/v1/checkout/confirm-webhook`
   `{"webhook_url": "<base>/api/checkout/v1/webhook/payos"}`.

## 1. Checklist → how to run

| mục 10 item | Steps | Expected |
|---|---|---|
| Pay exact amount | `/app/checkout` → plan → confirm → scan QR, pay exact | order PAID, plan open, receipt email ≤ 1 min |
| Same webhook 3× | payOS dashboard "resend webhook" ×3 (or replay the logged payload) | plan granted once (`payment_events` UNIQUE ref) |
| Bad signature | POST the payload with a changed `signature` | 400, `webhook.invalid_signature` event + warning log, order unchanged |
| Webhook off → reconcile | temporarily point payOS webhook elsewhere, pay; wait ≤ 7 min (job every 5 min) or admin "reconcile" | order PAID via reconcile |
| Underpaid | pay less than the amount | UNDERPAID; page shows remaining + **new QR for the remainder** (24 h) |
| returnUrl by hand | open `/app/checkout/return?orderCode=…` before paying | plan NOT opened |
| Tamper client amount | send `amount` in `POST /api/checkout/v1/orders` | ignored, server price used |
| QR expiry / new order | wait 15 min → EXPIRED; create a new order | old link cancelled via payOS API |
| Early renewal | pay the same plan again before expiry (or use the reminder magic link) | new end = old end + 1 period (`/app/my-plan`) |
| Grace end → Free | admin: detail of the PAID order → "Lùi kỳ gói" with days = days-left + 8 → "Chạy job nhắc hạn ngay" | subscription expired, `/api/core/v1/entitlements/me` plan FREE, budgets/learning data intact; final email |

Reminder schedule check (mục 7): use `POST /api/admin/v1/checkout/renewal/run`
`{"now_offset_days": N}` (test hooks only) to simulate D-14/D-3/D0/D+3/D+7.

## 2. After the run

- Unset `WELORA_CHECKOUT_TEST_HOOKS`. Production keeps `WELORA_CHECKOUT_ENABLED` unset until the
  founder signs off (mục 10 PASS + one real 2.000đ order + accountant tax confirmation).
- Verify on the test channel that a top-up transfer for an UNDERPAID order (same description,
  remainder QR) is matched by payOS to the same `orderCode` after the original 15-min link expiry.
  If payOS does not match it, handle via admin manual grant (CK-10) and report back.
