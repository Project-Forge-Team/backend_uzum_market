from django.conf import settings
from rest_framework import exceptions, permissions


class CrossSiteCsrfProtect(permissions.BasePermission):
    """Минимальная CSRF-защита для cookie-авторизации.

    DRF намеренно делает APIView csrf_exempt, а `SessionAuthentication` в
    DEFAULT_AUTHENTICATION_CLASSES нет — значит Django сам CSRF не проверит.
    Когда cookie живут в SameSite=Lax/Strict, кросс-сайтовый POST приходит без cookie
    и вопрос закрыт браузером. Как только включён SameSite=None (нужен для фронта
    на другом домене), защита обязана быть здесь.

    Правила:
      * safe-методы (GET/HEAD/OPTIONS) — всегда проходим;
      * запрос, авторизованный `Authorization: Bearer`, — проходим (CSRF не применим);
      * unsafe + cookie → требуем заголовок `X-CSRFToken`, равный cookie `csrftoken`
        (double-submit). Заголовок не входит в CORS-safe-list, поэтому чужой сайт не
        сможет ни прочитать cookie, ни отправить заголовок без успешного preflight на наш домен.

    Исключение бросаем сами (а не return False), иначе DRF превращает отказ в 401
    NotAuthenticated и фронт зацикливает на «сначала refresh».
    """

    message = (
        "CSRF-проверка не пройдена: при SameSite cookie unsafe-запросы должны нести "
        "заголовок X-CSRFToken (получить значение — GET /api/auth/csrf/)."
    )

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        if (request.META.get("HTTP_AUTHORIZATION") or "").lower().startswith("bearer "):
            return True
        if settings.JWT_COOKIE["SAMESITE"].lower() != "none":
            return True

        from .cookies import csrf_ok

        if not csrf_ok(request):
            raise exceptions.PermissionDenied(self.message, code="csrf_failed")
        return True
