from django.db import migrations, models


def seed_mursalat_summaries(apps, schema_editor):
    QuranMealNote = apps.get_model('api', 'QuranMealNote')
    note = QuranMealNote.objects.filter(surah=77, ayah__isnull=True).first()
    if not note:
        return
    changed = False
    if not (note.intro or '').strip():
        note.intro = (
            'Mürsələt surəsi insana qaçdığı böyük həqiqəti xatırladır: '
            'Bu dünya sonsuz bir yol deyil, hesab gününə aparan qısa bir səfərdir.'
        )
        changed = True
    if not note.paragraphs:
        note.paragraphs = [
            'Səndən əvvəl güclü millətlər gəldi və getdi. Sən də yoxdan yaradıldın '
            'və bir gün yenidən dirildiləcəksən. O gün yalanlayanların bəhanələri '
            'susacaq, təqva sahibləri isə Rəbbinin vədinə qovuşacaq.'
        ]
        changed = True
    if not note.summaries:
        note.summaries = [
            {
                'from': 1,
                'to': 15,
                'title': 'Andlar və xəbərdarlıq',
                'text': (
                    'Ardıcıl andlarla Qiyamət həqiqəti möhkəmləndirilir; '
                    'yalanlayanlar üçün ağır nəticə bildirilir.'
                ),
            },
            {
                'from': 16,
                'to': 28,
                'title': 'Keçmiş ümmətlər və yaradılış',
                'text': (
                    'Əvvəlki millətlərin aqibəti və insanın yaradılışı xatırladılır — '
                    'dirilmənin mümkünlüyü göstərilir.'
                ),
            },
            {
                'from': 29,
                'to': 40,
                'title': 'Cəhənnəm səhnəsi',
                'text': (
                    'Yalanlayanların cəhənnəmdəki vəziyyəti və bəhanələrinin '
                    'boşa çıxması təsvir olunur.'
                ),
            },
            {
                'from': 41,
                'to': 50,
                'title': 'Təqva sahibləri',
                'text': (
                    'Müttəqilərin mükafatı və son xəbərdarlıq — '
                    'Quranı inkar edənlərin aqibəti.'
                ),
            },
        ]
        changed = True
    if changed:
        note.save()


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0015_remove_seed_live_lessons'),
    ]

    operations = [
        migrations.AddField(
            model_name='quranmealnote',
            name='summaries',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='[{"from":1,"to":15,"title":"...","text":"..."}] — ayə aralıqları.',
                verbose_name='Ayə xülasələri',
            ),
        ),
        migrations.RunPython(seed_mursalat_summaries, noop_reverse),
    ]
