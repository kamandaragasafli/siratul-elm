"""Dərs silsilələrinin mövzu bölmələri."""

from __future__ import annotations

import re
from typing import Literal

LessonCategory = Literal['aqida', 'hadith', 'fiqh', 'tafsir', 'seerah', 'general']

LESSON_SECTIONS: list[LessonCategory] = [
    'aqida',
    'hadith',
    'fiqh',
    'tafsir',
    'seerah',
    'general',
]

SECTION_LABELS: dict[str, str] = {
    'aqida': 'Əqidə',
    'hadith': 'Hədis',
    'fiqh': 'Fiqh',
    'tafsir': 'Təfsir',
    'seerah': 'Sira',
    'general': 'Digər',
}

# Əvvəl daha spesifik qaydalar yoxlanılır
_RULES: list[tuple[LessonCategory, list[str]]] = [
    (
        'hadith',
        [
            r'h[əe]dis',
            r'40\s*h[əe]dis',
            r'ş[əe]rh\s*əs',
            r'əs[-\s]?s[üu]nn',
            r's[üu]nn[əe]',
        ],
    ),
    (
        'tafsir',
        [
            r'quran',
            r'qira',
            r'sur[əe]',
            r't[əe]fsir',
            r'kafirun',
        ],
    ),
    (
        'fiqh',
        [
            r'fiqh',
            r'fıqh',
            r'namaz',
            r'oruc',
            r't[əe]ravi',
            r'z[əe]kat',
            r'f[əe]sill',
            r'x[üu]tb',
            r'maliyy[əe]',
        ],
    ),
    (
        'seerah',
        [
            r'\bsira\b',
            r's[əe]rah',
            r'peyg[əa]mb',
            r'h[əe]yat[ıi]',
        ],
    ),
    (
        'aqida',
        [
            r'[əe]qid',
            r't[öo]vhid',
            r'iman',
            r'bid[əe]t',
            r's[əe]l[əe]f',
            r't[əe]kfir',
            r'firq',
            r'ateist',
            r'şi[əe]',
            r'maturid',
            r'[əe]şari',
            r'teymiyy',
            r'ixlas',
            r'3\s*[əe]sas',
            r'üç\s*[əe]sas',
            r'kafir',
        ],
    ),
]


def category_label(category: str) -> str:
    return SECTION_LABELS.get(category, SECTION_LABELS['general'])


def detect_series_category(title: str) -> LessonCategory:
    text = (title or '').strip().lower()
    if not text:
        return 'general'
    for category, patterns in _RULES:
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return category
    return 'general'
