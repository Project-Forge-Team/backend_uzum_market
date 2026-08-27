from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.models import TokenUser


class CookieJWTAuthentication(JWTAuthentication):
    """
    Аутентификация JWT из HttpOnly cookie `uzum_access_token`.
    Если cookie нет — возвращает None (анонимный запрос проходит дальше).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Убедимся что user_model — наша кастомная модель
        from django.contrib.auth import get_user_model
        self.user_model = get_user_model()

    def get_cookie_token(self, request):
        token = request.COOKIES.get("uzum_access_token")
        if not token:
            return None
        return token

    def authenticate(self, request):
        raw_token = self.get_cookie_token(request)
        if raw_token is None:
            return None

        validated_token = self.get_validated_token(raw_token)

        try:
            user = self.get_user(validated_token)
        except InvalidToken:
            return None

        if user is not None:
            return user, None

        return None
