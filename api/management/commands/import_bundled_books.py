from django.core.management.base import BaseCommand

from api.book_import import import_all_bundled_books


class Command(BaseCommand):
    help = 'Import Sirac/assets/books/*.json into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-update',
            action='store_true',
            help='Skip books that already exist (do not overwrite)',
        )
        parser.add_argument(
            '--overwrite-chapters',
            action='store_true',
            help='Replace existing chapter text from JSON (wipes admin edits)',
        )

    def handle(self, *args, **options):
        result = import_all_bundled_books(
            update_existing=not options['no_update'],
            overwrite_chapters=options['overwrite_chapters'],
        )
        if not result.get('ok'):
            self.stderr.write(self.style.ERROR(result.get('error') or 'Import failed'))
            return

        self.stdout.write(f"Qovluq: {result['directory']}")
        for item in result['results']:
            if not item.get('ok'):
                self.stdout.write(self.style.ERROR(f"  ✗ {item.get('file')}: {item.get('error')}"))
            elif item.get('skipped'):
                self.stdout.write(f"  · atlandı: {item['title']}")
            elif item.get('created'):
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  + {item['title']} ({item['chapters']} fəsil)"
                    )
                )
            else:
                note = 'fəsillər yazıldı' if item.get('chapters_written') else 'mətn saxlanıldı'
                self.stdout.write(
                    self.style.WARNING(
                        f"  ~ {item['title']} ({item['chapters']} fəsil, {note})"
                    )
                )
        self.stdout.write(
            self.style.SUCCESS(f"Hazır: {result['imported']}/{result['total']} kitab")
        )
