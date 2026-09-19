from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0017_book_pdf_format'),
    ]

    operations = [
        migrations.AddField(
            model_name='book',
            name='page_direction',
            field=models.CharField(
                choices=[('ltr', 'Soldan sağa (LTR)'), ('rtl', 'Sağdan sola (RTL)')],
                default='ltr',
                help_text=(
                    'PDF kitab çevirmə istiqaməti. Ərəb kitablarında «Sağdan sola» seçin — '
                    'səhifə çevirmə tərs olur.'
                ),
                max_length=3,
            ),
        ),
    ]
