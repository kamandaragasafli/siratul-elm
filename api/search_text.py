"""Axtarış üçün mətn normallaşdırma (SQLite icontains Az hərflərini düzgün tutmur)."""

from __future__ import annotations

import re
import unicodedata

# Oxşar hərfləri eyni açara sal — axtarış daha dözümlü olsun
_MAP = str.maketrans(
    {
        'ə': 'e',
        'Ə': 'e',
        'ı': 'i',
        'I': 'i',
        'İ': 'i',
        'i': 'i',
        'ğ': 'g',
        'Ğ': 'g',
        'ş': 's',
        'Ş': 's',
        'ç': 'c',
        'Ç': 'c',
        'ö': 'o',
        'Ö': 'o',
        'ü': 'u',
        'Ü': 'u',
        'â': 'a',
        'Â': 'a',
        'î': 'i',
        'Î': 'i',
        'û': 'u',
        'Û': 'u',
    }
)


def normalize_search(text: str) -> str:
    s = unicodedata.normalize('NFKC', text or '')
    s = s.translate(_MAP)
    s = s.casefold()
    s = re.sub(r'[^\w\s]+', ' ', s, flags=re.UNICODE)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def tokens(text: str) -> list[str]:
    return [t for t in normalize_search(text).split(' ') if t]


def text_matches(haystack: str, needle: str) -> bool:
    """Tam fraza və ya bütün sözlər (istənilən sıra) uyğun gəlsin."""
    n = normalize_search(needle)
    h = normalize_search(haystack)
    if not n:
        return False
    if n in h:
        return True
    words = n.split(' ')
    if len(words) > 1 and all(w in h for w in words):
        return True
    return False
