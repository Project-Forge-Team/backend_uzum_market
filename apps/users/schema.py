"""Схемы авторизации для OpenAPI (drf-spectacular).

Раньше spectacular не знал про наш аутентификатор и сыпал
`could not resolve authenticator … CookieJWTAuthentication`, а Swagger «Try it out»
не мог отправить авторизованный запрос.
"""

from django.conf import settings
from drf_spectacular.extensions import OpenApiAuthenticationExtension


class CookieJWTScheme(OpenApiAuthenticationExtension):
    target_class = "apps.users.authentication.CookieJWTAuthentication"
    name = "cookieAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": settings.JWT_COOKIE["ACCESS"],
            "description": "HttpOnly cookie, выдаётся POST /api/auth/login/.",
        }

    # ВНИМАНИЕ: `Authorization: Bearer` описывать отдельно не нужно — drf-spectacular
    # подхватывает схему `jwtAuth` с родительского SimpleJWT-аутентификатора, и security
    # для наших вьюх получается «cookieAuth ИЛИ jwtAuth».
