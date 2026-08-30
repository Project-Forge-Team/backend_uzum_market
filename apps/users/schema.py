"""Схема авторизации для OpenAPI: сессия в куке + double-submit CSRF."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SessionCookieScheme(OpenApiAuthenticationExtension):
    target_class = "apps.users.authentication.CookieSessionAuthentication"
    name = "sessionCookie"
    priority = -1

    def get_security_definition(self, auto_schema):
        return {
            "type": "apiKey",
            "in": "cookie",
            "name": "uzum_sessionid",
            "description": "Django-сессия. Unsafe-методы требуют заголовок X-CSRFToken, "
            "равный куке uzum_csrf (double-submit, см. GET /api/auth/csrf/).",
        }
