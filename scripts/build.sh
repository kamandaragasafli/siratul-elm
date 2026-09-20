#!/usr/bin/env bash
# Render Build Command: bash scripts/build.sh
set -euo pipefail
cd "$(dirname "$0")/.."

export DJANGO_SUPERUSER_USERNAME="${DJANGO_SUPERUSER_USERNAME:-Kamandar}"
export DJANGO_SUPERUSER_PASSWORD="${DJANGO_SUPERUSER_PASSWORD:-20012001Kamandar}"
export DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-kamandar@localhost}"

echo "==> pip install"
pip install -r requirements.txt

echo "==> migrate"
python manage.py migrate --noinput

echo "==> ensure_superuser (${DJANGO_SUPERUSER_USERNAME})"
python manage.py ensure_superuser

echo "==> collectstatic"
python manage.py collectstatic --noinput

echo "==> build OK"
