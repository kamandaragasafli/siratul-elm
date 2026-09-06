from django.db import models


def book_cover_upload_to(instance, filename: str) -> str:
    ext = (filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg')[:8]
    safe_id = (instance.public_id or 'book').replace('/', '-')[:80]
    return f'book-covers/{safe_id}.{ext}'


class Book(models.Model):
    LANGUAGE_CHOICES = [
        ('az', 'Azərbaycan'),
        ('ar', 'Ərəb'),
        ('en', 'İngilis'),
    ]
    SOURCE_CHOICES = [
        ('seed', 'Seed'),
        ('manual', 'Manual'),
        ('import', 'Import'),
        ('api', 'API'),
    ]

    public_id = models.CharField(max_length=120, unique=True, db_index=True)
    title = models.CharField(max_length=500)
    author = models.CharField(max_length=300, blank=True, default='')
    description = models.TextField(blank=True, default='')
    language = models.CharField(max_length=8, choices=LANGUAGE_CHOICES, default='az')
    cover_tone = models.PositiveSmallIntegerField(default=0)
    cover_image = models.ImageField(
        upload_to=book_cover_upload_to,
        blank=True,
        null=True,
    )
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='api')
    topics = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Chapter(models.Model):
    book = models.ForeignKey(Book, related_name='chapters', on_delete=models.CASCADE)
    public_id = models.CharField(max_length=120)
    title = models.CharField(max_length=500)
    content = models.TextField(blank=True, default='')
    blocks = models.JSONField(default=list, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        unique_together = [('book', 'public_id')]

    def __str__(self):
        return f'{self.book.title} — {self.title}'


class VideoChannel(models.Model):
    """Admin-dən əlavə olunan kanal — mobildə ad göstərilir."""

    name = models.CharField('Kanal adı', max_length=200)
    url = models.URLField(
        'Kanal / playlists linki',
        max_length=500,
        help_text=(
            'Məs: https://www.youtube.com/@Abu_Zeyd_Habibli/playlists — '
            'saxlayanda bütün playlistlər silsilə kimi yüklənir.'
        ),
    )
    description = models.CharField(max_length=400, blank=True, default='')
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'name']
        verbose_name = 'Video kanal'
        verbose_name_plural = 'Video kanallar'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.url and not (self.name or '').strip():
            from .youtube import fetch_youtube_title

            fetched = fetch_youtube_title(self.url)
            if fetched:
                self.name = fetched
        super().save(*args, **kwargs)


class VideoSeries(models.Model):
    """Kanalın silsiləsi — playlist linki kifayətdir."""

    CATEGORY_CHOICES = [
        ('aqida', 'Əqidə'),
        ('hadith', 'Hədis'),
        ('fiqh', 'Fiqh'),
        ('tafsir', 'Təfsir'),
        ('seerah', 'Sira'),
        ('general', 'Digər'),
    ]

    channel = models.ForeignKey(
        VideoChannel,
        related_name='series',
        on_delete=models.CASCADE,
        verbose_name='Kanal',
    )
    title = models.CharField('Silsilə adı', max_length=300)
    category = models.CharField(
        'Bölmə',
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='general',
        db_index=True,
    )
    description = models.CharField(max_length=500, blank=True, default='')
    playlist_url = models.URLField(
        'Playlist / playlists linki',
        max_length=500,
        blank=True,
        default='',
        help_text=(
            'Məs: https://www.youtube.com/playlist?list=... '
            'və ya https://www.youtube.com/@Kanal/playlists — '
            'dərsləri tək-tək əlavə etmək lazım deyil.'
        ),
    )
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Silsilə dərs'
        verbose_name_plural = 'Silsilə dərslər'

    def __str__(self):
        return f'{self.channel.name} — {self.title}'

    def save(self, *args, **kwargs):
        if self.playlist_url and not (self.title or '').strip():
            from .youtube import fetch_youtube_title

            fetched = fetch_youtube_title(self.playlist_url)
            if fetched:
                self.title = fetched
        if (self.category or 'general') == 'general' and (self.title or '').strip():
            from .lesson_categories import detect_series_category

            detected = detect_series_category(self.title)
            if detected != 'general':
                self.category = detected
        super().save(*args, **kwargs)


class VideoLesson(models.Model):
    """Playlist daxilindəki dərs — səs onlayn / endirmə üçün."""

    series = models.ForeignKey(
        VideoSeries,
        related_name='lessons',
        on_delete=models.CASCADE,
        verbose_name='Silsilə',
    )
    title = models.CharField('Dərs adı', max_length=300)
    url = models.URLField('Video linki', max_length=500, blank=True, default='')
    youtube_id = models.CharField(max_length=32, blank=True, default='', db_index=True)
    audio_file = models.FileField(
        'Səs faylı',
        upload_to='audio/%Y/%m/',
        blank=True,
        null=True,
        help_text='Endirilmiş audio — onlayn dinləmə və telefona yükləmə',
    )
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Dərs'
        verbose_name_plural = 'Dərslər'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.url and not (self.title or '').strip():
            from .youtube import fetch_youtube_title

            fetched = fetch_youtube_title(self.url)
            if fetched:
                self.title = fetched
        if self.url and not self.youtube_id:
            import re

            m = re.search(r'(?:v=|/shorts/|youtu\.be/)([\w-]{11})', self.url)
            if m:
                self.youtube_id = m.group(1)
        super().save(*args, **kwargs)


class SupportMessage(models.Model):
    """Mobil tətbiqdən gələn dəstək / yardım mesajları."""

    CATEGORY_CHOICES = [
        ('question', 'Sual'),
        ('problem', 'Problem'),
        ('suggestion', 'Təklif'),
        ('other', 'Digər'),
    ]

    name = models.CharField('Ad', max_length=120)
    contact = models.CharField(
        'Əlaqə',
        max_length=200,
        blank=True,
        default='',
        help_text='E-poçt və ya telefon (istəyə bağlı)',
    )
    category = models.CharField(
        'Kateqoriya',
        max_length=20,
        choices=CATEGORY_CHOICES,
        default='question',
    )
    message = models.TextField('Mesaj')
    app_version = models.CharField(max_length=40, blank=True, default='')
    is_read = models.BooleanField('Oxunub', default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Dəstək mesajı'
        verbose_name_plural = 'Dəstək mesajları'

    def __str__(self):
        preview = (self.message or '').replace('\n', ' ').strip()
        short = (preview[:48] + '…') if len(preview) > 48 else preview
        return f'{self.name}: {short}'


class TelegramLiveLesson(models.Model):
    """Telegram (və ya digər) canlı dərs cədvəli — mobil «Canlı» tab."""

    FORCE_STATUS_CHOICES = [
        ('', 'Avtomatik (vaxta görə)'),
        ('live', 'Məcburi canlı'),
        ('ended', 'Məcburi bitib'),
    ]

    title = models.CharField('Başlıq', max_length=300)
    teacher_name = models.CharField('Müəllim', max_length=120, blank=True, default='')
    description = models.CharField('Qısa təsvir', max_length=500, blank=True, default='')
    telegram_url = models.URLField(
        'Telegram linki',
        max_length=500,
        help_text='Qrup, kanal və ya canlı yayım linki (t.me/...)',
    )
    starts_at = models.DateTimeField('Başlanğıc')
    ends_at = models.DateTimeField('Bitmə')
    force_status = models.CharField(
        'Status override',
        max_length=10,
        choices=FORCE_STATUS_CHOICES,
        blank=True,
        default='',
    )
    order = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField('Yayınlı', default=True)
    # ── LiveKit tətbiq-daxili canlı yayım ──────────────────────────────────────
    livekit_room_name = models.CharField(
        'LiveKit Otaq adı',
        max_length=200,
        blank=True,
        default='',
        help_text=(
            'Boş saxlanılsa Telegram linki göstərilir. '
            'Doldurulduqda "Canlı Yayım" düyməsi tətbiq daxili LiveKit otağına qoşur.'
        ),
    )
    is_livekit_enabled = models.BooleanField(
        'LiveKit aktiv',
        default=False,
        help_text='İşarələnəndə LiveKit daxili yayım aktiv olur (Telegram linki əvəzinə).',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-starts_at', 'order', 'id']
        verbose_name = 'Telegram canlı dərs'
        verbose_name_plural = 'Telegram canlı dərslər'

    def __str__(self):
        return self.title

    def effective_status(self) -> str:
        from django.utils import timezone

        if self.force_status == 'live':
            return 'live'
        if self.force_status == 'ended':
            return 'ended'
        now = timezone.now()
        if now < self.starts_at:
            return 'scheduled'
        if now <= self.ends_at:
            return 'live'
        return 'ended'


class LiveTeacherCode(models.Model):
    """Canlı yayım üçün müəllim kodu — admin paneldən idarə olunur."""

    name = models.CharField('Müəllim adı', max_length=120)
    code = models.CharField(
        '6 rəqəmli kod',
        max_length=6,
        unique=True,
        help_text='Mobil tətbiqdə yayım açarkən daxil edilən kod.',
    )
    is_active = models.BooleanField('Aktiv', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name', 'id']
        verbose_name = 'Canlı yayım müəllimi'
        verbose_name_plural = 'Canlı yayım müəllimləri'

    def __str__(self):
        return f'{self.name} ({self.code})'

    def save(self, *args, **kwargs):
        self.code = (self.code or '').strip()
        super().save(*args, **kwargs)


class QuranMealNote(models.Model):
    """Qurani Kərim məal — qısa məlumat (surə / ayə) + haşiyələr / hökmlər."""

    SCOPE_SURAH = 'surah'
    SCOPE_AYAH = 'ayah'
    SCOPE_CHOICES = [
        (SCOPE_SURAH, 'Surə'),
        (SCOPE_AYAH, 'Ayə'),
    ]

    scope = models.CharField('Səviyyə', max_length=8, choices=SCOPE_CHOICES, default=SCOPE_SURAH)
    surah = models.PositiveSmallIntegerField('Surə №')
    ayah = models.PositiveSmallIntegerField(
        'Ayə №',
        null=True,
        blank=True,
        help_text='Yalnız ayə səviyyəsində doldurun.',
    )
    intro = models.TextField('Giriş', blank=True, default='')
    paragraphs = models.JSONField(
        'Əlavə abzaslar',
        default=list,
        blank=True,
        help_text='Mətn sətirləri siyahısı (JSON massiv).',
    )
    summaries = models.JSONField(
        'Ayə xülasələri',
        default=list,
        blank=True,
        help_text='[{"from":1,"to":15,"title":"...","text":"..."}] — ayə aralıqları.',
    )
    message = models.TextField('Əsas mesaj', blank=True, default='')
    author = models.CharField('Müəllif', max_length=200, blank=True, default='')
    footnotes = models.JSONField(
        'Haşiyələr / hökmlər',
        default=list,
        blank=True,
        help_text='[{"n":1,"text":"...","kind":"note"|"hukm"}]. Mətndə [1] yazın.',
    )
    is_published = models.BooleanField('Yayınlı', default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['surah', 'ayah', 'id']
        verbose_name = 'Məal qısa məlumat'
        verbose_name_plural = 'Məal qısa məlumatlar'
        constraints = [
            models.UniqueConstraint(
                fields=['surah'],
                condition=models.Q(ayah__isnull=True),
                name='uniq_quran_meal_note_surah',
            ),
            models.UniqueConstraint(
                fields=['surah', 'ayah'],
                condition=models.Q(ayah__isnull=False),
                name='uniq_quran_meal_note_ayah',
            ),
        ]

    def __str__(self):
        if self.scope == self.SCOPE_AYAH and self.ayah:
            return f'{self.surah}:{self.ayah}'
        return f'Surə {self.surah}'

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.surah < 1 or self.surah > 114:
            raise ValidationError({'surah': 'Surə 1–114 arası olmalıdır.'})
        if self.scope == self.SCOPE_SURAH:
            self.ayah = None
        elif self.scope == self.SCOPE_AYAH:
            if not self.ayah or self.ayah < 1:
                raise ValidationError({'ayah': 'Ayə nömrəsi mütləqdir.'})

    def save(self, *args, **kwargs):
        if self.scope == self.SCOPE_SURAH:
            self.ayah = None
        if not isinstance(self.paragraphs, list):
            self.paragraphs = []
        if not isinstance(self.summaries, list):
            self.summaries = []
        if not isinstance(self.footnotes, list):
            self.footnotes = []
        super().save(*args, **kwargs)

    def to_pack_entry(self) -> dict:
        entry: dict = {}
        if (self.intro or '').strip():
            entry['intro'] = self.intro.strip()
        paras = []
        for p in self.paragraphs or []:
            text = str(p or '').strip()
            if text:
                paras.append(text)
        if paras:
            entry['paragraphs'] = paras
        summaries = []
        for raw in self.summaries or []:
            if not isinstance(raw, dict):
                continue
            try:
                frm = int(raw.get('from'))
                to = int(raw.get('to'))
            except (TypeError, ValueError):
                continue
            text = str(raw.get('text') or '').strip()
            if frm < 1 or to < frm or not text:
                continue
            item = {'from': frm, 'to': to, 'text': text}
            title = str(raw.get('title') or '').strip()
            if title:
                item['title'] = title
            summaries.append(item)
        if summaries:
            summaries.sort(key=lambda x: (x['from'], x['to']))
            entry['summaries'] = summaries
        if (self.message or '').strip():
            entry['message'] = self.message.strip()
        if (self.author or '').strip():
            entry['author'] = self.author.strip()
        notes = []
        for raw in self.footnotes or []:
            if not isinstance(raw, dict):
                continue
            try:
                n = int(raw.get('n'))
            except (TypeError, ValueError):
                continue
            text = str(raw.get('text') or '').strip()
            if n < 1 or not text:
                continue
            kind = str(raw.get('kind') or 'note').strip().lower()
            if kind not in ('note', 'hukm'):
                kind = 'note'
            notes.append({'n': n, 'text': text, 'kind': kind})
        if notes:
            notes.sort(key=lambda x: x['n'])
            entry['footnotes'] = notes
        return entry
