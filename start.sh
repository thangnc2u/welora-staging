#!/usr/bin/env bash
set -eu
PORT_BIND="${PORT:-8000}"
# Client IP (CoS review #239): uvicorn must NOT rewrite request.client from X-Forwarded-For.
# Render's Python runtime sets FORWARDED_ALLOW_IPS=*, and with --proxy-headers uvicorn then takes the
# LEFTMOST (client-forged) X-Forwarded-For hop as the peer — every rate-limit bucket becomes
# spoofable. The app resolves the client itself from the real TCP peer + its own trust rules
# (welora/auth_ratelimit.py client_ip), so proxy headers are OFF here and the env is pinned too.
export FORWARDED_ALLOW_IPS="127.0.0.1"
echo "[welora] start.sh bind 0.0.0.0:${PORT_BIND} provider=${WELORA_LLM_PROVIDER:-stub}"
exec python -m uvicorn welora.api.app:app \
  --host 0.0.0.0 \
  --port "${PORT_BIND}" \
  --workers 1 \
  --no-proxy-headers \
  --timeout-keep-alive 5
