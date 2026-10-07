"""
Django settings for the Nepo backend.
Media files are stored in Supabase Storage (not Django's local storage) —
see accounts/business file URL fields: everything is a URL pointing at
your Supabase bucket, uploaded directly from the Next.js frontend using
the Supabase JS client + signed policies, or via the /api/uploads/ helper
which proxies to the Supabase Storage REST API using SUPABASE_SERVICE_KEY.
"""
import os
from datetime import timedelta
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def env_list(name, default):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


# Off unless explicitly enabled: DEBUG leaks stack traces and settings to anyone.
DEBUG = os.getenv("DJANGO_DEBUG", "False") == "True"

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if not DEBUG:
        # The key signs every login token; a guessable default would let anyone forge one.
        raise ImproperlyConfigured("Set DJANGO_SECRET_KEY (a long random string) in the environment.")
    SECRET_KEY = "django-insecure-local-development-only-key-do-not-use-in-production"

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,nepobackend.onrender.com")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "accounts",
    "content",
    "social",
    "business",
    "uploads",
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

ROOT_URLCONF = "nepo.urls"

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

WSGI_APPLICATION = "nepo.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}
# For production, point this at Supabase Postgres instead, e.g.:
# DATABASES["default"] = {
#     "ENGINE": "django.db.backends.postgresql",
#     "NAME": os.getenv("SUPABASE_DB_NAME", "postgres"),
#     "USER": os.getenv("SUPABASE_DB_USER"),
#     "PASSWORD": os.getenv("SUPABASE_DB_PASSWORD"),
#     "HOST": os.getenv("SUPABASE_DB_HOST"),
#     "PORT": os.getenv("SUPABASE_DB_PORT", "5432"),
# }

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "uploads" / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ),
    # The HTML browsable API is a dev convenience; production only speaks JSON.
    "DEFAULT_RENDERER_CLASSES": (
        ("rest_framework.renderers.JSONRenderer", "rest_framework.renderers.BrowsableAPIRenderer")
        if DEBUG else ("rest_framework.renderers.JSONRenderer",)
    ),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_PAGINATION_CLASS": "nepo.pagination.DefaultCursorPagination",
    "PAGE_SIZE": 12,
    # Rate limits. "auth" guards login/register against password guessing and
    # account spam; the global limits only stop runaway clients and scripts.
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "300/min",
        "user": "1200/min",
        "auth": "10/min",
        "token_refresh": "60/min",
        "uploads": "60/min",
    },
}

SIMPLE_JWT = {
    # Short-lived access tokens; the frontend renews them silently with the
    # refresh token, which is rotated on every use and revoked on logout.
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    # Changing the password invalidates every token issued before it.
    "CHECK_REVOKE_TOKEN": True,
}

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", "http://localhost:3000,https://nepowebapp.netlify.app"
)
# Auth uses an Authorization header, not cookies, so cross-site credentials are never needed.
CORS_ALLOW_CREDENTIALS = False

CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "https://nepobackend.onrender.com")

# --- Security hardening (production) ---
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
if not DEBUG:
    # Render (and most hosts) terminate HTTPS at a proxy and forward this header.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30

# Deliberately off: Render's edge already redirects HTTP->HTTPS (W008), and on a
# shared *.onrender.com domain we must not claim subdomains or HSTS preload (W005, W021).
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W008", "security.W021"]

# Uploads: per-file caps enforced in uploads/views.py.
MAX_IMAGE_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_VIDEO_UPLOAD_BYTES = 100 * 1024 * 1024

# Bump when the Terms & Conditions text changes (frontend: src/lib/terms.ts).
TERMS_VERSION = "2026-10-07"

# --- Supabase (media storage) ---
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
SUPABASE_MEDIA_BUCKET = os.getenv("SUPABASE_MEDIA_BUCKET", "nepo-media")
