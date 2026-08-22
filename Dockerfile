# Welora Phase 2 — Staging image
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    WELORA_STORE=sqlite \
    WELORA_DB_URL=/data/welora.db \
    WELORA_LLM_PROVIDER=stub \
    PORT=8000

RUN mkdir -p /data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY welora ./welora
COPY tests ./tests
COPY demo_e2e.py run_tests.sh ./

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

CMD ["uvicorn", "welora.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
