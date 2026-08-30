"""Аутентификация по сессионной куке `uzum_sessionid` (§3 ТЗ).

От `SessionAuthentication` DRF отличается только тем, что не дублирует CSRF:
double-submit-проверку делает `ApiCsrfMiddleware` для всех /api-запросов,
включая анонимные (DRF проверяет CSRF только для аутентифицированных).
"""

import logging

from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)


class CookieSessionAuthentication(authentication.BaseAuthentication):
    keyword = "Session"

    def authenticate(self, request):
        # user уже вычислен AuthenticationMiddleware по django_session.
        user = getattr(request._request, "user", None)
        if user is None or not user.is_authenticated:
            return None
        if not user.is_active:
            raise exceptions.AuthenticationFailed("Пользователь деактивирован.")
        return (user, None)

    def authenticate_header(self, request):
        # Без этого DRF отдаёт 403 вместо 401 на защищённых эндпоинтах.
        return self.keyword
