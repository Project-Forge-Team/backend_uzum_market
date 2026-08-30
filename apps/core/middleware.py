"""Double-submit CSRF для /api/* (§3 ТЗ).

Правило контракта: любой небезопасный метод (POST/PUT/PATCH/DELETE) обязан прийти
с заголовком `X-CSRFToken`, равным значению куки `uzum_csrf`. Не совпал/нет — 403
с `{"detail": "CSRF-токен не совпал. Обновите страницу."}`.

Почему своя проверка, а не Django CsrfViewMiddleware: DRF оборачивает свои view
в `csrf_exempt`, поэтому нативная проверка Django на них не действует (она живёт
в process_view). Наша проверка идёт middleware-ом до view и не зависит от DRF.

Токен выдаёт `GET /api/auth/csrf/` (django.middleware.csrf.get_token — валидный
64-hex токен Django), поэтому админка и Django-механика CSRF продолжают работать
с той же кукой без конфликтов.
"""

import re

from django.conf import settings
from django.http import JsonResponse
from django.utils.crypto import constant_time_compare
from django.utils.deprecation import MiddlewareMixin

CSRF_MISMATCH = "CSRF-токен не совпал. Обновите страницу."

SAFE_METHODS = ("GET", "HEAD", "OPTIONS", "TRACE")

# PUT /api/orders/ — превью сумм, по контракту без авторизации и без CSRF.
# POST /api/products/{id}/view/ — счётчик просмотров, «без тела и без авторизации».
CSRF_EXEMPT_RULES = (
    ("PUT", re.compile(r"^/api/orders/?$")),
    ("POST", re.compile(r"^/api/products/([^/]+)/view/?$")),
)

# Front-прокси нормализует пути, но на всякий случай exempt-ы сравниваем по «чистому» пути.


def _is_exempt(method: str, path: str) -> bool:
    for m, pattern in CSRF_EXEMPT_RULES:
        if method == m and pattern.match(path):
            return True
    return False


class ApiCsrfMiddleware(MiddlewareMixin):
    """Требует X-CSRFToken == кука CSRF для небезопасных методов под /api/."""

    def process_request(self, request):
        if not request.path.startswith("/api/"):
            return None
        if request.method in SAFE_METHODS:
            return None
        if _is_exempt(request.method, request.path):
            return None

        cookie_token = request.COOKIES.get(settings.CSRF_COOKIE_NAME, "")
        header_token = request.META.get(settings.CSRF_HEADER_NAME, "") or request.META.get("HTTP_X_CSRFTOKEN", "")
        if not cookie_token or not header_token or not constant_time_compare(cookie_token, header_token):
            return JsonResponse({"detail": CSRF_MISMATCH}, status=403)
        return None
