# The api service: REST and SSE, served entirely from cache.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Dependencies first, so a code change does not reinstall the world.
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
      "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.9" "pydantic-settings>=2.4" \
      "sqlalchemy>=2.0.30" "alembic>=1.13" "asyncpg>=0.29" "redis>=5.0" "httpx>=0.27" \
      "tenacity>=9.0" "structlog>=24.4" "itsdangerous>=2.2" "python-multipart>=0.0.9" \
      "feedparser>=6.0" "pillow>=10.4" "boto3>=1.35" "tzdata>=2026.1"

COPY shared ./shared
COPY services ./services
COPY migrations ./migrations
COPY alembic.ini ./

# Never run as root.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000

# The container's own zoneinfo may be stale or missing; the tzdata package above
# ships a known-good copy so Alberta's 2026-11-01 rule change is applied.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/healthz')"

CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
