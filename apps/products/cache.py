"""Ключи кэша каталога с версионированием.

Инкремент версии инвалидирует ВСЕ списки разом и не трогает чужие ключи в кэше
(в частности счётчики троттлинга — их `cache.clear()` сбросил бы и дал бы боту
бесконечные попытки). Локально LocMem, в проде Redis.
"""

import hashlib

from django.core.cache import cache

VERSION_KEY = "catalog:version"


def get_version():
    version = cache.get(VERSION_KEY)
    if version is None:
        cache.set(VERSION_KEY, 1, None)
        return 1
    return version


def bump_version():
    try:
        cache.incr(VERSION_KEY)
    except ValueError:  # ключа нет (свежий кэш/перезапуск процесса)
        cache.set(VERSION_KEY, 2, None)


def list_cache_key(request):
    raw = f"{request.get_host()}|{request.get_full_path()}"
    return f"catalog:v{get_version()}:" + hashlib.md5(raw.encode()).hexdigest()  # noqa: S324
