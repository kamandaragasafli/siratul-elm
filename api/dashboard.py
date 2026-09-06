import json
import re

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import logout
from django.db.models import Count, Max
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .book_import import import_all_bundled_books
from .chapter_ai import ChapterAIError, fix_chapter_text
from .chapter_blocks import (
    blocks_to_plain_text,
    chapter_editor_data,
    extract_footnotes,
    footnote_max_number,
    footnote_valid_numbers,
    html_to_blocks,
    html_to_plain_text,
    merge_footnotes,
    parse_footnote_entries,
    plain_to_blocks,
)
from .models import Book, Chapter, QuranMealNote, SupportMessage, TelegramLiveLesson, VideoChannel, VideoLesson, VideoSeries
from .surah_meta import surah_list, surah_name_az
from .youtube import fetch_youtube_title, sync_channel_playlists


def _parse_panel_datetime(raw: str):
    from django.utils.dateparse import parse_datetime

    s = (raw or '').strip()
    if not s:
        return None
    if len(s) == 16 and 'T' in s:
        s = f'{s}:00'
    dt = parse_datetime(s)
    if dt is None:
        return None
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _extract_youtube_id(url: str) -> str:
    m = re.search(r'(?:v=|/shorts/|youtu\.be/)([\w-]{11})', url or '')
    return m.group(1) if m else ''


def _base_ctx(nav: str, form_error=None):
    return {
        'now': timezone.now(),
        'nav': nav,
        'form_error': form_error,
    }


def _stats():
    books = Book.objects.all()
    channels = VideoChannel.objects.all()
    series = VideoSeries.objects.all()
    lessons = VideoLesson.objects.all()
    support = SupportMessage.objects.all()
    return {
        'books': books.count(),
        'books_published': books.filter(is_published=True).count(),
        'chapters': Chapter.objects.count(),
        'channels': channels.count(),
        'channels_published': channels.filter(is_published=True).count(),
        'series': series.count(),
        'series_published': series.filter(is_published=True).count(),
        'lessons': lessons.count(),
        'lessons_published': lessons.filter(is_published=True).count(),
        'lessons_with_audio': lessons.exclude(audio_file='').exclude(audio_file=None).count(),
        'support': support.count(),
        'support_unread': support.filter(is_read=False).count(),
        'meal_notes': QuranMealNote.objects.count(),
        'meal_notes_published': QuranMealNote.objects.filter(is_published=True).count(),
    }


def _handle_create_channel(request):
    name = (request.POST.get('name') or '').strip()
    url = (request.POST.get('url') or '').strip()
    description = (request.POST.get('description') or '').strip()
    published = request.POST.get('is_published') == 'on'
    do_sync = request.POST.get('sync_playlists') == 'on'

    if not url.startswith(('http://', 'https://')):
        return 'Düzgün kanal / playlists linki yazın.'
    if VideoChannel.objects.filter(url=url).exists():
        return 'Bu kanal linki artıq mövcuddur.'

    if not name:
        name = fetch_youtube_title(url) or ''
    if not name:
        return 'Kanal adı tapılmadı — adı əl ilə yazın.'

    max_order = VideoChannel.objects.aggregate(m=Max('order')).get('m') or 0
    channel = VideoChannel(
        name=name,
        url=url,
        description=description,
        order=max_order + 1,
        is_published=published,
    )
    channel.save()

    msg = f'Kanal əlavə olundu: {channel.name}'
    if do_sync:
        result = sync_channel_playlists(channel)
        if result.get('error'):
            messages.warning(request, f'{msg}. Playlist sinxronu: {result["error"]}')
        else:
            messages.success(
                request,
                (
                    f'{msg}. Playlistlər: {result["total"]} tapıldı, '
                    f'{result["created"]} yeni silsilə.'
                ),
            )
    else:
        messages.success(request, msg)
    return None


def _handle_create_lesson(request):
    series_id = (request.POST.get('series_id') or '').strip()
    url = (request.POST.get('url') or '').strip()
    title = (request.POST.get('title') or '').strip()
    published = request.POST.get('is_published') == 'on'

    series = VideoSeries.objects.filter(pk=series_id).first() if series_id.isdigit() else None
    if not series:
        return 'Silsilə seçin.'
    if not url.startswith(('http://', 'https://')):
        return 'Düzgün video linki yazın.'

    yt_id = _extract_youtube_id(url)
    if not yt_id:
        return 'YouTube video ID tapılmadı — linki yoxlayın.'
    if VideoLesson.objects.filter(series=series, youtube_id=yt_id).exists():
        return 'Bu video artıq bu silsilədə var.'

    if not title:
        title = fetch_youtube_title(url) or f'Dərs — {yt_id}'
    max_order = (
        VideoLesson.objects.filter(series=series).aggregate(m=Max('order')).get('m') or 0
    )
    lesson = VideoLesson.objects.create(
        series=series,
        title=title,
        url=url,
        youtube_id=yt_id,
        order=max_order + 1,
        is_published=published,
    )
    messages.success(request, f'Dərs əlavə olundu: {lesson.title}')
    return None


def _handle_delete_lesson(request):
    lesson_id = (request.POST.get('lesson_id') or '').strip()
    if not lesson_id.isdigit():
        return 'Dərs tapılmadı.'
    lesson = VideoLesson.objects.select_related('series').filter(pk=lesson_id).first()
    if not lesson:
        return 'Dərs tapılmadı.'

    title = lesson.title
    series_id = lesson.series_id
    if lesson.audio_file:
        try:
            lesson.audio_file.delete(save=False)
        except OSError:
            pass
    lesson.delete()
    messages.success(request, f'Dərs silindi: {title}')
    request._redirect_series_id = series_id
    return None


def _handle_sync_bundled_books(request):
    overwrite = request.POST.get('overwrite_chapters') == 'on'
    result = import_all_bundled_books(update_existing=True, overwrite_chapters=overwrite)
    if not result.get('ok'):
        return result.get('error') or 'JSON kitablar tapılmadı.'

    created = sum(1 for r in result['results'] if r.get('created'))
    updated = sum(1 for r in result['results'] if r.get('updated'))
    written = sum(1 for r in result['results'] if r.get('chapters_written'))
    failed = sum(1 for r in result['results'] if not r.get('ok'))
    messages.success(
        request,
        (
            f'JSON kitablar: {result["imported"]}/{result["total"]} '
            f'({created} yeni, {updated} meta, {written} fəsil yazıldı'
            + (f', {failed} xəta' if failed else '')
            + ').'
            + (
                ' Mövcud mətnlər JSON ilə əvəz olundu.'
                if overwrite
                else ' Mövcud fəsil mətnləri saxlanıldı.'
            )
        ),
    )
    return None


def _handle_save_chapter(request):
    chapter_id = (request.POST.get('chapter_id') or '').strip()
    title = (request.POST.get('title') or '').strip()
    content_html = request.POST.get('content_html')
    content = request.POST.get('content')
    if content is None:
        content = ''

    if not chapter_id.isdigit():
        return 'Fəsil tapılmadı.'
    chapter = Chapter.objects.select_related('book').filter(pk=chapter_id).first()
    if not chapter:
        return 'Fəsil tapılmadı.'
    if not title:
        return 'Fəsil başlığı boş ola bilməz.'

    if content_html is not None:
        blocks = html_to_blocks(content_html)
        footnote_items_raw = request.POST.get('footnote_items') or '[]'
        footnote_heading = (request.POST.get('footnote_heading') or 'Qeydlər və istinadlar').strip()
        try:
            footnote_items = json.loads(footnote_items_raw)
            if not isinstance(footnote_items, list):
                footnote_items = []
        except json.JSONDecodeError:
            footnote_items = []
        footnote_items = parse_footnote_entries(footnote_items)
        blocks = merge_footnotes(blocks, footnote_items, footnote_heading)
        chapter.blocks = blocks
        chapter.content = blocks_to_plain_text(blocks) or html_to_plain_text(content_html)
    else:
        chapter.content = content
        chapter.blocks = plain_to_blocks(content)

    chapter.title = title
    chapter.save(update_fields=['title', 'content', 'blocks'])
    chapter.book.save(update_fields=['updated_at'])
    messages.success(request, f'Fəsil yadda saxlanıldı: {chapter.title}')
    request._redirect_chapter = (chapter.book_id, chapter.id)
    return None


def _slug_id(prefix: str, title: str) -> str:
    import re as _re
    import time

    base = _re.sub(r'[^a-z0-9]+', '-', (title or '').lower()).strip('-')[:40] or 'kitab'
    return f'{prefix}-{base}-{int(time.time())}'


def _handle_create_book(request):
    title = (request.POST.get('title') or '').strip()
    author = (request.POST.get('author') or '').strip()
    description = (request.POST.get('description') or '').strip()
    language = (request.POST.get('language') or 'az').strip()[:8]
    topics_raw = (request.POST.get('topics') or '').strip()
    published = request.POST.get('is_published') == 'on'
    chapter_title = (request.POST.get('chapter_title') or '').strip()
    chapter_content = request.POST.get('chapter_content') or ''
    cover = request.FILES.get('cover_image')

    if not title:
        return 'Kitab başlığı lazımdır.'
    if language not in ('az', 'ar', 'en'):
        language = 'az'
    if cover and not (cover.content_type or '').startswith('image/'):
        return 'Qapaq yalnız şəkil faylı ola bilər (JPG, PNG, WebP).'

    topics = [t.strip() for t in topics_raw.split(',') if t.strip()][:20]
    public_id = _slug_id('manual', title)
    while Book.objects.filter(public_id=public_id).exists():
        public_id = _slug_id('manual', title)

    book = Book.objects.create(
        public_id=public_id,
        title=title,
        author=author,
        description=description,
        language=language,
        cover_tone=Book.objects.count() % 6,
        source='manual',
        topics=topics,
        is_published=published,
    )

    if cover:
        book.cover_image = cover
        book.save(update_fields=['cover_image'])

    if chapter_title or chapter_content.strip():
        Chapter.objects.create(
            book=book,
            public_id='ch-1',
            title=chapter_title or 'Fəsil 1',
            content=chapter_content,
            order=0,
        )

    messages.success(request, f'Kitab əlavə olundu: {book.title}')
    request._redirect_book_id = book.id
    return None


def _handle_create_chapter(request):
    book_id = (request.POST.get('book_id') or '').strip()
    title = (request.POST.get('title') or '').strip()
    content = request.POST.get('content') or ''

    book = Book.objects.filter(pk=book_id).first() if book_id.isdigit() else None
    if not book:
        return 'Kitab seçin.'
    if not title:
        return 'Fəsil başlığı lazımdır.'

    max_order = Chapter.objects.filter(book=book).aggregate(m=Max('order')).get('m')
    next_order = (max_order if max_order is not None else -1) + 1
    public_id = f'ch-{next_order + 1}'
    n = 1
    while Chapter.objects.filter(book=book, public_id=public_id).exists():
        n += 1
        public_id = f'ch-{next_order + 1}-{n}'

    chapter = Chapter.objects.create(
        book=book,
        public_id=public_id,
        title=title,
        content=content,
        order=next_order,
    )
    book.save(update_fields=['updated_at'])
    messages.success(request, f'Fəsil əlavə olundu: {chapter.title}')
    request._redirect_chapter = (book.id, chapter.id)
    return None


def _handle_toggle_book(request):
    book_id = (request.POST.get('book_id') or '').strip()
    book = Book.objects.filter(pk=book_id).first() if book_id.isdigit() else None
    if not book:
        return 'Kitab tapılmadı.'
    book.is_published = not book.is_published
    book.save(update_fields=['is_published', 'updated_at'])
    messages.success(
        request,
        f'«{book.title}» indi {"yayınlı" if book.is_published else "gizli"}.',
    )
    return None


def _handle_update_book_cover(request):
    book_id = (request.POST.get('book_id') or '').strip()
    cover = request.FILES.get('cover_image')
    book = Book.objects.filter(pk=book_id).first() if book_id.isdigit() else None
    if not book:
        return 'Kitab tapılmadı.'
    if not cover:
        return 'Qapaq şəkli seçin.'
    if not (cover.content_type or '').startswith('image/'):
        return 'Qapaq yalnız şəkil faylı ola bilər (JPG, PNG, WebP).'
    book.cover_image = cover
    book.save(update_fields=['cover_image', 'updated_at'])
    messages.success(request, f'«{book.title}» qapağı yeniləndi.')
    return None


def _handle_delete_book(request):
    book_id = (request.POST.get('book_id') or '').strip()
    if not book_id.isdigit():
        return 'Kitab tapılmadı.'
    book = Book.objects.filter(pk=book_id).first()
    if not book:
        return 'Kitab tapılmadı.'

    title = book.title
    chapter_count = book.chapters.count()
    if book.cover_image:
        try:
            book.cover_image.delete(save=False)
        except OSError:
            pass
    book.delete()
    messages.success(
        request,
        f'«{title}» silindi ({chapter_count} fəsil ilə birlikdə).',
    )
    return None


def _handle_toggle_channel(request):
    channel_id = (request.POST.get('channel_id') or '').strip()
    channel = (
        VideoChannel.objects.filter(pk=channel_id).first() if channel_id.isdigit() else None
    )
    if not channel:
        return 'Kanal tapılmadı.'
    channel.is_published = not channel.is_published
    channel.save(update_fields=['is_published', 'updated_at'])
    messages.success(
        request,
        f'«{channel.name}» indi {"yayınlı" if channel.is_published else "gizli"}.',
    )
    return None


def _handle_sync_channel(request):
    channel_id = (request.POST.get('channel_id') or '').strip()
    channel = (
        VideoChannel.objects.filter(pk=channel_id).first() if channel_id.isdigit() else None
    )
    if not channel:
        return 'Kanal tapılmadı.'
    result = sync_channel_playlists(channel)
    if result.get('error'):
        messages.warning(request, f'{channel.name}: {result["error"]}')
    else:
        messages.success(
            request,
            (
                f'{channel.name}: {result["total"]} playlist '
                f'({result["created"]} yeni, {result["updated"]} yeniləndi)'
            ),
        )
    return None


@staff_member_required
@require_http_methods(['GET'])
def panel_home(request):
    ctx = _base_ctx('home')
    ctx['stats'] = _stats()
    ctx['recent_books'] = Book.objects.order_by('-created_at')[:8]
    ctx['recent_lessons'] = (
        VideoLesson.objects.select_related('series', 'series__channel').order_by('-id')[:10]
    )
    return render(request, 'api/panel/home.html', ctx)


# Backward-compatible alias
dashboard = panel_home


@staff_member_required
@require_http_methods(['GET', 'POST'])
def panel_books(request):
    form_error = None
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'sync_bundled_books':
            form_error = _handle_sync_bundled_books(request)
            if not form_error:
                return redirect('panel-books')
        elif action == 'toggle_book':
            form_error = _handle_toggle_book(request)
            if not form_error:
                return redirect('panel-books')
        elif action == 'create_book':
            form_error = _handle_create_book(request)
            if not form_error:
                bid = getattr(request, '_redirect_book_id', None)
                if bid:
                    return redirect(f'/panel/chapters/?book={bid}')
                return redirect('panel-books')
        elif action == 'update_book_cover':
            form_error = _handle_update_book_cover(request)
            if not form_error:
                return redirect('panel-books')
        elif action == 'delete_book':
            form_error = _handle_delete_book(request)
            if not form_error:
                return redirect('panel-books')

    ctx = _base_ctx('books', form_error)
    ctx['books_list'] = Book.objects.annotate(chapter_count=Count('chapters')).order_by(
        '-created_at'
    )
    ctx['language_choices'] = Book.LANGUAGE_CHOICES
    return render(request, 'api/panel/books.html', ctx)


@staff_member_required
@require_http_methods(['GET', 'POST'])
def panel_chapters(request):
    form_error = None
    selected_book_id = (request.GET.get('book') or '').strip()
    selected_chapter_id = (request.GET.get('chapter') or '').strip()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_chapter':
            form_error = _handle_save_chapter(request)
            if not form_error:
                bid, cid = getattr(request, '_redirect_chapter', (None, None))
                if bid and cid:
                    return redirect(f'/panel/chapters/?book={bid}&chapter={cid}')
                return redirect('panel-chapters')
        elif action == 'create_chapter':
            form_error = _handle_create_chapter(request)
            if not form_error:
                bid, cid = getattr(request, '_redirect_chapter', (None, None))
                if bid and cid:
                    return redirect(f'/panel/chapters/?book={bid}&chapter={cid}')
                return redirect('panel-chapters')

    selected_book = None
    book_chapters = []
    edit_chapter = None
    if selected_book_id.isdigit():
        selected_book = Book.objects.filter(pk=selected_book_id).first()
        if selected_book:
            book_chapters = list(
                Chapter.objects.filter(book=selected_book).order_by('order', 'id')
            )
    if selected_chapter_id.isdigit():
        edit_chapter = (
            Chapter.objects.select_related('book').filter(pk=selected_chapter_id).first()
        )
        if edit_chapter and not selected_book:
            selected_book = edit_chapter.book
            selected_book_id = str(selected_book.id)
            book_chapters = list(
                Chapter.objects.filter(book=selected_book).order_by('order', 'id')
            )

    ctx = _base_ctx('chapters', form_error)
    ctx.update(
        {
            'book_choices': Book.objects.order_by('title'),
            'selected_book': selected_book,
            'selected_book_id': selected_book_id if selected_book else '',
            'book_chapters': book_chapters,
            'edit_chapter': edit_chapter,
        }
    )
    if edit_chapter:
        editor_html, footnote_items, footnote_heading = chapter_editor_data(
            edit_chapter.blocks,
            edit_chapter.content,
        )
        ctx['editor_html'] = editor_html
        ctx['footnote_items'] = footnote_items
        ctx['footnote_heading'] = footnote_heading
        if selected_book and book_chapters:
            max_n = 0
            for ch in book_chapters:
                _, entries, _ = extract_footnotes(ch.blocks)
                max_n = max(max_n, footnote_max_number(entries))
            ctx['footnote_next_suggest'] = max_n + 1 if max_n else 1
    return render(request, 'api/panel/chapters.html', ctx)


@staff_member_required
@require_http_methods(['POST'])
def panel_chapter_preview(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Yanlış sorğu.'}, status=400)

    content_html = body.get('content_html') or ''
    title = (body.get('title') or '').strip()
    language = (body.get('language') or 'az').strip()[:8]
    footnote_items = body.get('footnote_items') or []
    footnote_heading = (body.get('footnote_heading') or 'Qeydlər və istinadlar').strip()
    if not isinstance(footnote_items, list):
        footnote_items = []
    footnote_items = parse_footnote_entries(footnote_items)
    blocks = merge_footnotes(
        html_to_blocks(content_html),
        footnote_items,
        footnote_heading,
    )
    valid_numbers = sorted(footnote_valid_numbers(footnote_items))

    return render(
        request,
        'api/panel/chapter_preview_fragment.html',
        {
            'blocks': blocks,
            'chapter_title': title,
            'rtl': language == 'ar',
            'valid_numbers': valid_numbers,
        },
    )


@staff_member_required
@require_http_methods(['POST'])
def panel_chapter_ai_fix(request):
    try:
        body = json.loads(request.body.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Yanlış sorğu formatı.'}, status=400)

    title = (body.get('title') or '').strip()
    content = body.get('content')
    content_html = body.get('content_html')
    if content is None and content_html:
        content = html_to_plain_text(content_html)
    if content is None:
        content = ''
    language = (body.get('language') or 'az').strip()[:8]

    try:
        result = fix_chapter_text(title=title, content=content, language=language)
        from .chapter_blocks import blocks_to_html, plain_to_blocks

        fixed_content = result.get('content', content)
        result['content_html'] = blocks_to_html(plain_to_blocks(fixed_content))
        return JsonResponse(result)
    except ChapterAIError as e:
        return JsonResponse({'error': str(e)}, status=502)


@staff_member_required
@require_http_methods(['GET', 'POST'])
def panel_channels(request):
    form_error = None
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_channel':
            form_error = _handle_create_channel(request)
            if not form_error:
                return redirect('panel-channels')
        elif action == 'toggle_channel':
            form_error = _handle_toggle_channel(request)
            if not form_error:
                return redirect('panel-channels')
        elif action == 'sync_channel':
            form_error = _handle_sync_channel(request)
            if not form_error:
                return redirect('panel-channels')

    ctx = _base_ctx('channels', form_error)
    ctx['channels_list'] = VideoChannel.objects.annotate(
        series_count=Count('series'),
    ).order_by('order', 'name')
    return render(request, 'api/panel/channels.html', ctx)


@staff_member_required
@require_http_methods(['GET', 'POST'])
def panel_lessons(request):
    form_error = None
    selected_series_id = (request.GET.get('series') or '').strip()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_lesson':
            form_error = _handle_create_lesson(request)
            if not form_error:
                return redirect('panel-lessons')
        elif action == 'delete_lesson':
            form_error = _handle_delete_lesson(request)
            if not form_error:
                sid = getattr(request, '_redirect_series_id', None)
                if sid:
                    return redirect(f'/panel/lessons/?series={sid}')
                return redirect('panel-lessons')

    selected_series = None
    series_lessons = []
    if selected_series_id.isdigit():
        selected_series = (
            VideoSeries.objects.select_related('channel').filter(pk=selected_series_id).first()
        )
        if selected_series:
            series_lessons = list(
                VideoLesson.objects.filter(series=selected_series).order_by('order', 'id')
            )

    ctx = _base_ctx('lessons', form_error)
    ctx.update(
        {
            'series_choices': VideoSeries.objects.select_related('channel').order_by(
                'channel__name', 'order', 'title'
            ),
            'selected_series': selected_series,
            'selected_series_id': selected_series_id if selected_series else '',
            'series_lessons': series_lessons,
        }
    )
    return render(request, 'api/panel/lessons.html', ctx)


def _handle_create_live_lesson(request):
    title = (request.POST.get('title') or '').strip()
    teacher = (request.POST.get('teacher_name') or '').strip()
    description = (request.POST.get('description') or '').strip()
    url = (request.POST.get('telegram_url') or '').strip()
    starts = _parse_panel_datetime(request.POST.get('starts_at'))
    ends = _parse_panel_datetime(request.POST.get('ends_at'))
    published = request.POST.get('is_published') == 'on'
    livekit_enabled = request.POST.get('is_livekit_enabled') == 'on'
    room_name = (request.POST.get('livekit_room_name') or '').strip()

    if len(title) < 2:
        return 'Dərs başlığı yazın.'
    if livekit_enabled:
        if not room_name:
            # Avtomatik otaq adı
            import re
            import time
            slug = re.sub(r'[^a-z0-9]+', '-', title.lower())[:40].strip('-') or 'ders'
            room_name = f'{slug}-{int(time.time()) % 100000}'
        if not url:
            url = 'https://t.me/'
    elif not url.startswith(('http://', 'https://')):
        return 'Düzgün Telegram linki yazın (https://t.me/...) və ya LiveKit işarələyin.'
    if not starts:
        return 'Başlanğıc vaxtı seçin.'
    if not ends:
        return 'Bitmə vaxtı seçin.'
    if ends <= starts:
        return 'Bitmə vaxtı başlanğıcdan sonra olmalıdır.'

    max_order = TelegramLiveLesson.objects.aggregate(m=Max('order')).get('m') or 0
    TelegramLiveLesson.objects.create(
        title=title,
        teacher_name=teacher,
        description=description,
        telegram_url=url,
        starts_at=starts,
        ends_at=ends,
        order=max_order + 1,
        is_published=published,
        livekit_room_name=room_name if livekit_enabled else '',
        is_livekit_enabled=livekit_enabled,
    )
    messages.success(request, f'Canlı dərs əlavə olundu: {title}')
    return None


def _handle_toggle_live_lesson(request):
    lesson_id = (request.POST.get('live_lesson_id') or '').strip()
    lesson = (
        TelegramLiveLesson.objects.filter(pk=lesson_id).first()
        if lesson_id.isdigit()
        else None
    )
    if not lesson:
        return 'Dərs tapılmadı.'
    lesson.is_published = not lesson.is_published
    lesson.save(update_fields=['is_published', 'updated_at'])
    messages.success(
        request,
        'Yayınlandı.' if lesson.is_published else 'Gizlədildi.',
    )
    return None


def _handle_delete_live_lesson(request):
    lesson_id = (request.POST.get('live_lesson_id') or '').strip()
    lesson = (
        TelegramLiveLesson.objects.filter(pk=lesson_id).first()
        if lesson_id.isdigit()
        else None
    )
    if not lesson:
        return 'Dərs tapılmadı.'
    title = lesson.title
    lesson.delete()
    messages.success(request, f'Silindi: {title}')
    return None


def _handle_live_lesson_force(request):
    lesson_id = (request.POST.get('live_lesson_id') or '').strip()
    force = (request.POST.get('force_status') or '').strip()
    lesson = (
        TelegramLiveLesson.objects.filter(pk=lesson_id).first()
        if lesson_id.isdigit()
        else None
    )
    if not lesson:
        return 'Dərs tapılmadı.'
    if force not in ('', 'live', 'ended'):
        return 'Naməlum status.'
    lesson.force_status = force
    lesson.save(update_fields=['force_status', 'updated_at'])
    labels = {'': 'Avtomatik', 'live': 'Canlı', 'ended': 'Bitib'}
    messages.success(request, f'Status: {labels[force]}')
    return None


@staff_member_required
@require_http_methods(['GET', 'POST'])
def panel_live_lessons(request):
    form_error = None
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_live_lesson':
            form_error = _handle_create_live_lesson(request)
        elif action == 'toggle_live_lesson':
            form_error = _handle_toggle_live_lesson(request)
        elif action == 'delete_live_lesson':
            form_error = _handle_delete_live_lesson(request)
        elif action == 'force_live_lesson':
            form_error = _handle_live_lesson_force(request)
        if not form_error:
            return redirect('panel-live-lessons')

    ctx = _base_ctx('live-lessons', form_error)
    lessons = list(TelegramLiveLesson.objects.all())
    for lesson in lessons:
        lesson.computed_status = lesson.effective_status()
    ctx['live_lessons_list'] = lessons
    return render(request, 'api/panel/live_lessons.html', ctx)


@staff_member_required
@require_http_methods(['GET', 'POST'])
def panel_support(request):
    form_error = None
    if request.method == 'POST':
        action = request.POST.get('action')
        msg_id = (request.POST.get('id') or '').strip()
        msg = SupportMessage.objects.filter(pk=msg_id).first() if msg_id.isdigit() else None
        if not msg:
            form_error = 'Mesaj tapılmadı.'
        elif action == 'mark_read':
            msg.is_read = True
            msg.save(update_fields=['is_read'])
            messages.success(request, 'Mesaj oxunmuş kimi işarələndi.')
            return redirect('panel-support')
        elif action == 'mark_unread':
            msg.is_read = False
            msg.save(update_fields=['is_read'])
            messages.success(request, 'Mesaj oxunmamış kimi işarələndi.')
            return redirect('panel-support')
        elif action == 'delete':
            msg.delete()
            messages.success(request, 'Mesaj silindi.')
            return redirect('panel-support')
        else:
            form_error = 'Naməlum əməliyyat.'

    filter_q = (request.GET.get('filter') or 'all').strip()
    qs = SupportMessage.objects.all()
    if filter_q == 'unread':
        qs = qs.filter(is_read=False)
    elif filter_q == 'read':
        qs = qs.filter(is_read=True)

    ctx = _base_ctx('support', form_error)
    ctx['items'] = qs[:200]
    ctx['filter'] = filter_q
    ctx['stats'] = _stats()
    return render(request, 'api/panel/support.html', ctx)


def _parse_meal_footnotes(request) -> list[dict]:
    """POST-dan haşiyə sətirləri: fn_n[], fn_text[], fn_kind[]."""
    ns = request.POST.getlist('fn_n')
    texts = request.POST.getlist('fn_text')
    kinds = request.POST.getlist('fn_kind')
    out = []
    for i, raw_n in enumerate(ns):
        try:
            n = int(str(raw_n).strip())
        except (TypeError, ValueError):
            continue
        text = (texts[i] if i < len(texts) else '').strip()
        kind = (kinds[i] if i < len(kinds) else 'note').strip().lower()
        if kind not in ('note', 'hukm'):
            kind = 'note'
        if n < 1 or not text:
            continue
        out.append({'n': n, 'text': text, 'kind': kind})
    out.sort(key=lambda x: x['n'])
    return out


def _parse_meal_paragraphs(request) -> list[str]:
    raw = (request.POST.get('paragraphs') or '').strip()
    if not raw:
        return []
    # Boş sətirlə ayrılan abzaslar; yoxdursa sətir-sətir
    if '\n\n' in raw:
        return [p.strip() for p in raw.split('\n\n') if p.strip()]
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _parse_meal_summaries(request) -> list[dict]:
    """POST: sum_from[], sum_to[], sum_title[], sum_text[]."""
    frms = request.POST.getlist('sum_from')
    tos = request.POST.getlist('sum_to')
    titles = request.POST.getlist('sum_title')
    texts = request.POST.getlist('sum_text')
    out = []
    for i, raw_from in enumerate(frms):
        try:
            frm = int(str(raw_from).strip())
            to = int(str(tos[i] if i < len(tos) else '').strip())
        except (TypeError, ValueError, IndexError):
            continue
        text = (texts[i] if i < len(texts) else '').strip()
        if frm < 1 or to < frm or not text:
            continue
        item = {'from': frm, 'to': to, 'text': text}
        title = (titles[i] if i < len(titles) else '').strip()
        if title:
            item['title'] = title
        out.append(item)
    out.sort(key=lambda x: (x['from'], x['to']))
    return out


def _handle_save_meal_note(request):
    note_id = (request.POST.get('id') or '').strip()
    scope = (request.POST.get('scope') or 'surah').strip()
    if scope not in (QuranMealNote.SCOPE_SURAH, QuranMealNote.SCOPE_AYAH):
        return 'Səviyyə yanlışdır.'
    try:
        surah = int((request.POST.get('surah') or '').strip())
    except ValueError:
        return 'Surə seçin.'
    if surah < 1 or surah > 114:
        return 'Surə seçimi yanlışdır.'

    ayah = None
    if scope == QuranMealNote.SCOPE_AYAH:
        try:
            ayah = int((request.POST.get('ayah') or '').strip())
        except ValueError:
            return 'Ayə nömrəsi yanlışdır.'
        if ayah < 1:
            return 'Ayə nömrəsi mütləqdir.'

    intro = (request.POST.get('intro') or '').strip()
    paragraphs = _parse_meal_paragraphs(request)
    summaries = _parse_meal_summaries(request) if scope == QuranMealNote.SCOPE_SURAH else []
    message = (request.POST.get('message') or '').strip()
    author = (request.POST.get('author') or '').strip()
    footnotes = _parse_meal_footnotes(request)
    is_published = request.POST.get('is_published') == 'on'

    if not (intro or paragraphs or summaries or message or footnotes):
        return 'Ən azı surə məlumatı, xülasə, əsas mesaj və ya haşiyə/hökm lazımdır.'

    note = None
    if note_id.isdigit():
        note = QuranMealNote.objects.filter(pk=int(note_id)).first()
        if not note:
            return 'Qeyd tapılmadı.'

    clash_qs = QuranMealNote.objects.all()
    if note:
        clash_qs = clash_qs.exclude(pk=note.pk)
    name = surah_name_az(surah)
    if scope == QuranMealNote.SCOPE_SURAH:
        if clash_qs.filter(surah=surah, ayah__isnull=True).exists():
            return f'«{name}» üçün qısa məlumat artıq var.'
    else:
        if clash_qs.filter(surah=surah, ayah=ayah).exists():
            return f'«{name}» {ayah} üçün qısa məlumat artıq var.'

    if note is None:
        note = QuranMealNote()

    note.scope = scope
    note.surah = surah
    note.ayah = ayah
    note.intro = intro
    note.paragraphs = paragraphs
    note.summaries = summaries
    note.message = message
    note.author = author
    note.footnotes = footnotes
    note.is_published = is_published
    note.save()
    messages.success(request, f'Saxlanıldı: {name}' + (f' {ayah}' if ayah else ''))
    request._redirect_meal_note_id = note.id
    return None


def _handle_delete_meal_note(request):
    note_id = (request.POST.get('id') or '').strip()
    note = QuranMealNote.objects.filter(pk=note_id).first() if note_id.isdigit() else None
    if not note:
        return 'Qeyd tapılmadı.'
    label = str(note)
    note.delete()
    messages.success(request, f'Silindi: {label}')
    return None


def _handle_toggle_meal_note(request):
    note_id = (request.POST.get('id') or '').strip()
    note = QuranMealNote.objects.filter(pk=note_id).first() if note_id.isdigit() else None
    if not note:
        return 'Qeyd tapılmadı.'
    note.is_published = not note.is_published
    note.save(update_fields=['is_published', 'updated_at'])
    messages.success(
        request,
        f'{"Yayınlandı" if note.is_published else "Gizlədildi"}: {note}',
    )
    return None


@staff_member_required
@require_http_methods(['GET', 'POST'])
def panel_meal_notes(request):
    form_error = None
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_meal_note':
            form_error = _handle_save_meal_note(request)
            if not form_error:
                nid = getattr(request, '_redirect_meal_note_id', None)
                if nid:
                    return redirect(f'/panel/meal-notes/?edit={nid}')
                return redirect('panel-meal-notes')
        elif action == 'delete_meal_note':
            form_error = _handle_delete_meal_note(request)
            if not form_error:
                return redirect('panel-meal-notes')
        elif action == 'toggle_meal_note':
            form_error = _handle_toggle_meal_note(request)
            if not form_error:
                return redirect('panel-meal-notes')
        else:
            form_error = 'Naməlum əməliyyat.'

    edit_id = (request.GET.get('edit') or '').strip()
    edit_note = (
        QuranMealNote.objects.filter(pk=int(edit_id)).first()
        if edit_id.isdigit()
        else None
    )

    ctx = _base_ctx('meal-notes', form_error)
    notes = list(QuranMealNote.objects.all()[:300])
    for n in notes:
        n.surah_label = surah_name_az(n.surah)
    ctx['notes'] = notes
    ctx['surah_choices'] = surah_list()
    ctx['edit_note'] = edit_note
    ctx['stats'] = _stats()
    if edit_note:
        ctx['form_scope'] = edit_note.scope
        ctx['form_surah'] = edit_note.surah
        ctx['form_ayah'] = edit_note.ayah or ''
        ctx['form_intro'] = edit_note.intro or ''
        ctx['form_paragraphs'] = '\n\n'.join(edit_note.paragraphs or [])
        ctx['form_summaries'] = edit_note.summaries or []
        ctx['form_message'] = edit_note.message
        ctx['form_author'] = edit_note.author
        ctx['form_footnotes'] = edit_note.footnotes or []
        ctx['form_published'] = edit_note.is_published
        ctx['form_id'] = edit_note.id
    else:
        ctx['form_scope'] = 'surah'
        ctx['form_surah'] = ''
        ctx['form_ayah'] = ''
        ctx['form_intro'] = ''
        ctx['form_paragraphs'] = ''
        ctx['form_summaries'] = []
        ctx['form_message'] = ''
        ctx['form_author'] = ''
        ctx['form_footnotes'] = []
        ctx['form_published'] = True
        ctx['form_id'] = ''
    return render(request, 'api/panel/meal_notes.html', ctx)


@staff_member_required
@require_http_methods(['GET', 'POST'])
def panel_logout(request):
    logout(request)
    return redirect('/admin/login/?next=/')
