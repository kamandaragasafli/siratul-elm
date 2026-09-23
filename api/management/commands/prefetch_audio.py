"""
Dərslərin səsini YouTube-dan prefetch edib storage-a yazır (resumable, gündəlik kvota).

Nümunə:
  python manage.py prefetch_audio
  python manage.py prefetch_audio --daily-limit 40 --workers 2
  python manage.py prefetch_audio --limit 5 --delay 15 --skip-po-check
  python manage.py prefetch_audio --series 12 --force
"""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.db.models import Q
from django.utils import timezone

from api.audio import ensure_audio_file
from api.models import VideoLesson, VideoSeries
from api.ytdlp_opts import check_po_token_provider, po_token_provider_url


class Command(BaseCommand):
    help = 'VideoLesson səslərini YouTube-dan prefetch edib media storage-a yazır (resumable)'

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
            help='Bu işə salınmada əlavə maksimum (0 = yalnız daily-limit)',
        )
        parser.add_argument(
            '--daily-limit',
            type=int,
            default=40,
            help='Gündəlik maksimum cəhd (default 40)',
        )
        parser.add_argument(
            '--workers',
            type=int,
            default=1,
            help='Paralel worker sayı (default 1, məsləhət 2-3)',
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
            help='Yalnız bu silsilə (id və ya title)',
        )
        parser.add_argument(
            '--skip-po-check',
            action='store_true',
            help='PO token provider yoxlamasını keç (tövsiyə olunmur)',
        )
        parser.add_argument(
            '--progress-every',
            type=int,
            default=50,
            help='Hər N cəhddən bir progress xülasəsi (default 50)',
        )
        parser.add_argument(
            '--min-success-rate',
            type=float,
            default=50.0,
            help='Son 50 cəhddə minimum uğur %% (default 50)',
        )

    def handle(self, *args, **options):
        delay = max(0.0, float(options['delay']))
        jitter = max(0.0, float(options['jitter']))
        limit = max(0, int(options['limit'] or 0))
        daily_limit = max(1, int(options['daily_limit'] or 40))
        workers = max(1, min(8, int(options['workers'] or 1)))
        force = bool(options['force'])
        series_key = (options['series'] or '').strip()
        skip_po = bool(options['skip_po_check'])
        progress_every = max(1, int(options['progress_every'] or 50))
        min_success_rate = float(options['min_success_rate'] or 50.0)

        if not skip_po:
            ok_po, po_msg = check_po_token_provider()
            if not ok_po:
                raise CommandError(
                    f'{po_msg}\n'
                    'Bu miqyasda PO token provider olmadan prefetch boşa gedir. '
                    'YTDLP_PO_PROVIDER_URL təyin edin və ya --skip-po-check '
                    '(yalnız test üçün).'
                )
            self.stdout.write(self.style.SUCCESS(po_msg))
            self.stdout.write(f'Provider: {po_token_provider_url()}')
        else:
            self.stdout.write(
                self.style.WARNING('PO token yoxlaması keçildi (--skip-po-check)')
            )

        now_local = timezone.localtime()
        today_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

        attempted_today = VideoLesson.objects.filter(
            audio_fetch_attempted_at__gte=today_start,
        ).count()
        remaining_quota = max(0, daily_limit - attempted_today)
        if remaining_quota <= 0:
            self.stdout.write(
                self.style.WARNING(
                    f'Gündəlik kvota dolub ({attempted_today}/{daily_limit}). '
                    'Sabah davam edin — resume avtomatikdir.'
                )
            )
            return

        qs = VideoLesson.objects.select_related('series').order_by('id')
        if series_key:
            series = self._resolve_series(series_key)
            qs = qs.filter(series=series)
            self.stdout.write(f'Silsilə: [{series.pk}] {series.title}')

        if not force:
            qs = qs.filter(Q(audio_file='') | Q(audio_file__isnull=True))
            # Bu gün cəhd olunmuşları keç — resume sabah / növbəti gün
            qs = qs.filter(
                Q(audio_fetch_attempted_at__isnull=True)
                | Q(audio_fetch_attempted_at__lt=today_start)
            )

        # Bu run üçün necə dərs götürək
        run_cap = remaining_quota
        if limit > 0:
            run_cap = min(run_cap, limit)

        lesson_ids = list(qs.values_list('id', flat=True)[:run_cap])
        total = len(lesson_ids)
        if total == 0:
            self.stdout.write(self.style.WARNING('Yüklənəcək dərs yoxdur.'))
            return

        pending_total = qs.count()
        self.stdout.write(
            f'Bu run: {total} dərs | daily={daily_limit} '
            f'(bu gün artıq {attempted_today}) | qalan (filtr): ~{pending_total} | '
            f'workers={workers} delay={delay}s jitter=0..{jitter}s force={force}'
        )

        started = time.monotonic()
        started_at = timezone.now()
        stop_event = threading.Event()
        stop_reason: list[str] = []
        lock = threading.Lock()
        recent: deque[bool] = deque(maxlen=50)
        ok_count = 0
        fail_count = 0
        consecutive_blocking = 0
        done_count = 0

        def record_result(ok: bool, is_blocking: bool) -> None:
            nonlocal ok_count, fail_count, consecutive_blocking, done_count
            with lock:
                done_count += 1
                recent.append(ok)
                if ok:
                    ok_count += 1
                    consecutive_blocking = 0
                else:
                    fail_count += 1
                    if is_blocking:
                        consecutive_blocking += 1
                    else:
                        consecutive_blocking = 0

                if consecutive_blocking >= 3 and not stop_event.is_set():
                    stop_event.set()
                    stop_reason.append(
                        'Ardıcıl 3 blok xətası (bot yoxlaması / player). '
                        'PO token və ya cookies problemi ola bilər — dayandırıldı.'
                    )

                if len(recent) >= 50 and not stop_event.is_set():
                    rate = 100.0 * sum(1 for x in recent if x) / len(recent)
                    if rate < min_success_rate:
                        stop_event.set()
                        stop_reason.append(
                            f'Uğur faizi {rate:.0f}% — çox güman IP bloklanıb '
                            f've ya PO token provider işləmir, dayandırıldı.'
                        )

                if done_count % progress_every == 0 or done_count == total:
                    self._print_progress(
                        done=done_count,
                        total=total,
                        ok=ok_count,
                        fail=fail_count,
                        recent=recent,
                        started=started,
                        pending_estimate=max(0, pending_total - ok_count),
                    )

        def process_one(lesson_id: int, worker_index: int) -> None:
            if stop_event.is_set():
                return
            close_old_connections()
            try:
                lesson = (
                    VideoLesson.objects.select_related('series')
                    .filter(pk=lesson_id)
                    .first()
                )
                if not lesson:
                    return

                label = (
                    f'[w{worker_index} id={lesson.pk}] «{(lesson.title or "")[:50]}»'
                )
                self.stdout.write(f'{label} …')
                self.stdout.flush()

                ok, err, is_blocking = ensure_audio_file(lesson, force=force)

                # Hər cəhddən dərhal DB stamp — resume / daily kvota
                VideoLesson.objects.filter(pk=lesson.pk).update(
                    audio_fetch_attempted_at=timezone.now(),
                )

                if ok:
                    self.stdout.write(self.style.SUCCESS(f'  OK — {label}'))
                else:
                    self.stdout.write(
                        self.style.ERROR(f'  FAIL — {label}: {err or "naməlum"}')
                    )
                self.stdout.flush()
                record_result(ok, is_blocking)

                if not stop_event.is_set():
                    wait = delay + (random.uniform(0, jitter) if jitter > 0 else 0)
                    if wait > 0:
                        # stop üçün qısa dilimlə gözlə
                        end = time.monotonic() + wait
                        while time.monotonic() < end and not stop_event.is_set():
                            time.sleep(min(0.5, end - time.monotonic()))
            finally:
                close_old_connections()

        if workers == 1:
            for lid in lesson_ids:
                if stop_event.is_set():
                    break
                process_one(lid, 0)
        else:
            # Hər worker öz dilimini götürür: id % workers == worker_index
            buckets: list[list[int]] = [[] for _ in range(workers)]
            for lid in lesson_ids:
                buckets[lid % workers].append(lid)

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = []
                for wi, bucket in enumerate(buckets):
                    for lid in bucket:
                        futures.append(pool.submit(process_one, lid, wi))
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except Exception as exc:
                        self.stderr.write(self.style.ERROR(f'Worker xətası: {exc}'))
                        record_result(False, False)

        if stop_reason:
            self.stderr.write(self.style.ERROR('\n' + stop_reason[0]))

        elapsed = timezone.now() - started_at
        rate = (
            100.0 * sum(1 for x in recent if x) / len(recent) if recent else 0.0
        )
        self.stdout.write('')
        self.stdout.write(
            self.style.NOTICE(
                f'Statistika: cəhd={done_count} uğurlu={ok_count} uğursuz={fail_count} '
                f'son50={rate:.0f}% vaxt={self._fmt_delta(elapsed)} '
                f'bu_gün_cəhd≈{attempted_today + done_count}/{daily_limit}'
            )
        )

    def _print_progress(
        self,
        *,
        done: int,
        total: int,
        ok: int,
        fail: int,
        recent: deque,
        started: float,
        pending_estimate: int,
    ) -> None:
        elapsed = max(0.001, time.monotonic() - started)
        per_sec = done / elapsed
        remain = max(0, total - done)
        eta_sec = int(remain / per_sec) if per_sec > 0 else 0
        rate = 100.0 * sum(1 for x in recent if x) / len(recent) if recent else 0.0
        self.stdout.write(
            self.style.NOTICE(
                f'── progress {done}/{total} | OK={ok} FAIL={fail} | '
                f'son50={rate:.0f}% | qalan≈{pending_estimate} | '
                f'ETA~{self._fmt_delta(timedelta(seconds=eta_sec))} ──'
            )
        )
        self.stdout.flush()

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
        total_sec = max(0, int(delta.total_seconds()))
        mins, secs = divmod(total_sec, 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f'{hours}saat {mins}dəq {secs}san'
        if mins:
            return f'{mins}dəq {secs}san'
        return f'{secs}san'
