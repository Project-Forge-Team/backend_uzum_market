from django.core.exceptions import ImproperlyConfigured
from rest_framework.settings import api_settings
from rest_framework.throttling import ScopedRateThrottle


class ProxyAwareScopedRateThrottle(ScopedRateThrottle):
    """Троттлинг по реальному клиенту + актуальные лимиты из настроек.

    Два отличия от ванильного ScopedRateThrottle:

    1. IP берём из первого элемента `X-Forwarded-For`: за Render-прокси `REMOTE_ADDR` —
       адрес прокси, и без XFF лимит «10 попыток/мин» стал бы общим на всех юзеров
       (первый же бот положил бы вход всему сервису).
    2. DRF привязывает `THROTTLE_RATES` к классу на import, поэтому правки
       REST_FRAMEWORK (в т.ч. override_settings в тестах) он не видит. Читаем настройки
       в момент вычисления лимита.
    """

    def get_rate(self):
        if not getattr(self, "scope", None):
            raise ImproperlyConfigured(f"{self.__class__.__name__}: у view не задан throttle_scope")
        try:
            return api_settings.DEFAULT_THROTTLE_RATES[self.scope]
        except KeyError as exc:
            raise ImproperlyConfigured(f"Нет throttle-лимита для scope '{self.scope}'") from exc

    def get_cache_key(self, request, view):
        ident = self._client_ip(request)
        if not ident or self.rate is None:
            return None
        return self.cache_format % {"scope": self.scope, "ident": ident}

    @staticmethod
    def _client_ip(request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            # цепочка «клиент, прокси1, прокси2» — берём самого первого
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")
