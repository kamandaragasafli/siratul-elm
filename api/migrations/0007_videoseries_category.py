from django.db import migrations, models

from api.lesson_categories import detect_series_category


def assign_series_categories(apps, schema_editor):
    VideoSeries = apps.get_model('api', 'VideoSeries')
    for series in VideoSeries.objects.all().iterator():
        detected = detect_series_category(series.title)
        if series.category != detected:
            series.category = detected
            series.save(update_fields=['category'])


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0006_supportmessage'),
    ]

    operations = [
        migrations.AddField(
            model_name='videoseries',
            name='category',
            field=models.CharField(
                choices=[
                    ('aqida', 'Əqidə'),
                    ('hadith', 'Hədis'),
                    ('fiqh', 'Fiqh'),
                    ('tafsir', 'Təfsir'),
                    ('seerah', 'Sira'),
                    ('general', 'Digər'),
                ],
                db_index=True,
                default='general',
                max_length=20,
                verbose_name='Bölmə',
            ),
        ),
        migrations.RunPython(assign_series_categories, migrations.RunPython.noop),
    ]
