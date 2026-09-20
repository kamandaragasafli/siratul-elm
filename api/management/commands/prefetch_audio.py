"""
Bütün (və ya filtrələnmiş) dərslərin səsini YouTube-dan əvvəlcədən yükləyib storage-a yazır.

Nümunə:
  python manage.py prefetch_audio
  python manage.py prefetch_audio --limit 5 --delay 15
  python manage.py prefetch_audio --series 12
  python manage.py prefetch_audio --force --series "Fiqh"
"""

from __future__ import annotations

import random
import time
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone

from api.audio import ensure_audio_file
from api.models import VideoLesson, VideoSeries


class Command(BaseCommand):
    help = 'VideoLesson səslərini YouTube-dan prefetch edib media storage-a yazır'

    def add_arguments(self, parser):
        parser.add_argument(
            '--delay',
            type=float,
            default=20.0,
            help='Dərslər arası gözləmə (saniyə, default 20)',
        )
        parser.add_argument(
            '--jitter',
            type=float,
            default=10.0,
            help='Əlavə təsadüfi gecikmə üst həddi (0..jitter san, default 10)',
        )
        parser.add_argument(
            '--limit',
            type=int,
            default=0,
            help='Maksimum dərs sayı (0 = hamısı; test üçün)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Mövcud audio_file-ları da yenidən yüklə',
        )
        parser.add_argument(
            '--series',
            type=str,
            default='',
            help='Yalnız bu silsilə (id və ya title / slug-ə bənzər ad)',
        )

    def handle(self, *args, **options):
        delay = max(0.0, float(options['delay']))
        jitter = max(0.0, float(options['jitter']))
        limit = int(options['limit'] or 0)
        force = bool(options['force'])
        series_key = (options['series'] or '').strip()

        qs = VideoLesson.objects.select_related('series').order_by('series_id', 'order', 'id')

        if series_key:
            series = self._resolve_series(series_key)
            qs = qs.filter(series=series)
            self.stdout.write(f'Silsilə: [{series.pk}] {series.title}')

        if not force:
            qs = qs.filter(Q(audio_file='') | Q(audio_file__isnull=True))

        if limit > 0:
            qs = qs[:limit]

        lessons = list(qs)
        total = len(lessons)
        if total == 0:
            self.stdout.write(self.style.WARNING('Yüklənəcək dərs yoxdur.'))
            return

        self.stdout.write(
            f'{total} dərs — delay={delay}s jitter=0..{jitter}s force={force}'
        )

        started = timezone.now()
        ok_count = 0
        fail_count = 0
        consecutive_blocking = 0

        for i, lesson in enumerate(lessons, start=1):
            label = f'[{i}/{total}] id={lesson.pk} «{lesson.title[:60]}»'
            self.stdout.write(f'{label} …')

            ok, err, is_blocking = ensure_audio_file(lesson, force=force)
            if ok:
                ok_count += 1
                consecutive_blocking = 0
                self.stdout.write(self.style.SUCCESS(f'  OK — {label}'))
            else:
                fail_count += 1
                self.stdout.write(
                    self.style.ERROR(f'  FAIL — {label}: {err or "naməlum xəta"}')
                )
                if is_blocking:
                    consecutive_blocking += 1
                else:
                    consecutive_blocking = 0

                if consecutive_blocking >= 3:
                    self.stderr.write(
                        self.style.ERROR(
                            '\nArdıcıl 3 blok xətası (bot yoxlaması / player cavabı). '
                            'Proses dayandırıldı — PO token və ya YTDLP_COOKIES_FILE / cookies '
                            'problemi ola bilər. Sonsuz uğursuz dövrəyə düşməmək üçün çıkılır.'
                        )
                    )
                    break

            if i < total:
                wait = delay + (random.uniform(0, jitter) if jitter > 0 else 0)
                if wait > 0:
                    self.stdout.write(f'  … {wait:.1f}s gözləmə')
                    time.sleep(wait)

        elapsed = timezone.now() - started
        self.stdout.write('')
        self.stdout.write(
            self.style.NOTICE(
                f'Statistika: cəmi={total} uğurlu={ok_count} uğursuz={fail_count} '
                f'vaxt={self._fmt_delta(elapsed)}'
            )
        )

    def _resolve_series(self, key: str) -> VideoSeries:
        if key.isdigit():
            series = VideoSeries.objects.filter(pk=int(key)).first()
            if series:
                return series
            raise CommandError(f'Silsilə id={key} tapılmadı')

        # Slug yoxdur — title dəqiq / slug-ə bənzər / contains
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
