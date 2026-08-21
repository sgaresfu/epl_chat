#!/usr/bin/env sh
# Start the api, migrating first.
#
# Render's preDeployCommand — the proper hook for this — is a paid-tier
# feature, so on the free plan migrations run here instead.
#
# `set -e` matters: if the migration fails the container exits non-zero and
# Render reports a failed deploy, which is what should happen. Running it
# inside the application's own start-up instead would risk logging a warning
# and then serving traffic against a schema that is not there.
#
# `alembic upgrade head` is idempotent, so running it on every restart is safe.
set -e

echo "running migrations..."
alembic upgrade head
echo "migrations up to date"

# exec so uvicorn becomes PID 1 and receives Render's shutdown signals directly,
# which lets the lifespan close the poller and the database pool cleanly.
exec uvicorn services.api.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers
