"""Троттлинг контракта (§1 ТЗ):

- auth (login/register/password) — ≥ 10/мин/**IP**;
- запись товаров — ≥ 60/ч/**юзер** (для анонима — IP).

Ключ берём из `X-Forwarded-For` первым элементом: за прокси (Render/nginx)
REMOTE_ADDR — это адрес прокси, и лимит стал бы общим на всех клиентов.
Лимиты читаются из настроек в момент запроса (override_settings в тестах работает).
"""

from django.core.exceptions import ImproperlyConfigured
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle


def client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


class ScopedRateThrottleBase(ScopedRateThrottle):
    """ScopedRateThrottle с «живым» чтением лимитов и осмысленным ключом."""

    ident_by_user = False

    def get_rate(self):
        if not getattr(self, "scope", None):
            raise ImproperlyConfigured(f"{self.__class__.__name__}: у view не задан throttle_scope")
        try:
            return api_settings.DEFAULT_THROTTLE_RATES[self.scope]
        except KeyError as exc:
            raise ImproperlyConfigured(f"Нет throttle-лимита для scope '{self.scope}'") from exc

    def get_ident(self, request):
        user = getattr(request, "user", None)
        if self.ident_by_user and getattr(user, "is_authenticated", False):
            return f"u{user.pk}"
        return client_ip(request) or "anonymous"

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        if self.rate is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}


class ScopedIpThrottle(ScopedRateThrottleBase):
    """Лимит по IP (auth-эндпоинты)."""

    ident_by_user = False


class ScopedUserOrIpThrottle(ScopedRateThrottleBase):
    """Лимит по юзеру, для анонима — по IP (запись товаров)."""

    ident_by_user = True
