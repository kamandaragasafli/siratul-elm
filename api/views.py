from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count as models_Count
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from rest_framework import status, viewsets
from rest_framework.decorators import api_view, action, parser_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
import os

from .audio import (
    ensure_audio_file,
    lesson_audio_size_bytes,
    lesson_has_stored_audio,
    lesson_remote_audio_url,
    lesson_stored_audio_url,
    resolve_stream_url,
    sync_series_lessons,
)
from .telegram_notify import format_qa_telegram_message, send_telegram_message
from .models import Book, SupportMessage, TelegramLiveLesson, LiveTeacherCode, QuranMealNote, VideoChannel, VideoLesson, VideoSeries
from .serializers import (
    BookListSerializer,
    BookSerializer,
    QuranQACreateSerializer,
    SupportMessageCreateSerializer,
    TelegramLiveLessonSerializer,
    VideoChannelDetailSerializer,
    VideoChannelSerializer,
    VideoLessonSerializer,
    VideoSeriesDetailSerializer,
)
from .youtube import fetch_youtube_title


@api_view(['GET'])
def lesson_sections(request):
    """Dərsləri mövzu bölmələrinə görə qruplaşdırır."""
    from .lesson_categories import LESSON_SECTIONS, SECTION_LABELS

    qs = (
        VideoSeries.objects.filter(
            is_published=True,
            channel__is_published=True,
        )
        .select_related('channel')
        .order_by('order', 'title')
    )

    grouped: dict[str, list] = {key: [] for key in LESSON_SECTIONS}
    for series in qs:
        cat = series.category if series.category in grouped else 'general'
        grouped[cat].append(
            {
                'id': series.id,
                'title': series.title,
                'category': cat,
                'channelId': series.channel_id,
                'channelName': series.channel.name,
                'lessonCount': series.lessons.filter(is_published=True).count(),
            }
        )

    sections = [
        {
            'id': key,
            'title': SECTION_LABELS[key],
            'seriesCount': len(grouped[key]),
            'series': grouped[key],
        }
        for key in LESSON_SECTIONS
        if grouped[key]
    ]
    return Response({'sections': sections, 'count': len(sections)})


@api_view(['GET', 'POST'])
def deploy_ixlasla_api(request):
    """
    Shell olmadan bir dəfəlik sync.
    Render env: DEPLOY_IXLASLA_SECRET=... sonra:
      https://elm-yolu.onrender.com/api/deploy-ixlasla/?key=SECRET
    Bitəndən sonra secret-i sil.
    """
    import threading

    from .ixlasla import sync_ixlasla
    from .models import VideoChannel, VideoLesson

    expected = (os.environ.get('DEPLOY_IXLASLA_SECRET') or '').strip()
    provided = (
        request.query_params.get('key')
        or request.data.get('key')
        or request.headers.get('X-Deploy-Key')
        or ''
    ).strip()
    if not expected or provided != expected:
        return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    def run():
        try:
            yt = VideoChannel.objects.filter(
                Q(url__icontains='youtube.com') | Q(url__icontains='youtu.be')
            )
            yt.delete()
            VideoLesson.objects.filter(
                Q(youtube_id__gt='')
                | Q(url__icontains='youtube.com')
                | Q(url__icontains='youtu.be')
            ).exclude(remote_audio_url__gt='').delete()
            sync_ixlasla()
        except Exception:
            import logging

            logging.getLogger(__name__).exception('deploy_ixlasla_api failed')

    threading.Thread(target=run, daemon=True).start()
    return Response(
        {
            'ok': True,
            'detail': 'ixlasla sync started in background (3–5 dəq). Sonra secret sil.',
        }
    )


@api_view(['GET'])
def quran_meal_notes(request):
    """Məal «Qısa məlumat» + haşiyə/hökm paketi (mobil üçün)."""
    qs = QuranMealNote.objects.filter(is_published=True)
    surahs: dict = {}
    ayahs: dict = {}
    latest = None
    for note in qs:
        entry = note.to_pack_entry()
        if not entry:
            continue
        if note.updated_at and (latest is None or note.updated_at > latest):
            latest = note.updated_at
        if note.scope == QuranMealNote.SCOPE_AYAH and note.ayah:
            ayahs[f'{note.surah}:{note.ayah}'] = entry
        else:
            surahs[str(note.surah)] = entry
    return Response(
        {
            'surahs': surahs,
            'ayahs': ayahs,
            'updated_at': latest.isoformat() if latest else None,
        }
    )


@api_view(['POST'])
def support_create(request):
    """Mobil tətbiqdən dəstək / yardım mesajı qəbul edir."""
    serializer = SupportMessageCreateSerializer(data=request.data)
    if not serializer.is_valid():
        # İlk xətanı sadə mesaj kimi qaytar
        first = next(iter(serializer.errors.values()), ['Yanlış məlumat'])
        detail = first[0] if isinstance(first, list) else str(first)
        return Response(
            {'ok': False, 'message': detail, 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    msg = serializer.save()
    return Response(
        {
            'ok': True,
            'id': msg.id,
            'message': 'Mesajınız qəbul olundu. Tezliklə cavab verəcəyik.',
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['POST'])
def quran_qa_create(request):
    """Qarilər bələdçisindən sual — DB-yə yazılır və Telegram qrupuna göndərilir."""
    serializer = QuranQACreateSerializer(data=request.data)
    if not serializer.is_valid():
        first = next(iter(serializer.errors.values()), ['Yanlış məlumat'])
        detail = first[0] if isinstance(first, list) else str(first)
        return Response(
            {'ok': False, 'message': detail, 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    data = serializer.validated_data
    name = data['name']
    contact = (data.get('contact') or '').strip()
    message = data['message']
    app_version = (data.get('appVersion') or '').strip()

    msg = SupportMessage.objects.create(
        name=name,
        contact=contact,
        category='question',
        message=f'[Qarilər] {message}',
        app_version=app_version,
    )

    telegram_text = format_qa_telegram_message(
        name=name,
        contact=contact,
        message=message,
        app_version=app_version,
    )
    sent = send_telegram_message(telegram_text)

    return Response(
        {
            'ok': True,
            'id': msg.id,
            'telegramSent': sent,
            'message': 'Sualınız qəbul olundu. Tezliklə cavab verəcəyik.',
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
def video_search(request):
    """Kanal + silsilə + dərs axtarışı (Az hərfləri və boş silsilələr nəzərə alınır)."""
    from .search_text import text_matches

    q = (request.GET.get('q') or '').strip()
    if len(q) < 1:
        return Response({'channels': [], 'series': [], 'lessons': [], 'query': q})

    # Uyğun boş silsilələrin dərslərini sinxron et (axtarışda tapılsın)
    empty_series = (
        VideoSeries.objects.filter(
            is_published=True,
            channel__is_published=True,
            playlist_url__gt='',
        )
        .annotate(_lc=models_Count('lessons'))
        .filter(_lc=0)
        .select_related('channel')[:40]
    )
    synced = 0
    for s in empty_series:
        if text_matches(s.title, q) or text_matches(s.channel.name, q):
            sync_series_lessons(s)
            synced += 1
            if synced >= 5:
                break

    channels_qs = list(
        VideoChannel.objects.filter(is_published=True).order_by('order', 'name')
    )
    series_qs = list(
        VideoSeries.objects.filter(
            is_published=True,
            channel__is_published=True,
        )
        .select_related('channel')
        .order_by('order', 'title')
    )
    lessons_qs = list(
        VideoLesson.objects.filter(
            is_published=True,
            series__is_published=True,
            series__channel__is_published=True,
        ).select_related('series', 'series__channel')
    )

    channels = [c for c in channels_qs if text_matches(c.name, q) or text_matches(c.description, q)][
        :30
    ]
    series = [s for s in series_qs if text_matches(s.title, q) or text_matches(s.channel.name, q)][
        :40
    ]
    lessons = [
        lesson
        for lesson in lessons_qs
        if text_matches(lesson.title, q)
        or text_matches(lesson.series.title, q)
        or text_matches(lesson.series.channel.name, q)
    ][:60]

    return Response(
        {
            'query': q,
            'channels': [
                {
                    'id': c.id,
                    'name': c.name,
                    'description': c.description,
                    'seriesCount': c.series.filter(is_published=True).count(),
                }
                for c in channels
            ],
            'series': [
                {
                    'id': s.id,
                    'title': s.title,
                    'channelId': s.channel_id,
                    'channelName': s.channel.name,
                    'category': s.category,
                    'lessonCount': s.lessons.filter(is_published=True).count(),
                }
                for s in series
            ],
            'lessons': [
                {
                    'id': lesson.id,
                    'title': lesson.title,
                    'seriesId': lesson.series_id,
                    'seriesTitle': lesson.series.title,
                    'channelId': lesson.series.channel_id,
                    'channelName': lesson.series.channel.name,
                    'order': lesson.order,
                }
                for lesson in lessons
            ],
        }
    )


@staff_member_required
@require_GET
def youtube_title_lookup(request):
    url = (request.GET.get('url') or '').strip()
    if not url:
        return JsonResponse({'ok': False, 'title': '', 'error': 'url required'}, status=400)
    title = fetch_youtube_title(url)
    if not title:
        return JsonResponse({'ok': False, 'title': '', 'error': 'not_found'})
    return JsonResponse({'ok': True, 'title': title})


class BookViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = 'public_id'
    lookup_url_kwarg = 'public_id'

    def get_queryset(self):
        return Book.objects.filter(is_published=True).prefetch_related('chapters')

    def get_serializer_class(self):
        if self.action == 'list':
            return BookListSerializer
        return BookSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response({'results': serializer.data, 'count': queryset.count()})

    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
        except Book.DoesNotExist:
            return Response({'detail': 'Kitab tapılmadı.'}, status=status.HTTP_404_NOT_FOUND)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class VideoChannelViewSet(viewsets.ReadOnlyModelViewSet):
    def get_queryset(self):
        return VideoChannel.objects.filter(is_published=True).prefetch_related('series__lessons')

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return VideoChannelDetailSerializer
        return VideoChannelSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response({'results': serializer.data, 'count': queryset.count()})


class VideoSeriesViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = VideoSeriesDetailSerializer

    def get_queryset(self):
        return VideoSeries.objects.filter(
            is_published=True,
            channel__is_published=True,
        ).prefetch_related('lessons')

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Dersler yoxdursa playlist-den avtomatik cek
        if not instance.lessons.exists() and instance.playlist_url:
            sync_series_lessons(instance)
            instance.refresh_from_db()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def sync_lessons(self, request, pk=None):
        instance = self.get_object()
        result = sync_series_lessons(instance)
        if result.get('error'):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


class VideoLessonViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = VideoLessonSerializer

    def get_queryset(self):
        return VideoLesson.objects.filter(
            is_published=True,
            series__is_published=True,
            series__channel__is_published=True,
        )

    @action(detail=True, methods=['get'])
    def play(self, request, pk=None):
        """Onlayn dinləmə — saxlanmış fayl / uzaq MP3 (proxy) / YouTube."""
        lesson = self.get_object()
        youtube_id = (lesson.youtube_id or '').strip()
        if not youtube_id and lesson.url:
            import re

            m = re.search(r'(?:v=|/shorts/|youtu\.be/)([\w-]{11})', lesson.url)
            if m:
                youtube_id = m.group(1)

        proxy_url = request.build_absolute_uri(
            f'/api/lessons/{lesson.pk}/proxy_stream/'
        )

        # Lokal / S3 fayl — birbaşa
        if lesson_has_stored_audio(lesson):
            stored_url = lesson_stored_audio_url(lesson, request)
            if stored_url:
                size = lesson_audio_size_bytes(lesson)
                return Response(
                    {
                        'id': lesson.id,
                        'title': lesson.title,
                        'mode': 'file',
                        'streamUrl': stored_url,
                        'downloadUrl': stored_url,
                        'durationSeconds': lesson.duration_seconds,
                        'sizeBytes': size,
                        'hasAudio': True,
                        'youtubeId': youtube_id or None,
                    }
                )

        # ixlasla MP3 — birbaşa CDN (Backblaze). Render free-də proxy bütün
        # dinləməni dyno-dan keçirərdi (timeout/kvota). Bildiriş metadata app-dədir.
        remote = lesson_remote_audio_url(lesson)
        if remote:
            use_proxy = (
                request.query_params.get('proxy') == '1'
                or os.environ.get('AUDIO_PROXY_REMOTE', '').lower()
                in ('1', 'true', 'yes')
            )
            return Response(
                {
                    'id': lesson.id,
                    'title': lesson.title,
                    'mode': 'file',
                    'streamUrl': proxy_url if use_proxy else remote,
                    'downloadUrl': remote,
                    'durationSeconds': lesson.duration_seconds,
                    'sizeBytes': None,
                    'hasAudio': True,
                    'youtubeId': youtube_id or None,
                }
            )

        # YouTube stream fallback
        stream, duration, size_bytes, err = resolve_stream_url(lesson.url)
        if err or not stream:
            return Response(
                {'detail': err or 'Ses axi tapilmadi'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        if duration and not lesson.duration_seconds:
            VideoLesson.objects.filter(pk=lesson.pk).update(duration_seconds=duration)
        return Response(
            {
                'id': lesson.id,
                'title': lesson.title,
                'mode': 'stream',
                'streamUrl': proxy_url,
                'downloadUrl': None,
                'durationSeconds': duration or lesson.duration_seconds,
                'sizeBytes': size_bytes,
                'hasAudio': False,
                'youtubeId': youtube_id or None,
            }
        )

    @action(detail=True, methods=['get'], url_path='proxy_stream')
    def proxy_stream(self, request, pk=None):
        """
        Səs axını server üzərindən — YouTube IP kilidi və ixlasla ID3
        (loqo/metadata) telefona düşməsin.
        """
        import re
        import requests as http_requests

        lesson = self.get_object()

        # Lokal / S3 fayl — redirect
        if lesson_has_stored_audio(lesson):
            stored = None
            try:
                stored = lesson.audio_file.url
            except Exception:
                stored = None
            if stored:
                if not stored.startswith(('http://', 'https://')):
                    stored = request.build_absolute_uri(stored)
                return HttpResponseRedirect(stored)

        remote = lesson_remote_audio_url(lesson)
        stream = remote
        strip_id3 = bool(remote)
        if not stream:
            stream, _duration, _size, err = resolve_stream_url(lesson.url)
            if err or not stream:
                return Response(
                    {'detail': err or 'Ses axi tapilmadi'},
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            strip_id3 = False

        upstream_headers = {
            'User-Agent': request.META.get(
                'HTTP_USER_AGENT',
                'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
            ),
            'Accept': '*/*',
        }
        range_header = request.META.get('HTTP_RANGE')
        range_starts_at_zero = True
        if range_header:
            upstream_headers['Range'] = range_header
            m = re.match(r'bytes=(\d+)-', range_header.strip())
            if m and int(m.group(1)) > 0:
                range_starts_at_zero = False
                strip_id3 = False

        try:
            upstream = http_requests.get(
                stream,
                stream=True,
                timeout=(15, 120),
                headers=upstream_headers,
            )
        except http_requests.RequestException as exc:
            return Response(
                {'detail': f'Səs oxunmadı: {exc}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        if upstream.status_code >= 400:
            upstream.close()
            return Response(
                {'detail': f'Səs mənbəsi xətası: {upstream.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        content_type = upstream.headers.get('Content-Type') or 'audio/mpeg'

        def generate():
            try:
                if not strip_id3 or not range_starts_at_zero:
                    for chunk in upstream.iter_content(chunk_size=64 * 1024):
                        if chunk:
                            yield chunk
                    return

                buf = b''
                it = upstream.iter_content(chunk_size=64 * 1024)
                while len(buf) < 10:
                    piece = next(it, b'')
                    if not piece:
                        break
                    buf += piece
                skip = 0
                if len(buf) >= 10 and buf.startswith(b'ID3'):
                    size = (
                        (buf[6] & 0x7F) << 21
                        | (buf[7] & 0x7F) << 14
                        | (buf[8] & 0x7F) << 7
                        | (buf[9] & 0x7F)
                    )
                    skip = 10 + size
                if skip:
                    if len(buf) > skip:
                        yield buf[skip:]
                    else:
                        need = skip - len(buf)
                        while need > 0:
                            piece = next(it, b'')
                            if not piece:
                                break
                            if len(piece) <= need:
                                need -= len(piece)
                            else:
                                yield piece[need:]
                                need = 0
                elif buf:
                    yield buf
                for chunk in it:
                    if chunk:
                        yield chunk
            finally:
                upstream.close()

        response = StreamingHttpResponse(
            generate(),
            status=200 if strip_id3 else upstream.status_code,
            content_type=content_type,
        )
        if not strip_id3:
            for header in ('Content-Length', 'Content-Range', 'Accept-Ranges'):
                value = upstream.headers.get(header)
                if value:
                    response[header] = value
        response['Accept-Ranges'] = 'bytes'
        response['Cache-Control'] = 'no-store'
        safe_title = ''.join(
            ch if ch.isalnum() or ch in ' -_' else '_'
            for ch in (lesson.title or 'ders')[:60]
        )
        response['Content-Disposition'] = f'inline; filename="Sirac - {safe_title}.mp3"'
        return response

    @action(detail=True, methods=['post', 'get'])
    def prepare_audio(self, request, pk=None):
        """Səs faylını serverə endir — sonra telefona yükləmək olar."""
        lesson = self.get_object()
        ok, err, _blocking = ensure_audio_file(lesson)
        if not ok:
            return Response({'ok': False, 'error': err}, status=status.HTTP_502_BAD_GATEWAY)
        lesson.refresh_from_db()
        size = lesson_audio_size_bytes(lesson)
        download_url = lesson_stored_audio_url(lesson, request)
        return Response(
            {
                'ok': True,
                'id': lesson.id,
                'title': lesson.title,
                'downloadUrl': download_url,
                'durationSeconds': lesson.duration_seconds,
                'sizeBytes': size,
                'hasAudio': True,
            }
        )


class TelegramLiveLessonViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = TelegramLiveLessonSerializer

    def get_queryset(self):
        return TelegramLiveLesson.objects.filter(is_published=True)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        return Response({'results': serializer.data, 'count': queryset.count()})


@api_view(['POST'])
def live_teacher_lookup(request):
    """Müəllim kodunu yoxlayır — adı qaytarır (mobil UI önizləmə və yayım)."""
    code = (request.data.get('code') or '').strip()
    if not code.isdigit() or len(code) != 6:
        return Response({'error': 'Kod 6 rəqəm olmalıdır.'}, status=status.HTTP_400_BAD_REQUEST)

    teacher = LiveTeacherCode.objects.filter(code=code, is_active=True).first()
    if not teacher:
        return Response({'error': 'Kod yanlışdır.'}, status=status.HTTP_403_FORBIDDEN)

    return Response({'ok': True, 'name': teacher.name, 'code': teacher.code})


def _resolve_teacher_by_code(code: str) -> LiveTeacherCode | None:
    if not code.isdigit() or len(code) != 6:
        return None
    return LiveTeacherCode.objects.filter(code=code, is_active=True).first()


@api_view(['POST'])
def livekit_token(request):
    """
    LiveKit JWT token yaradır.

    Body: { roomName, role: "teacher"|"student", teacherPin? }
    Müəllim: teacherPin ilə admin-dəki kod yoxlanılır, ad avtomatik təyin olunur.
    Cavab: { token, serverUrl, role, identity, teacherName? }
    """
    from django.conf import settings as django_settings

    room_name = (request.data.get('roomName') or '').strip()
    role = (request.data.get('role') or 'student').strip()
    teacher_pin = (request.data.get('teacherPin') or '').strip()

    if not room_name:
        return Response({'error': 'roomName lazımdır.'}, status=status.HTTP_400_BAD_REQUEST)

    is_teacher = False
    identity = 'Qonaq'
    teacher_name = ''

    if role == 'teacher':
        teacher = _resolve_teacher_by_code(teacher_pin)
        if not teacher:
            return Response(
                {'error': 'Kod yanlışdır və ya deaktivdir.'},
                status=status.HTTP_403_FORBIDDEN,
            )
        identity = teacher.name[:80]
        teacher_name = teacher.name
        is_teacher = True

    try:
        from livekit.api import AccessToken, VideoGrants

        api_key = getattr(django_settings, 'LIVEKIT_API_KEY', '') or ''
        api_secret = getattr(django_settings, 'LIVEKIT_API_SECRET', '') or ''
        server_url = getattr(django_settings, 'LIVEKIT_SERVER_URL', '') or ''

        if not api_key or not api_secret or not server_url:
            return Response(
                {
                    'error': (
                        'LiveKit konfiqurasiya edilməyib. '
                        'Render-də LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_SERVER_URL təyin edin.'
                    ),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        if not (server_url.startswith('wss://') or server_url.startswith('ws://')):
            return Response(
                {'error': 'LIVEKIT_SERVER_URL wss:// və ya ws:// ilə başlamalıdır.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        at = AccessToken(api_key=api_key, api_secret=api_secret)
        at.identity = identity
        at.name = identity
        at.video = VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=is_teacher,
            can_subscribe=True,
            can_publish_data=is_teacher,
        )
        token_jwt = at.to_jwt()
    except Exception as exc:
        return Response(
            {'error': f'Token yaradılmadı: {exc}'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        'token': token_jwt,
        'serverUrl': server_url,
        'role': 'teacher' if is_teacher else 'student',
        'identity': identity,
        'teacherName': teacher_name,
    })


@api_view(['POST'])
@parser_classes([MultiPartParser, FormParser])
def hifz_evaluate(request):
    """Hifz: səs faylı + ayə mətni → Whisper + lokal müqayisə + yazılı təcvid."""
    from django.conf import settings

    from .hifz import HifzError, evaluate_hifz_recitation

    audio = request.FILES.get('audio')
    expected = (request.data.get('expectedArabic') or '').strip()

    if not audio:
        return Response({'message': 'audio faylı lazımdır.'}, status=status.HTTP_400_BAD_REQUEST)
    if not expected:
        return Response({'message': 'expectedArabic lazımdır.'}, status=status.HTTP_400_BAD_REQUEST)

    max_mb = getattr(settings, 'HIFZ_MAX_AUDIO_MB', 12)
    if audio.size > max_mb * 1024 * 1024:
        return Response(
            {'message': f'Səs faylı {max_mb}MB-dan böyük ola bilməz.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    surah_id = request.data.get('surahId')
    ayah_number = request.data.get('ayahNumber')
    try:
        surah_id = int(surah_id) if surah_id not in (None, '') else None
    except (TypeError, ValueError):
        surah_id = None
    try:
        ayah_number = int(ayah_number) if ayah_number not in (None, '') else None
    except (TypeError, ValueError):
        ayah_number = None

    try:
        result = evaluate_hifz_recitation(audio, expected, surah_id, ayah_number)
        return Response(result)
    except HifzError as e:
        return Response({'message': str(e)}, status=status.HTTP_502_BAD_GATEWAY)
