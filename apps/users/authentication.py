import logging

from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from .cookies import get_access_token

logger = logging.getLogger(__name__)


class CookieJWTAuthentication(JWTAuthentication):
    """JWT из HttpOnly-cookie ``uzum_access_token``, либо из ``Authorization: Bearer …``.

    Два отличия от ванильного JWTAuthentication, оба осознанные:

    1. Сначала заголовок, потом cookie — один и тот же эндпоинт работает и у браузера
       (cookie), и у мобильного/серверного клиента (Bearer).
    2. Битый/просроченный/поддельный токен = **аноним**, а не 401. Иначе публичные
       эндпоинты (/api/products/, /api/categories/) падали с 401 у каждого, у кого
       истёк access-токен, хотя доступ там анонимный. Защищённые view при этом всё
       равно получают 401 — через ``IsAuthenticated``.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user_model = get_user_model()

    def resolve_raw_token(self, request):
        """Сырой токен: из заголовка, иначе из cookie."""
        header = self.get_header(request)
        if header is not None:
            return self.get_raw_token(header)
        return get_access_token(request)

    def authenticate(self, request):
        try:
            raw_token = self.resolve_raw_token(request)
            if not raw_token:
                return None
            validated_token = self.get_validated_token(raw_token)
        except (InvalidToken, AuthenticationFailed):
            # невалидная/истёкшая cookie или заголовок — считаем запрос анонимным
            return None

        try:
            user = self.get_user(validated_token)
        except (InvalidToken, self.user_model.DoesNotExist):
            logger.debug("JWT ссылается на несуществующего пользователя", exc_info=True)
            return None

        if user is None or not getattr(user, "is_active", False):
            return None

        return user, validated_token
