"""yt-dlp ümumi seçimlər — YouTube bot yoxlaması üçün client fallback + cookies."""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

# ios/android PO token tələb etmir — 2026.x-də ən stabil seçim
_DEFAULT_PLAYER_CLIENTS = ['ios', 'android', 'tv_embedded', 'mweb']

_YT_HOSTS = (
    'youtube.com',
    'google.com',
    'googlevideo.com',
    'youtu.be',
    'ggpht.com',
    'ytimg.com',
)


def _media_root() -> Path:
    try:
        from django.conf import settings as dj_settings

        return Path(dj_settings.MEDIA_ROOT)
    except Exception:
        return Path(tempfile.gettempdir()) / 'sirac_ytdlp'


def _is_youtube_cookie_line(line: str) -> bool:
    if not line.strip() or line.startswith('#'):
        return True  # header saxla
    domain = line.split('\t', 1)[0].lower().lstrip('.')
    return any(h in domain for h in _YT_HOSTS)


def _writable_cookie_copy(src: Path) -> str:
    """
    Render Secret Files read-only-dur; yt-dlp çıxışda cookie yazmağa çalışır → OSError 30.
    Writable nüsxə + yalnız YouTube/Google sətirləri.
    """
    dest_dir = _media_root() / 'audio'
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / 'ytdlp_cookies.txt'

    try:
        raw = src.read_text(encoding='utf-8', errors='ignore')
    except OSError as exc:
        logger.warning('cookies oxunmadı %s: %s', src, exc)
        return str(src)

    filtered = [line for line in raw.splitlines() if _is_youtube_cookie_line(line)]
    useful = sum(1 for L in filtered if L.strip() and not L.startswith('#'))

    if useful < 3:
        shutil.copyfile(src, dest)
        logger.info('cookies writable copy (full) → %s', dest)
    else:
        text = '\n'.join(filtered) + '\n'
        if not dest.exists() or dest.read_text(encoding='utf-8', errors='ignore') != text:
            dest.write_text(text, encoding='utf-8')
        logger.info('cookies writable copy (%s youtube/google sətir) → %s', useful, dest)
    return str(dest)


def _cookies_file() -> str | None:
    """
    Render / lokal:
      YTDLP_COOKIES_FILE=/path/to/cookies.txt
      və ya YTDLP_COOKIES=<Netscape cookies.txt məzmunu>
    """
    path = os.environ.get('YTDLP_COOKIES_FILE', '').strip()
    media_root = _media_root()
    try:
        from django.conf import settings as dj_settings

        if not path:
            path = (getattr(dj_settings, 'YTDLP_COOKIES_FILE', None) or '').strip()
    except Exception:
        pass

    if path and Path(path).is_file():
        src = Path(path)
        # /etc/secrets və digər read-only yollar → writable nüsxə
        try:
            with open(src, 'a', encoding='utf-8'):
                pass
            # Yazıla bilir — yenə də filter üçün nüsxə götür
            return _writable_cookie_copy(src)
        except OSError:
            return _writable_cookie_copy(src)

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
        # format yoxlamasını söndür — "Requested format not available" bypass
        'check_formats': False,
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
                # web client-i PO token olmadan deaktiv et
                'player_skip': ['webpage', 'configs'],
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
    if 'page needs to be reloaded' in low:
        return (
            'YouTube müvəqqəti cavab vermədi (page reload). '
            'Bir az sonra «Səs hazırla» ilə yenidən cəhd edin.'
        )
    if 'requested format is not available' in low:
        return 'YouTube bu video üçün səs formatı vermədi. Yenidən cəhd edin.'
    if 'private video' in low or 'login required' in low:
        return 'Video gizli və ya giriş tələb edir.'
    if 'video unavailable' in low:
        return 'Video tapılmadı və ya silinib.'
    # Çox uzun yt-dlp stack-i kəs
    cleaned = re.sub(r'\s+', ' ', text).strip()
    if len(cleaned) > 220:
        cleaned = cleaned[:220] + '…'
    return cleaned or 'YouTube səsi oxunmadı'
