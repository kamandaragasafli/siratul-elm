#!/usr/bin/env bash
# Render — Shell lazım deyil. Build/Start bu skripti işlədir.
set -euo pipefail
cd "$(dirname "$0")/.."

# Admin (Render Environment ilə override oluna bilər)
export DJANGO_SUPERUSER_USERNAME="${DJANGO_SUPERUSER_USERNAME:-Kamandar}"
export DJANGO_SUPERUSER_PASSWORD="${DJANGO_SUPERUSER_PASSWORD:-20012001Kamandar}"
export DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-kamandar@localhost}"

RETRY=(bash scripts/db_retry.sh)

echo "==> migrate"
"${RETRY[@]}" python manage.py migrate --noinput

echo "==> ensure_superuser (${DJANGO_SUPERUSER_USERNAME})"
"${RETRY[@]}" python manage.py ensure_superuser

echo "==> collectstatic"
python manage.py collectstatic --noinput

echo "==> gunicorn"
exec gunicorn config.wsgi:application \
  --config gunicorn.conf.py \
  --bind "0.0.0.0:${PORT:-8000}"
