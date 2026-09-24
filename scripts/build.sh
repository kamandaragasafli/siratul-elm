#!/usr/bin/env bash
# Render Build Command: bash scripts/build.sh
set -euo pipefail
cd "$(dirname "$0")/.."

export DJANGO_SUPERUSER_USERNAME="${DJANGO_SUPERUSER_USERNAME:-Kamandar}"
export DJANGO_SUPERUSER_PASSWORD="${DJANGO_SUPERUSER_PASSWORD:-20012001Kamandar}"
export DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-kamandar@localhost}"

RETRY=(bash scripts/db_retry.sh)

echo "==> pip install"
pip install -r requirements.txt

echo "==> migrate"
"${RETRY[@]}" python manage.py migrate --noinput

echo "==> ensure_superuser (${DJANGO_SUPERUSER_USERNAME})"
"${RETRY[@]}" python manage.py ensure_superuser

echo "==> collectstatic"
python manage.py collectstatic --noinput

# Shell yoxdursa: Render Environment-də DEPLOY_IXLASLA=1 qoy → Manual Deploy.
# Sync bitəndən sonra bu env-i sil (hər build-də 3–5 dəq çəkməsin).
if [ "${DEPLOY_IXLASLA:-}" = "1" ]; then
  echo "==> deploy_ixlasla (YouTube sil + ixlasla MP3 sync)"
  "${RETRY[@]}" python manage.py deploy_ixlasla
else
  echo "==> skip deploy_ixlasla (DEPLOY_IXLASLA!=1)"
fi

echo "==> build OK"
