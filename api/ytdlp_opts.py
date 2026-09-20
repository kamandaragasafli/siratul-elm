"""yt-dlp ümumi seçimlər — YouTube bot yoxlaması üçün client fallback + cookies."""

from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

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
        return True
    domain = line.split('\t', 1)[0].lower().lstrip('.')
    return any(h in domain for h in _YT_HOSTS)


def _writable_cookie_copy(src: Path) -> str:
    """Render Secret Files read-only — writable nüsxə + yalnız YT/Google."""
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
        logger.info('cookies writable copy (%s sətir) → %s', useful, dest)
    return str(dest)


def cookies_file_path() -> str | None:
    """Mövcud cookies faylının writable yolu (yoxdursa None)."""
    path = os.environ.get('YTDLP_COOKIES_FILE', '').strip()
    media_root = _media_root()
    try:
        from django.conf import settings as dj_settings

        if not path:
            path = (getattr(dj_settings, 'YTDLP_COOKIES_FILE', None) or '').strip()
    except Exception:
        pass

    if path and Path(path).is_file():
        return _writable_cookie_copy(Path(path))

    raw = (os.environ.get('YTDLP_COOKIES') or '').strip()
    if not raw:
        return None

    cache = media_root / 'audio' / 'ytdlp_cookies.txt'
    cache.parent.mkdir(parents=True, exist_ok=True)
    text = raw.replace('\\n', '\n')
    if not cache.exists() or cache.read_text(encoding='utf-8', errors='ignore') != text:
        cache.write_text(text, encoding='utf-8')
    return str(cache)


def ytdlp_base_opts(*, use_cookies: bool = True, player_clients: list[str] | None = None, **extra) -> dict:
    """Bütün YouTube extract/download üçün baza opts."""
    if player_clients is None:
        env = os.environ.get('YTDLP_PLAYER_CLIENTS', '').strip()
        player_clients = (
            [c.strip() for c in env.split(',') if c.strip()]
            if env
            else ['android', 'ios']
        )

    opts: dict = {
        'quiet': True,
        'no_warnings': True,
        'socket_timeout': 30,
        'retries': 3,
        'fragment_retries': 3,
        'extractor_retries': 2,
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
            },
        },
    }

    if use_cookies:
        cookiefile = cookies_file_path()
        if cookiefile:
            opts['cookiefile'] = cookiefile
            logger.info('yt-dlp cookies: %s', cookiefile)
        else:
            logger.warning(
                'yt-dlp: use_cookies=True amma YTDLP_COOKIES_FILE / YTDLP_COOKIES yoxdur'
            )

    opts.update(extra)
    return opts


# Bot yoxlaması / player cavabı — prefetch-i dayandırmağa dəyər xətalar
_BLOCKING_ERROR_MARKERS = (
    'bot yoxlaması',
    'player cavab vermədi',
    'müvəqqəti cavab vermədi',
    'sign in to confirm',
    'not a bot',
    'cookies-from-browser',
    'confirm you',
    'page needs to be reloaded',
    'failed to extract any player response',
    'datacenter ip',
)


def is_blocking_ytdlp_error(exc: BaseException | str | None) -> bool:
    """Bot yoxlaması / player cavabı kimi sistematik blok xətasıdırsa True."""
    text = str(exc or '').lower()
    return any(m in text for m in _BLOCKING_ERROR_MARKERS)


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
            'Admin paneldən dərsə «Səs hazırla» basın.'
        )
    if 'page needs to be reloaded' in low:
        return (
            'YouTube müvəqqəti cavab vermədi. '
            'Admin paneldən «Səs hazırla» basın.'
        )
    if 'failed to extract any player response' in low:
        return (
            'YouTube player cavab vermədi (datacenter IP blok). '
            'Admin paneldən «Səs hazırla» basın və ya cookies yeniləyin.'
        )
    if 'error code: 152' in low or 'watch video on youtube' in low:
        return (
            'Bu video yalnız YouTube tətbiqində açılır (kod 152). '
            'Admin paneldən «Səs hazırla» ilə serverə yükləyin.'
        )
    if 'requested format is not available' in low:
        return 'YouTube səs formatı vermədi. Yenidən cəhd edin.'
    if 'private video' in low or 'login required' in low:
        return 'Video gizli və ya giriş tələb edir.'
    if 'video unavailable' in low:
        return 'Video tapılmadı və ya silinib.'
    cleaned = re.sub(r'\s+', ' ', text).strip()
    if len(cleaned) > 220:
        cleaned = cleaned[:220] + '…'
    return cleaned or 'YouTube səsi oxunmadı'
