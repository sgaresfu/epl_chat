# The api, serving the React app from the same origin.
#
# BRIEF section 2 says the frontend is a static site on a CDN and is "never
# served from the Python process", and gives a good reason: a Python process
# should not spend its time on asset bytes.
#
# It costs something that matters more here. Two origins means the session
# cookie is third-party, and every browser on iOS is WebKit, so Safari's
# tracking prevention drops it — nobody could sign in from a phone, which is
# how three of the four actually watch. The alternatives were a paid custom
# domain or an unverified proxy rewrite.
#
# Same-origin removes the whole class: no CORS, no SameSite=None, no
# VITE_API_BASE to get wrong (both of which already broke a deploy), and one
# service instead of two. Static assets are hashed and served with a long
# immutable cache, so Python hands out each file approximately once.

# ---- stage 1: build the frontend
FROM node:20-slim AS web

WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

COPY apps/web ./
# Empty on purpose: same-origin means relative /api paths.
ENV VITE_API_BASE=""
RUN npm run build

# ---- stage 2: the api
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir \
      "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.9" "pydantic-settings>=2.4" \
      "sqlalchemy>=2.0.30" "alembic>=1.13" "asyncpg>=0.29" "psycopg[binary]>=3.2" \
      "redis>=5.0" "httpx>=0.27" \
      "tenacity>=9.0" "structlog>=24.4" "itsdangerous>=2.2" "python-multipart>=0.0.9" \
      "feedparser>=6.0" "pillow>=10.4" "boto3>=1.35" "tzdata>=2026.1"

COPY shared ./shared
COPY services ./services
COPY migrations ./migrations
COPY alembic.ini ./
COPY --from=web /web/dist ./static

RUN chmod +x services/api/entrypoint.sh

# Never run as root.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000

# The container's own zoneinfo may be stale or missing; the tzdata package above
# ships a known-good copy so Alberta's 2026-11-01 rule change is applied.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import os,urllib.request;urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT','8000')}/healthz\")"

# Migrations run in the entrypoint rather than a preDeployCommand, which Render
# only offers on paid plans. A failed migration exits non-zero and fails the
# deploy, instead of serving traffic against a schema that never arrived.
CMD ["./services/api/entrypoint.sh"]
