"""
Django settings for Sirac backend.
"""

from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

# backend/.env — OPENAI_API_KEY və s. (fayl dəyərləri üstünlük təşkil edir)
_env_path = BASE_DIR / '.env'
if _env_path.exists():
    for _line in _env_path.read_text(encoding='utf-8-sig').splitlines():
        _line = _line.strip()
        if not _line or _line.startswith('#') or '=' not in _line:
            continue
        _k, _, _v = _line.partition('=')
        _v = _v.strip().strip('"').strip("'")
        if _k.strip():
            os.environ[_k.strip()] = _v

SECRET_KEY = 'django-insecure-5rei!(v0azf7p5qvazfhaxvtn17r4@lf5wrsyaxz!ey(otf9s7'

DEBUG = True

# Mobil və lokal şəbəkə üçün (sonra production-da məhdudlaşdırılacaq)
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'corsheaders',
    'api',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'az'
TIME_ZONE = 'Asia/Baku'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
    },
}
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Mobil (Expo / React Native) üçün CORS — inkişaf mərhələsi
CORS_ALLOW_ALL_ORIGINS = True

REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')
HIFZ_MAX_AUDIO_MB = int(os.environ.get('HIFZ_MAX_AUDIO_MB', '12'))

# ── LiveKit (cloud.livekit.io və ya öz serveriniz — mütləq wss://) ───────────
# Render Environment-də təyin edin. Default lokal IP APK-də işləmir.
LIVEKIT_API_KEY = os.environ.get('LIVEKIT_API_KEY', '').strip()
LIVEKIT_API_SECRET = os.environ.get('LIVEKIT_API_SECRET', '').strip()
LIVEKIT_SERVER_URL = os.environ.get('LIVEKIT_SERVER_URL', '').strip()
# Müəllim kodları Django admin → «Canlı yayım müəllimləri» bölməsindədir.

# YouTube yt-dlp bot yoxlaması — Netscape cookies.txt yolu (Render disk / secret file)
YTDLP_COOKIES_FILE = os.environ.get('YTDLP_COOKIES_FILE', '').strip()

# ── Telegram sual-cavab (tətbiqdən birbaşa göndərmə) ────────────────────────
# Botu «Sirac sual» qrupuna admin kimi əlavə edin; chat ID-ni getUpdates ilə alın.
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_QA_CHAT_ID = os.environ.get('TELEGRAM_QA_CHAT_ID', '')
