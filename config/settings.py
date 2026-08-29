"""
Настройки проекта.

Всё, что зависит от окружения, читается через переменные (см. .env.example).
Здесь же — единый источник правды для JWT-cookie, пагинации, фильтров и прод-безопасности,
чтобы значения не разъезжались между settings.py и вьюхами.
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


def env_seconds(name, default_minutes):
    """Токены живут минуты (окружение задаёт минуты, чтобы не возиться с timedelta в .env)."""
    return timedelta(minutes=env_int(name, default_minutes) * 60 // 60)


# ------------------------------------------------------------------- базовое
# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError(
        "SECRET_KEY environment variable is not set. "
        "Скопируйте .env.example в .env и сгенерируйте ключ: "
        "python -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())'"
    )
if len(SECRET_KEY) < 50:
    # JWT (HS256) подписывается этим же ключом: короткий ключ = подбираемая подпись.
    raise ValueError("SECRET_KEY слишком короткий: нужно минимум 50 символов (он же подписывает JWT).")

DEBUG = env_bool("DEBUG", False)

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
if DEBUG and ".localhost" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS += [".localhost", "testserver"]

# Первичное имя домена приложения: нужно для CSRF при кросс-доменных POST (admin/ и cookie-auth).
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

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
    # Сжатие JSON: каталог без него уезжает ~15 КБ на страницу, с ним ~1.5 КБ.
    "django.middleware.gzip.GZipMiddleware",
    # ETag/Last-Modified → браузер фронта получает 304 на повторных запросах каталога.
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

# Без явного BigAutoField Django оставляет AutoField и хочет миграцию,
# меняющую тип id на проде (bigint -> int). Миграции в репо уже BigAutoField.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# ------------------------------------------------------------------------- БД
# В DEBUG не требуем поднятой БД: без DATABASE_URL подключается локальный sqlite-файл,
# и проект стартует командой из README. На проде DATABASE_URL обязателен — иначе сервис
# молча уйдёт на файл, который на Render живёт до первой перезагрузки (данные «испарятся»).
DATABASE_URL = env("DATABASE_URL")
if not DATABASE_URL:
    if DEBUG:
        DATABASE_URL = f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
    else:
        raise ImproperlyConfigured(
            "DATABASE_URL не задан. При DEBUG=False это обязательная настройка "
            "(на Render — Internal Database URL). Для локальной разработки достаточно "
            "DEBUG=True: тогда подключится sqlite://db.sqlite3."
        )

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=env_int("DB_CONN_MAX_AGE", 600),
        conn_health_checks=True,  # Render рвёт простаивающие коннекты: без проверки получаем 500
        # sslmode='require' имеет смысл только для Postgres (sqlite от него падает)
        ssl_require=env_bool("DB_SSL_REQUIRE", not DEBUG) and "postgre" in DATABASE_URL.lower(),
    )
}


# --------------------------------------------------------------------- кэш/ЖД
REDIS_URL = env("REDIS_URL")
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
else:
    # LocMem живёт внутри одного процесса: shared-состояние (троттлинг) на 3 worker'ах
    # будет «своим» на каждый — поэтому в проде выставляйте REDIS_URL.
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "uzum-market",
            "TIMEOUT": 60,
        }
    }

SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"  # admin/CSRF без таблицы sessions


# ----------------------------------------------------------- статика и медиа
def _url_prefix(name, default):
    """Ведущий и завершающий '/' обязательны, иначе относительные ссылки ломаются.

    Без ведущего slash `{% static %}` и наш `absolute_media_url` выдают путь без '/':
    браузер резолвит его от текущего URL страницы (/admin/js/… вместо /static/js/…),
    а `build_absolute_uri` при другом пути запроса даёт /api/media/… .
    Внешний абсолютный URL (бакет/CDN в MEDIA_URL) оставляем как есть.
    """
    # пусто или мусорное значение -> дефолт, а не «/» (иначе /media/ просто перестанет отдаваться)
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

# WhiteNoise без Compressed/Manifest = без .gz и без хэша в имени → нет длительного кэша.
#
# Manifest-хранилище умеет отдавать {hashed URLs + Cache-Control: immutable} только когда статика
# собрана. Правила выбора:
#   * DEBUG=True            -> Compressed (finders, без предсборки);
#   * DEBUG=False, собрано   -> CompressedManifest (то, что нужно на Render);
#   * DEBUG=False, не собрано -> Compressed: локальный запуск «как в проде» без collectstatic
#     не должен превращаться в 500 на каждой странице админки
#     («The file 'admin/css/base.css' could not be found»).
# Курица-и-яйцо (манифеста ещё нет, поэтому и хранилище не Manifest) разрешает build.sh: он
# экспортирует STATIC_MANIFEST_REQUIRED=1 перед collectstatic, чтобы хэши и манифест сгенерировались.
# Замечание: WHITENOISE_MANIFEST_STRICT/manifest_strict=False от 500 не спасает — при отсутствующем
# манифесте Django пытается захэшировать исходник и падает, если его нет в STATIC_ROOT. Поэтому
# хранилище выбирается по факту сборки статики, а не только по DEBUG.
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

# Опциональный S3/R2 для пользовательских загрузок (диск Render эфемерный: media/ стирается
# при каждом деплое). Включается только когда задан бакет, чтобы не ломать локальную разработку:
#   pip install -r requirements/storage.txt  (django-storages + boto3)
#   AWS_STORAGE_BUCKET_NAME=... USE_S3=True
USE_S3 = env_bool("USE_S3", False) and bool(env("AWS_STORAGE_BUCKET_NAME"))
if USE_S3:
    try:
        import storages  # noqa: F401
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError(
            "USE_S3=True, но django-storages не установлен: pip install -r requirements/storage.txt"
        ) from exc
    STORAGES["default"] = {"BACKEND": "storages.backends.s3boto3.S3Boto3Storage"}
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", "us-east-1")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL") or None
    AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN") or None
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "public, max-age=31536000"}


# ----------------------------------------------------------------------- почта
# Раньше блок назывался MAILERS — такой настройки в Django нет, и почта молча
# уходила на localhost:25. Правильно — плоские EMAIL_*.
# Значения задаём всегда (а не только в проде): `DEFAULT_FROM_EMAIL` опирается на
# EMAIL_HOST_USER, и в DEBUG-ветке получался NameError на первом же импорте настроек.
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

# Реальные настройки SimpleJWT. Раньше здесь лежали AUTH_COOKIE/REFRESH_COOKIE_* —
# таких ключей в SimpleJWT нет, они игнорировались, а настоящие значения были
# захардкожены в auth_views (и разъезжались с ACCESS_TOKEN_LIFETIME).
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
    # Ротация + блэклист: без них украденный refresh живёт все 7 дней и не отзывается.
    "ROTATE_REFRESH_TOKENS": env_bool("JWT_ROTATE_REFRESH", True),
    "BLACKLIST_AFTER_ROTATION": env_bool("JWT_BLACKLIST_AFTER_ROTATION", True),
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": SECRET_KEY,
}

# Настройки HTTP-cookie (единственный источник правды для apps/users/cookies.py).
# ВАЖНО: при фронте на ДРУГОМ домене (vercel.app → onrender.com) SameSite=Lax ломает
# авторизацию — браузер не сохраняет и не отправляет такую cookie в кросс-сайтовом fetch.
# Поэтому в проде по умолчанию None (+ обязательный Secure). Либо проксируйте /api через
# фронт (см. README/API.md «Проксирование») и верните COOKIE_SAMESITE=Lax.
COOKIE_SAMESITE = env("COOKIE_SAMESITE", "Lax" if DEBUG else "None")
COOKIE_SECURE = env_bool("COOKIE_SECURE", True if COOKIE_SAMESITE.lower() == "none" else not DEBUG)
if COOKIE_SAMESITE.lower() == "none" and not COOKIE_SECURE:
    raise ValueError("SameSite=None требует Secure=True (браузер отклонит такую cookie).")

JWT_COOKIE = {
    "ACCESS": env("ACCESS_COOKIE_NAME", "uzum_access_token"),
    "REFRESH": env("REFRESH_COOKIE_NAME", "uzum_refresh_token"),
    "SECURE": COOKIE_SECURE,
    "SAMESITE": COOKIE_SAMESITE,
    "HTTP_ONLY": env_bool("COOKIE_HTTP_ONLY", True),
    "ACCESS_PATH": env("ACCESS_COOKIE_PATH", "/"),
    # refresh нужен только на /api/auth/refresh|logout — не светим его на весь домен
    "REFRESH_PATH": env("REFRESH_COOKIE_PATH", "/api/auth/"),
    # Своя (не Django-овская) cookie с CSRF-токеном для double-submit: Django's
    # CsrfViewMiddleware перезаписывает `csrftoken` на каждый запрос DRF-вьюхи
    # (они csrf_exempt), поэтому делить с ним имя нельзя — сравнение рассинхронизируется.
    "CSRF_NAME": env("CSRF_COOKIE_NAME", "uzum_csrf"),
}

# CORS: разрешаем все домены.
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGIN_REGEXES = env_list("CORS_ALLOWED_ORIGIN_REGEXES")
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
CORS_EXPOSE_HEADERS = ["content-encoding", "etag", "last-modified"]

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "apps.products.pagination.CatalogPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # cookie-first для веба, Bearer — для мобильных/серверных клиентов.
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
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")  # без этого на Render вечный 301
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SAMESITE = COOKIE_SAMESITE
    CSRF_COOKIE_SAMESITE = COOKIE_SAMESITE
    CSRF_COOKIE_DOMAIN = env("CSRF_COOKIE_DOMAIN") or None
    CSRF_COOKIE_HTTPONLY = env_bool("CSRF_COOKIE_HTTPONLY", False)  # фронт читает csrftoken из JS
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31_536_000)  # 12 месяцев
    # security.W005/W021 (subdomains/preload) намеренно НЕ включаем: хост живёт в чужой
    # зоне onrender.com, и включать subdomains/preload для домена, которым вы не владеете,
    # нельзя. Для своего домена выставьте SECURE_HSTS_INCLUDE_SUBDOMAINS/SECURE_HSTS_PRELOAD=True.
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)

    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"


# См. комментарий выше: для домена в чужой зоне (onrender.com) subdomains/preload
# включать нельзя, поэтому предупреждения Django про это заглушены осознанно.
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W021"]


# ------------------------------------------------------------------------- i18n
LANGUAGE_CODE = env("LANGUAGE_CODE", "en-us")
TIME_ZONE = "UTC"  # храним UTC; локальное время — ответственность клиента
USE_I18N = True
USE_TZ = True


# ----------------------------------------------------------------- OpenAPI/Swagger
SPECTACULAR_SETTINGS = {
    "TITLE": "Uzum Market API",
    "DESCRIPTION": (
        "Каталог товаров, категории, продавцы и JWT-авторизация в HttpOnly cookies.\n\n"
        "**Авторизация:** `POST /api/auth/login/` ставит cookie `uzum_access_token` (15 мин) и "
        "`uzum_refresh_token` (7 дней). Далее `Authorization: Bearer <access>` **или** cookie — "
        "обои поддерживаются одновременно. При `SameSite=None` все unsafe-запросы требуют "
        "заголовок `X-CSRFToken` (значение — в cookie `csrftoken`, не HttpOnly).\n\n"
        "**Списки:** `page`, `page_size` (≤100), `ordering`, `search`, `min_price`, `max_price`."
    ),
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
# Логгирование было по умолчанию → проглоченные except Exception не видно нигде.
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

# ------------------------------------------------------------------ прочее мелкое
PAGE_SIZE = env_int("PAGE_SIZE", 10)
PAGE_SIZE_MAX = env_int("PAGE_SIZE_MAX", 100)
# Публичные списки (категории/продавцы) почти не меняются — кэшируем ответ на короткое время.
CATALOG_CACHE_SECONDS = env_int("CATALOG_CACHE_SECONDS", 60)
# Локально Django сам отдаёт /media/ (см. config/urls.py); на проде это делает nginx/CDN/S3.
SERVE_MEDIA = env_bool("SERVE_MEDIA", DEBUG)    