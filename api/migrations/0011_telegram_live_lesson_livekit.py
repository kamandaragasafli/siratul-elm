from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0010_telegram_live_lesson'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegramlivelesson',
            name='livekit_room_name',
            field=models.CharField(
                blank=True,
                default='',
                help_text=(
                    'Boş saxlanılsa Telegram linki göstərilir. '
                    'Doldurulduqda "Canlı Yayım" düyməsi tətbiq daxili LiveKit otağına qoşur.'
                ),
                max_length=200,
                verbose_name='LiveKit Otaq adı',
            ),
        ),
        migrations.AddField(
            model_name='telegramlivelesson',
            name='is_livekit_enabled',
            field=models.BooleanField(
                default=False,
                help_text='İşarələnəndə LiveKit daxili yayım aktiv olur (Telegram linki əvəzinə).',
                verbose_name='LiveKit aktiv',
            ),
        ),
    ]
