"""Playlist videolarını dərs kimi sync + səs faylı çıxarma."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from django.conf import settings
from django.core.files import File

from .ytdlp_opts import friendly_ytdlp_error, ytdlp_base_opts

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

    # Əvvəl sürətli klientlər; uğursuz olsa baza fallback (mweb/tv/web + cookies)
    attempts: list[list[str]] = [
        ['android', 'ios'],
        ['android_creator', 'ios', 'mweb', 'tv'],
        ['android', 'ios', 'mweb', 'tv', 'web'],
    ]
    last_err: str | None = None
    info = None
    for clients in attempts:
        opts = ytdlp_base_opts(
            format='bestaudio[ext=m4a]/bestaudio/best',
            skip_download=True,
            socket_timeout=25,
            retries=2,
        )
        opts['extractor_args'] = {'youtube': {'player_client': clients}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(youtube_url, download=False)
            if info:
                break
        except Exception as exc:
            last_err = friendly_ytdlp_error(exc)
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


def ensure_audio_file(lesson) -> tuple[bool, str | None]:
    """
    Dərsi səs faylı kimi media-ya endirir (telefona yükləmə / sabit stream).
    Returns: (ok, error)
    """
    if lesson.audio_file and lesson.audio_file.name:
        path = Path(lesson.audio_file.path)
        if path.exists() and path.stat().st_size > 0:
            return True, None

    source = (lesson.url or '').strip()
    if not source and lesson.youtube_id:
        source = f'https://www.youtube.com/watch?v={lesson.youtube_id}'
    if not source:
        return False, 'Video linki yoxdur'

    try:
        import yt_dlp
    except ImportError:
        return False, 'yt-dlp yoxdur'

    import shutil

    out_dir = Path(settings.MEDIA_ROOT) / 'audio' / 'cache'
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = lesson.youtube_id or f'lesson-{lesson.pk}'
    outtmpl = str(out_dir / f'{stem}.%(ext)s')

    opts: dict = ytdlp_base_opts(
        format='bestaudio/best',
        outtmpl=outtmpl,
        socket_timeout=120,
        retries=5,
    )
    if shutil.which('ffmpeg'):
        opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '128',
        }]
    else:
        opts['format'] = 'bestaudio[ext=m4a]/bestaudio/best'
        opts['prefer_ffmpeg'] = False
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(source, download=True)
    except Exception as exc:
        logger.exception('ensure_audio_file failed lesson=%s', lesson.pk)
        return False, friendly_ytdlp_error(exc)

    # Tapilan fayl (mp3 postprocessor və ya birbaşa m4a/webm)
    ext = (info or {}).get('ext') or 'mp3'
    candidate = out_dir / f'{stem}.{ext}'
    if not candidate.exists():
        # yt-dlp bəzən başqa uzantı yazır
        matches = list(out_dir.glob(f'{stem}.*'))
        if not matches:
            return False, 'Ses fayli yaradilmadi'
        candidate = matches[0]

    duration = (info or {}).get('duration')
    with candidate.open('rb') as fh:
        lesson.audio_file.save(candidate.name, File(fh), save=False)
    if duration:
        lesson.duration_seconds = int(duration)
    lesson.save(update_fields=['audio_file', 'duration_seconds'])
    return True, None
