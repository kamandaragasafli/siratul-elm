"""Superuser yarat / yenilə — default: Kamandar (Render skripti də set edir)."""

from __future__ import annotations

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Superuser yarat / yenilə (DJANGO_SUPERUSER_* və ya default Kamandar)'

    def handle(self, *args, **options):
        username = (os.environ.get('DJANGO_SUPERUSER_USERNAME') or 'Kamandar').strip()
        password = (os.environ.get('DJANGO_SUPERUSER_PASSWORD') or '20012001Kamandar').strip()
        email = (os.environ.get('DJANGO_SUPERUSER_EMAIL') or 'kamandar@localhost').strip()

        User = get_user_model()
        user = User.objects.filter(username=username).first()
        if user:
            user.set_password(password)
            user.email = email
            user.is_staff = True
            user.is_superuser = True
            user.is_active = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Superuser yeniləndi: {username}'))
        else:
            User.objects.create_superuser(username=username, email=email, password=password)
            self.stdout.write(self.style.SUCCESS(f'Superuser yaradıldı: {username}'))
