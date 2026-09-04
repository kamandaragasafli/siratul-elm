from django import forms
from django.contrib import admin, messages
from django.utils.html import format_html
from django.utils.text import slugify

from .models import Book, Chapter, LiveTeacherCode, QuranMealNote, SupportMessage, VideoChannel, VideoLesson, VideoSeries
from .youtube import fetch_youtube_title, sync_channel_playlists


def _book_public_id(title: str, prefix: str = 'manual') -> str:
    import time

    base = slugify(title or 'kitab')[:40] or 'kitab'
    return f'{prefix}-{base}-{int(time.time())}'


def _next_chapter_public_id(order: int, used_ids: set[str]) -> str:
    base = f'ch-{int(order) + 1}'
    public_id = base
    n = 1
    while public_id in used_ids:
        n += 1
        public_id = f'{base}-{n}'
    used_ids.add(public_id)
    return public_id


class BookAdminForm(forms.ModelForm):
    topics_text = forms.CharField(
        label='Mövzular',
        required=False,
        help_text='Vergüllə yazın, məs: əqidə, fiqh, təfsir',
        widget=forms.TextInput(attrs={'placeholder': 'əqidə, fiqh, təfsir', 'style': 'width: 70%;'}),
    )

    class Meta:
        model = Book
        exclude = ('topics',)
        labels = {
            'public_id': 'Kitab ID (texniki)',
            'title': 'Kitab adı',
            'author': 'Müəllif',
            'description': 'Qısa təsvir',
            'language': 'Dil',
            'cover_image': 'Qapaq şəkli',
            'cover_tone': 'Rəng kodu (qapaq yoxdursa)',
            'source': 'Mənbə',
            'is_published': 'Tətbiqdə göstər (yayınlı)',
        }
        help_texts = {
            'public_id': 'Boş buraxa bilərsiniz — kitab adından avtomatik yaranacaq. Yalnız latın hərfləri və tire.',
            'title': 'Sirac tətbiqində görünən əsas başlıq.',
            'author': 'Məs: İmam Qazvini, Əl-Buxari',
            'description': 'Kitabxana siyahısında qısa izah (1–2 cümlə).',
            'language': 'Kitabın əsas dili. Çox vaxt «Azərbaycan» qalır.',
            'cover_image': 'JPG, PNG və ya WebP. Tövsiyə: şaquli format, ən azı 400×600 px.',
            'cover_tone': '0–5 arası rəqəm. Qapaq şəkli olmayanda placeholder rəngi seçir.',
            'is_published': 'Söndürsəniz kitab tətbiqdə gizlənir.',
        }
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3, 'style': 'width: 90%;'}),
            'public_id': forms.TextInput(
                attrs={'placeholder': 'Boş buraxın — avtomatik', 'style': 'width: 60%;'},
            ),
            'title': forms.TextInput(attrs={'placeholder': 'Məs: Tövhidin əsil üsulları', 'style': 'width: 70%;'}),
            'author': forms.TextInput(attrs={'placeholder': 'Müəllif adı', 'style': 'width: 50%;'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            topics = self.instance.topics or []
            if isinstance(topics, list):
                self.fields['topics_text'].initial = ', '.join(str(t) for t in topics)
        self.fields['source'].initial = self.fields['source'].initial or 'manual'
        self.fields['is_published'].initial = True
        self.fields['cover_tone'].widget.attrs.update({'style': 'width: 80px'})
        self.fields['public_id'].required = False

    def clean(self):
        cleaned = super().clean()
        title = (cleaned.get('title') or '').strip()
        public_id = (cleaned.get('public_id') or '').strip()
        if not title:
            self.add_error('title', 'Kitab adı mütləqdir.')
        if not public_id and title:
            pid = _book_public_id(title)
            while Book.objects.filter(public_id=pid).exists():
                pid = _book_public_id(title)
            cleaned['public_id'] = pid
        raw_topics = (cleaned.pop('topics_text', None) or '').strip()
        if raw_topics:
            cleaned['topics'] = [t.strip() for t in raw_topics.split(',') if t.strip()][:20]
        elif not cleaned.get('topics'):
            cleaned['topics'] = []
        return cleaned


class ChapterAdminForm(forms.ModelForm):
    class Meta:
        model = Chapter
        fields = '__all__'
        labels = {
            'book': 'Kitab',
            'order': 'Sıra nömrəsi',
            'public_id': 'Fəsil ID',
            'title': 'Fəsil adı',
            'content': 'Fəsil mətni',
        }
        help_texts = {
            'order': '0 = birinci fəsil, 1 = ikinci və s.',
            'public_id': 'Boş buraxın — avtomatik ch-1, ch-2…',
            'content': 'Oxucuda görünəcək tam mətn. Abzasları Enter ilə ayırın.',
        }
        widgets = {
            'content': forms.Textarea(
                attrs={
                    'rows': 28,
                    'cols': 100,
                    'style': 'font-family: Consolas, monospace; font-size: 14px; width: 95%;',
                    'placeholder': 'Fəsil mətnini buraya yapışdırın…',
                }
            ),
            'title': forms.TextInput(
                attrs={'style': 'width: 60%;', 'placeholder': 'Məs: Müqəddimə'},
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'public_id' in self.fields:
            self.fields['public_id'].required = False
        if 'order' in self.fields:
            self.fields['order'].required = False

    def clean(self):
        cleaned = super().clean()
        public_id = (cleaned.get('public_id') or '').strip()
        title = (cleaned.get('title') or '').strip()
        content = (cleaned.get('content') or '').strip()
        book = cleaned.get('book')

        if not title and not content:
            return cleaned
        if not title:
            self.add_error('title', 'Fəsil adı lazımdır.')
            return cleaned

        # Yeni kitab + inline: order/public_id formset-də təyin olunur (book hələ DB-də yoxdur).
        if not public_id and book and book.pk:
            order = cleaned.get('order')
            if order is None:
                from django.db.models import Max

                max_order = Chapter.objects.filter(book=book).aggregate(m=Max('order')).get('m')
                order = (max_order if max_order is not None else -1) + 1
                cleaned['order'] = order
            used_ids = set(
                Chapter.objects.filter(book=book).values_list('public_id', flat=True),
            )
            cleaned['public_id'] = _next_chapter_public_id(order, used_ids)
        return cleaned


class ChapterInlineFormSet(forms.BaseInlineFormSet):
    """Yeni kitab əlavə edərkən fəsillərə sıra və ID verir (book hələ saxlanmamış ola bilər)."""

    def clean(self):
        super().clean()
        next_order = 0
        used_public_ids: set[str] = set()

        if self.instance.pk:
            from django.db.models import Max

            max_order = Chapter.objects.filter(book=self.instance).aggregate(m=Max('order')).get('m')
            next_order = (max_order if max_order is not None else -1) + 1
            used_public_ids = set(
                Chapter.objects.filter(book=self.instance).values_list('public_id', flat=True),
            )

        for form in self.forms:
            if not form.cleaned_data or form.cleaned_data.get('DELETE'):
                continue
            title = (form.cleaned_data.get('title') or '').strip()
            content = (form.cleaned_data.get('content') or '').strip()
            if not title and not content:
                continue

            if not self.instance.pk or form.cleaned_data.get('order') in (None, ''):
                form.cleaned_data['order'] = next_order
                form.instance.order = next_order
                next_order += 1

            if not (form.cleaned_data.get('public_id') or '').strip():
                public_id = _next_chapter_public_id(
                    form.cleaned_data['order'],
                    used_public_ids,
                )
                form.cleaned_data['public_id'] = public_id
                form.instance.public_id = public_id


class ChapterInline(admin.StackedInline):
    model = Chapter
    form = ChapterAdminForm
    formset = ChapterInlineFormSet
    extra = 1
    min_num = 0
    fields = ('title', 'content')
    show_change_link = True
    verbose_name = 'Fəsil'
    verbose_name_plural = '4. Fəsillər — kitabın oxunacaq mətni (ad + mətn yazın)'
    classes = ['wide']


@admin.register(Book)
class BookAdmin(admin.ModelAdmin):
    form = BookAdminForm
    change_form_template = 'admin/api/book/change_form.html'

    class Media:
        css = {'all': ('api/admin_book_form.css',)}

    list_display = (
        'cover_thumb',
        'title',
        'author',
        'language',
        'chapter_count',
        'is_published',
        'updated_at',
    )
    list_filter = ('language', 'is_published')
    search_fields = ('title', 'author', 'public_id', 'description')
    list_editable = ('is_published',)
    readonly_fields = ('created_at', 'updated_at', 'cover_preview')
    inlines = [ChapterInline]

    add_fieldsets = (
        (
            '1. Kitab haqqında',
            {
                'description': (
                    'Ən azı <strong>kitab adını</strong> yazın. '
                    'Müəllif və təsvir istəyə bağlıdır — tətbiqdə kitabxana kartında görünür.'
                ),
                'fields': ('title', 'author', 'description', 'language', 'topics_text'),
            },
        ),
        (
            '2. Qapaq şəkli',
            {
                'description': (
                    'Şəkil yükləyin — Sirac tətbiqində kitab qapağı kimi görünəcək. '
                    'Şəkil yoxdursa rəng kodu (0–5) placeholder rəngi seçir.'
                ),
                'fields': ('cover_image', 'cover_tone'),
            },
        ),
        (
            '3. Tətbiqdə göstər',
            {
                'description': 'İşarəli qalsın — kitab tətbiqdə dərhal görünsün. Söndürsəniz gizli qalır.',
                'fields': ('is_published',),
            },
        ),
        (
            'Texniki (adətən toxunmayın)',
            {
                'classes': ('collapse',),
                'description': 'Kitab ID avtomatik yaranır. Yalnız xüsusi ehtiyac olduqda dəyişdirin.',
                'fields': ('public_id', 'source'),
            },
        ),
    )

    fieldsets = (
        (
            'Kitab haqqında',
            {
                'fields': ('title', 'author', 'description', 'language', 'topics_text'),
            },
        ),
        (
            'Qapaq',
            {
                'fields': ('cover_image', 'cover_preview', 'cover_tone'),
            },
        ),
        (
            'Tətbiq',
            {
                'fields': ('is_published', 'public_id', 'source'),
            },
        ),
        (
            'Tarix',
            {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)},
        ),
    )

    def get_fieldsets(self, request, obj=None):
        if obj is None:
            return self.add_fieldsets
        return self.fieldsets

    def get_readonly_fields(self, request, obj=None):
        if obj is None:
            return ()
        return self.readonly_fields

    @admin.display(description='Qapaq')
    def cover_thumb(self, obj):
        if obj.cover_image:
            return format_html(
                '<img src="{}" alt="" style="height:48px;width:34px;object-fit:cover;border-radius:3px" />',
                obj.cover_image.url,
            )
        return '—'

    @admin.display(description='Önizləmə')
    def cover_preview(self, obj):
        if obj and obj.cover_image:
            return format_html(
                '<img src="{}" alt="" style="max-height:160px;border-radius:6px;border:1px solid #ccc" />',
                obj.cover_image.url,
            )
        return 'Qapaq şəkli yüklənməyib.'

    @admin.display(description='Fəsil')
    def chapter_count(self, obj):
        return obj.chapters.count()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if not change:
            messages.success(
                request,
                f'«{obj.title}» əlavə olundu. Aşağıda fəsil mətni yazıb yenidən saxlaya bilərsiniz.',
            )


class YoutubeTitleAdminMixin:
    class Media:
        js = ('api/admin_youtube_title.js',)


@admin.register(Chapter)
class ChapterAdmin(admin.ModelAdmin):
    form = ChapterAdminForm
    list_display = ('title', 'book', 'order', 'public_id', 'content_preview')
    list_filter = ('book',)
    search_fields = ('title', 'content', 'public_id', 'book__title')
    list_select_related = ('book',)
    autocomplete_fields = ('book',)
    ordering = ('book', 'order', 'id')
    fieldsets = (
        (
            None,
            {
                'fields': ('book', 'title', 'content', 'order', 'public_id'),
            },
        ),
    )

    @admin.display(description='Mətn')
    def content_preview(self, obj):
        text = (obj.content or '').replace('\n', ' ').strip()
        return (text[:80] + '…') if len(text) > 80 else text


class VideoChannelForm(forms.ModelForm):
    sync_playlists = forms.BooleanField(
        label='Playlistləri avtomatik yüklə (silsilə dərslər)',
        required=False,
        initial=True,
        help_text=(
            'Kanal /playlists linkindən bütün playlistləri silsilə kimi əlavə edir. '
            'Məs: https://www.youtube.com/@Abu_Zeyd_Habibli/playlists'
        ),
    )

    class Meta:
        model = VideoChannel
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['name'].required = False
        self.fields['name'].help_text = 'Boş buraxın — linkdən avtomatik dolacaq.'
        # Yenidən açanda default True qalsın
        self.fields['sync_playlists'].initial = True

    def clean(self):
        cleaned = super().clean()
        url = (cleaned.get('url') or '').strip()
        name = (cleaned.get('name') or '').strip()
        if url and not name:
            fetched = fetch_youtube_title(url)
            if fetched:
                cleaned['name'] = fetched
            else:
                self.add_error('name', 'Başlıq tapılmadı — əl ilə yazın və ya linki yoxlayın.')
        elif not name:
            self.add_error('name', 'Kanal adı və ya link lazımdır.')
        return cleaned


class VideoSeriesForm(forms.ModelForm):
    class Meta:
        model = VideoSeries
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].required = False
        self.fields['title'].help_text = 'Boş buraxın — playlist linkindən avtomatik dolacaq.'

    def clean(self):
        cleaned = super().clean()
        url = (cleaned.get('playlist_url') or '').strip()
        title = (cleaned.get('title') or '').strip()
        if url and not title:
            fetched = fetch_youtube_title(url)
            if fetched:
                cleaned['title'] = fetched
            else:
                self.add_error('title', 'Başlıq tapılmadı — əl ilə yazın və ya linki yoxlayın.')
        elif not title:
            self.add_error('title', 'Silsilə adı və ya playlist linki lazımdır.')
        return cleaned


class VideoLessonForm(forms.ModelForm):
    class Meta:
        model = VideoLesson
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['title'].required = False
        self.fields['title'].help_text = 'Boş buraxın — video linkindən avtomatik dolacaq.'

    def clean(self):
        cleaned = super().clean()
        url = (cleaned.get('url') or '').strip()
        title = (cleaned.get('title') or '').strip()
        if url and not title:
            fetched = fetch_youtube_title(url)
            if fetched:
                cleaned['title'] = fetched
            else:
                self.add_error('title', 'Başlıq tapılmadı — əl ilə yazın və ya linki yoxlayın.')
        elif not title:
            self.add_error('title', 'Dərs adı və ya video linki lazımdır.')
        return cleaned


class VideoLessonInline(YoutubeTitleAdminMixin, admin.StackedInline):
    model = VideoLesson
    form = VideoLessonForm
    extra = 0
    fields = ('url', 'title', 'order', 'is_published')
    classes = ('collapse',)
    verbose_name_plural = 'Dərslər (istəyə bağlı — playlist linki varsa lazım deyil)'


class VideoSeriesInline(YoutubeTitleAdminMixin, admin.TabularInline):
    model = VideoSeries
    form = VideoSeriesForm
    extra = 0
    fields = ('playlist_url', 'title', 'order', 'is_published')
    show_change_link = True
    verbose_name_plural = 'Silsilə dərslər (avtomatik yüklənə bilər)'


@admin.register(VideoChannel)
class VideoChannelAdmin(YoutubeTitleAdminMixin, admin.ModelAdmin):
    form = VideoChannelForm
    list_display = ('name', 'url', 'series_count', 'order', 'is_published', 'created_at')
    list_editable = ('order', 'is_published')
    list_filter = ('is_published',)
    search_fields = ('name', 'url', 'description')
    fields = ('url', 'name', 'sync_playlists', 'description', 'order', 'is_published')
    inlines = [VideoSeriesInline]
    actions = ['action_sync_playlists']

    @admin.display(description='Silsilə')
    def series_count(self, obj):
        return obj.series.count()

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if form.cleaned_data.get('sync_playlists'):
            result = sync_channel_playlists(obj)
            if result.get('error'):
                messages.warning(
                    request,
                    f'Playlist sinxronu: {result["error"]}',
                )
            else:
                messages.success(
                    request,
                    (
                        f'Playlistlər yükləndi: {result["total"]} tapıldı, '
                        f'{result["created"]} yeni silsilə, '
                        f'{result["updated"]} yeniləndi.'
                    ),
                )

    @admin.action(description='Seçilmiş kanallardan playlistləri yenilə')
    def action_sync_playlists(self, request, queryset):
        total_created = 0
        for ch in queryset:
            result = sync_channel_playlists(ch)
            if result.get('error'):
                messages.warning(request, f'{ch.name}: {result["error"]}')
            else:
                total_created += result['created']
                messages.success(
                    request,
                    f'{ch.name}: {result["total"]} playlist '
                    f'({result["created"]} yeni, {result["updated"]} yeniləndi)',
                )


@admin.register(VideoSeries)
class VideoSeriesAdmin(YoutubeTitleAdminMixin, admin.ModelAdmin):
    form = VideoSeriesForm
    list_display = ('title', 'channel', 'category', 'playlist_url', 'order', 'is_published', 'created_at')
    list_filter = ('is_published', 'category', 'channel')
    search_fields = ('title', 'description', 'playlist_url', 'channel__name')
    list_editable = ('order', 'is_published')
    fields = ('channel', 'playlist_url', 'title', 'category', 'description', 'order', 'is_published')
    inlines = [VideoLessonInline]
    actions = ['action_sync_lessons']

    @admin.action(description='Playlist dərslərini yüklə (videolar → dərslər)')
    def action_sync_lessons(self, request, queryset):
        from .audio import sync_series_lessons

        for series in queryset:
            result = sync_series_lessons(series)
            if result.get('error'):
                messages.warning(request, f'{series.title}: {result["error"]}')
            else:
                messages.success(
                    request,
                    f'{series.title}: {result["total"]} video '
                    f'({result["created"]} yeni, {result["updated"]} yeniləndi)',
                )


@admin.register(SupportMessage)
class SupportMessageAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'category',
        'contact',
        'is_read',
        'message_preview',
        'created_at',
    )
    list_filter = ('category', 'is_read', 'created_at')
    search_fields = ('name', 'contact', 'message')
    list_editable = ('is_read',)
    readonly_fields = ('created_at', 'app_version')
    ordering = ('-created_at',)

    @admin.display(description='Mesaj')
    def message_preview(self, obj):
        text = (obj.message or '').replace('\n', ' ').strip()
        return (text[:80] + '…') if len(text) > 80 else text


@admin.register(VideoLesson)
class VideoLessonAdmin(YoutubeTitleAdminMixin, admin.ModelAdmin):
    form = VideoLessonForm
    list_display = ('title', 'series', 'has_audio', 'order', 'is_published')
    list_filter = ('is_published', 'series__channel')
    search_fields = ('title', 'url', 'series__title', 'youtube_id')
    fields = ('series', 'url', 'title', 'youtube_id', 'audio_file', 'duration_seconds', 'order', 'is_published')
    actions = ['action_prepare_audio']

    @admin.display(boolean=True, description='Səs')
    def has_audio(self, obj):
        return bool(obj.audio_file)

    @admin.action(description='Səs faylını endir (media)')
    def action_prepare_audio(self, request, queryset):
        from .audio import ensure_audio_file

        for lesson in queryset:
            ok, err = ensure_audio_file(lesson)
            if ok:
                messages.success(request, f'{lesson.title}: səs hazırdır')
            else:
                messages.warning(request, f'{lesson.title}: {err}')


@admin.register(LiveTeacherCode)
class LiveTeacherCodeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'is_active', 'updated_at')
    list_editable = ('is_active',)
    search_fields = ('name', 'code')
    ordering = ('name', 'id')
    fields = ('name', 'code', 'is_active', 'created_at', 'updated_at')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(QuranMealNote)
class QuranMealNoteAdmin(admin.ModelAdmin):
    list_display = ('label', 'scope', 'surah', 'ayah', 'is_published', 'updated_at')
    list_filter = ('scope', 'is_published')
    search_fields = ('intro', 'message', 'author')
    list_editable = ('is_published',)
    ordering = ('surah', 'ayah')
    fields = (
        'scope',
        'surah',
        'ayah',
        'intro',
        'paragraphs',
        'message',
        'author',
        'footnotes',
        'is_published',
        'created_at',
        'updated_at',
    )
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Yer')
    def label(self, obj):
        if obj.scope == QuranMealNote.SCOPE_AYAH and obj.ayah:
            return f'{obj.surah}:{obj.ayah}'
        return f'Surə {obj.surah}'
