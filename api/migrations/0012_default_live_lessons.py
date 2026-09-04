"""Default canlı yayım dərsləri — tələbələr dərhal qoşula bilsin."""

from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def seed_default_live_lessons(apps, schema_editor):
    TelegramLiveLesson = apps.get_model('api', 'TelegramLiveLesson')
    if TelegramLiveLesson.objects.filter(livekit_room_name__startswith='sirac-').exists():
        return

    now = timezone.now()
    defaults = [
        {
            'title': 'Fiqh — canlı sual-cavab',
            'teacher_name': 'Müəllim',
            'description': 'Gündəlik fiqh suallarına canlı cavab.',
            'telegram_url': 'https://t.me/sirac_app',
            'livekit_room_name': 'sirac-fiqh',
            'force_status': 'live',
            'order': 1,
        },
        {
            'title': 'Quran təfsiri',
            'teacher_name': 'Müəllim',
            'description': 'Həftəlik surə təfsiri — canlı yayım.',
            'telegram_url': 'https://t.me/sirac_app',
            'livekit_room_name': 'sirac-tafsir',
            'force_status': 'live',
            'order': 2,
        },
        {
            'title': 'Əqidə dərsi',
            'teacher_name': 'Müəllim',
            'description': 'Əsas əqidə mövzuları — tələbələr dinləyə bilər.',
            'telegram_url': 'https://t.me/sirac_app',
            'livekit_room_name': 'sirac-aqida',
            'force_status': 'live',
            'order': 3,
        },
    ]

    for item in defaults:
        TelegramLiveLesson.objects.create(
            title=item['title'],
            teacher_name=item['teacher_name'],
            description=item['description'],
            telegram_url=item['telegram_url'],
            livekit_room_name=item['livekit_room_name'],
            is_livekit_enabled=True,
            force_status=item['force_status'],
            starts_at=now - timedelta(hours=1),
            ends_at=now + timedelta(days=7),
            order=item['order'],
            is_published=True,
        )


def unseed_default_live_lessons(apps, schema_editor):
    TelegramLiveLesson = apps.get_model('api', 'TelegramLiveLesson')
    TelegramLiveLesson.objects.filter(livekit_room_name__startswith='sirac-').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0011_telegram_live_lesson_livekit'),
    ]

    operations = [
        migrations.RunPython(seed_default_live_lessons, unseed_default_live_lessons),
    ]
