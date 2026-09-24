"""Expo Push göndərmə — https://docs.expo.dev/push-notifications/sending-notifications/"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any

logger = logging.getLogger(__name__)

EXPO_PUSH_URL = 'https://exp.host/--/api/v2/push/send'
CHUNK = 100


def _is_expo_token(token: str) -> bool:
    t = (token or '').strip()
    return t.startswith('ExponentPushToken[') or t.startswith('ExpoPushToken[')


def send_expo_push(
    tokens: list[str],
    *,
    title: str,
    body: str,
    data: dict[str, Any] | None = None,
) -> dict[str, int]:
    """Bütün Expo tokenlərə bildiriş göndər. invalid tokenləri silmək üçün sayğac qaytarır."""
    clean = [t.strip() for t in tokens if _is_expo_token(t)]
    if not clean:
        return {'sent': 0, 'failed': 0, 'invalid': 0}

    sent = 0
    failed = 0
    invalid = 0
    payload_data = data or {}

    for i in range(0, len(clean), CHUNK):
        chunk = clean[i : i + CHUNK]
        messages = [
            {
                'to': tok,
                'sound': 'default',
                'title': title[:100],
                'body': body[:200],
                'data': payload_data,
                'priority': 'high',
                'channelId': 'live',
            }
            for tok in chunk
        ]
        try:
            req = urllib.request.Request(
                EXPO_PUSH_URL,
                data=json.dumps(messages).encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                method='POST',
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
            parsed = json.loads(raw)
            tickets = parsed.get('data') or []
            if isinstance(tickets, dict):
                tickets = [tickets]
            for ticket in tickets:
                if not isinstance(ticket, dict):
                    failed += 1
                    continue
                if ticket.get('status') == 'ok':
                    sent += 1
                else:
                    failed += 1
                    details = ticket.get('details') or {}
                    err = (ticket.get('message') or '') + str(details.get('error') or '')
                    if 'DeviceNotRegistered' in err or 'InvalidCredentials' in err:
                        invalid += 1
        except urllib.error.HTTPError as he:
            logger.warning('Expo push HTTP %s: %s', he.code, he.read()[:200])
            failed += len(chunk)
        except Exception:
            logger.exception('Expo push failed')
            failed += len(chunk)

    return {'sent': sent, 'failed': failed, 'invalid': invalid}


def notify_live_started(*, title: str, teacher_name: str = '', lesson_id: int | None = None) -> dict[str, int]:
    from .models import PushDevice

    tokens = list(PushDevice.objects.values_list('token', flat=True))
    teacher = (teacher_name or '').strip()
    body = f'{teacher} canlı dərsə başladı — qoşulun' if teacher else 'Canlı dərs başladı — qoşulun'
    result = send_expo_push(
        tokens,
        title=title or 'Canlı dərs',
        body=body,
        data={
            'type': 'live_started',
            'lessonId': lesson_id,
            'screen': 'LiveLessons',
        },
    )
    logger.info(
        'Live push «%s»: sent=%s failed=%s invalid=%s tokens=%s',
        title,
        result['sent'],
        result['failed'],
        result['invalid'],
        len(tokens),
    )
    return result
