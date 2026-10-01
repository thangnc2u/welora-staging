# Welora Staging

Personal finance OS — **An Toàn trước** · Cổng ≥ 3 tháng · Hard Deny trước LLM.

## Local

```bash
pip install -r requirements.txt
export PYTHONPATH=. WELORA_STORE=sqlite WELORA_DB_URL=/tmp/welora.db WELORA_ENV=staging
uvicorn welora.api.app:app --host 0.0.0.0 --port 8000 --no-proxy-headers
```

- `/health` · `/app/demo` · `/docs`

## Deploy Render (URL cố định)

1. [render.com](https://render.com) → **New** → **Blueprint**
2. Connect GitHub repo `thangnc2u/welora-staging`
3. Apply `render.yaml` → service `welora-staging`
4. Wait build → open `https://welora-staging.onrender.com` (hoặc URL Render cấp)

Hoặc **Web Service** thủ công:
- Root: `.`
- Build: `pip install -r requirements.txt`
- Start: `bash start.sh` (uvicorn với `--no-proxy-headers` — KHÔNG dùng `--proxy-headers`: Render đặt `FORWARDED_ALLOW_IPS=*`, uvicorn sẽ lấy hop X-Forwarded-For ngoài cùng bên trái do client tự ghi làm IP → rate limit bị lách. App tự xác định IP thật, xem `welora/auth_ratelimit.py`)
- Health: `/health`
- Env: `PYTHONPATH=.` · `WELORA_STORE=sqlite` · `WELORA_DB_URL=/tmp/welora_staging.db` · `WELORA_LLM_PROVIDER=stub` · `WELORA_ENV=staging`

## Principles

Safety Gate hard · Score không bypass · Deny không gọi LLM.
