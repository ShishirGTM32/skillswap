#!/usr/bin/env bash
set -euo pipefail

cd /app

postgres_ready() {
  python - <<'PY'
import os
import sys

import psycopg

conn = None
try:
    conn = psycopg.connect(
        dbname=os.environ["POSTGRES_DB"],
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=os.environ.get("POSTGRES_PORT", "5432"),
        connect_timeout=3,
    )
    conn.close()
except Exception as exc:
    print(f"PostgreSQL not ready: {exc}", file=sys.stderr)
    sys.exit(1)
PY
}

redis_ready() {
  python - <<'PY'
import os
import sys

import redis

try:
    client = redis.from_url(os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0"))
    client.ping()
except Exception as exc:
    print(f"Redis not ready: {exc}", file=sys.stderr)
    sys.exit(1)
PY
}

echo "Waiting for PostgreSQL..."
until postgres_ready; do
  sleep 2
done

echo "Waiting for Redis..."
until redis_ready; do
  sleep 2
done

echo "Applying database migrations..."
python manage.py makemigrations --noinput
python manage.py migrate --noinput

if [ "${COLLECT_STATIC:-true}" = "true" ]; then
  echo "Collecting static files..."
  python manage.py collectstatic --noinput
fi

echo "Starting: $*"
exec "$@"
