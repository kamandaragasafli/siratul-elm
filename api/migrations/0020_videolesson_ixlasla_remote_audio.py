from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0019_videolesson_audio_fetch_attempted_at'),
    ]

    operations = [
        migrations.AddField(
            model_name='videolesson',
            name='ixlasla_id',
            field=models.PositiveIntegerField(
                blank=True,
                db_index=True,
                help_text='ixlasla.com API dərs id — sync üçün',
                null=True,
                unique=True,
                verbose_name='ixlasla dərs ID',
            ),
        ),
        migrations.AddField(
            model_name='videolesson',
            name='remote_audio_url',
            field=models.URLField(
                blank=True,
                default='',
                help_text='Birbaşa MP3 (məs. Backblaze) — YouTube olmadan dinləmə',
                max_length=800,
                verbose_name='Uzaq səs URL',
            ),
        ),
    ]
