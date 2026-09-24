#!/usr/bin/env bash
# Neon/Render SSL kəsilməsi üçün retry — migrate və digər DB əmrləri.
# İstifadə: bash scripts/db_retry.sh python manage.py migrate --noinput
set -euo pipefail

MAX_ATTEMPTS="${DB_RETRY_ATTEMPTS:-5}"
SLEEP_SEC="${DB_RETRY_SLEEP:-8}"
attempt=1

while true; do
  if "$@"; then
    exit 0
  fi
  code=$?
  if [ "$attempt" -ge "$MAX_ATTEMPTS" ]; then
    echo "==> DB əmri $MAX_ATTEMPTS cəhddən sonra uğursuz (exit $code)"
    exit "$code"
  fi
  echo "==> DB bağlantısı kəsildi (cəhd $attempt/$MAX_ATTEMPTS). ${SLEEP_SEC}s gözləyir…"
  attempt=$((attempt + 1))
  sleep "$SLEEP_SEC"
done
