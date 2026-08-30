"""Настройки для тестов: `python manage.py test --settings=config.test_settings`.

Самодостаточны: sqlite в памяти, без внешних сервисов.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault(
    "SECRET_KEY",
    "test-only-secret-key-not-used-anywhere-else-0123456789abcdefghij",
)
os.environ.setdefault("SEED_MEDIA_ROOT_DIR", "seed_media_test")

from config.settings import *
from config.settings import BASE_DIR, INSTALLED_APPS

DEBUG = False

SECURE_SSL_REDIRECT = False
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    }
}

# Тесты ходят по http — куки без Secure.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "tests"}}

REST_FRAMEWORK = {
    **REST_FRAMEWORK,  # noqa: F405
    "DEFAULT_THROTTLE_RATES": {
        "csrf": "1000/min",
        "login": "1000/min",
        "register": "1000/min",
        "password": "1000/min",
        "product_write": "1000/min",
    },
}

# Тесты пишут SVG-картинки сида — держим их в отдельной папке (gitignore).
SEED_MEDIA_ROOT = BASE_DIR / "seed_media_test"
