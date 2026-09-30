# Checkout VietQR — mục 10 acceptance run guide (test channel, non-prod)

payOS has **no separate sandbox host**. "Sandbox" = a separate payOS **test channel** with its
own `PAYOS_CLIENT_ID` / `PAYOS_API_KEY` / `PAYOS_CHECKSUM_KEY`, run on a **non-prod** Render
service against the same base URL `https://api-merchant.payos.vn`. CI never calls payOS
(MockPaymentProvider only).

## 0. Setup (non-prod service only)

| Env | Value |
|---|---|
| `WELORA_ENV` | `staging` (never `production` for this run) |
| `WELORA_DB_URL` | **Postgres URL** (Neon / Render Postgres, see 0.1) — durable users, orders, 2FA state. Without it the Free service uses SQLite in `/tmp` and loses everything on each deploy/restart/spin-down |
| `WELORA_ADMIN_EMAILS` | comma-separated admin emails, e.g. `founder@example.com` (case-insensitive). Empty/unset = **nobody is admin** |
| `WELORA_ADMIN_TOTP_SECRETS` | `<admin_email>:<BASE32>` from `python -m welora.admin_2fa gen <admin_email>` (the older `<user_id>:<BASE32>` form still works) |
| `WELORA_SMTP_HOST` / `WELORA_SMTP_PORT` / `WELORA_SMTP_USER` / `WELORA_SMTP_PASSWORD` / `WELORA_MAIL_FROM` | real SMTP — **required** for the admin login code (and receipts/reminders) |
| `WELORA_CHECKOUT_ENABLED` | `1` (non-prod only; production stays unset) |
| `PAYMENT_PROVIDER` | `payos` |
| `PAYOS_CLIENT_ID` / `PAYOS_API_KEY` / `PAYOS_CHECKSUM_KEY` | test-channel keys (Render secret) |
| `WELORA_PUBLIC_BASE_URL` | the non-prod HTTPS URL |
| `WELORA_CHECKOUT_TEST_HOOKS` | `1` (enables grace time-travel; refused when `WELORA_ENV=production`) |

### 0.1 Durable database (Founder, one-time)

Render Free web services have no persistent disk, so use an external Postgres:

- **Neon Free (recommended for staging)**: no expiry; 0.5 GB storage/project, 100 CU-hours/month,
  compute scales to zero after 5 min idle (first query wakes it in < 1 s). neon.com → Sign up →
  *New project* (region **AWS Asia Pacific (Singapore)**, Postgres 17) → *Connect* → copy the
  connection string `postgresql://…@…neon.tech/neondb?sslmode=require…`.
- **Render Postgres Free**: 1 GB, but **expires 30 days after creation** (14-day grace to upgrade,
  then deleted, no backups). Only if you accept re-creating it monthly; same region as the web
  service (Singapore); use the *Internal Database URL*.

Then on Render → `welora-staging` → *Environment*: set `WELORA_DB_URL` to that URL (keep
`WELORA_STORE=sqlite`: it only means "DB-backed store"; the URL decides the dialect) → *Save* (Render
redeploys). On start the app runs migrations 001–011 automatically (idempotent). Check
`GET /health` → `"dialect": "postgres"`. `render.yaml` declares `WELORA_DB_URL` with `sync: false`, so
a Blueprint sync never overwrites the Dashboard value. `psycopg[binary]` ships in `requirements.txt`.

Local check (optional): `WELORA_DB_URL=<url> PYTHONPATH=. python -m welora.db.migrate` twice →
second run prints `OK up-to-date`.

### 0.2 First admin (no Render Shell needed)

1. Set `WELORA_ADMIN_EMAILS=<your email>` and SMTP env (above).
2. Locally: `PYTHONPATH=. python -m welora.admin_2fa gen <your email>` → put the printed
   `email:BASE32` line into `WELORA_ADMIN_TOTP_SECRETS`; scan the printed `otpauth://` URI in an
   authenticator app. Never commit or paste the secret anywhere else.
3. Open `/app/admin/login` → enter the email → a 6-digit code arrives by email (10 min, 5 tries,
   max 5 codes / 15 min) → you are signed in with role `admin` (audited in `auth_audit`).
4. `/app/admin/checkout` → enter the TOTP code → admin tools unlocked (12 h session).
5. Register the webhook once for this channel: `POST /api/admin/v1/checkout/confirm-webhook`
   `{"webhook_url": "<base>/api/checkout/v1/webhook/payos"}`.

Rules: admin is granted **only** after the email-OTP proves the mailbox (a password sign-up with the
same address is never promoted and its sessions are revoked on promotion). Password, device and
phone-OTP logins into an admin account are refused. Removing an email from `WELORA_ADMIN_EMAILS`
demotes that user at the next restart (env change → redeploy) or next login, audited
(`admin_role_revoked`). With Postgres, the admin keeps the same `user_id` across deploys.

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

## 3. P1 follow-ups — extra test-channel checks

### Late UNDERPAID top-up (after the 15-min link expired)

Server behaviour (covered by CI with MockPaymentProvider):
- Webhook with our `orderCode` → accumulates (`_sum_paid`) → PAID + grant when total ≥ amount.
- Webhook with missing/unknown `orderCode` → matched by transfer content: `WELORA<orderCode>`
  (exact) or `WL<last 7 digits>` (only if exactly one open order matches; otherwise left for admin).
  Match traced as `payment_events.match.description`.
- Reconcile: `GET /v2/payment-requests/{orderCode}` transactions for UNDERPAID orders (any age
  until REFUND_PENDING at 24 h), plus re-matching of stored signed webhooks with no order.
- Anything unmatched: `GET /api/admin/v1/checkout/unmatched-payments` (2FA) → manual grant / refund.

NOT verifiable without the payOS test channel — record what you see:
| # | Question | How |
|---|---|---|
| 1 | Does the bank accept a transfer to the link's virtual account after the link expired? | pay 60% → wait 16 min → scan the remainder QR on `/app/checkout` |
| 2 | If accepted: does payOS send a webhook? With which `orderCode` (same / other / none) and `description`? | check `payment_events.raw_payload` (or `/unmatched-payments`) |
| 3 | Does `GET /v2/payment-requests/{orderCode}` list the late transaction (`transactions[]`, `amountPaid`)? | admin "reconcile" → order status |
| 4 | Is `reference` identical in webhook and API (dedupe relies on it)? | compare both rows' `provider_txn_ref` |

### Renewal Web Push
1. `python -m welora.webpush gen-vapid` locally → set `WELORA_PUSH_PROVIDER=webpush`,
   `WELORA_VAPID_PUBLIC_KEY`, `WELORA_VAPID_PRIVATE_KEY`, `WELORA_VAPID_SUBJECT=mailto:…` on Render.
2. `/app/my-plan` → "Bật thông báo nhắc gia hạn" → allow (Chrome/Edge/Firefox; iOS needs the site
   added to Home Screen, iOS ≥ 16.4).
3. Admin → "Chạy job nhắc hạn ngay" with a D-3 offset → notification appears; click opens the renewal link.

### Upgrade refund
Buy ACA → upgrade to OS1 → refund OS1 (request + complete) → `/app/my-plan` shows ACA active with the
days it had left at upgrade time (counted from the refund); `payment_events.upgrade.restored_previous`.

### A/B price on /pricing
Only when `experiments[aca_price_ab].active=true` (both config copies): logged-in user in group B sees
ACA 49.000 ₫/tháng on `/pricing` and is charged the same at checkout; anonymous visitors see the control price.
