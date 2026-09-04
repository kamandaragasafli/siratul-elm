from rest_framework import serializers

from .models import Book, Chapter, SupportMessage, TelegramLiveLesson, VideoChannel, VideoLesson, VideoSeries


def book_cover_url(book: Book, request) -> str | None:
    if not book.cover_image:
        return None
    url = book.cover_image.url
    if request is not None:
        return request.build_absolute_uri(url)
    return url


class ChapterSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='public_id')

    class Meta:
        model = Chapter
        fields = ['id', 'title', 'content', 'blocks']


class BookSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='public_id')
    coverTone = serializers.IntegerField(source='cover_tone')
    coverUrl = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', format='iso-8601')
    chapters = ChapterSerializer(many=True, read_only=True)

    class Meta:
        model = Book
        fields = [
            'id',
            'title',
            'author',
            'description',
            'language',
            'coverTone',
            'coverUrl',
            'chapters',
            'createdAt',
            'source',
            'topics',
        ]

    def get_coverUrl(self, obj):
        return book_cover_url(obj, self.context.get('request'))


class BookListSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='public_id')
    coverTone = serializers.IntegerField(source='cover_tone')
    coverUrl = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', format='iso-8601')
    chapterCount = serializers.SerializerMethodField()

    class Meta:
        model = Book
        fields = [
            'id',
            'title',
            'author',
            'description',
            'language',
            'coverTone',
            'coverUrl',
            'createdAt',
            'source',
            'topics',
            'chapterCount',
        ]

    def get_chapterCount(self, obj):
        return obj.chapters.count()

    def get_coverUrl(self, obj):
        return book_cover_url(obj, self.context.get('request'))


class VideoLessonSerializer(serializers.ModelSerializer):
    hasAudio = serializers.SerializerMethodField()
    durationSeconds = serializers.IntegerField(source='duration_seconds', allow_null=True)
    sizeBytes = serializers.SerializerMethodField()

    class Meta:
        model = VideoLesson
        fields = ['id', 'title', 'url', 'order', 'hasAudio', 'durationSeconds', 'sizeBytes']

    def get_hasAudio(self, obj):
        return bool(obj.audio_file)

    def get_sizeBytes(self, obj):
        from .audio import lesson_audio_size_bytes

        return lesson_audio_size_bytes(obj)


class VideoSeriesSerializer(serializers.ModelSerializer):
    lessonCount = serializers.SerializerMethodField()
    playlistUrl = serializers.CharField(source='playlist_url', allow_blank=True)
    channelId = serializers.IntegerField(source='channel_id', read_only=True)
    channelName = serializers.CharField(source='channel.name', read_only=True)

    class Meta:
        model = VideoSeries
        fields = [
            'id',
            'title',
            'description',
            'playlistUrl',
            'order',
            'category',
            'lessonCount',
            'channelId',
            'channelName',
        ]

    def get_lessonCount(self, obj):
        return obj.lessons.filter(is_published=True).count()


class VideoSeriesBriefSerializer(serializers.ModelSerializer):
    lessonCount = serializers.SerializerMethodField()
    channelId = serializers.IntegerField(source='channel_id', read_only=True)
    channelName = serializers.CharField(source='channel.name', read_only=True)

    class Meta:
        model = VideoSeries
        fields = ['id', 'title', 'category', 'order', 'lessonCount', 'channelId', 'channelName']

    def get_lessonCount(self, obj):
        return obj.lessons.filter(is_published=True).count()


class VideoSeriesDetailSerializer(serializers.ModelSerializer):
    lessons = serializers.SerializerMethodField()
    playlistUrl = serializers.CharField(source='playlist_url', allow_blank=True)
    channelId = serializers.IntegerField(source='channel_id', read_only=True)
    channelName = serializers.CharField(source='channel.name', read_only=True)

    class Meta:
        model = VideoSeries
        fields = [
            'id',
            'title',
            'description',
            'playlistUrl',
            'order',
            'category',
            'channelId',
            'channelName',
            'lessons',
        ]

    def get_lessons(self, obj):
        qs = obj.lessons.filter(is_published=True)
        return VideoLessonSerializer(qs, many=True).data


class VideoChannelSerializer(serializers.ModelSerializer):
    seriesCount = serializers.SerializerMethodField()

    class Meta:
        model = VideoChannel
        fields = ['id', 'name', 'url', 'description', 'seriesCount']

    def get_seriesCount(self, obj):
        return obj.series.filter(is_published=True).count()


class VideoChannelDetailSerializer(serializers.ModelSerializer):
    series = serializers.SerializerMethodField()

    class Meta:
        model = VideoChannel
        fields = ['id', 'name', 'url', 'description', 'series']

    def get_series(self, obj):
        qs = obj.series.filter(is_published=True)
        return VideoSeriesSerializer(qs, many=True).data


class SupportMessageCreateSerializer(serializers.ModelSerializer):
    appVersion = serializers.CharField(
        source='app_version',
        required=False,
        allow_blank=True,
        max_length=40,
        default='',
    )

    class Meta:
        model = SupportMessage
        fields = ['name', 'contact', 'category', 'message', 'appVersion']

    def validate_name(self, value):
        name = (value or '').strip()
        if len(name) < 2:
            raise serializers.ValidationError('Ad ən azı 2 simvol olmalıdır.')
        return name

    def validate_message(self, value):
        text = (value or '').strip()
        if len(text) < 10:
            raise serializers.ValidationError('Mesaj ən azı 10 simvol olmalıdır.')
        if len(text) > 4000:
            raise serializers.ValidationError('Mesaj çox uzundur (maks. 4000).')
        return text

    def validate_category(self, value):
        allowed = {c[0] for c in SupportMessage.CATEGORY_CHOICES}
        if value not in allowed:
            raise serializers.ValidationError('Kateqoriya yanlışdır.')
        return value


class QuranQACreateSerializer(serializers.Serializer):
    """Qarilər bələdçisindən birbaşa sual — Telegram qrupuna yönləndirilir."""

    name = serializers.CharField(max_length=120)
    contact = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=200,
        default='',
    )
    message = serializers.CharField()
    appVersion = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=40,
        default='',
    )

    def validate_name(self, value):
        name = (value or '').strip()
        if len(name) < 2:
            raise serializers.ValidationError('Ad ən azı 2 simvol olmalıdır.')
        return name

    def validate_message(self, value):
        text = (value or '').strip()
        if not text:
            raise serializers.ValidationError('Sual yazın.')
        if len(text) > 4000:
            raise serializers.ValidationError('Sual çox uzundur (maks. 4000).')
        return text


class TelegramLiveLessonSerializer(serializers.ModelSerializer):
    teacherName = serializers.CharField(source='teacher_name', allow_blank=True)
    telegramUrl = serializers.URLField(source='telegram_url')
    startsAt = serializers.DateTimeField(source='starts_at', format='iso-8601')
    endsAt = serializers.DateTimeField(source='ends_at', format='iso-8601')
    status = serializers.SerializerMethodField()
    livekitRoomName = serializers.CharField(source='livekit_room_name', allow_blank=True)
    isLivekitEnabled = serializers.BooleanField(source='is_livekit_enabled')

    class Meta:
        model = TelegramLiveLesson
        fields = [
            'id',
            'title',
            'teacherName',
            'description',
            'telegramUrl',
            'startsAt',
            'endsAt',
            'status',
            'order',
            'livekitRoomName',
            'isLivekitEnabled',
        ]

    def get_status(self, obj):
        return obj.effective_status()
