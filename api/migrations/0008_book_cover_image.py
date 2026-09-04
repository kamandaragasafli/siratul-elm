from django.db import migrations, models

import api.models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0007_videoseries_category'),
    ]

    operations = [
        migrations.AddField(
            model_name='book',
            name='cover_image',
            field=models.ImageField(
                blank=True,
                null=True,
                upload_to=api.models.book_cover_upload_to,
            ),
        ),
    ]
