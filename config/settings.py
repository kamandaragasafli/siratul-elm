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

# ── Media storage ────────────────────────────────────────────────────────────
# Default: lokal disk (MEDIA_ROOT). Render disk ephemeral-dır — production-da
# AWS S3 / DigitalOcean Spaces / Cloudflare R2 təyin edin (django-storages).
#
# Lazımi env (nümunə — DigitalOcean Spaces):
#   AWS_ACCESS_KEY_ID=...
#   AWS_SECRET_ACCESS_KEY=...
#   AWS_STORAGE_BUCKET_NAME=sirac-media
#   AWS_S3_REGION_NAME=nyc3
#   AWS_S3_ENDPOINT_URL=https://nyc3.digitaloceanspaces.com
#   AWS_S3_CUSTOM_DOMAIN=sirac-media.nyc3.cdn.digitaloceanspaces.com  # optional
#
# Cloudflare R2:
#   AWS_S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
#   AWS_S3_REGION_NAME=auto
#
# AWS S3: ENDPOINT_URL boş buraxın; REGION = us-east-1 və s.
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'  # yt-dlp lokal cache üçün saxlanır

_AWS_BUCKET = os.environ.get('AWS_STORAGE_BUCKET_NAME', '').strip()
_USE_S3 = os.environ.get('USE_S3', '').lower() in ('1', 'true', 'yes') or bool(_AWS_BUCKET)

if _USE_S3 and _AWS_BUCKET:
    if 'storages' not in INSTALLED_APPS:
        INSTALLED_APPS = [*INSTALLED_APPS, 'storages']

    AWS_ACCESS_KEY_ID = os.environ.get('AWS_ACCESS_KEY_ID', '').strip()
    AWS_SECRET_ACCESS_KEY = os.environ.get('AWS_SECRET_ACCESS_KEY', '').strip()
    AWS_STORAGE_BUCKET_NAME = _AWS_BUCKET
    AWS_S3_REGION_NAME = os.environ.get('AWS_S3_REGION_NAME', 'us-east-1').strip()
    AWS_S3_ENDPOINT_URL = os.environ.get('AWS_S3_ENDPOINT_URL', '').strip() or None
    AWS_S3_CUSTOM_DOMAIN = os.environ.get('AWS_S3_CUSTOM_DOMAIN', '').strip() or None
    AWS_DEFAULT_ACL = os.environ.get('AWS_DEFAULT_ACL', 'public-read').strip() or None
    AWS_QUERYSTRING_AUTH = os.environ.get('AWS_QUERYSTRING_AUTH', '').lower() in (
        '1',
        'true',
        'yes',
    )
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
    AWS_S3_FILE_OVERWRITE = False

    STORAGES = {
        'default': {
            'BACKEND': 'storages.backends.s3boto3.S3Boto3Storage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
        },
    }
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/'
    elif AWS_S3_ENDPOINT_URL:
        # Spaces / R2 path-style URL
        MEDIA_URL = f'{AWS_S3_ENDPOINT_URL.rstrip("/")}/{AWS_STORAGE_BUCKET_NAME}/'
    else:
        MEDIA_URL = f'https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/'
else:
    STORAGES = {
        'default': {
            'BACKEND': 'django.core.files.storage.FileSystemStorage',
        },
        'staticfiles': {
            'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
        },
    }

# PDF kitab yükləməsi (panel)
DATA_UPLOAD_MAX_MEMORY_SIZE = 120 * 1024 * 1024  # 120 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = '/login/'
LOGIN_REDIRECT_URL = '/'
LOGOUT_REDIRECT_URL = '/login/'

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
