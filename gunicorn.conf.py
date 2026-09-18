"""Gunicorn konfiqurasiyası — Render üçün."""

# yt-dlp 3 attempt × 25s socket_timeout = max ~120s
timeout = 120
graceful_timeout = 30
keepalive = 5

# Render free: 1 worker kifayət edir, çox worker RAM yeyir
workers = 1
worker_class = 'sync'
threads = 4

# Logları Render-in stdout-una yaz
accesslog = '-'
errorlog = '-'
loglevel = 'info'
