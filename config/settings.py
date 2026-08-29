"""
Настройки проекта.
Единый источник правды для JWT-cookie, пагинации, фильтров и безопасности.
Адаптирован для работы как локально (localhost), так и на Render.com.
"""

import os
from datetime import timedelta
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
    raise ValueError(
        "SECRET_KEY environment variable is not set. "
        "Скопируйте .env.example в .env и сгенерируйте ключ."
    )
if len(SECRET_KEY) < 50 and not env_bool("DEBUG"):
    raise ValueError("SECRET_KEY слишком короткий для продакшена: нужно минимум 50 символов.")

DEBUG = env_bool("DEBUG", False)

# Добавляем .onrender.com по умолчанию для продакшена
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,.onrender.com")
if DEBUG and ".localhost" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS += [".localhost", "testserver"]

# КРИТИЧЕСКИ ВАЖНО для Render + внешний фронтенд (Vercel/localhost)
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", 
    "http://localhost:3000,http://127.0.0.1:3000,https://your-frontend-domain.vercel.app"
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
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "apps.products",
    "apps.users",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
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


# ------------------------------------------------------------------------- БД
DATABASE_URL = env("DATABASE_URL")
if not DATABASE_URL:
    if DEBUG:
        DATABASE_URL = f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
    else:
        raise ImproperlyConfigured(
            "DATABASE_URL не задан. На Render это обязательная настройка (Internal Database URL)."
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

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"


# ----------------------------------------------------------- статика и медиа
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


# ------------------------------------------------------------------ авторизация
AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

ACCESS_TOKEN_LIFETIME = timedelta(minutes=env_int("ACCESS_TOKEN_MINUTES", 15))
REFRESH_TOKEN_LIFETIME = timedelta(days=env_int("REFRESH_TOKEN_DAYS", 7))

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": ACCESS_TOKEN_LIFETIME,
    "REFRESH_TOKEN_LIFETIME": REFRESH_TOKEN_LIFETIME,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "AUTH_TOKEN_CLASSES": ("rest_framework_simplejwt.tokens.AccessToken",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "JTI_CLAIM": "jti",
    "ROTATE_REFRESH_TOKENS": env_bool("JWT_ROTATE_REFRESH", True),
    "BLACKLIST_AFTER_ROTATION": env_bool("JWT_BLACKLIST_AFTER_ROTATION", True),
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
}

# ==============================================================================
# 🔥 ИСПРАВЛЕННЫЙ БЛОК COOKIE И CORS (Ключ к решению вашей проблемы)
# ==============================================================================

# 1. Имя CSRF куки должно совпадать с тем, что ждет фронтенд (uzum_csrf)
CSRF_COOKIE_NAME = env("CSRF_COOKIE_NAME", "uzum_csrf")

# 2. Логика SameSite и Secure:
# Локально (DEBUG=True): Lax, Secure=False (разрешено на http://localhost)
# Продакшен (DEBUG=False): None, Secure=True (обязательно для кросс-доменных запросов на https)
_COOKIE_SAMESITE_DEFAULT = "Lax" if DEBUG else "None"
_COOKIE_SECURE_DEFAULT = False if DEBUG else True

COOKIE_SAMESITE = env("COOKIE_SAMESITE", _COOKIE_SAMESITE_DEFAULT)
COOKIE_SECURE = env_bool("COOKIE_SECURE", _COOKIE_SECURE_DEFAULT)

if COOKIE_SAMESITE.lower() == "none" and not COOKIE_SECURE:
    raise ValueError("SameSite=None требует Secure=True (браузер отклонит такую cookie).")

JWT_COOKIE = {
    "ACCESS": env("ACCESS_COOKIE_NAME", "uzum_access_token"),
    "REFRESH": env("REFRESH_COOKIE_NAME", "uzum_refresh_token"),
    "SECURE": COOKIE_SECURE,
    "SAMESITE": COOKIE_SAMESITE,
    "HTTP_ONLY": env_bool("COOKIE_HTTP_ONLY", True),
    "ACCESS_PATH": env("ACCESS_COOKIE_PATH", "/"),
    "REFRESH_PATH": env("REFRESH_COOKIE_PATH", "/api/auth/"),
    "CSRF_NAME": CSRF_COOKIE_NAME,
}

# 3. CORS: Читаем из .env, запрещаем "все подряд" при использовании credentials
CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS", 
    "http://localhost:3000,http://127.0.0.1:3000,https://your-frontend-domain.vercel.app"
)
CORS_ALLOW_ALL_ORIGINS = False  # ВАЖНО: Должно быть False при использовании куки!
CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
    "x-csrf-token",
]
CORS_EXPOSE_HEADERS = ["content-encoding", "etag", "last-modified", "set-cookie"]

# ==============================================================================

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "apps.products.pagination.CatalogPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.users.authentication.CookieJWTAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "login": env("THROTTLE_LOGIN", "10/min"),
        "register": env("THROTTLE_REGISTER", "5/hour"),
        "refresh": env("THROTTLE_REFRESH", "60/hour"),
    },
    "EXCEPTION_HANDLER": "apps.users.exceptions.api_exception_handler",
    "NON_FIELD_ERRORS_KEY": "detail",
    "COERCE_DECIMAL_TO_STRING": True,
}

# ------------------------------------------------------------------- продакшен
if not DEBUG:
    # Render использует прокси, поэтому этот заголовок критически важен для определения HTTPS
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    
    # Принудительно применяем безопасные настройки куки для продакшена
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = COOKIE_SAMESITE
    CSRF_COOKIE_SAMESITE = COOKIE_SAMESITE
    CSRF_COOKIE_DOMAIN = env("CSRF_COOKIE_DOMAIN") or None
    
    # Фронтенд ДОЛЖЕН читать эту куку через JS, поэтому HttpOnly = False
    CSRF_COOKIE_HTTPONLY = False  

    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31_536_000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"

SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]


# ------------------------------------------------------------------------- i18n
LANGUAGE_CODE = env("LANGUAGE_CODE", "ru-ru") # Изменил на русский по умолчанию
TIME_ZONE = "Asia/Tashkent" # Или "UTC", как вам удобнее
USE_I18N = True
USE_TZ = True


# ----------------------------------------------------------------- OpenAPI
SPECTACULAR_SETTINGS = {
    "TITLE": "Uzum Market API",
    "DESCRIPTION": "Каталог товаров, категории, продавцы и JWT-авторизация в HttpOnly cookies.",
    "VERSION": "1.2.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SCHEMA_PATH_PREFIX": "/api",
    "COMPONENT_SPLIT_REQUEST": True,
    "ENUM_GENERATE_CHOICE_DESCRIPTION": False,
    "TAGS": [
        {"name": "auth", "description": "Регистрация, логин, profile"},
        {"name": "products", "description": "Каталог товаров"},
        {"name": "categories", "description": "Категории"},
        {"name": "sellers", "description": "Продавцы"},
    ],
}


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

PAGE_SIZE = env_int("PAGE_SIZE", 10)
PAGE_SIZE_MAX = env_int("PAGE_SIZE_MAX", 100)
CATALOG_CACHE_SECONDS = env_int("CATALOG_CACHE_SECONDS", 60)
SERVE_MEDIA = env_bool("SERVE_MEDIA", DEBUG)