"""Единая точка правды для HTTP-cookie с JWT и double-submit CSRF-токена.

Раньше параметры cookie (max_age=900, path, samesite) были захардкожены в auth_views,
а в settings лежали несуществующие ключи SIMPLE_JWT — значения могли разъехаться
(пример: ACCESS_TOKEN_LIFETIME меняешь на 30 минут, а cookie продолжает жить 15).

CSRF-токен реализован как «double-submit»: DRF-вьюхи csrf_exempt (это их природа),
поэтому machinery Django здесь не помощник — проверяем просто совпадение значения
в cookie и в заголовке X-CSRFToken.
"""

import hmac
import secrets

from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken

CSRF_HEADER_META = "HTTP_X_CSRFTOKEN"


def cookie_kwargs(path: str) -> dict:
    cfg = settings.JWT_COOKIE
    return {
        "path": path,
        "domain": cfg.get("DOMAIN") or None,
        "secure": cfg["SECURE"],
        "httponly": cfg["HTTP_ONLY"],
        "samesite": cfg["SAMESITE"],
    }


def _lifetime(name: str) -> int:
    key = "ACCESS_TOKEN_LIFETIME" if name == settings.JWT_COOKIE["ACCESS"] else "REFRESH_TOKEN_LIFETIME"
    return int(settings.SIMPLE_JWT[key].total_seconds())


def set_auth_cookies(request, response, *, access=None, refresh=None):
    """Ставит access (и опционально refresh) в HttpOnly cookies + держит CSRF-куку живой."""
    cfg = settings.JWT_COOKIE
    if access:
        response.set_cookie(
            cfg["ACCESS"], access, max_age=_lifetime(cfg["ACCESS"]), **cookie_kwargs(cfg["ACCESS_PATH"])
        )
    if refresh:
        response.set_cookie(
            cfg["REFRESH"], refresh, max_age=_lifetime(cfg["REFRESH"]), **cookie_kwargs(cfg["REFRESH_PATH"])
        )
    return ensure_csrf_cookie(request, response)


def delete_cookie_kwargs(path: str) -> dict:
    """Атрибуты удаления: Django умеет передавать только path/domain/samesite (без secure/httponly).

    Удаление обязано совпадать по path/domain/samesite с исходной cookie, иначе браузер
    её не затрёт (для SameSite=None молча не работает удаление без samesite=None).
    """
    cfg = settings.JWT_COOKIE
    return {"path": path, "domain": cfg.get("DOMAIN") or None, "samesite": cfg["SAMESITE"]}


def clear_auth_cookies(response):
    """Удаляет обе cookie и снимает авторизацию на стороне клиента."""
    cfg = settings.JWT_COOKIE
    for name, path in ((cfg["ACCESS"], cfg["ACCESS_PATH"]), (cfg["REFRESH"], cfg["REFRESH_PATH"])):
        response.delete_cookie(name, **delete_cookie_kwargs(path))
    return response


def _explicit_refresh(request):
    """`refresh` из тела запроса (JSON или form-encoded), если он там есть."""
    try:
        data = request.data
    except Exception:  # невалидный JSON/ multipart — считаем, что тела нет (415 отдаёт DRF сам)
        return None
    if isinstance(data, dict):
        value = data.get("refresh")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def get_refresh_token(request):
    """Refresh-токен: явный из тела важнее cookie.

    Иначе клиент, приславший просроченный/отозванный токен в теле, получил бы 204 «успех»
    (обновление по cookie) вместо 401 — и никогда бы не узнал, что его токен негоден.
    """
    return _explicit_refresh(request) or request.COOKIES.get(settings.JWT_COOKIE["REFRESH"])


def get_access_token(request):
    return request.COOKIES.get(settings.JWT_COOKIE["ACCESS"])


def tokens_for_user(user):
    """(refresh, access) для пользователя — один путь для login и register."""
    refresh = RefreshToken.for_user(user)
    return str(refresh), str(refresh.access_token)


# ------------------------------------------------------------------ CSRF (double submit)
def ensure_csrf_cookie(request, response):
    """Гарантирует, что csrftoken установлен: фронт читает его и кладёт в X-CSRFToken."""
    name = settings.JWT_COOKIE["CSRF_NAME"]
    value = request.COOKIES.get(name) or secrets.token_urlsafe(32)
    response.set_cookie(
        name,
        value,
        max_age=int(settings.CSRF_COOKIE_AGE),
        httponly=False,  # читается из JS намеренно
        secure=settings.CSRF_COOKIE_SECURE,
        samesite=settings.CSRF_COOKIE_SAMESITE,
        path=settings.CSRF_COOKIE_PATH,
        domain=settings.JWT_COOKIE.get("DOMAIN") or None,
    )
    return response


def csrf_ok(request) -> bool:
    """Совпадает ли заголовок с cookie. Пустой заголовок = не прошёл."""
    name = settings.JWT_COOKIE["CSRF_NAME"]
    header = request.META.get(CSRF_HEADER_META) or ""
    cookie = request.COOKIES.get(name) or ""
    if not header or not cookie:
        return False
    # Токен генерируется как случайная строка и кладётся в cookie и заголовок без изменений,
    # поэтому достаточно сравнения с постоянным временем (без mask/unmask machinery Django).
    return hmac.compare_digest(str(header), str(cookie))
