from django.db import migrations


def remove_seed_live_lessons(apps, schema_editor):
    TelegramLiveLesson = apps.get_model('api', 'TelegramLiveLesson')
    TelegramLiveLesson.objects.filter(livekit_room_name__startswith='sirac-').delete()
    TelegramLiveLesson.objects.filter(livekit_room_name='preview-room').delete()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('api', '0014_quran_meal_note'),
    ]

    operations = [
        migrations.RunPython(remove_seed_live_lessons, noop_reverse),
    ]
