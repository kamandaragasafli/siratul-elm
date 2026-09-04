"""Telegram Bot API — tətbiqdən gələn sualları qrupa göndərir."""

from __future__ import annotations

import html
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)


def _esc(text: str) -> str:
    return html.escape((text or '').strip())


def format_qa_telegram_message(
    *,
    name: str,
    contact: str,
    message: str,
    app_version: str = '',
) -> str:
    lines = [
        '📩 <b>Sirac tətbiq — yeni sual</b>',
        '',
        f'👤 <b>Ad:</b> {_esc(name)}',
    ]
    if contact.strip():
        lines.append(f'📞 <b>Əlaqə:</b> {_esc(contact)}')
    if app_version.strip():
        lines.append(f'📱 <b>Tətbiq:</b> {_esc(app_version)}')
    lines.extend(['', '💬 <b>Sual:</b>', _esc(message)])
    return '\n'.join(lines)


def send_telegram_message(text: str) -> bool:
    """Telegram qrupuna mesaj göndərir. Konfiqurasiya yoxdursa False qaytarır."""
    token = (getattr(settings, 'TELEGRAM_BOT_TOKEN', '') or '').strip()
    chat_id = (getattr(settings, 'TELEGRAM_QA_CHAT_ID', '') or '').strip()
    if not token or not chat_id:
        logger.warning('Telegram QA: TELEGRAM_BOT_TOKEN və ya TELEGRAM_QA_CHAT_ID təyin olunmayıb')
        return False

    payload = json.dumps(
        {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
        }
    ).encode('utf-8')

    url = f'https://api.telegram.org/bot{token}/sendMessage'
    req = urllib.request.Request(
        url,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = json.loads(resp.read().decode('utf-8'))
            if body.get('ok'):
                return True
            logger.error('Telegram QA cavabı uğursuz: %s', body)
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode('utf-8', errors='replace')
        except Exception:
            detail = str(exc)
        logger.error('Telegram QA HTTP xətası: %s — %s', exc.code, detail)
    except Exception as exc:
        logger.exception('Telegram QA göndərilmədi: %s', exc)

    return False
