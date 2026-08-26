"""Django settings for ParcelPilot Support Intelligence."""
import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent
_docs_env = os.getenv("DOCS_DIR")
DOCS_DIR = Path(_docs_env) if _docs_env else BASE_DIR.parent / "Docs for implementation"
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

_INSECURE_SECRETS = {
    "dev-insecure-parcelpilot-change-me",
    "dev-jwt-secret",
    "compose-dev-secret",
    "compose-jwt-secret",
}

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "dev-insecure-parcelpilot-change-me")
DEBUG = os.getenv("DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]
for _host in ("localhost", "127.0.0.1", "backend"):
    if _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)
_jwt_secret = os.getenv("JWT_SECRET", SECRET_KEY)
if not DEBUG:
    if not SECRET_KEY or SECRET_KEY in _INSECURE_SECRETS:
        raise ImproperlyConfigured("Set a unique DJANGO_SECRET_KEY when DEBUG=false")
    if not _jwt_secret or _jwt_secret in _INSECURE_SECRETS:
        raise ImproperlyConfigured("Set a unique JWT_SECRET when DEBUG=false")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "apps.users",
    "apps.accounts",
    "apps.orders",
    "apps.tickets",
    "apps.documents",
    "apps.agent",
    "apps.source_resolution",
    "apps.actions",
    "apps.issue_intelligence",
    "apps.observability",
    "apps.audit",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

_pg_user = os.getenv("POSTGRES_USER") or os.getenv("USER") or "postgres"
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "parcelpilot"),
        "USER": _pg_user,
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", ""),
        "HOST": os.getenv("POSTGRES_HOST", "localhost"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024

USE_X_FORWARDED_HOST = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "false").lower() == "true"
SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=12),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "SIGNING_KEY": _jwt_secret,
}

CORS_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    ).split(",")
    if o.strip()
]
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = [
    o.strip()
    for o in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if o.strip()
]

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
DATASET_REFERENCE_TIME = os.getenv(
    "DATASET_REFERENCE_TIME", "2026-08-16T11:00:00+05:30"
)
PENDING_ACTION_TTL_MINUTES = int(os.getenv("PENDING_ACTION_TTL_MINUTES", "30"))
EMBEDDING_DIMENSIONS = 1536
# When no API key, use deterministic local hash embeddings for demo/tests
USE_MOCK_EMBEDDINGS = os.getenv("USE_MOCK_EMBEDDINGS", "").lower() == "true" or not OPENAI_API_KEY
