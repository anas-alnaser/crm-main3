#!/bin/sh
# Production entrypoint: apply migrations, collect static, then serve with gunicorn.
set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Collecting static files..."
python manage.py collectstatic --noinput

echo "Starting gunicorn..."
# Cloud Run injects PORT (the container must listen on it, on all interfaces).
# Falls back to 8000 for docker-compose / local runs, matching the Dockerfile
# EXPOSE and HEALTHCHECK.
exec gunicorn crm.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-3}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --access-logfile - \
    --error-logfile -
