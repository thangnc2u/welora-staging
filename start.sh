#!/bin/sh
set -eu
# Render injects PORT. Never wrap expansion in single quotes.
exec python -m uvicorn welora.api.app:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --workers 1 \
  --proxy-headers \
  --timeout-keep-alive 5
