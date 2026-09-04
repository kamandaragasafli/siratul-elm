"""Hifz yoxlaması — Whisper (səs→mətn) + lokal müqayisə + yazılı təcvid dərsləri."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from .tajweed_rules import build_tajweed_context

OPENAI_API_BASE = 'https://api.openai.com/v1'


class HifzError(Exception):
    pass


def _api_key() -> str:
    key = (getattr(settings, 'OPENAI_API_KEY', '') or os.environ.get('OPENAI_API_KEY', '')).strip()
    if not key:
        raise HifzError(
            'OpenAI API açarı tapılmadı. backend/.env faylında OPENAI_API_KEY yazın və '
            'serveri yenidən başladın (runserver).',
        )
    return key


def _openai_json(path: str, payload: dict, timeout: float = 90.0) -> dict:
    data = json.dumps(payload).encode('utf-8')
    req = Request(
        f'{OPENAI_API_BASE}{path}',
        data=data,
        headers={
            'Authorization': f'Bearer {_api_key()}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except HTTPError as e:
        try:
            body = json.loads(e.read().decode('utf-8'))
            msg = body.get('error', {}).get('message') or str(e)
        except Exception:
            msg = str(e)
        raise HifzError(msg) from e
    except URLError as e:
        raise HifzError(f'OpenAI şəbəkə xətası: {e.reason}') from e


def _encode_multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str]]) -> tuple[bytes, str]:
    boundary = f'----SiracHifz{uuid.uuid4().hex}'
    chunks: list[bytes] = []

    for name, value in fields.items():
        chunks.append(f'--{boundary}\r\n'.encode())
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        chunks.append(value.encode('utf-8'))
        chunks.append(b'\r\n')

    for name, (filename, content, content_type) in files.items():
        chunks.append(f'--{boundary}\r\n'.encode())
        chunks.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode(),
        )
        chunks.append(f'Content-Type: {content_type}\r\n\r\n'.encode())
        chunks.append(content)
        chunks.append(b'\r\n')

    chunks.append(f'--{boundary}--\r\n'.encode())
    body = b''.join(chunks)
    content_type = f'multipart/form-data; boundary={boundary}'
    return body, content_type


def _normalize_arabic(text: str) -> str:
    if not text:
        return ''
    t = text
    t = re.sub(r'[\u064B-\u065F\u0670\u06D6-\u06ED\u0610-\u061A\u08F0-\u08FF]', '', t)
    t = re.sub(r'[\u200E\u200F\u200B\u200C\u200D\uFEFF\u0640]', '', t)
    t = re.sub(r'[\u0622\u0623\u0625\u0671\u0672\u0673\u0675]', '\u0627', t)
    t = t.replace('\u0649', '\u064A').replace('\u0629', '\u0647')
    t = re.sub(r'[^\u0621-\u063A\u0641-\u064A0-9]', '', t)
    return t


def _levenshtein(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


def _local_verdict(expected: str, transcribed: str) -> dict[str, Any]:
    na = _normalize_arabic(expected)
    nb = _normalize_arabic(transcribed)
    if not na or not nb:
        return {'correct': False, 'score': 0}
    if na == nb:
        return {'correct': True, 'score': 100}
    dist = _levenshtein(na, nb)
    score = max(0, round((1 - dist / max(len(na), len(nb))) * 100))
    return {'correct': score >= 78, 'score': score}


def _feedback_az(expected: str, transcribed: str, correct: bool, score: int) -> str:
    if correct:
        return 'Əla! Ayə düzgün oxundu.'
    na = _normalize_arabic(expected)
    nb = _normalize_arabic(transcribed)
    if not nb:
        return 'Səs tanınmadı. Yenidən və aydın oxuyun.'
    if len(nb) < len(na) * 0.85:
        return 'Bəzi sözlər atlanmış ola bilər — ayəni yenidən yoxlayın.'
    if len(nb) > len(na) * 1.12:
        return 'Əlavə sözlər eşidildi — yaddaşınızı yoxlayın.'
    if score >= 60:
        return 'Demək olar ki, düzgündür, amma kiçik fərqlər var — bir daha oxuyun.'
    return 'Tam uyğun deyil — müəllimin düzgün oxunuşunu dinləyib yenidən cəhd edin.'


def _format_tajweed_lessons(context: list[dict]) -> list[dict]:
    out: list[dict] = []
    for lesson in context[:6]:
        rid = str(lesson.get('id') or '').strip()
        title = str(lesson.get('title') or '').strip()
        content = str(lesson.get('content') or '').strip()
        if not rid or not title:
            continue
        if len(content) > 280:
            content = content[:277].rstrip() + '…'
        out.append({
            'ruleId': rid,
            'ruleTitle': title,
            'content': content,
        })
    return out


def _transcribe(audio_file) -> str:
    audio_file.seek(0)
    raw = audio_file.read()
    name = getattr(audio_file, 'name', 'recitation.m4a') or 'recitation.m4a'
    content_type = getattr(audio_file, 'content_type', None) or mimetypes.guess_type(name)[0] or 'audio/m4a'

    body, ctype = _encode_multipart(
        {
            'model': 'whisper-1',
            'language': 'ar',
            'prompt': 'قرآن كريم تلاوة بالعربية',
            'response_format': 'json',
        },
        {'file': (name, raw, content_type)},
    )

    req = Request(
        f'{OPENAI_API_BASE}/audio/transcriptions',
        data=body,
        headers={
            'Authorization': f'Bearer {_api_key()}',
            'Content-Type': ctype,
        },
        method='POST',
    )
    try:
        with urlopen(req, timeout=90.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))
    except HTTPError as e:
        try:
            err = json.loads(e.read().decode('utf-8'))
            msg = err.get('error', {}).get('message') or str(e)
        except Exception:
            msg = str(e)
        raise HifzError(f'Whisper xətası: {msg}') from e
    except URLError as e:
        raise HifzError(f'Whisper şəbəkə xətası: {e.reason}') from e

    return (data.get('text') or '').strip()


def evaluate_hifz_recitation(
    audio_file,
    expected_arabic: str,
    surah_id: int | None = None,
    ayah_number: int | None = None,
) -> dict[str, Any]:
    expected_arabic = (expected_arabic or '').strip()
    if not expected_arabic:
        raise HifzError('expectedArabic boş ola bilməz.')

    applied_rules, tajweed_context = build_tajweed_context(expected_arabic)
    transcribed = _transcribe(audio_file)

    if not transcribed:
        return {
            'correct': False,
            'score': 0,
            'feedbackAz': 'Səs tanınmadı. Yenidən və aydın oxuyun.',
            'transcribed': '',
            'appliedRules': applied_rules,
            'tajweedLessons': _format_tajweed_lessons(tajweed_context),
            'tajweedNotes': [],
        }

    local = _local_verdict(expected_arabic, transcribed)
    correct = bool(local['correct'])
    score = int(local['score'])
    lessons = _format_tajweed_lessons(tajweed_context) if not correct else []

    result = {
        'correct': correct,
        'score': score,
        'feedbackAz': _feedback_az(expected_arabic, transcribed, correct, score),
        'transcribed': transcribed,
        'appliedRules': applied_rules,
        'tajweedLessons': lessons,
        'tajweedNotes': [],
    }
    result['score'] = max(0, min(100, score))
    return result
