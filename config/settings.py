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

# ── Database ────────────────────────────────────────────────────────────────
# Lokal: SQLite. Production (Render + Neon): DATABASE_URL env.
# Neon console → Connection string → "Pooled connection" (Render üçün tövsiyə):
#   postgresql://USER:PASS@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require
_DATABASE_URL = os.environ.get('DATABASE_URL', '').strip()
if _DATABASE_URL:
    import dj_database_url

    # Neon serverless: uzun yaşayan bağlantı SSL ilə kəsilir.
    # Pooler URL (-pooler) + qısa/conn_max_age=0 tövsiyə olunur.
    _conn_max_age = int(os.environ.get('DB_CONN_MAX_AGE', '0') or '0')
    DATABASES = {
        'default': dj_database_url.config(
            default=_DATABASE_URL,
            conn_max_age=_conn_max_age,
            conn_health_checks=True,
            ssl_require=True,
        )
    }
else:
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
# Supabase Storage VƏYA Cloudflare R2 (hər ikisi S3-compatible; AWS hesabı lazım deyil).
#
# --- Cloudflare R2 (böyük PDF üçün) ---
#   AWS_ACCESS_KEY_ID=...
#   AWS_SECRET_ACCESS_KEY=...
#   AWS_STORAGE_BUCKET_NAME=media
#   AWS_S3_REGION_NAME=auto
#   AWS_S3_ENDPOINT_URL=https://<ACCOUNT_ID>.r2.cloudflarestorage.com
#   AWS_S3_CUSTOM_DOMAIN=pub-xxxx.r2.dev   # bucket Public access → r2.dev
#   (Supabase env-ləri olmamalı — əks halda Supabase üstün gəlir)
#
# --- Supabase Storage ---
#   USE_SUPABASE_STORAGE=1
#   SUPABASE_PROJECT_REF=abcdefghij
#   SUPABASE_STORAGE_BUCKET=media
#   SUPABASE_S3_ACCESS_KEY=...
#   SUPABASE_S3_SECRET_KEY=...
#   SUPABASE_S3_REGION=eu-central-1
#
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'  # yt-dlp lokal cache üçün saxlanır


def _env(*names: str, default: str = '') -> str:
    for name in names:
        val = os.environ.get(name, '').strip()
        if val:
            return val
    return default


_SUPABASE_REF = _env('SUPABASE_PROJECT_REF')
_BUCKET = _env('SUPABASE_STORAGE_BUCKET', 'AWS_STORAGE_BUCKET_NAME', default='media')
_ACCESS_KEY = _env('SUPABASE_S3_ACCESS_KEY', 'AWS_ACCESS_KEY_ID')
_SECRET_KEY = _env('SUPABASE_S3_SECRET_KEY', 'AWS_SECRET_ACCESS_KEY')
_REGION = _env('SUPABASE_S3_REGION', 'AWS_S3_REGION_NAME', default='eu-central-1')

_R2_ENDPOINT = _env('AWS_S3_ENDPOINT_URL')
_USE_R2 = 'r2.cloudflarestorage.com' in (_R2_ENDPOINT or '')

_USE_SUPABASE = (not _USE_R2) and (
    os.environ.get('USE_SUPABASE_STORAGE', '').lower() in ('1', 'true', 'yes')
    or bool(_SUPABASE_REF or _env('SUPABASE_S3_ACCESS_KEY'))
)

if _USE_R2:
    # Cloudflare R2 — public URL üçün AWS_S3_CUSTOM_DOMAIN (r2.dev) mütləqdir
    _ENDPOINT = _R2_ENDPOINT
    _PUBLIC = _env('AWS_S3_CUSTOM_DOMAIN') or None
    _REGION = _env('AWS_S3_REGION_NAME', default='auto')
elif _USE_SUPABASE and (_SUPABASE_REF or _env('SUPABASE_S3_ENDPOINT_URL')):
    _ENDPOINT = _env(
        'SUPABASE_S3_ENDPOINT_URL',
        'AWS_S3_ENDPOINT_URL',
        default=(
            f'https://{_SUPABASE_REF}.supabase.co/storage/v1/s3' if _SUPABASE_REF else ''
        ),
    ) or None
    _PUBLIC = (
        _env(
            'SUPABASE_PUBLIC_URL',
            'AWS_S3_CUSTOM_DOMAIN',
            default=(
                f'{_SUPABASE_REF}.supabase.co/storage/v1/object/public/{_BUCKET}'
                if _SUPABASE_REF
                else ''
            ),
        )
        .removeprefix('https://')
        .removeprefix('http://')
        .rstrip('/')
        or None
    )
elif _env('AWS_STORAGE_BUCKET_NAME') or _R2_ENDPOINT:
    _ENDPOINT = _R2_ENDPOINT or None
    _PUBLIC = _env('AWS_S3_CUSTOM_DOMAIN') or None
else:
    _ENDPOINT = None
    _PUBLIC = None

# Endpoint və ya public URL olmadan remote media açılmır (AWS S3 fallback yoxdur)
_USE_REMOTE_MEDIA = bool(_BUCKET and _ACCESS_KEY and _SECRET_KEY and (_ENDPOINT or _PUBLIC))

if _USE_REMOTE_MEDIA:
    if 'storages' not in INSTALLED_APPS:
        INSTALLED_APPS = [*INSTALLED_APPS, 'storages']

    # django-storages boto3 — Supabase Storage S3 gateway
    AWS_ACCESS_KEY_ID = _ACCESS_KEY
    AWS_SECRET_ACCESS_KEY = _SECRET_KEY
    AWS_STORAGE_BUCKET_NAME = _BUCKET
    AWS_S3_REGION_NAME = _REGION
    AWS_S3_ENDPOINT_URL = _ENDPOINT or None
    AWS_S3_CUSTOM_DOMAIN = _PUBLIC or None
    AWS_DEFAULT_ACL = None  # Supabase ACL-siz; bucket public olmalıdır
    AWS_QUERYSTRING_AUTH = os.environ.get('AWS_QUERYSTRING_AUTH', '').lower() in (
        '1',
        'true',
        'yes',
    )
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    AWS_S3_ADDRESSING_STYLE = 'path'

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
    else:
        MEDIA_URL = f'{AWS_S3_ENDPOINT_URL.rstrip("/")}/{AWS_STORAGE_BUCKET_NAME}/'
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
# Vacib: KEY + SECRET eyni LiveKit layihəsindən olmalıdır (URL ilə uyğun).
def _env_clean(name: str) -> str:
    return (os.environ.get(name, '') or '').strip().strip('"').strip("'").strip()


LIVEKIT_API_KEY = _env_clean('LIVEKIT_API_KEY')
LIVEKIT_API_SECRET = _env_clean('LIVEKIT_API_SECRET')
LIVEKIT_SERVER_URL = _env_clean('LIVEKIT_SERVER_URL')
# Müəllim kodları Django admin → «Canlı yayım müəllimləri» bölməsindədir.

# YouTube yt-dlp bot yoxlaması — Netscape cookies.txt yolu (Render disk / secret file)
YTDLP_COOKIES_FILE = os.environ.get('YTDLP_COOKIES_FILE', '').strip()
# PO token provider (bgutil-ytdlp-pot-provider) — məs: http://127.0.0.1:4416
YTDLP_PO_PROVIDER_URL = os.environ.get('YTDLP_PO_PROVIDER_URL', '').strip()

# ── Telegram sual-cavab (tətbiqdən birbaşa göndərmə) ────────────────────────
# Botu «Sirac sual» qrupuna admin kimi əlavə edin; chat ID-ni getUpdates ilə alın.
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_QA_CHAT_ID = os.environ.get('TELEGRAM_QA_CHAT_ID', '')
