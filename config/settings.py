"""
Настройки проекта «Uzum Market Clone» (контракт BACKEND_SPEC.md, v2).

Авторизация: Django-сессии в куке `uzum_sessionid` + double-submit CSRF `uzum_csrf`.
Деньги — целые числа. Пагинация — envelope с boolean next/previous.
"""

import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# ---------------------------------------------------------------- помощники env
def env(name, default=""):
    return os.getenv(name, default)


def env_bool(name, default=False):
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return raw.strip().lower() in ("1", "true", "yes", "on")


def env_int(name, default=0):
    raw = os.getenv(name)
    try:
        return int(raw) if raw not in (None, "") else int(default)
    except (TypeError, ValueError):
        return int(default)


def env_list(name, default=""):
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


# ------------------------------------------------------------------- базовое
SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set. Скопируйте .env.example в .env и сгенерируйте ключ.")
if len(SECRET_KEY) < 50 and not env_bool("DEBUG"):
    raise ValueError("SECRET_KEY слишком короткий для продакшена: нужно минимум 50 символов.")

DEBUG = env_bool("DEBUG", False)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,.onrender.com")
if DEBUG and ".localhost" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS += [".localhost", "testserver"]

# Домен фронта для CSRF-форм и админки (протокол обязателен).
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "apps.core",
    "apps.products",
    "apps.orders",
    "apps.uploads",
    "apps.users",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    # double-submit CSRF для /api/*: X-CSRFToken == кука uzum_csrf (§3 ТЗ)
    "apps.core.middleware.ApiCsrfMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.http.ConditionalGetMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

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

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------- пароли
# argon2id — как в ТЗ (§2): не md5 и не plaintext.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "/admin/login/"
LOGIN_REDIRECT_URL = "/admin/"

# ------------------------------------------------------------------------- БД
DATABASE_URL = env("DATABASE_URL")
if not DATABASE_URL:
    if DEBUG:
        DATABASE_URL = f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
    else:
        raise ImproperlyConfigured(
            "DATABASE_URL не задан. На сервере это обязательная настройка (например, postgres://…)."
        )

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=env_int("DB_CONN_MAX_AGE", 600),
        conn_health_checks=True,
        ssl_require=env_bool("DB_SSL_REQUIRE", not DEBUG) and "postgres" in DATABASE_URL.lower(),
    )
}


# --------------------------------------------------------------------- кэш
REDIS_URL = env("REDIS_URL")
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "uzum-market",
            "TIMEOUT": 60,
        }
    }

# Сессии — в БД: logout и смена пароля отзывают их на сервере.
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# --------------------------------------------------------------- сессии и CSRF
# Имена и флаги — §3 ТЗ. SameSite=Lax: фронт проксирует /api через себя (§10 ТЗ).
SESSION_COOKIE_NAME = "uzum_sessionid"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 7  # 7 дней
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG  # prod: только по HTTPS

CSRF_COOKIE_NAME = "uzum_csrf"
CSRF_COOKIE_HTTPONLY = False  # фронт читает куку из JS для X-CSRFToken
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_AGE = 60 * 60 * 24 * 365
CSRF_HEADER_NAME = "HTTP_X_CSRFTOKEN"
CSRF_COOKIE_DOMAIN = env("CSRF_COOKIE_DOMAIN") or None

# CORS: только конкретный домен фронта (§1 ТЗ)
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "user-agent",
    "x-csrftoken",
    "x-csrf-token",
    "x-requested-with",
]
CORS_EXPOSE_HEADERS = ["content-encoding", "etag", "last-modified"]


# --------------------------------------------------------------- статика/медиа
def _url_prefix(name, default):
    value = (env(name, default) or "").strip().strip("/")
    if not value:
        value = default.strip("/")
    if value.startswith(("http://", "https://")):
        return value if value.endswith("/") else value + "/"
    return f"/{value}/"


STATIC_URL = _url_prefix("STATIC_URL", "/static/")
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = _url_prefix("MEDIA_URL", "/media/")
MEDIA_ROOT = BASE_DIR / env("MEDIA_ROOT_DIR", "media")

_manifest_built = (STATIC_ROOT / "staticfiles.json").exists()
USE_MANIFEST_STATIC = not DEBUG and (env_bool("STATIC_MANIFEST_REQUIRED", False) or _manifest_built)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if USE_MANIFEST_STATIC
        else "whitenoise.storage.CompressedStaticFilesStorage"
    },
}

# Демо-картинки сида: /products/gen/*.svg (§9 ТЗ).
SEED_MEDIA_ROOT = BASE_DIR / "seed_media"
# Отдавать /media/ из Django (в проде статику раздаёт WhiteNoise/CDN).
SERVE_MEDIA = env_bool("SERVE_MEDIA", DEBUG)

# ----------------------------------------------------------------------- почта
EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend" if DEBUG else "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", "smtp.gmail.com" if not DEBUG else "localhost")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "no-reply@uzum-market.local")
SERVER_EMAIL = DEFAULT_FROM_EMAIL


# ------------------------------------------------------------------------ DRF
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.EnvelopePagination",
    "PAGE_SIZE": 20,
    "DEFAULT_AUTHENTICATION_CLASSES": ["apps.users.authentication.CookieSessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_THROTTLE_CLASSES": ["apps.core.throttling.ScopedIpThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "csrf": env("THROTTLE_CSRF", "60/min"),
        "login": env("THROTTLE_LOGIN", "10/min"),
        "register": env("THROTTLE_REGISTER", "10/min"),
        "password": env("THROTTLE_PASSWORD", "10/min"),
        "product_write": env("THROTTLE_PRODUCT_WRITE", "60/hour"),
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "NON_FIELD_ERRORS_KEY": "detail",
    "COERCE_DECIMAL_TO_STRING": True,
    "UNAUTHENTICATED_USER": "django.contrib.auth.models.AnonymousUser",
}

# ------------------------------------------------------------------ OpenAPI
SPECTACULAR_SETTINGS = {
    "TITLE": "Uzum Market Clone API",
    "DESCRIPTION": "Маркетплейс: каталог, заказы, отзывы, кабинеты покупателя и продавца. Контракт — BACKEND_SPEC.md.",
    "VERSION": "2.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_GENERATE_CHOICE_DESCRIPTION": False,
    "TAGS": [
        {"name": "auth", "description": "Регистрация, вход, профиль"},
        {"name": "products", "description": "Каталог товаров"},
        {"name": "categories", "description": "Категории"},
        {"name": "sellers", "description": "Магазины"},
        {"name": "reviews", "description": "Отзывы и ответы продавца"},
        {"name": "orders", "description": "Заказы и статусы"},
        {"name": "shop", "description": "Кабинет продавца"},
        {"name": "uploads", "description": "Загрузка картинок"},
        {"name": "service", "description": "Health и demo-reset"},
    ],
}

# ------------------------------------------------------------------ продакшен
if not DEBUG:
    # За прокси (Render/nginx) HTTPS определяется по X-Forwarded-Proto.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)

    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31_536_000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

SILENCED_SYSTEM_CHECKS = ["security.W021"]  # .csrf: Lax-куки — осознанно (фронт проксирует /api)

# ------------------------------------------------------------------------- i18n
LANGUAGE_CODE = env("LANGUAGE_CODE", "ru-ru")
TIME_ZONE = env("TIME_ZONE", "Asia/Tashkent")
USE_I18N = True
USE_TZ = True

# --------------------------------------------------------------- служебные env
BACKEND_ID = env("BACKEND_ID", "django")  # в /api/health: какая реализация отвечает
LOCK_DEMO = env_bool("UZUM_LOCK_DEMO", False)  # POST /api/demo/reset/ → 403
SEED_DEMO_DATA = env_bool("SEED_DEMO_DATA", True)

# Потолок тела запроса: покрывает multipart-картинки до 2 МБ (§7 ТЗ).
# (Django ограничивает и JSON, и multipart одной настройкой.)
DATA_UPLOAD_MAX_MEMORY_SIZE = 3 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 2 * 1024 * 1024

# ------------------------------------------------------------------------- лог
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose", "stream": "ext://sys.stdout"},
    },
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO" if DEBUG else "WARNING")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "apps": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO"), "propagate": False},
    },
}
