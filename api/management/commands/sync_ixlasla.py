"""
ixlasla.com-dan hazır MP3 dərsləri sync edir.

  python manage.py sync_ixlasla
  python manage.py sync_ixlasla --teacher "Emin Hacıyev"
  python manage.py sync_ixlasla --split-teachers
"""

from django.core.management.base import BaseCommand

from api.ixlasla import split_existing_by_teacher, sync_ixlasla


class Command(BaseCommand):
    help = 'ixlasla.com API-dən audio dərsləri çəkir (birbaşa MP3 URL)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--teacher',
            default='',
            help='Müəllim adı filtri (qismən uyğunluq)',
        )
        parser.add_argument(
            '--series',
            default='',
            help='Silsilə adı filtri (qismən uyğunluq)',
        )
        parser.add_argument(
            '--max-lessons',
            type=int,
            default=None,
            help='Maksimum dərs sayı (test üçün)',
        )
        parser.add_argument(
            '--split-teachers',
            action='store_true',
            help='Movcud silsilələri müəllim kanallarına ayır (sync etmədən)',
        )

    def handle(self, *args, **options):
        progress = lambda m: self.stdout.write(
            m.encode('ascii', 'replace').decode('ascii')
        )

        if options.get('split_teachers'):
            self.stdout.write(self.style.NOTICE('Split by teacher...'))
            stats = split_existing_by_teacher(progress=progress)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Done: moved {stats["moved"]}, '
                    f'renamed {stats["renamed"]}, '
                    f'channels {stats["channels"]}'
                )
            )
            return

        teacher = (options.get('teacher') or '').strip() or None
        series = (options.get('series') or '').strip() or None
        max_lessons = options.get('max_lessons')

        self.stdout.write(self.style.NOTICE('ixlasla.com sync baslayir...'))
        stats = sync_ixlasla(
            teacher_filter=teacher,
            series_filter=series,
            max_lessons=max_lessons,
            progress=progress,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Done: +{stats["lessons_created"]} lessons, '
                f'updated {stats["lessons_updated"]}, '
                f'series +{stats["series_created"]}, '
                f'errors {len(stats["errors"])}'
            )
        )
        for err in stats['errors'][:20]:
            self.stdout.write(self.style.WARNING(err))
