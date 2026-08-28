"""Настройки для тестов: `python manage.py test --settings=config.test_settings`.

Самодостаточны: не нужны ни DATABASE_URL, ни SECRET_KEY, ни поднятая БД — sqlite в памяти.
Родительские `settings.py` проверяют эти переменные на импорте, поэтому задаём их в окружении
до импорта (значения тестов не используют: БД и ключ переопределены ниже).
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault(
    "SECRET_KEY",
    "test-only-secret-key-not-used-anywhere-else-0123456789abcdefghij",  # >=50 символов, как требует settings
)

from datetime import timedelta

from config.settings import *
from config.settings import INSTALLED_APPS

DEBUG = False

# Тестовый клиент ходит по http, а в проде у нас принудительный HTTPS — иначе
# каждый запрос получил бы 301 и ни один тест ничего бы не проверял.
SECURE_SSL_REDIRECT = False
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tests"}}

# В тестах по умолчанию same-site (Lax): double-submit CSRF включается отдельным тестом.
JWT_COOKIE = {
    "ACCESS": "uzum_access_token",
    "REFRESH": "uzum_refresh_token",
    "CSRF_NAME": "uzum_csrf",
    "SECURE": False,
    "SAMESITE": "Lax",
    "HTTP_ONLY": True,
    "ACCESS_PATH": "/",
    "REFRESH_PATH": "/api/auth/",
    "DOMAIN": None,
}

SIMPLE_JWT = {
    **SIMPLE_JWT,  # noqa: F405
    "ACCESS_TOKEN_LIFETIME": timedelta(seconds=2),  # чтобы проверить поведение на истёкшем токене
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
}

PAGE_SIZE = 10
PAGE_SIZE_MAX = 50
CATALOG_CACHE_SECONDS = 60
SERVE_MEDIA = False

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    # В тестах лимиты по умолчанию высокие; конкретный тест троттлинга переопределяет их сам.
    "DEFAULT_THROTTLE_RATES": {"login": "1000/min", "register": "1000/hour", "refresh": "1000/hour"},
}
