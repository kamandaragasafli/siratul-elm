"""114 surə — Azərbaycan adları (panel seçimi üçün)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# app/assets/quran/surah-meta.json
_META_PATH = (
    Path(__file__).resolve().parents[2] / 'app' / 'assets' / 'quran' / 'surah-meta.json'
)


@lru_cache(maxsize=1)
def surah_list() -> list[dict]:
    """[{id, nameAz, verses}, ...]"""
    if _META_PATH.is_file():
        raw = json.loads(_META_PATH.read_text(encoding='utf-8'))
        out = []
        for row in raw:
            out.append(
                {
                    'id': int(row['id']),
                    'nameAz': str(row.get('nameAz') or f"Surə {row['id']}"),
                    'verses': int(row.get('verses') or 0),
                }
            )
        return out
    return [{'id': i, 'nameAz': f'Surə {i}', 'verses': 0} for i in range(1, 115)]


def surah_name_az(surah_id: int) -> str:
    for row in surah_list():
        if row['id'] == surah_id:
            return row['nameAz']
    return f'Surə {surah_id}'
