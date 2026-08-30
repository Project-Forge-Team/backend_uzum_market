"""Auth-API: сессии в HttpOnly-cookie + double-submit CSRF (§3, §5.1 ТЗ).

Вход/выход ставят/снимают ОБЕ куки (uzum_sessionid + uzum_csrf) одним ответом.
Токены и хэши в теле ответа отсутствуют.
"""

import logging

from django.conf import settings
from django.contrib.auth import login, logout
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.cache import cache_private

from .authentication import CookieSessionAuthentication
from .serializers import (
    LoginSerializer,
    MeUpdateSerializer,
    PasswordSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .throttling import ScopedIpThrottle

logger = logging.getLogger(__name__)


class AuthAPIView(APIView):
    """Общее для auth-эндпоинтов: троттлинг по IP.

    Аутентификатор нужен даже анонимным view: без него DRF не может построить
    WWW-Authenticate и рендерит 401 как 403.
    """

    permission_classes = [permissions.AllowAny]
    authentication_classes = [CookieSessionAuthentication]
    throttle_classes = [ScopedIpThrottle]

    def get_serializer_context(self):
        return {"request": self.request, "format": self.format_kwarg, "view": self}

    def get_serializer(self, *args, **kwargs):
        kwargs.setdefault("context", self.get_serializer_context())
        return self.serializer_class(*args, **kwargs)


def issue_csrf_token(request) -> str:
    """Выдаёт CSRF-токен для double-submit.

    Формат — 64 hex-символа, как нативный токен Django: тогда нативная проверка
    (админка) и наша double-submit-проверка живут на одной куке без конфликтов.
    Уже выданный валидный токен переиспользуется (токен стабилен на браузер).
    """
    import re
    import secrets

    current = request.COOKIES.get(settings.CSRF_COOKIE_NAME, "")
    if re.fullmatch(r"[0-9a-f]{64}", current):
        token = current
    else:
        token = secrets.token_hex(32)
    # Django-механика (админка/формы) продолжит работать с этим же токеном.
    raw_request = request._request if hasattr(request, "_request") else request
    raw_request.META["CSRF_COOKIE"] = token
    raw_request.META.pop("CSRF_COOKIE_MASKED", None)
    return token


def ensure_csrf_cookie(request, response, token: str | None = None):
    """Ставит куку uzum_csrf (без HttpOnly — фронт читает из JS).

    `token` передаётся, когда он уже сгенерирован (иначе каждый вызов создавал бы новый).
    """
    if token is None:
        token = issue_csrf_token(request)
    response.set_cookie(
        settings.CSRF_COOKIE_NAME,
        token,
        max_age=60 * 60 * 24 * 365,
        domain=settings.CSRF_COOKIE_DOMAIN or None,
        path="/",
        secure=settings.CSRF_COOKIE_SECURE,
        samesite=settings.CSRF_COOKIE_SAMESITE,
        httponly=False,
    )
    return response


class CsrfView(AuthAPIView):
    """GET /api/auth/csrf/ — бустрап double-submit CSRF-токена."""

    throttle_scope = "csrf"
    serializer_class = None

    @extend_schema(tags=["auth"], responses={200: None})
    def get(self, request):
        token = issue_csrf_token(request)
        response = Response({"detail": "CSRF cookie issued", "csrf": token})
        return ensure_csrf_cookie(request, response, token=token)


class RegisterView(AuthAPIView):
    """POST /api/auth/register/ — профиль + автоматически созданный магазин + куки."""

    serializer_class = RegisterSerializer
    throttle_scope = "register"

    @extend_schema(tags=["auth"], request=RegisterSerializer, responses={201: UserSerializer})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        login(request._request, user)
        response = Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return ensure_csrf_cookie(request, response)


class LoginView(AuthAPIView):
    """POST /api/auth/login/ — вход: профиль + обе куки."""

    serializer_class = LoginSerializer
    throttle_scope = "login"

    @extend_schema(tags=["auth"], request=LoginSerializer, responses={200: UserSerializer})
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        login(request._request, user)
        response = Response(UserSerializer(user).data, status=status.HTTP_200_OK)
        return ensure_csrf_cookie(request, response)


class LogoutView(AuthAPIView):
    """POST /api/auth/logout/ — выход, куки чистятся (идемпотентно, работает и анонимно)."""

    serializer_class = serializers.Serializer
    throttle_classes = []

    @extend_schema(tags=["auth"], responses={200: None})
    def post(self, request):
        if request.session.session_key or request.user.is_authenticated:
            logout(request._request)
        response = Response({"detail": "Вы вышли из аккаунта"}, status=status.HTTP_200_OK)
        response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
        response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/")
        return response


class MeNotAuthenticated(exceptions.NotAuthenticated):
    def __init__(self):
        super().__init__(detail="Вы не авторизованы")


class IsAuthenticatedForMe(permissions.BasePermission):
    message = "Вы не авторизованы"

    def has_permission(self, request, view):
        if request.user and request.user.is_authenticated:
            return True
        raise MeNotAuthenticated()


class MeView(APIView):
    """GET/PATCH /api/auth/me/ — профиль текущего пользователя.

    401 с текстом «Вы не авторизованы» (§3 ТЗ) — фронт по нему включает гостевой режим.
    """

    serializer_class = UserSerializer
    authentication_classes = [CookieSessionAuthentication]
    permission_classes = [IsAuthenticatedForMe]

    @extend_schema(tags=["auth"], responses={200: UserSerializer})
    def get(self, request):
        return cache_private(Response(UserSerializer(request.user).data), request)

    @extend_schema(tags=["auth"], request=MeUpdateSerializer, responses={200: UserSerializer})
    def patch(self, request):
        serializer = MeUpdateSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return cache_private(Response(UserSerializer(request.user).data), request)


class PasswordView(APIView):
    """POST /api/auth/password/ — смена пароля + инвалидация прочих сессий."""

    permission_classes = [permissions.IsAuthenticated]
    throttle_classes = [ScopedIpThrottle]
    throttle_scope = "password"

    @extend_schema(tags=["auth"], request=PasswordSerializer, responses={200: None})
    def post(self, request):
        serializer = PasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = request.user
        user.set_password(serializer.validated_data["next"])
        user.save(update_fields=["password", "password_updated_at"])

        # Прочие сессии инвалидируются сами: в django_session лежит _auth_user_hash,
        # посчитанный от старого пароля. Текущую продлеваем новым хэшем, чтобы
        # не разлогинивать человека посреди смены пароля (should из ТЗ).
        request.session["_auth_user_hash"] = user.get_session_auth_hash()

        return Response({"detail": "Пароль обновлён"}, status=status.HTTP_200_OK)
