"""
Production: YouTube kanallarını sil + ixlasla.com MP3 sync.

  python manage.py deploy_ixlasla
  python manage.py deploy_ixlasla --skip-sync   # yalnız YouTube sil
"""

from django.core.management.base import BaseCommand
from django.db.models import Q

from api.ixlasla import sync_ixlasla
from api.models import VideoChannel, VideoLesson


class Command(BaseCommand):
    help = 'YouTube dərslərini silir və ixlasla.com-dan MP3 sync edir'

    def add_arguments(self, parser):
        parser.add_argument(
            '--skip-sync',
            action='store_true',
            help='Yalnız YouTube sil, sync etmə',
        )
        parser.add_argument(
            '--teacher',
            default='',
            help='Sync filtri (müəllim)',
        )

    def handle(self, *args, **options):
        progress = lambda m: self.stdout.write(
            m.encode('ascii', 'replace').decode('ascii')
        )

        yt_ch = VideoChannel.objects.filter(
            Q(url__icontains='youtube.com') | Q(url__icontains='youtu.be')
        )
        n = yt_ch.count()
        if n:
            deleted = yt_ch.delete()
            self.stdout.write(self.style.WARNING(f'Deleted YouTube channels: {n} -> {deleted}'))
        else:
            self.stdout.write('No YouTube channels')

        leftover = VideoLesson.objects.filter(
            Q(youtube_id__gt='')
            | Q(url__icontains='youtube.com')
            | Q(url__icontains='youtu.be')
        ).exclude(remote_audio_url__gt='')
        if leftover.exists():
            self.stdout.write(self.style.WARNING(f'Deleted leftover YT lessons: {leftover.delete()}'))

        if options.get('skip_sync'):
            return

        teacher = (options.get('teacher') or '').strip() or None
        self.stdout.write(self.style.NOTICE('Syncing ixlasla.com ...'))
        stats = sync_ixlasla(
            teacher_filter=teacher,
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
