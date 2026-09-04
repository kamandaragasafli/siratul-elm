"""Import bundled book JSON files (Sirac/assets/books) into Django DB."""

from __future__ import annotations

import json
from pathlib import Path

from django.db import transaction

from .models import Book, Chapter

# backend/ → repo root → Sirac/assets/books
_DEFAULT_DIRS = [
    Path(__file__).resolve().parents[2] / 'Elmun-Tariq' / 'assets' / 'books',
    Path(__file__).resolve().parents[2] / 'Sirac' / 'assets' / 'books',
    Path(__file__).resolve().parents[1] / 'data' / 'books',
]


def bundled_books_dir() -> Path | None:
    for d in _DEFAULT_DIRS:
        if d.is_dir():
            return d
    return None


def list_bundled_json_files(directory: Path | None = None) -> list[Path]:
    root = directory or bundled_books_dir()
    if not root:
        return []
    return sorted(
        p for p in root.glob('*.json') if not p.name.startswith('_') and p.name != 'package.json'
    )


@transaction.atomic
def import_book_json(
    path: Path,
    *,
    update_existing: bool = True,
    overwrite_chapters: bool = False,
) -> dict:
    data = json.loads(path.read_text(encoding='utf-8'))
    public_id = (data.get('id') or '').strip()
    if not public_id:
        return {'file': path.name, 'ok': False, 'error': 'id yoxdur'}

    chapters = data.get('chapters') or []
    defaults = {
        'title': (data.get('title') or path.stem).strip(),
        'author': (data.get('author') or '').strip(),
        'description': (data.get('description') or '').strip(),
        'language': (data.get('language') or 'az').strip()[:8],
        'cover_tone': int(data.get('coverTone') or data.get('cover_tone') or 0),
        'source': (data.get('source') or 'seed').strip()[:20],
        'topics': data.get('topics') if isinstance(data.get('topics'), list) else [],
        'is_published': True,
    }

    book = Book.objects.filter(public_id=public_id).first()
    created = book is None
    if book is None:
        book = Book.objects.create(public_id=public_id, **defaults)
    elif not update_existing:
        return {
            'file': path.name,
            'ok': True,
            'skipped': True,
            'public_id': public_id,
            'title': book.title,
            'chapters': book.chapters.count(),
        }
    else:
        # Metadata only — chapter text stays (admin typos preserved)
        for k, v in defaults.items():
            setattr(book, k, v)
        book.save()

    should_write_chapters = created or overwrite_chapters or not book.chapters.exists()
    if should_write_chapters:
        book.chapters.all().delete()
        Chapter.objects.bulk_create(
            [
                Chapter(
                    book=book,
                    public_id=str(ch.get('id') or f'ch-{i + 1}'),
                    title=(ch.get('title') or f'Fəsil {i + 1}').strip(),
                    content=ch.get('content') or '',
                    order=i,
                )
                for i, ch in enumerate(chapters)
                if isinstance(ch, dict)
            ]
        )

    return {
        'file': path.name,
        'ok': True,
        'created': created,
        'updated': not created,
        'chapters_written': should_write_chapters,
        'public_id': public_id,
        'title': book.title,
        'chapters': book.chapters.count() if not should_write_chapters else len(chapters),
    }


def import_all_bundled_books(
    *,
    update_existing: bool = True,
    overwrite_chapters: bool = False,
) -> dict:
    root = bundled_books_dir()
    if not root:
        return {
            'ok': False,
            'error': 'assets/books qovluğu tapılmadı',
            'results': [],
        }

    results = []
    for path in list_bundled_json_files(root):
        try:
            results.append(
                import_book_json(
                    path,
                    update_existing=update_existing,
                    overwrite_chapters=overwrite_chapters,
                )
            )
        except Exception as exc:  # noqa: BLE001 — report per-file, continue
            results.append({'file': path.name, 'ok': False, 'error': str(exc)})

    ok_count = sum(1 for r in results if r.get('ok'))
    return {
        'ok': True,
        'directory': str(root),
        'total': len(results),
        'imported': ok_count,
        'results': results,
    }
