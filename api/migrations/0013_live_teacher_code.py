from django.db import migrations, models


def seed_demo_teacher_code(apps, schema_editor):
    LiveTeacherCode = apps.get_model('api', 'LiveTeacherCode')
    if not LiveTeacherCode.objects.filter(code='847291').exists():
        LiveTeacherCode.objects.create(
            name='Müəllim',
            code='847291',
            is_active=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0012_default_live_lessons'),
    ]

    operations = [
        migrations.CreateModel(
            name='LiveTeacherCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=120, verbose_name='Müəllim adı')),
                (
                    'code',
                    models.CharField(
                        help_text='Mobil tətbiqdə yayım açarkən daxil edilən kod.',
                        max_length=6,
                        unique=True,
                        verbose_name='6 rəqəmli kod',
                    ),
                ),
                ('is_active', models.BooleanField(default=True, verbose_name='Aktiv')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Canlı yayım müəllimi',
                'verbose_name_plural': 'Canlı yayım müəllimləri',
                'ordering': ['name', 'id'],
            },
        ),
        migrations.RunPython(seed_demo_teacher_code, migrations.RunPython.noop),
    ]
