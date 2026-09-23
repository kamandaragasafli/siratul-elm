# Generated manually for audio prefetch daily quota

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0018_book_page_direction'),
    ]

    operations = [
        migrations.AddField(
            model_name='videolesson',
            name='audio_fetch_attempted_at',
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text='Son prefetch / endirmə cəhdi (gündəlik kvota üçün)',
                null=True,
                verbose_name='Səs yükləmə cəhdi',
            ),
        ),
    ]
