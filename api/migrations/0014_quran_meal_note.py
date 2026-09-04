from django.db import migrations, models


def seed_mursalat(apps, schema_editor):
    QuranMealNote = apps.get_model('api', 'QuranMealNote')
    if QuranMealNote.objects.filter(surah=77, ayah__isnull=True).exists():
        return
    QuranMealNote.objects.create(
        scope='surah',
        surah=77,
        ayah=None,
        intro=(
            'Mürsələt surəsi insana qaçdığı böyük həqiqəti xatırladır: '
            'Bu dünya sonsuz bir yol deyil, hesab gününə aparan qısa bir səfərdir.'
        ),
        paragraphs=[
            'Səndən əvvəl güclü millətlər gəldi və getdi. Sən də yoxdan yaradıldın '
            'və bir gün yenidən dirildiləcəksən. O gün yalanlayanların bəhanələri '
            'susacaq, təqva sahibləri isə Rəbbinin vədinə qovuşacaq.'
        ],
        message='İnsan Qiyaməti unutsa da, Qiyamət insanı unutmayıb.',
        author='Yunus Alihuseynli',
        footnotes=[],
        is_published=True,
    )


def unseed_mursalat(apps, schema_editor):
    QuranMealNote = apps.get_model('api', 'QuranMealNote')
    QuranMealNote.objects.filter(surah=77, ayah__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0013_live_teacher_code'),
    ]

    operations = [
        migrations.CreateModel(
            name='QuranMealNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scope', models.CharField(choices=[('surah', 'Surə'), ('ayah', 'Ayə')], default='surah', max_length=8, verbose_name='Səviyyə')),
                ('surah', models.PositiveSmallIntegerField(verbose_name='Surə №')),
                ('ayah', models.PositiveSmallIntegerField(blank=True, help_text='Yalnız ayə səviyyəsində doldurun.', null=True, verbose_name='Ayə №')),
                ('intro', models.TextField(blank=True, default='', verbose_name='Giriş')),
                ('paragraphs', models.JSONField(blank=True, default=list, help_text='Mətn sətirləri siyahısı (JSON massiv).', verbose_name='Əlavə abzaslar')),
                ('message', models.TextField(blank=True, default='', verbose_name='Əsas mesaj')),
                ('author', models.CharField(blank=True, default='', max_length=200, verbose_name='Müəllif')),
                ('footnotes', models.JSONField(blank=True, default=list, help_text='[{"n":1,"text":"...","kind":"note"|"hukm"}]. Mətndə [1] yazın.', verbose_name='Haşiyələr / hökmlər')),
                ('is_published', models.BooleanField(default=True, verbose_name='Yayınlı')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Məal qısa məlumat',
                'verbose_name_plural': 'Məal qısa məlumatlar',
                'ordering': ['surah', 'ayah', 'id'],
            },
        ),
        migrations.AddConstraint(
            model_name='quranmealnote',
            constraint=models.UniqueConstraint(condition=models.Q(('ayah__isnull', True)), fields=('surah',), name='uniq_quran_meal_note_surah'),
        ),
        migrations.AddConstraint(
            model_name='quranmealnote',
            constraint=models.UniqueConstraint(condition=models.Q(('ayah__isnull', False)), fields=('surah', 'ayah'), name='uniq_quran_meal_note_ayah'),
        ),
        migrations.RunPython(seed_mursalat, unseed_mursalat),
    ]
