"""Cache-Control по §8 ТЗ.

- приватные эндпоинты (orders, products/mine, shop*, auth/me) → `no-store`;
- публичные списки → `public, max-age=15, stale-while-revalidate=60`,
  но если пришла кука сессии (ответ персонализирован: has_own_review/own) — `private`.
"""

from django.utils.cache import add_never_cache_headers, patch_cache_control


def cache_public(response, request, max_age=15, swr=60):
    if getattr(request, "user", None) is not None and request.user.is_authenticated:
        patch_cache_control(response, private=True, max_age=max_age)
    else:
        patch_cache_control(response, public=True, max_age=max_age, stale_while_revalidate=swr)
    return response


def cache_private(response, request=None):
    add_never_cache_headers(response)
    return response
