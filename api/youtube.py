"""YouTube: basliq ve kanal playlistlerini cekmek."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape

logger = logging.getLogger(__name__)

_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
)


def fetch_youtube_title(url: str) -> str | None:
    url = (url or '').strip()
    if not url or not url.startswith(('http://', 'https://')):
        return None

    title = _from_oembed(url)
    if title:
        return title

    return _from_html(url)


def normalize_playlists_url(url: str) -> str:
    """Kanal linkini /playlists sehifesine cevirir."""
    url = (url or '').strip()
    # Kopiya zamanı görünməyən simvollar / trailing slash
    url = url.replace('\u200b', '').replace('\xa0', ' ').strip().rstrip('/')
    if not url:
        return url

    # Tek playlist linkini oldugu kimi saxla
    if 'list=' in url and '/playlist' in url:
        return url.split('&')[0]

    if '/playlists' in url:
        return url.split('?')[0]

    # @handle / channel / c/
    if re.search(r'youtube\.com/@[^/\s]+$', url, re.I):
        return url + '/playlists'
    if re.search(r'youtube\.com/channel/[^/\s]+$', url, re.I):
        return url + '/playlists'
    if re.search(r'youtube\.com/c/[^/\s]+$', url, re.I):
        return url + '/playlists'
    # /videos ve ya kanal ana sehifesi
    m = re.match(
        r'(https?://(?:www\.)?youtube\.com/@[^/\s]+)',
        url,
        re.I,
    )
    if m:
        return m.group(1) + '/playlists'
    m = re.match(
        r'(https?://(?:www\.)?youtube\.com/channel/[^/\s]+)',
        url,
        re.I,
    )
    if m:
        return m.group(1) + '/playlists'
    return url


def _ydl_extract(url: str) -> tuple[dict | None, str | None]:
    try:
        import yt_dlp
    except ImportError:
        import sys

        return (
            None,
            'yt-dlp bu Python-da yoxdur. '
            f'({sys.executable}) — .venv aktivləşdirib: pip install yt-dlp',
        )

    opts = {
        'extract_flat': 'in_playlist',
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'ignoreerrors': True,
        'socket_timeout': 30,
        'retries': 3,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info, None
    except Exception as exc:
        logger.exception('yt-dlp extract failed for %s', url)
        return None, f'YouTube oxunmadi: {exc}'


def fetch_channel_playlists(url: str) -> tuple[list[dict], str | None]:
    """
    Returns: (playlists, error)
    playlists: [{'id','title','url'}, ...]
    """
    raw = (url or '').strip()
    if not raw:
        return [], 'Kanal linki bosdur'

    url = normalize_playlists_url(raw)
    candidates = [url]
    # /playlists islemese @kanal ana URL-i de yoxla
    if url.endswith('/playlists'):
        candidates.append(url[: -len('/playlists')])

    last_error = None
    for candidate in candidates:
        info, err = _ydl_extract(candidate)
        if err:
            last_error = err
            continue
        if not info:
            last_error = 'YouTube cavab vermedi'
            continue

        # Tek playlist sehifesi: ozunu bir silsile kimi qaytar
        if 'list=' in candidate and '/playlists' not in candidate:
            pid = ''
            m = re.search(r'list=([A-Za-z0-9_-]+)', candidate)
            if m:
                pid = m.group(1)
            title = (info.get('title') or pid or 'Playlist').strip()
            if pid:
                return (
                    [
                        {
                            'id': pid,
                            'title': title,
                            'url': f'https://www.youtube.com/playlist?list={pid}',
                        }
                    ],
                    None,
                )

        results: list[dict] = []
        seen: set[str] = set()
        entries = info.get('entries')
        if entries is None:
            last_error = 'Playlist siyahisi bos geldi'
            continue

        for entry in entries:
            if not entry:
                continue
            parsed = _entry_to_playlist(entry)
            if not parsed:
                continue
            if parsed['id'] in seen:
                continue
            seen.add(parsed['id'])
            results.append(parsed)

        if results:
            return results, None

        last_error = (
            f'"{candidate}" ucun playlist tapilmadi '
            f'(YouTube {len(list(entries) if entries else [])} element verdi, '
            f'amma playlist kimi taninmadi)'
        )

    return [], last_error or 'Playlist tapilmadi — linki yoxlayin'


def _entry_to_playlist(entry: dict) -> dict | None:
    pid = (entry.get('id') or '').strip()
    title = (entry.get('title') or '').strip()
    url = str(entry.get('url') or entry.get('webpage_url') or '')

    m = re.search(r'list=([A-Za-z0-9_-]+)', url)
    if m:
        pid = m.group(1)
    elif re.search(r'list=([A-Za-z0-9_-]+)', pid):
        pid = re.search(r'list=([A-Za-z0-9_-]+)', pid).group(1)

    # Video ID-leri (11 simvol) playlist deyil — kec
    if not pid:
        return None
    if re.fullmatch(r'[\w-]{11}', pid) and not pid.startswith('PL'):
        return None
    # Playlist ID: PL... ve ya uzun ID
    if not (
        pid.startswith('PL')
        or pid.startswith('UU')
        or pid.startswith('OL')
        or len(pid) >= 16
    ):
        # Bezi playlist id-ler PL ile bashlamir amma url-de list= var idi
        if 'list=' not in url and 'playlist' not in url.lower():
            return None

    return {
        'id': pid,
        'title': title or pid,
        'url': f'https://www.youtube.com/playlist?list={pid}',
    }


def sync_channel_playlists(channel) -> dict:
    """
    Kanaldaki URL-den playlistleri VideoSeries kimi yaradir/yenileyir.
    """
    from .models import VideoSeries

    url = (channel.url or '').strip()
    if not url:
        return {'created': 0, 'updated': 0, 'total': 0, 'error': 'Kanal linki yoxdur'}

    playlists, err = fetch_channel_playlists(url)
    if err and not playlists:
        return {'created': 0, 'updated': 0, 'total': 0, 'error': err}

    created = 0
    updated = 0
    for i, pl in enumerate(playlists):
        existing = (
            VideoSeries.objects.filter(channel=channel, playlist_url__icontains=pl['id']).first()
            or VideoSeries.objects.filter(channel=channel, title=pl['title']).first()
        )
        if existing:
            changed = False
            if existing.title != pl['title']:
                existing.title = pl['title']
                changed = True
            if existing.playlist_url != pl['url']:
                existing.playlist_url = pl['url']
                changed = True
            if changed:
                # save() YouTube title yeniden cekmesin deye update_fields
                VideoSeries.objects.filter(pk=existing.pk).update(
                    title=existing.title,
                    playlist_url=existing.playlist_url,
                )
                updated += 1
        else:
            # create — title artiq var, save() yeniden fetch etmesin
            obj = VideoSeries(
                channel=channel,
                title=pl['title'],
                playlist_url=pl['url'],
                order=i,
                is_published=True,
            )
            # title dolu oldugu ucun save() fetch etmeyecek
            obj.save()
            created += 1

    return {
        'created': created,
        'updated': updated,
        'total': len(playlists),
        'error': None,
    }


def _from_oembed(url: str) -> str | None:
    endpoint = (
        'https://www.youtube.com/oembed?format=json&url='
        + urllib.parse.quote(url, safe='')
    )
    try:
        req = urllib.request.Request(endpoint, headers={'User-Agent': _UA})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode('utf-8', errors='ignore'))
        title = (data.get('title') or '').strip()
        return title or None
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, ValueError):
        return None


def _from_html(url: str) -> str | None:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': _UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode('utf-8', errors='ignore')
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None

    patterns = [
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:title["\']',
        r'<meta[^>]+name=["\']title["\'][^>]+content=["\']([^"\']+)["\']',
        r'<title[^>]*>([^<]+)</title>',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if not m:
            continue
        title = unescape(m.group(1)).strip()
        title = re.sub(r'\s*[-–|]\s*YouTube\s*$', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s+', ' ', title).strip()
        if title:
            return title
    return None
