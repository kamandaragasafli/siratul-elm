"""Playlist videolarını dərs kimi sync + səs faylı çıxarma."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from django.conf import settings
from django.core.files import File

from .ytdlp_opts import (
    cookies_file_path,
    friendly_ytdlp_error,
    is_blocking_ytdlp_error,
    ytdlp_base_opts,
)

logger = logging.getLogger(__name__)


def sync_series_lessons(series) -> dict:
    """Playlist URL-dən videoları VideoLesson kimi əlavə edir."""
    from .models import VideoLesson

    url = (series.playlist_url or '').strip()
    if not url:
        return {'created': 0, 'updated': 0, 'total': 0, 'error': 'Playlist linki yoxdur'}

    try:
        import yt_dlp
    except ImportError:
        return {'created': 0, 'updated': 0, 'total': 0, 'error': 'yt-dlp yoxdur'}

    opts = ytdlp_base_opts(
        use_cookies=False,
        extract_flat='in_playlist',
        skip_download=True,
        ignoreerrors=True,
        socket_timeout=30,
    )
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        logger.exception('sync_series_lessons failed')
        return {
            'created': 0,
            'updated': 0,
            'total': 0,
            'error': friendly_ytdlp_error(exc),
        }

    if not info:
        return {'created': 0, 'updated': 0, 'total': 0, 'error': 'Playlist oxunmadi'}

    entries = [e for e in (info.get('entries') or []) if e]
    created = 0
    updated = 0

    for i, entry in enumerate(entries):
        vid = (entry.get('id') or '').strip()
        title = (entry.get('title') or '').strip() or f'Ders {i + 1}'
        # Playlist entry olmasin
        if vid.startswith('PL') and len(vid) > 15:
            continue
        if not vid or not re.fullmatch(r'[\w-]{11}', vid):
            # url-den cixart
            u = str(entry.get('url') or entry.get('webpage_url') or '')
            m = re.search(r'(?:v=|/shorts/|youtu\.be/)([\w-]{11})', u)
            if not m:
                continue
            vid = m.group(1)

        video_url = f'https://www.youtube.com/watch?v={vid}'
        existing = VideoLesson.objects.filter(series=series, youtube_id=vid).first()
        if existing:
            changed = False
            if existing.title != title:
                existing.title = title
                changed = True
            if existing.order != i:
                existing.order = i
                changed = True
            if changed:
                VideoLesson.objects.filter(pk=existing.pk).update(title=title, order=i)
                updated += 1
        else:
            VideoLesson.objects.create(
                series=series,
                title=title,
                url=video_url,
                youtube_id=vid,
                order=i,
                is_published=True,
            )
            created += 1

    return {
        'created': created,
        'updated': updated,
        'total': len(entries),
        'error': None,
    }


def _pick_filesize(info: dict | None) -> int | None:
    if not info:
        return None
    size = info.get('filesize') or info.get('filesize_approx')
    if size:
        try:
            return int(size)
        except (TypeError, ValueError):
            pass
    for f in info.get('formats') or []:
        if (f.get('acodec') or 'none') == 'none':
            continue
        size = f.get('filesize') or f.get('filesize_approx')
        if size:
            try:
                return int(size)
            except (TypeError, ValueError):
                continue
    return None


_STREAM_CACHE: dict[str, tuple[float, str, int | None, int | None]] = {}
_STREAM_CACHE_TTL = 8 * 60  # saniyə


def resolve_stream_url(
    youtube_url: str,
) -> tuple[str | None, int | None, int | None, str | None]:
    """Returns: stream_url, duration_sec, size_bytes, error"""
    import time

    cache_key = (youtube_url or '').strip()
    now = time.time()
    cached = _STREAM_CACHE.get(cache_key)
    if cached and now - cached[0] < _STREAM_CACHE_TTL:
        return cached[1], cached[2], cached[3], None

    try:
        import yt_dlp
    except ImportError:
        return None, None, None, 'yt-dlp yoxdur'

    # Cookies bəzən pozur (page reload / no formats) — əvvəl cookies-siz
    attempts: list[tuple[bool, list[str]]] = [
        (False, ['android']),
        (False, ['ios']),
        (True, ['web_embedded', 'android']),
        (True, ['android', 'ios']),
        (False, ['tv_embedded']),
    ]
    last_err: str | None = None
    info = None
    for use_cookies, clients in attempts:
        opts = ytdlp_base_opts(
            use_cookies=use_cookies,
            player_clients=clients,
            format='bestaudio/best',
            skip_download=True,
            socket_timeout=20,
            retries=1,
        )
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
            if info and (info.get('url') or info.get('formats')):
                break
            info = None
        except Exception as exc:
            last_err = friendly_ytdlp_error(exc)
            logger.warning(
                'resolve_stream_url fail cookies=%s clients=%s: %s',
                use_cookies,
                clients,
                last_err,
            )
            info = None
    if not info:
        return None, None, None, last_err or 'Audio tapilmadi'

    stream = info.get('url')
    duration = info.get('duration')
    size_bytes = _pick_filesize(info)
    if not stream:
        for f in info.get('formats') or []:
            if f.get('url') and (f.get('acodec') or 'none') != 'none':
                stream = f['url']
                if not size_bytes:
                    size_bytes = f.get('filesize') or f.get('filesize_approx')
                    if size_bytes:
                        try:
                            size_bytes = int(size_bytes)
                        except (TypeError, ValueError):
                            size_bytes = None
                break
    if stream:
        _STREAM_CACHE[cache_key] = (
            now,
            stream,
            int(duration) if duration else None,
            size_bytes,
        )
    return stream, int(duration) if duration else None, size_bytes, None


def lesson_audio_size_bytes(lesson) -> int | None:
    if lesson.audio_file and lesson.audio_file.name:
        try:
            return int(lesson.audio_file.size)
        except Exception:
            try:
                path = Path(lesson.audio_file.path)
                if path.exists():
                    return path.stat().st_size
            except Exception:
                return None
    return None


def lesson_has_stored_audio(lesson) -> bool:
    """DB-də audio_file adı varsa və (mümkünsə) lokal fayl mövcuddursa."""
    if not lesson.audio_file or not lesson.audio_file.name:
        return False
    try:
        path = Path(lesson.audio_file.path)
        return path.exists() and path.stat().st_size > 0
    except (NotImplementedError, ValueError):
        # S3 / R2 / Spaces — lokal path yoxdur; storage adı kifayətdir
        return True
    except OSError:
        return False


def lesson_remote_audio_url(lesson) -> str | None:
    """ixlasla / birbaşa MP3 linki."""
    remote = (getattr(lesson, 'remote_audio_url', None) or '').strip()
    if remote.startswith(('http://', 'https://')):
        return remote
    u = (lesson.url or '').strip()
    if not u.startswith(('http://', 'https://')):
        return None
    low = u.lower()
    if low.endswith('.mp3') or 'backblazeb2.com' in low or '/file/ixlasla/' in low:
        return u
    return None


def lesson_stored_audio_url(lesson, request=None) -> str | None:
    """
    Saxlanmış səs faylının URL-i (storage) və ya uzaq MP3.
    S3/R2 artıq absolute URL verir; lokalda request ilə absolute edilir.
    """
    if lesson_has_stored_audio(lesson):
        try:
            url = lesson.audio_file.url
        except Exception:
            url = None
        if url:
            if url.startswith(('http://', 'https://')):
                return url
            if request is not None:
                return request.build_absolute_uri(url)
            return url
    return lesson_remote_audio_url(lesson)


def ensure_audio_file(
    lesson, *, force: bool = False
) -> tuple[bool, str | None, bool]:
    """
    Dərsi səs faylı kimi media-ya endirir (telefona yükləmə / sabit stream).
    Returns: (ok, error, is_blocking_error)
    is_blocking_error — bot yoxlaması / player cavabı kimi sistematik xəta.
    """
    if not force and lesson.audio_file and lesson.audio_file.name:
        try:
            path = Path(lesson.audio_file.path)
            if path.exists() and path.stat().st_size > 0:
                return True, None, False
            # Lokal disk ephemeral — fayl itib, yenidən endir
        except (NotImplementedError, ValueError):
            # Remote storage — artıq var
            return True, None, False

    source = (lesson.url or '').strip()
    if not source and lesson.youtube_id:
        source = f'https://www.youtube.com/watch?v={lesson.youtube_id}'
    if not source:
        return False, 'Video linki yoxdur', False

    try:
        import yt_dlp
    except ImportError:
        return False, 'yt-dlp yoxdur', False

    import shutil

    out_dir = Path(settings.MEDIA_ROOT) / 'audio' / 'cache'
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = lesson.youtube_id or f'lesson-{lesson.pk}'
    outtmpl = str(out_dir / f'{stem}.%(ext)s')

    # Cookies ilə web əvvəl; cookies-siz android/ios
    has_cookies = bool(cookies_file_path())
    client_attempts: list[tuple[bool, list[str]]] = (
        [
            (True, ['web', 'web_embedded']),
            (True, ['mweb', 'web_embedded']),
            (True, ['android']),
            (False, ['android']),
            (False, ['ios']),
        ]
        if has_cookies
        else [
            (False, ['android']),
            (False, ['ios']),
            (False, ['tv_embedded']),
        ]
    )
    info = None
    last_err: str | None = None
    for use_cookies, clients in client_attempts:
        opts: dict = ytdlp_base_opts(
            use_cookies=use_cookies,
            player_clients=clients,
            format='bestaudio/best',
            outtmpl=outtmpl,
            socket_timeout=90,
            retries=3,
        )
        if shutil.which('ffmpeg'):
            # Yalnız audio axını — /best (video) fallback olmasın
            opts['format'] = 'bestaudio/bestaudio*'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '128',
            }]
        else:
            opts['format'] = 'bestaudio[ext=m4a]/bestaudio[ext=webm]/bestaudio'
            opts['prefer_ffmpeg'] = False
            # Video konteynerə düşməsin
            opts['format_sort'] = ['aext:m4a', 'aext:webm', 'acodec', 'size']
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(source, download=True)
            if info:
                break
        except Exception as exc:
            last_err = friendly_ytdlp_error(exc)
            info = None
            logger.warning(
                'ensure_audio_file fail lesson=%s cookies=%s clients=%s: %s',
                lesson.pk,
                use_cookies,
                clients,
                last_err,
            )
    if not info:
        err = last_err or 'Ses endirilmedi'
        logger.error('ensure_audio_file failed lesson=%s: %s', lesson.pk, err)
        return False, err, is_blocking_ytdlp_error(err)

    # Tapilan fayl (mp3 postprocessor və ya birbaşa m4a/webm)
    ext = (info or {}).get('ext') or 'mp3'
    candidate = out_dir / f'{stem}.{ext}'
    if not candidate.exists():
        # yt-dlp bəzən başqa uzantı yazır
        matches = list(out_dir.glob(f'{stem}.*'))
        if not matches:
            return False, 'Ses fayli yaradilmadi', False
        candidate = matches[0]

    duration = (info or {}).get('duration')
    with candidate.open('rb') as fh:
        lesson.audio_file.save(candidate.name, File(fh), save=False)
    if duration:
        lesson.duration_seconds = int(duration)
    lesson.save(update_fields=['audio_file', 'duration_seconds'])
    return True, None, False
