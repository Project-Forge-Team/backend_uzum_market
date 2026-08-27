from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed


class CookieJWTAuthentication(JWTAuthentication):
    """
    Аутентификация JWT из HttpOnly cookie `uzum_access_token`.
    Если cookie нет — возвращает None (анонимный запрос проходит дальше).
    """

    def get_cookie_token(self, request):
        token = request.COOKIES.get("uzum_access_token")
        if not token:
            return None
        return token

    def authenticate(self, request):
        token = self.get_cookie_token(request)
        if token is None:
            return None

        identified_user = None
        try:
            identified_user = self.get_user(token)
            if identified_user is None:
                return None
        except AuthenticationFailed:
            raise

        if identified_user is not None:
            auth = self.get_auth_header_prefix() + b" " + token.encode(request.encoding)
            return identified_user, auth

        return None
