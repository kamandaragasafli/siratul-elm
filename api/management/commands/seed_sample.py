from django.core.management.base import BaseCommand

from api.models import Book, Chapter


class Command(BaseCommand):
    help = 'Add sample book for API testing'

    def handle(self, *args, **options):
        book, created = Book.objects.get_or_create(
            public_id='api-welcome',
            defaults={
                'title': 'API salam - Sirac',
                'author': 'Backend',
                'description': 'Bu kitab Django API-den gelir. Internet elaesi isleyir.',
                'language': 'az',
                'cover_tone': 2,
                'source': 'api',
                'topics': ['api', 'test'],
                'is_published': True,
            },
        )
        if created or not book.chapters.exists():
            Chapter.objects.update_or_create(
                book=book,
                public_id='ch-1',
                defaults={
                    'title': 'Birinci fasıl',
                    'content': (
                        'Salam. Bu metn Django REST API vasitesiyle mobil tetbiqe '
                        'sebeke / internet uzerinden gelir.\n\n'
                        'Novbeti merhelelerde kitablar, autentifikasiya ve diger '
                        'funksiyalar elave olunacaq.'
                    ),
                    'order': 0,
                },
            )
            self.stdout.write(self.style.SUCCESS('Sample book created: api-welcome'))
        else:
            self.stdout.write('Sample book already exists.')
