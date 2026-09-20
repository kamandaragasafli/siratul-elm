"""
Playlist-lərdən VideoLesson sətirlərini SQLite-a sync edir.

Nümunə:
  python manage.py sync_video_lessons
  python manage.py sync_video_lessons --only-empty --limit 20
  python manage.py sync_video_lessons --series 12
  python manage.py sync_video_lessons --delay 3
"""

from __future__ import annotations

import random
import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.utils import timezone

from api.audio import sync_series_lessons
from api.models import VideoSeries
from api.ytdlp_opts import is_blocking_ytdlp_error


class Command(BaseCommand):
    help = 'YouTube playlist-lərindən dərsləri SQLite-a (VideoLesson) yükləyir'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delay',
            type=float,
            default=3.0,
            help='Silsilələr arası gözləmə (saniyə, default 3)',
        )
        parser.add_argument(
            '--jitter',
            type=float,
            default=2.0,
            help='Əlavə təsadüfi gecikmə üst həddi (0..jitter, default 2)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Maksimum silsilə sayı (0 = hamısı)',
        )
        parser.add_argument(
            '--only-empty',
            action='store_true',
            help='Yalnız hələ dərsı olmayan silsilələr',
        )
        parser.add_argument(
            '--series',
            type=str,
            default='',
            help='Yalnız bu silsilə (id və ya title)',
        )

    def handle(self, *args, **options):
        delay = max(0.0, float(options['delay']))
        jitter = max(0.0, float(options['jitter']))
        limit = int(options['limit'] or 0)
        only_empty = bool(options['only_empty'])
        series_key = (options['series'] or '').strip()

        qs = (
            VideoSeries.objects.exclude(playlist_url='')
            .annotate(lesson_count=Count('lessons'))
            .select_related('channel')
            .order_by('channel_id', 'order', 'id')
        )

        if series_key:
            series = self._resolve_series(series_key)
            qs = qs.filter(pk=series.pk)
            self.stdout.write(f'Silsilə: [{series.pk}] {series.title}')

        if only_empty:
            qs = qs.filter(lesson_count=0)

        if limit > 0:
            qs = qs[:limit]

        series_list = list(qs)
        total = len(series_list)
        if total == 0:
            self.stdout.write(self.style.WARNING('Sync ediləcək silsilə yoxdur.'))
            return

        self.stdout.write(
            f'{total} silsilə — delay={delay}s jitter=0..{jitter}s only_empty={only_empty}'
        )

        started = timezone.now()
        created_total = 0
        updated_total = 0
        ok_count = 0
        fail_count = 0
        consecutive_blocking = 0

        for i, series in enumerate(series_list, start=1):
            label = (
                f'[{i}/{total}] id={series.pk} '
                f'«{series.channel.name} — {series.title[:50]}»'
            )
            self.stdout.write(f'{label} …')
            self.stdout.flush()

            result = sync_series_lessons(series)
            err = result.get('error')
            if err:
                fail_count += 1
                self.stdout.write(self.style.ERROR(f'  FAIL — {err}'))
                self.stdout.flush()
                if is_blocking_ytdlp_error(err):
                    consecutive_blocking += 1
                else:
                    consecutive_blocking = 0
                if consecutive_blocking >= 3:
                    self.stderr.write(
                        self.style.ERROR(
                            '\nArdıcıl 3 blok xətası. Proses dayandırıldı — '
                            'cookies / bot yoxlaması problemi ola bilər.'
                        )
                    )
                    break
            else:
                ok_count += 1
                consecutive_blocking = 0
                created = int(result.get('created') or 0)
                updated = int(result.get('updated') or 0)
                pl_total = int(result.get('total') or 0)
                created_total += created
                updated_total += updated
                self.stdout.write(
                    self.style.SUCCESS(
                        f'  OK — playlist={pl_total} created={created} updated={updated}'
                    )
                )
                self.stdout.flush()

            if i < total:
                wait = delay + (random.uniform(0, jitter) if jitter > 0 else 0)
                if wait > 0:
                    time.sleep(wait)

        elapsed = timezone.now() - started
        self.stdout.write('')
        self.stdout.write(
            self.style.NOTICE(
                f'Statistika: silsilə={total} uğurlu={ok_count} uğursuz={fail_count} '
                f'yeni_dərs={created_total} yenilənən={updated_total} '
                f'vaxt={self._fmt_delta(elapsed)}'
            )
        )

    def _resolve_series(self, key: str) -> VideoSeries:
        if key.isdigit():
            series = VideoSeries.objects.filter(pk=int(key)).first()
            if series:
                return series
            raise CommandError(f'Silsilə id={key} tapılmadı')

        slugish = key.replace('-', ' ').replace('_', ' ').strip()
        series = (
            VideoSeries.objects.filter(title__iexact=key).first()
            or VideoSeries.objects.filter(title__iexact=slugish).first()
            or VideoSeries.objects.filter(title__icontains=key).first()
            or VideoSeries.objects.filter(title__icontains=slugish).first()
        )
        if not series:
            raise CommandError(f'Silsilə tapılmadı: {key!r}')
        return series

    @staticmethod
    def _fmt_delta(delta: timedelta) -> str:
        total_sec = int(delta.total_seconds())
        mins, secs = divmod(total_sec, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f'{hours}saat {mins}dəq {secs}san'
        if mins:
            return f'{mins}dəq {secs}san'
        return f'{secs}san'
