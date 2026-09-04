"""Fəsil mətni — AI ilə orfoqrafiya / format düzəlişi (OpenAI)."""

from __future__ import annotations

import json
import re

from .hifz import HifzError, _openai_json

ChapterAIError = HifzError

MAX_CHARS = 24_000


def fix_chapter_text(
    *,
    title: str = '',
    content: str = '',
    language: str = 'az',
) -> dict[str, str]:
    title = (title or '').strip()
    content = content or ''
    combined_len = len(title) + len(content)
    if combined_len == 0:
        raise ChapterAIError('Düzəltmək üçün mətn lazımdır.')
    if combined_len > MAX_CHARS:
        raise ChapterAIError(
            f'Mətn çox uzundur ({combined_len} simvol). '
            f'Ən çox {MAX_CHARS} simvol dəstəklənir — fəsili bölməyin.',
        )

    lang_note = {
        'az': 'Azərbaycan dili',
        'ar': 'Ərəb dili',
        'en': 'İngilis dili',
    }.get(language, 'Azərbaycan dili')

    system = (
        'Sən islami kitab redaktorusan. Verilmiş fəsil başlığı və mətnində YALNIZ '
        'orfoqrafiya, interpunksiya, boşluq və format səhvlərini düzəlt.\n'
        'QAYDALAR:\n'
        '- Məna, fakt və terminologiyanı DƏYİŞMƏ.\n'
        '- **qalın** və *italik* markdown işarələrini saxla; lazım gələrsə düzgün yerləşdir.\n'
        '- Mətndə [1], [2] istinad işarələrini və qeyd nömrələrini saxla.\n'
        '- Ərəbcə ayə/hədis mətnini olduğu kimi saxla (yalnız aydın typo varsa düzəlt).\n'
        '- radıyallahu anh/anha/anhum, rahiməhullah, sallallahu aleyhi və səlləm və s. '
        'honorific ifadələri saxla.\n'
        '- Abzasları və sətir qırılmalarını oxunaqlı saxla.\n'
        '- Yeni mətn əlavə etmə, cümlələri silmə.\n'
        'Yalnız JSON qaytar: {"title":"...","content":"..."}'
    )

    payload = {
        'model': 'gpt-4o-mini',
        'temperature': 0.15,
        'response_format': {'type': 'json_object'},
        'messages': [
            {'role': 'system', 'content': system},
            {
                'role': 'user',
                'content': json.dumps(
                    {
                        'language': lang_note,
                        'title': title,
                        'content': content,
                    },
                    ensure_ascii=False,
                ),
            },
        ],
    }

    data = _openai_json('/chat/completions', payload, timeout=120.0)
    raw = data.get('choices', [{}])[0].get('message', {}).get('content') or '{}'
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ChapterAIError('AI cavabı oxunmadı.') from e

    out_title = str(parsed.get('title') if parsed.get('title') is not None else title).strip()
    out_content = str(parsed.get('content') if parsed.get('content') is not None else content)
    if not out_title and title:
        out_title = title
    if not out_content.strip() and content.strip():
        out_content = content

    # Markdown wrapper-ları pozulmasın
    out_content = re.sub(r'\r\n?', '\n', out_content)
    return {'title': out_title, 'content': out_content}
