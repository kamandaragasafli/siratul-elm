"""yt-dlp ümumi seçimlər — YouTube bot yoxlaması üçün client fallback + cookies."""

from __future__ import annotations

import logging
import os
import re
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# Datacenter IP-lərdə web client tez-tez bot sayılır; android/ios daha stabil olur
_DEFAULT_PLAYER_CLIENTS = ['android', 'ios', 'mweb', 'tv', 'web']


def _cookies_file() -> str | None:
    """
    Render / lokal:
      YTDLP_COOKIES_FILE=/path/to/cookies.txt
      və ya YTDLP_COOKIES=<Netscape cookies.txt məzmunu>
    """
    path = os.environ.get('YTDLP_COOKIES_FILE', '').strip()
    try:
        from django.conf import settings as dj_settings

        if not path:
            path = (getattr(dj_settings, 'YTDLP_COOKIES_FILE', None) or '').strip()
        media_root = Path(dj_settings.MEDIA_ROOT)
    except Exception:
        media_root = Path(tempfile.gettempdir()) / 'sirac_ytdlp'

    if path and Path(path).is_file():
        return path

    raw = (os.environ.get('YTDLP_COOKIES') or '').strip()
    if not raw:
        return None

    cache = media_root / 'audio' / 'ytdlp_cookies.txt'
    cache.parent.mkdir(parents=True, exist_ok=True)
    text = raw.replace('\\n', '\n')
    if cache.exists() and cache.read_text(encoding='utf-8', errors='ignore') == text:
        return str(cache)
    cache.write_text(text, encoding='utf-8')
    return str(cache)


def ytdlp_base_opts(**extra) -> dict:
    """Bütün YouTube extract/download üçün baza opts."""
    clients = os.environ.get('YTDLP_PLAYER_CLIENTS', '').strip()
    player_clients = (
        [c.strip() for c in clients.split(',') if c.strip()]
        if clients
        else list(_DEFAULT_PLAYER_CLIENTS)
    )

    opts: dict = {
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 45,
        'retries': 5,
        'fragment_retries': 5,
        'extractor_retries': 3,
        'http_headers': {
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/131.0.0.0 Safari/537.36'
            ),
            'Accept-Language': 'en-US,en;q=0.9',
        },
        'extractor_args': {
            'youtube': {
                'player_client': player_clients,
            },
        },
    }

    cookiefile = _cookies_file()
    if cookiefile:
        opts['cookiefile'] = cookiefile

    opts.update(extra)
    return opts


def friendly_ytdlp_error(exc: BaseException | str) -> str:
    """İstifadəçiyə göstərilən qısa Azərbaycan mesajı."""
    text = str(exc or '')
    low = text.lower()
    if (
        'sign in to confirm' in low
        or 'not a bot' in low
        or 'cookies-from-browser' in low
        or 'confirm you' in low
    ):
        return (
            'YouTube bot yoxlaması səsi blokladı. '
            'Admin paneldən dərsə «Səs hazırla» basın və ya Render-ə YouTube cookies əlavə edin.'
        )
    if 'private video' in low or 'login required' in low:
        return 'Video gizli və ya giriş tələb edir.'
    if 'video unavailable' in low:
        return 'Video tapılmadı və ya silinib.'
    # Çox uzun yt-dlp stack-i kəs
    cleaned = re.sub(r'\s+', ' ', text).strip()
    if len(cleaned) > 220:
        cleaned = cleaned[:220] + '…'
    return cleaned or 'YouTube səsi oxunmadı'
