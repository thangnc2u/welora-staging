#!/usr/bin/env bash
set -eu
PORT_BIND="${PORT:-8000}"
echo "[welora] start.sh bind 0.0.0.0:${PORT_BIND} provider=${WELORA_LLM_PROVIDER:-stub}"
exec python -m uvicorn welora.api.app:app \
  --host 0.0.0.0 \
  --port "${PORT_BIND}" \
  --workers 1 \
  --proxy-headers \
  --timeout-keep-alive 5
