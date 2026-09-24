# Generated manually for PushDevice + TelegramLiveLesson.push_notified_at

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0020_videolesson_ixlasla_remote_audio'),
    ]

    operations = [
        migrations.AddField(
            model_name='telegramlivelesson',
            name='push_notified_at',
            field=models.DateTimeField(
                blank=True,
                help_text='Yayım başlayanda son push göndərilmə vaxtı (təkrar spam olmasın).',
                null=True,
                verbose_name='Push bildiriş vaxtı',
            ),
        ),
        migrations.CreateModel(
            name='PushDevice',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(db_index=True, max_length=255, unique=True)),
                ('platform', models.CharField(blank=True, default='', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Push cihaz',
                'verbose_name_plural': 'Push cihazlar',
                'ordering': ['-updated_at'],
            },
        ),
    ]
