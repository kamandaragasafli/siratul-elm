"""Təcvid qaydaları — tecvid.json + ayə mətninə görə uyğun dərslər."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent.parent / 'data' / 'tecvid.json'

PATTERN_RULES: list[tuple[re.Pattern[str], list[str]]] = [
    (re.compile(r'[ن][\u064B-\u0652\u0670]|[ًٌٍ](?=[\u0621-\u064A])'), [
        'nun-sakin', 'izhar', 'idgam', 'idgam-ghunnah', 'idgam-bila-ghunnah', 'iqlab', 'ikhfa',
    ]),
    (re.compile(r'م[\u0652\u06E1]'), ['mim-hokm', 'idgam-mim', 'ikhfa-mim', 'izhar-mim']),
    (re.compile(r'[\u0651]'), ['idgam-misleyn', 'idgam-mutecaniseyn', 'idgam-muteqarebeyn']),
    (re.compile(r'[قطبجد][\u0652\u06E1]'), ['qalqale']),
    (re.compile(r'ل(?:ل|ّ)[ه]|ٱ?لله|الله'), ['lefzullah']),
    (re.compile(r'(?<=[\u064E\u064F\u0650\u0653])[اوي\u0648\u064A\u0627]|[اوي][\u064E\u064F\u0650]'), [
        'med-herf', 'med-muttasil', 'med-munfasil', 'med-lazim', 'med-arid', 'med-lin', 'med-ivad',
    ]),
    (re.compile(r'(?<![\u0621-\u064A])ال[\u0621-\u064A]'), ['idgam-semsiyye', 'izhar-qamariyye']),
]


@lru_cache(maxsize=1)
def _load_tecvid() -> dict:
    with DATA_PATH.open(encoding='utf-8') as f:
        return json.load(f)


@lru_cache(maxsize=1)
def _lessons_by_id() -> dict[str, dict]:
    data = _load_tecvid()
    out: dict[str, dict] = {}
    for section in data.get('sections', []):
        for lesson in section.get('lessons', []):
            lid = lesson.get('id')
            if lid:
                out[lid] = {
                    **lesson,
                    'sectionId': section.get('id'),
                    'sectionTitle': section.get('title'),
                }
    return out


def detect_rule_ids(arabic: str) -> list[str]:
    if not arabic:
        return []
    seen: set[str] = set()
    ordered: list[str] = []
    for pattern, rule_ids in PATTERN_RULES:
        if pattern.search(arabic):
            for rid in rule_ids:
                if rid not in seen:
                    seen.add(rid)
                    ordered.append(rid)
    if not ordered:
        ordered.append('terminler')
    return ordered[:10]


def _compact_lesson(lesson: dict) -> dict:
    examples = lesson.get('arabicExamples') or []
    compact_examples = [
        {'label': ex.get('label'), 'arabic': ex.get('arabic'), 'note': ex.get('note')}
        for ex in examples[:4]
        if ex.get('arabic')
    ]
    letters = lesson.get('arabicLetters')
    compact_letters: list[str] = []
    if isinstance(letters, list):
        for item in letters[:12]:
            if isinstance(item, str):
                compact_letters.append(item)
            elif isinstance(item, dict):
                compact_letters.append(str(item.get('letter') or item.get('name') or ''))

    content = (lesson.get('content') or '').strip()
    if len(content) > 420:
        content = content[:417].rstrip() + '…'

    return {
        'id': lesson.get('id'),
        'title': lesson.get('title'),
        'sectionTitle': lesson.get('sectionTitle'),
        'content': content,
        'arabicLetters': compact_letters or None,
        'arabicExamples': compact_examples or None,
        'exceptionWords': (lesson.get('exceptionWords') or [])[:6] or None,
    }


def build_tajweed_context(expected_arabic: str) -> tuple[list[str], list[dict]]:
    rule_ids = detect_rule_ids(expected_arabic)
    lessons_map = _lessons_by_id()
    context: list[dict] = []
    for rid in rule_ids:
        lesson = lessons_map.get(rid)
        if lesson:
            context.append(_compact_lesson(lesson))
    return rule_ids, context


def lesson_title(rule_id: str) -> str | None:
    lesson = _lessons_by_id().get(rule_id)
    return lesson.get('title') if lesson else None
