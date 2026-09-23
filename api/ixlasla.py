"""ixlasla.com API — hazır MP3 dərsləri sync."""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote, urlencode

import requests
from django.db import transaction
from django.utils.text import slugify

logger = logging.getLogger(__name__)

API_BASE = 'https://ixlasla.com'
CHANNEL_NAME = 'ixlasla.com'
CHANNEL_URL = 'https://ixlasla.com/'
TEACHER_URL_PREFIX = 'https://ixlasla.com/?teacher='
REQUEST_TIMEOUT = 45
PAGE_SIZE = 100

# ixlasla kateqoriya slug → bizim VideoSeries.category
_CATEGORY_MAP = {
    'aqide': 'aqida',
    'hedis': 'hadith',
    'hedis-elmi': 'hadith',
    'fiqh': 'fiqh',
    'tefsir': 'tafsir',
    'quran': 'tafsir',
    'siyer': 'seerah',
    'sira': 'seerah',
}


def _get_json(path: str, params: dict | None = None) -> Any:
    url = f'{API_BASE}{path}'
    if params:
        # boş dəyərləri at
        params = {k: v for k, v in params.items() if v is not None and v != ''}
        url = f'{url}?{urlencode(params, quote_via=quote)}'
    r = requests.get(
        url,
        timeout=REQUEST_TIMEOUT,
        headers={'Accept': 'application/json', 'User-Agent': 'SiracApp/1.0'},
    )
    r.raise_for_status()
    r.encoding = 'utf-8'
    return r.json()


def fetch_teachers() -> list[dict]:
    data = _get_json('/api/teachers')
    if isinstance(data, list):
        return data
    return data.get('items') or data.get('teachers') or []


def fetch_series_for_teacher(teacher: str) -> list[dict]:
    data = _get_json('/api/series', {'teacher': teacher})
    if isinstance(data, list):
        return data
    return data.get('items') or data.get('series') or []


def fetch_lessons_page(
    *,
    teacher: str,
    series: str,
    offset: int = 0,
    limit: int = PAGE_SIZE,
) -> tuple[list[dict], int]:
    data = _get_json(
        '/api/lessons',
        {
            'teacher': teacher,
            'series': series,
            'offset': offset,
            'limit': limit,
        },
    )
    if isinstance(data, list):
        return data, len(data)
    items = data.get('items') or []
    total = int(data.get('total') or len(items))
    return items, total


def _map_category(item: dict | None, series_meta: dict | None = None) -> str:
    from .lesson_categories import detect_series_category

    slugs: list[str] = []
    if item:
        slugs.extend(item.get('category_slugs') or [])
    raw = ''
    if series_meta:
        raw = str(series_meta.get('categories') or '')
    if item and not raw:
        raw = str(item.get('categories') or '')
    for s in slugs:
        key = str(s).strip().lower()
        if key in _CATEGORY_MAP:
            return _CATEGORY_MAP[key]
    for part in re.split(r'[|,/]', raw):
        key = slugify(part.strip(), allow_unicode=False) or part.strip().lower()
        # əl ilə bir neçə
        low = part.strip().lower()
        if 'əqidə' in low or 'aqide' in low or 'aqida' in low:
            return 'aqida'
        if 'hədis' in low or 'hedis' in low:
            return 'hadith'
        if 'fiqh' in low or 'fiqeh' in low:
            return 'fiqh'
        if 'təfsir' in low or 'tefsir' in low or 'quran' in low:
            return 'tafsir'
        if 'sirə' in low or 'sira' in low or 'siyer' in low:
            return 'seerah'
        if key in _CATEGORY_MAP:
            return _CATEGORY_MAP[key]

    # Başlıqdan təxmin
    title_bits = []
    if series_meta:
        title_bits.append(str(series_meta.get('series') or ''))
    if item:
        title_bits.append(str(item.get('series') or item.get('series_display') or ''))
        title_bits.append(str(item.get('title_display') or ''))
    detected = detect_series_category(' '.join(title_bits))
    return detected


def _series_title(teacher: str, series: str) -> str:
    """Kanal artıq müəllimdirsə — silsilə adında müəllim təkrarlanmasın."""
    return series


def _playlist_marker(teacher: str, series: str) -> str:
    """Unikal marker — playlist_url sahəsində saxlanır."""
    return f'ixlasla://{quote(teacher, safe="")}/{quote(series, safe="")}'


def _parse_marker(playlist_url: str) -> tuple[str, str] | None:
    raw = (playlist_url or '').strip()
    if not raw.startswith('ixlasla://'):
        return None
    rest = raw[len('ixlasla://') :]
    parts = rest.split('/', 1)
    if len(parts) != 2:
        return None
    from urllib.parse import unquote

    teacher = unquote(parts[0]).strip()
    series = unquote(parts[1]).strip()
    if not teacher or not series:
        return None
    return teacher, series


def teacher_channel_url(teacher: str) -> str:
    return f'{TEACHER_URL_PREFIX}{quote(teacher)}'


def ensure_teacher_channel(teacher: str, *, order: int = 0):
    """Hər müəllim üçün ayrı kanal."""
    from .models import VideoChannel

    name = teacher.strip()
    url = teacher_channel_url(name)
    channel, created = VideoChannel.objects.get_or_create(
        url=url,
        defaults={
            'name': name,
            'description': f'ixlasla.com — {name}',
            'order': order,
            'is_published': True,
        },
    )
    if not created:
        fields = []
        if channel.name != name:
            channel.name = name
            fields.append('name')
        if not channel.is_published:
            channel.is_published = True
            fields.append('is_published')
        if channel.order != order and order:
            channel.order = order
            fields.append('order')
        desc = f'ixlasla.com — {name}'
        if channel.description != desc:
            channel.description = desc
            fields.append('description')
        if fields:
            fields.append('updated_at')
            channel.save(update_fields=fields)
    return channel


def ensure_ixlasla_channel():
    """Köhnə ümumi kanal — artıq istifadə olunmur; uyğunluq üçün saxlanılır."""
    from .models import VideoChannel

    channel, _ = VideoChannel.objects.get_or_create(
        url=CHANNEL_URL,
        defaults={
            'name': CHANNEL_NAME,
            'description': 'ixlasla.com — birbaşa MP3 audio dərslər',
            'order': 999,
            'is_published': False,
        },
    )
    return channel


def split_existing_by_teacher(*, progress=None) -> dict:
    """
    Ümumi ixlasla.com kanalındakı silsilələri müəllim kanallarına ayırır.
    Silsilə adından «Müəllim — » prefiksini silir.
    """
    from .models import VideoChannel, VideoSeries

    def log(msg: str):
        logger.info(msg)
        if progress:
            progress(msg)

    stats = {
        'moved': 0,
        'channels': 0,
        'renamed': 0,
        'umbrella_unpublished': False,
    }

    # Bütün ixlasla:// marker-li silsilələr (hansı kanalda olursa olsun)
    qs = VideoSeries.objects.filter(playlist_url__startswith='ixlasla://').select_related(
        'channel'
    )
    teacher_order = 0
    seen_teachers: set[str] = set()

    for series_obj in qs.iterator():
        parsed = _parse_marker(series_obj.playlist_url)
        if not parsed:
            # title-dan cəhd: "Müəllim — Silsilə"
            title = series_obj.title or ''
            if ' — ' in title:
                teacher, series_name = title.split(' — ', 1)
            elif ' - ' in title:
                teacher, series_name = title.split(' - ', 1)
            else:
                log(f'skip (no teacher): {title}')
                continue
        else:
            teacher, series_name = parsed

        teacher = teacher.strip()
        series_name = series_name.strip()
        if teacher not in seen_teachers:
            seen_teachers.add(teacher)
            teacher_order += 1
        channel = ensure_teacher_channel(teacher, order=teacher_order)

        fields = []
        if series_obj.channel_id != channel.id:
            series_obj.channel = channel
            fields.append('channel')
            stats['moved'] += 1
        if series_obj.title != series_name:
            series_obj.title = series_name
            fields.append('title')
            stats['renamed'] += 1
        if fields:
            series_obj.save(update_fields=fields)

    stats['channels'] = len(seen_teachers)

    umbrella = VideoChannel.objects.filter(url=CHANNEL_URL).first()
    if umbrella:
        # Boşdursa sil, yoxsa gizlət
        if not umbrella.series.exists():
            umbrella.delete()
            stats['umbrella_unpublished'] = True
            log('Umumi ixlasla.com kanalı silindi')
        else:
            umbrella.is_published = False
            umbrella.order = 999
            umbrella.save(update_fields=['is_published', 'order', 'updated_at'])
            stats['umbrella_unpublished'] = True
            log('Umumi ixlasla.com kanalı gizlədildi')

    log(f'Ayirma: {stats["moved"]} silsilə, {stats["channels"]} müəllim kanalı')
    return stats


def sync_ixlasla(
    *,
    teacher_filter: str | None = None,
    series_filter: str | None = None,
    max_lessons: int | None = None,
    progress=None,
) -> dict:
    """
    Bütün (və ya filtr) müəllim/silsilə/dərsləri DB-yə yazır.
    progress: callable(str) — konsol mesajı.
    """
    from .models import VideoLesson, VideoSeries

    def log(msg: str):
        logger.info(msg)
        if progress:
            progress(msg)

    channel = None  # per-teacher below
    teachers = fetch_teachers()
    if teacher_filter:
        tf = teacher_filter.casefold()
        teachers = [t for t in teachers if tf in str(t.get('teacher') or '').casefold()]

    stats = {
        'teachers': 0,
        'series_created': 0,
        'series_updated': 0,
        'lessons_created': 0,
        'lessons_updated': 0,
        'skipped_no_url': 0,
        'errors': [],
    }
    lessons_budget = max_lessons

    for t_idx, t_row in enumerate(teachers):
        teacher = (t_row.get('teacher') or '').strip()
        if not teacher:
            continue
        stats['teachers'] += 1
        channel = ensure_teacher_channel(teacher, order=t_idx)
        try:
            series_list = fetch_series_for_teacher(teacher)
        except Exception as exc:
            msg = f'series fail [{teacher}]: {exc}'
            stats['errors'].append(msg)
            log(msg)
            continue

        if series_filter:
            sf = series_filter.casefold()
            series_list = [
                s for s in series_list if sf in str(s.get('series') or '').casefold()
            ]

        for s_row in series_list:
            if lessons_budget is not None and lessons_budget <= 0:
                log('max_lessons limitə çatdı')
                return stats

            series_name = (s_row.get('series') or '').strip()
            if not series_name:
                continue

            title = _series_title(teacher, series_name)
            marker = _playlist_marker(teacher, series_name)
            category = _map_category(None, s_row)

            series_obj = VideoSeries.objects.filter(playlist_url=marker).first()
            if not series_obj:
                series_obj = VideoSeries.objects.filter(
                    channel=channel, title=title
                ).first()

            if series_obj:
                changed = False
                if series_obj.channel_id != channel.id:
                    series_obj.channel = channel
                    changed = True
                if series_obj.title != title:
                    series_obj.title = title
                    changed = True
                if series_obj.playlist_url != marker:
                    series_obj.playlist_url = marker
                    changed = True
                if series_obj.category == 'general' and category != 'general':
                    series_obj.category = category
                    changed = True
                if not series_obj.is_published:
                    series_obj.is_published = True
                    changed = True
                if changed:
                    series_obj.save()
                    stats['series_updated'] += 1
            else:
                series_obj = VideoSeries.objects.create(
                    channel=channel,
                    title=title,
                    category=category,
                    description=f'{teacher} / {series_name}',
                    playlist_url=marker,
                    order=0,
                    is_published=True,
                )
                stats['series_created'] += 1

            offset = 0
            total = None
            log(f'→ {title}')
            while True:
                if lessons_budget is not None and lessons_budget <= 0:
                    break
                limit = PAGE_SIZE
                if lessons_budget is not None:
                    limit = min(limit, lessons_budget)
                try:
                    items, total = fetch_lessons_page(
                        teacher=teacher,
                        series=series_name,
                        offset=offset,
                        limit=limit,
                    )
                except Exception as exc:
                    msg = f'lessons fail [{title}] offset={offset}: {exc}'
                    stats['errors'].append(msg)
                    log(msg)
                    break

                if not items:
                    break

                with transaction.atomic():
                    for item in items:
                        lid = item.get('id')
                        stream = (item.get('stream_url') or '').strip()
                        if not stream:
                            stats['skipped_no_url'] += 1
                            continue
                        lesson_title = (
                            (item.get('title_display') or item.get('lesson_title_az') or '')
                            .strip()
                            or f'Dərs {item.get("lesson_number") or lid}'
                        )
                        order = int(item.get('lesson_number') or 0) or 0
                        duration = item.get('duration_seconds') or None
                        try:
                            duration = int(duration) if duration else None
                            if duration == 0:
                                duration = None
                        except (TypeError, ValueError):
                            duration = None

                        existing = None
                        if lid is not None:
                            existing = VideoLesson.objects.filter(ixlasla_id=lid).first()
                        if not existing:
                            existing = VideoLesson.objects.filter(
                                series=series_obj, remote_audio_url=stream
                            ).first()

                        if existing:
                            fields = []
                            if existing.series_id != series_obj.id:
                                existing.series = series_obj
                                fields.append('series')
                            if existing.title != lesson_title:
                                existing.title = lesson_title
                                fields.append('title')
                            if existing.remote_audio_url != stream:
                                existing.remote_audio_url = stream
                                fields.append('remote_audio_url')
                            if existing.url != stream:
                                existing.url = stream
                                fields.append('url')
                            if lid and existing.ixlasla_id != lid:
                                existing.ixlasla_id = lid
                                fields.append('ixlasla_id')
                            if order and existing.order != order:
                                existing.order = order
                                fields.append('order')
                            if duration and existing.duration_seconds != duration:
                                existing.duration_seconds = duration
                                fields.append('duration_seconds')
                            if not existing.is_published:
                                existing.is_published = True
                                fields.append('is_published')
                            if fields:
                                existing.save(update_fields=fields)
                                stats['lessons_updated'] += 1
                        else:
                            VideoLesson.objects.create(
                                series=series_obj,
                                title=lesson_title,
                                url=stream,
                                remote_audio_url=stream,
                                ixlasla_id=lid,
                                youtube_id='',
                                duration_seconds=duration,
                                order=order,
                                is_published=True,
                            )
                            stats['lessons_created'] += 1

                        if lessons_budget is not None:
                            lessons_budget -= 1

                offset += len(items)
                if total is not None and offset >= total:
                    break
                if len(items) < limit:
                    break

    log(
        f'Hazır: teachers={stats["teachers"]} '
        f'series +{stats["series_created"]}/~{stats["series_updated"]} '
        f'lessons +{stats["lessons_created"]}/~{stats["lessons_updated"]}'
    )
    return stats
