import os
import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .config import env, env_bool, env_int, env_list

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key"
    else:
        raise ImproperlyConfigured("Ustaw DJANGO_SECRET_KEY")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if DEBUG and not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]
for host in ("127.0.0.1", "localhost"):
    if host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)

CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = ["converter"]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "distoweb.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": ["django.template.context_processors.request"]},
    }
]

WSGI_APPLICATION = "distoweb.wsgi.application"

DATABASES = {}

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"

LANGUAGE_CODE = "pl"
TIME_ZONE = "Europe/Warsaw"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = env_int("DJANGO_HSTS_SECONDS", 0)

X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

DATA_UPLOAD_MAX_NUMBER_FILES = env_int("DATA_UPLOAD_MAX_NUMBER_FILES", 1000)
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int("FILE_UPLOAD_MAX_MEMORY_SIZE_MB", 5) * 1024 * 1024

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

DISTO_PASSWORD = env("DISTO_PASSWORD", "")
DISTO_MAX_FILES = env_int("DISTO_MAX_FILES", 40)
DISTO_MAX_FILE_BYTES = env_int("DISTO_MAX_FILE_MB", 25) * 1024 * 1024
DISTO_MAX_TOTAL_BYTES = env_int("DISTO_MAX_TOTAL_MB", 150) * 1024 * 1024
DISTO_EPHEMERAL_DIR = env("DISTO_EPHEMERAL_DIR", os.path.join(tempfile.gettempdir(), "distoweb"))
DISTO_EPHEMERAL_TTL = env_int("DISTO_EPHEMERAL_TTL", 900)
DISTO_RATE_LIMIT = env_int("DISTO_RATE_LIMIT", 30)
DISTO_RATE_WINDOW = env_int("DISTO_RATE_WINDOW", 600)
DISTO_CLIENT_IP_HEADER = env("DISTO_CLIENT_IP_HEADER", "REMOTE_ADDR")
