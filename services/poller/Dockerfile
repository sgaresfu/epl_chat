# The poller: the only process permitted to call an upstream.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
      "pydantic>=2.9" "pydantic-settings>=2.4" "sqlalchemy>=2.0.30" "asyncpg>=0.29" \
      "redis>=5.0" "httpx>=0.27" "tenacity>=9.0" "structlog>=24.4" "feedparser>=6.0" \
      "boto3>=1.35" "tzdata>=2026.1"

COPY shared ./shared
COPY services ./services

RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

CMD ["python", "-m", "services.poller.main"]
