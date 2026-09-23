"""Dump JSON → Neon (psycopg2, ORM save hook-suz)."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import psycopg2
import psycopg2.extras

ROOT = Path(__file__).resolve().parent.parent


def connect():
    url = os.environ.get('DATABASE_URL', '').strip()
    if not url:
        raise SystemExit('DATABASE_URL lazımdır')
    # channel_binding psycopg2-də problem çıxara bilər
    url = url.replace('&channel_binding=require', '').replace('?channel_binding=require&', '?')
    return psycopg2.connect(url, connect_timeout=30)


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'data_export_videos.json')
    print('reading', path, flush=True)
    data = json.loads(path.read_text(encoding='utf-8'))
    print('objects', len(data), flush=True)

    by = {}
    for item in data:
        by.setdefault(item['model'], []).append(item)

    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()
    print('connected', flush=True)

    # channels
    rows = by.get('api.videochannel', [])
    print('channels', len(rows), flush=True)
    for it in rows:
        f = it['fields']
        cur.execute(
            """
            INSERT INTO api_videochannel
              (id, name, url, description, "order", is_published, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
              name=EXCLUDED.name, url=EXCLUDED.url, description=EXCLUDED.description,
              "order"=EXCLUDED."order", is_published=EXCLUDED.is_published
            """,
            (
                it['pk'], f['name'], f['url'], f.get('description') or '',
                f.get('order') or 0, f.get('is_published', True),
                f['created_at'], f['updated_at'],
            ),
        )
    conn.commit()
    print('channels OK', flush=True)

    # series
    rows = by.get('api.videoseries', [])
    print('series', len(rows), flush=True)
    for i, it in enumerate(rows, 1):
        f = it['fields']
        cur.execute(
            """
            INSERT INTO api_videoseries
              (id, channel_id, title, category, description, playlist_url,
               "order", is_published, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
              channel_id=EXCLUDED.channel_id, title=EXCLUDED.title,
              category=EXCLUDED.category, description=EXCLUDED.description,
              playlist_url=EXCLUDED.playlist_url, "order"=EXCLUDED."order",
              is_published=EXCLUDED.is_published
            """,
            (
                it['pk'], f['channel'], f['title'], f.get('category') or 'general',
                f.get('description') or '', f.get('playlist_url') or '',
                f.get('order') or 0, f.get('is_published', True),
                f['created_at'], f['updated_at'],
            ),
        )
        if i % 50 == 0:
            conn.commit()
            print(f'  series {i}/{len(rows)}', flush=True)
    conn.commit()
    print('series OK', flush=True)

    # lessons
    rows = by.get('api.videolesson', [])
    print('lessons', len(rows), flush=True)
    batch = []
    for i, it in enumerate(rows, 1):
        f = it['fields']
        batch.append((
            it['pk'], f['series'], f['title'], f.get('url') or '',
            f.get('youtube_id') or '', f.get('audio_file') or '',
            f.get('duration_seconds'), f.get('order') or 0,
            f.get('is_published', True),
        ))
        if len(batch) >= 500:
            psycopg2.extras.execute_batch(
                cur,
                """
                INSERT INTO api_videolesson
                  (id, series_id, title, url, youtube_id, audio_file,
                   duration_seconds, "order", is_published)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (id) DO UPDATE SET
                  series_id=EXCLUDED.series_id, title=EXCLUDED.title,
                  url=EXCLUDED.url, youtube_id=EXCLUDED.youtube_id,
                  audio_file=EXCLUDED.audio_file,
                  duration_seconds=EXCLUDED.duration_seconds,
                  "order"=EXCLUDED."order", is_published=EXCLUDED.is_published
                """,
                batch,
                page_size=500,
            )
            conn.commit()
            print(f'  lessons {i}/{len(rows)}', flush=True)
            batch = []
    if batch:
        psycopg2.extras.execute_batch(
            cur,
            """
            INSERT INTO api_videolesson
              (id, series_id, title, url, youtube_id, audio_file,
               duration_seconds, "order", is_published)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id) DO UPDATE SET
              series_id=EXCLUDED.series_id, title=EXCLUDED.title,
              url=EXCLUDED.url, youtube_id=EXCLUDED.youtube_id,
              audio_file=EXCLUDED.audio_file,
              duration_seconds=EXCLUDED.duration_seconds,
              "order"=EXCLUDED."order", is_published=EXCLUDED.is_published
            """,
            batch,
            page_size=500,
        )
        conn.commit()
    print('lessons OK', flush=True)

    # books
    rows = by.get('api.book', [])
    print('books', len(rows), flush=True)
    for it in rows:
        f = it['fields']
        topics = f.get('topics')
        if not isinstance(topics, str):
            topics = json.dumps(topics or [], ensure_ascii=False)
        cur.execute(
            """
            INSERT INTO api_book
              (id, public_id, title, author, description, language, cover_tone,
               cover_image, format, pdf_file, pdf_page_count, page_direction,
               source, topics, created_at, updated_at, is_published)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                it['pk'], f['public_id'], f['title'], f.get('author') or '',
                f.get('description') or '', f.get('language') or 'az',
                f.get('cover_tone') or 0, f.get('cover_image') or '',
                f.get('format') or '', f.get('pdf_file') or '',
                f.get('pdf_page_count'), f.get('page_direction') or '',
                f.get('source') or '', topics,
                f['created_at'], f['updated_at'], f.get('is_published', True),
            ),
        )
    conn.commit()
    print('books OK', flush=True)

    # chapters
    rows = by.get('api.chapter', [])
    print('chapters', len(rows), flush=True)
    for i, it in enumerate(rows, 1):
        f = it['fields']
        blocks = f.get('blocks')
        if not isinstance(blocks, str):
            blocks = json.dumps(blocks if blocks is not None else None, ensure_ascii=False)
        cur.execute(
            """
            INSERT INTO api_chapter
              (id, book_id, public_id, title, content, blocks, "order")
            VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                it['pk'], f['book'], f['public_id'], f['title'],
                f.get('content') or '', blocks, f.get('order') or 0,
            ),
        )
        if i % 50 == 0:
            conn.commit()
            print(f'  chapters {i}/{len(rows)}', flush=True)
    conn.commit()
    print('chapters OK', flush=True)

    # sequences
    for table in (
        'api_videochannel', 'api_videoseries', 'api_videolesson',
        'api_book', 'api_chapter',
    ):
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
            f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
        )
    conn.commit()

    cur.execute('SELECT COUNT(*) FROM api_videochannel')
    ch = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM api_videoseries')
    ser = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM api_videolesson')
    les = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM api_book')
    books = cur.fetchone()[0]
    print(f'DONE ch={ch} ser={ser} les={les} books={books}', flush=True)

    cur.close()
    conn.close()


if __name__ == '__main__':
    main()
