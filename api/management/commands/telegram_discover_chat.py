"""Telegram qrup chat ID-ni getUpdates-dən tapır."""

from __future__ import annotations

import json
import urllib.request

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Telegram botunun gördüyü chat ID-ləri göstərir (qrup üçün mesaj yazın).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--set',
            action='store_true',
            help='Tapılan qrup/kanal chat ID-ni .env faylına yaz',
        )

    def handle(self, *args, **options):
        token = (settings.TELEGRAM_BOT_TOKEN or '').strip()
        if not token:
            self.stderr.write('TELEGRAM_BOT_TOKEN .env-də yoxdur.')
            return

        url = (
            f'https://api.telegram.org/bot{token}/getUpdates'
            '?allowed_updates=["message","my_chat_member"]&limit=100'
        )
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        if not data.get('ok'):
            self.stderr.write(f'getUpdates uğursuz: {data}')
            return

        chats: dict[int, dict] = {}
        for item in data.get('result') or []:
            msg = item.get('message') or item.get('my_chat_member', {}).get('chat')
            if not msg:
                continue
            chat = msg if 'type' in msg else item.get('message', {}).get('chat')
            if not chat:
                chat = item.get('my_chat_member', {}).get('chat')
            if not chat:
                continue
            cid = chat.get('id')
            if cid is None:
                continue
            chats[cid] = {
                'id': cid,
                'type': chat.get('type', '?'),
                'title': chat.get('title') or chat.get('first_name') or chat.get('username') or '—',
            }

        if not chats:
            self.stdout.write(
                'Hech bir chat tapilmadi.\n'
                '1) Botu «Sirac sual» qrupuna admin elave edin\n'
                '2) Qrupda «test» yazin\n'
                '3) Bu emri yeniden ise salin'
            )
            return

        self.stdout.write('Tapilan chat-ler:')
        group_id = None
        for info in chats.values():
            line = f"  {info['id']}  ({info['type']})  {info['title']}"
            self.stdout.write(line)
            if info['type'] in ('group', 'supergroup', 'channel'):
                group_id = info['id']

        if options['set'] and group_id is not None:
            env_path = settings.BASE_DIR / '.env'
            text = env_path.read_text(encoding='utf-8-sig')
            if 'TELEGRAM_QA_CHAT_ID=' in text:
                lines = []
                for line in text.splitlines():
                    if line.startswith('TELEGRAM_QA_CHAT_ID='):
                        lines.append(f'TELEGRAM_QA_CHAT_ID={group_id}')
                    else:
                        lines.append(line)
                env_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
            else:
                env_path.write_text(text.rstrip() + f'\nTELEGRAM_QA_CHAT_ID={group_id}\n', encoding='utf-8')
            self.stdout.write(self.style.SUCCESS(f'TELEGRAM_QA_CHAT_ID={group_id} yazildi. Django-nu yeniden basladin.'))
        elif group_id is None:
            self.stdout.write(
                '\nQrup/kanal tapilmadi — yalniz sexsi mesaj var. '
                'Botu qrupa elave edib qrupda mesaj yazin.'
            )
