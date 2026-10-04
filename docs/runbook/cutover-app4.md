# Runbook — Cutover Production GP lên https://app4.welora.vn

Ticket: «GP · Cutover Production app4.welora.vn (GP)» — https://app.notion.com/p/3e6a91c4dcdf81b6b05cda9dc8d61715
Service Render production: **`welora-prod`** (service mới, tách khỏi `welora-staging`).
Mọi bước dưới đây là việc **Founder làm tay** sau khi PR được review. PR không đụng Render / Neon / DNS / Resend,
không có migration mới, không đổi Hard Deny, `TARGET_MONTHS`, `gate_months` (= 3), Pre-Rule, Lifetime, bảng giá,
payOS logic, cổng demo N02-01/N02-02. Checkout giữ **OFF**. Không đụng www / app2 / app3.

## 1. Bảng env production (`welora-prod`)

Giá trị trong bảng là **mẫu / chỗ trống**. Secret thật chỉ đặt trong Render Dashboard, không bao giờ vào repo.
"Chặn khởi động" = thiếu / sai thì process production dừng ngay lúc khởi động (`ProdConfigError`, Render giữ bản deploy cũ).

| Biến | Bắt buộc? | Giá trị prod (mẫu) | Ghi chú |
|---|---|---|---|
| `WELORA_ENV` | Bắt buộc | `production` | Bật toàn bộ chốt production. |
| `WELORA_PUBLIC_BASE_URL` | Bắt buộc · chặn khởi động | `https://app4.welora.vn` | Origin https, không path, không `/` cuối. Link payOS return/cancel/webhook, link gia hạn dựng từ đây; CORS luôn có origin này. |
| `WELORA_OTP_HMAC_KEY` | Bắt buộc · chặn khởi động | `<secret ≥ 32 ký tự>` | Tạo: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. `/health` phải ra `otp_hmac_key: env`. |
| `WELORA_GUEST_DEMO` | Bắt buộc · chặn khởi động | `0` | Khác `0` (kể cả không đặt) → không khởi động. Tắt khách/demo P1–P6. |
| `WELORA_ADMIN_TOTP_SECRETS` | Bắt buộc · chặn khởi động | `<email_admin>:<BASE32>` (nhiều mục cách nhau dấu phẩy) | 2FA admin. Tạo trên máy mình: `PYTHONPATH=. python -m welora.admin_2fa gen <email_admin>`. |
| `WELORA_ADMIN_EMAILS` | Bắt buộc cho admin | `<email_admin>` | Email được nâng quyền admin sau khi xác minh qua OTP email. |
| `WELORA_DB_URL` | Bắt buộc (dữ liệu bền) | `<DSN Neon production>?sslmode=require` | DB **riêng** cho prod, không dùng DB staging. Thiếu → SQLite tạm, mất khi redeploy. |
| `WELORA_STORE` | Bắt buộc | `postgres` | Cùng `WELORA_DB_URL` Postgres. |
| `WELORA_MAIL_PROVIDER` | Bắt buộc (mail OTP thật) | `resend` | |
| `RESEND_API_KEY` | Bắt buộc (mail OTP thật) | `<re_… secret>` | Domain `welora.vn` phải xác minh xong trên Resend. |
| `WELORA_MAIL_FROM` | Bắt buộc (mail OTP thật) | `Welora <…@welora.vn>` | Địa chỉ gửi trên domain đã xác minh. Thiếu → sender thử của Resend, chỉ gửi được cho chủ tài khoản Resend. |
| `WELORA_CORS_ORIGINS` | Tùy chọn | (để trống) | Danh sách origin, dấu phẩy. Production: chỉ các origin này + `WELORA_PUBLIC_BASE_URL`; `*` bị bỏ qua. App cùng origin nên không cần thêm. |
| `WELORA_ALLOWED_HOSTS` | Tùy chọn | `app4.welora.vn` | Đặt → Host khác bị 400 (trừ `/health`, `/healthz`). Nếu muốn smoke qua `welora-prod.onrender.com` thì thêm host đó, hoặc để trống. |
| `WELORA_LLM_PROVIDER` / `WELORA_LLM_API_KEY` | Tùy chọn | như staging / `<secret>` | Không đặt → `stub`. |
| `WELORA_CONTENT_ROOT` | Tùy chọn | `content` | Như staging. |
| `PYTHON_VERSION`, `PYTHONPATH`, `PYTHONUNBUFFERED`, `PYTHONDONTWRITEBYTECODE` | Bắt buộc (build) | `3.11.11`, `.`, `1`, `1` | Như `render.yaml` staging. Start command: `bash start.sh` (không thêm `--proxy-headers`). |
| `PAYOS_CLIENT_ID` / `PAYOS_API_KEY` / `PAYOS_CHECKSUM_KEY` | Chưa cần cho demo | `<secret>` | Chỉ liệt kê. Checkout OFF. |
| `WELORA_VAPID_PUBLIC_KEY` / `WELORA_VAPID_PRIVATE_KEY` / `WELORA_VAPID_SUBJECT`, `WELORA_PUSH_PROVIDER` | Chưa cần cho demo | `<secret>` / `mailto:…` / `webpush` | Chỉ liệt kê. Không đặt → push chỉ ghi log. |

**Không bao giờ đặt trên production** (đặt là chặn khởi động): `WELORA_OTP_ECHO` (bất kỳ giá trị nào),
`WELORA_OTP_FIXED`, `WELORA_RESET_ECHO`, `WELORA_CHECKOUT_TEST_HOOKS`, và mọi `WELORA_RL_*` ≤ 0 (tắt giới hạn lượt).
Cũng không đặt `WELORA_CHECKOUT_ENABLED` (checkout OFF).

## 2. Neon production (Founder chạy)

Đã tạo (ticket, 04/10 08:16): project Neon `welora-prod` (Singapore, Postgres 17), DB `neondb`, branch `production`.
Project mới, tách hẳn khỏi staging, không chép dữ liệu staging, chưa migrate.

1. Chuỗi kết nối (pooled, `?sslmode=require`) Founder giữ và dán thẳng vào `WELORA_DB_URL` của `welora-prod`.
   Không dán vào repo, ticket hay chat.
2. **Sao lưu trước khi migrate**: trước lần migrate đầu tiên tạo branch sao lưu `pre-cutover-YYYYMMDD` từ `production`
   trên https://console.neon.tech (không tự xóa). Làm lại bước này trước mỗi lần migrate sau.
3. Chạy migration từ máy có repo ở đúng commit sẽ deploy (hoặc Render Shell của `welora-prod`):
   `WELORA_DB_URL='<DSN prod>' PYTHONPATH=. python -m welora.db.migrate`
   Lệnh áp các file `welora/db/migrations/postgres/*.sql` theo thứ tự tên (hiện có `001_init` … `021_verify_snooze`),
   rồi in `OK migrate` / `OK up-to-date` và danh sách version. PR này **không** thêm migration.
   Nếu lệnh lỗi qua chuỗi pooled, chạy lại bằng chuỗi direct (không pooled) của cùng branch `production`.
   (App cũng tự áp migration còn thiếu khi dùng DB lần đầu; chạy tay trước giúp thấy lỗi trước khi mở cho người dùng.)

## 3. Render `welora-prod`

1. Tạo Web Service mới tên **`welora-prod`** từ repo `thangnc2u/welora-staging`, branch `main`, runtime Python, build như
   `render.yaml` (`pip install --no-cache-dir --only-binary=:all: -r requirements.txt`), start `bash start.sh`,
   health check path `/health`. **Tắt Auto-Deploy** (chỉ Manual Deploy sau khi Founder merge).
2. Đặt env theo bảng mục 1.
3. Settings → Custom Domains → thêm `app4.welora.vn`. Render hiển thị host đích cho CNAME.
4. Chờ Render cấp HTTPS cho `app4.welora.vn` xong rồi mới smoke.

## 4. DNS

CNAME `app4` → đúng host Render hiển thị ở bước 3.3 (không đoán). Không sửa bản ghi `www`, `app2`, `app3`.

## 5. Seed demo đối tác

Không seed trên production. Các lệnh seed hiện có (`welora.partner_demo_seed`, `python -m welora.seed_db`, `POST /auth/demo/seed`)
là của staging/demo: production với `WELORA_GUEST_DEMO=0` tắt tài khoản demo P1–P6, không tự seed lúc khởi động, và
`/auth/demo/seed` trả 404. Không chạy `python -m welora.seed_db` vào DB production. Tài khoản demo đối tác trên prod = đăng ký thật.

## 6. Smoke sau Manual Deploy

1. `GET https://app4.welora.vn/health`:
   `env: "production"`, `git_sha` = commit vừa deploy, `gate_months: 3`, `hard_deny: true`, `otp_hmac_key: "env"`,
   `auth_test_flags_ignored: []`, `otp_echo/otp_fixed/reset_echo: false`, `guest_academy: false`,
   `entitlements.checkout_enabled: false`.
2. Mở `https://app4.welora.vn/app/login`: trang tải qua HTTPS, không lỗi CORS trong console.
3. Đăng ký một tài khoản bằng email thật → nhận mã OTP xác minh qua mail (gửi từ `@welora.vn`) → xác minh được.
4. Đăng nhập admin (email trong `WELORA_ADMIN_EMAILS`): OTP email + mã TOTP 2FA.
5. Đọc 1 bài Academy.
6. Nếu process không lên: xem log Render — dòng `production refuses to start: …` liệt kê đủ biến thiếu / sai.

## 7. Sau smoke

Báo CoS. CoS kiểm trực tiếp, rồi GP UAT chạy lại trên https://app4.welora.vn.
Dọn tài khoản rác (mục A ticket) và policy SIM swap / squatting (mục C) không nằm trong PR này.
