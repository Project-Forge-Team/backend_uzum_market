"""Auth-API: JWT в HttpOnly cookies (+ поддержка Authorization: Bearer).

Один стиль для всех эндпоинтов: токены НЕ возвращаются в теле, они кладутся в cookie.
Это закрывает и расхождение с документацией, и XSS-вектор с localStorage.
"""

import logging

from django.core.exceptions import ObjectDoesNotExist
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .cookies import clear_auth_cookies, get_refresh_token, set_auth_cookies, tokens_for_user
from .permissions import CrossSiteCsrfProtect
from .serializers import EmailTokenObtainPairSerializer, RegisterSerializer, UserSerializer
from .throttling import ProxyAwareScopedRateThrottle

logger = logging.getLogger(__name__)


class AuthAPIView(APIView):
    """Общее для всех auth-эндпоинтов: CSRF-защита cookie-флоу + троттлинг."""

    serializer_class = None
    permission_classes = [CrossSiteCsrfProtect]
    throttle_classes = [ProxyAwareScopedRateThrottle]

    def get_serializer_context(self):
        return {"request": self.request, "format": self.format_kwarg, "view": self}

    def get_serializer(self, *args, **kwargs):
        kwargs.setdefault("context", self.get_serializer_context())
        return self.serializer_class(*args, **kwargs)


@extend_schema(tags=["auth"])
class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/ — регистрация + сразу авторизованные cookies."""

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny, CrossSiteCsrfProtect]
    authentication_classes = []
    throttle_classes = [ProxyAwareScopedRateThrottle]
    throttle_scope = "register"

    @extend_schema(
        request=RegisterSerializer,
        responses={201: UserSerializer},
    )
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh, access = tokens_for_user(user)
        response = Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)
        return set_auth_cookies(request, response, access=access, refresh=refresh)


@extend_schema(tags=["auth"])
class LoginView(AuthAPIView):
    """POST /api/auth/login/ — вход по email + паролю, токены уходят в HttpOnly cookies."""

    serializer_class = EmailTokenObtainPairSerializer
    permission_classes = [permissions.AllowAny, CrossSiteCsrfProtect]
    throttle_classes = [ProxyAwareScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=EmailTokenObtainPairSerializer, responses={200: UserSerializer})
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = getattr(serializer, "user", None)
        if user is None:  # фолбэк на случай изменения внутреннего API simplejwt
            from django.contrib.auth import get_user_model
            from rest_framework_simplejwt.tokens import AccessToken

            access = serializer.validated_data["access"]
            user = get_user_model().objects.get(pk=AccessToken(str(access))["user_id"])

        response = Response(UserSerializer(user).data, status=status.HTTP_200_OK)
        return set_auth_cookies(
            request,
            response,
            access=serializer.validated_data["access"],
            refresh=serializer.validated_data.get("refresh"),
        )


@extend_schema(tags=["auth"])
class RefreshView(AuthAPIView):
    """POST /api/auth/refresh/ — новый access (и, при ротации, новый refresh) из cookie."""

    serializer_class = TokenRefreshSerializer
    permission_classes = [permissions.AllowAny, CrossSiteCsrfProtect]
    throttle_classes = [ProxyAwareScopedRateThrottle]
    throttle_scope = "refresh"

    @extend_schema(request=None, responses={204: None})
    def post(self, request, *args, **kwargs):
        refresh_token = get_refresh_token(request)
        if not refresh_token:
            return clear_auth_cookies(
                Response({"detail": "Refresh token not found in cookies."}, status=status.HTTP_401_UNAUTHORIZED)
            )

        serializer = self.serializer_class(data={"refresh": refresh_token}, context={"request": request})
        try:
            serializer.is_valid(raise_exception=True)
        except (InvalidToken, TokenError, ObjectDoesNotExist):
            return clear_auth_cookies(
                Response({"detail": "Token is invalid or expired."}, status=status.HTTP_401_UNAUTHORIZED)
            )

        response = Response(status=status.HTTP_204_NO_CONTENT)
        return set_auth_cookies(
            request,
            response,
            access=serializer.validated_data.get("access"),
            refresh=serializer.validated_data.get("refresh"),
        )


@extend_schema(tags=["auth"])
class LogoutView(AuthAPIView):
    """POST /api/auth/logout/ — отзыв refresh-токена (блэклист) + чистка cookies."""

    permission_classes = [permissions.AllowAny, CrossSiteCsrfProtect]

    @extend_schema(request=None, responses={200: None})
    def post(self, request, *args, **kwargs):
        raw = get_refresh_token(request)
        if raw:
            try:
                RefreshToken(raw).blacklist()
            except TokenError:
                pass  # уже отозван/истёк/blacklist-приложение выключено
            except Exception:
                logger.exception("Не удалось добавить refresh-токен в блэклист")

        response = Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        return clear_auth_cookies(response)


@extend_schema(tags=["auth"])
@method_decorator(ensure_csrf_cookie, name='dispatch') # 🔥 ГАРАНТИРОВАННО заставляет Django отправить Set-Cookie
class CsrfView(APIView):
    """GET /api/auth/csrf/ — бустрап double-submit CSRF-токена."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = [] # 🔥 Явно отключаем, аутентификация здесь не нужна

    @extend_schema(responses={200: None})
    def get(self, request, *args, **kwargs):
        # Благодаря декоратору выше, Django сам добавит заголовок Set-Cookie с токеном
        return Response({"detail": "CSRF cookie set"}, status=status.HTTP_200_OK)


@extend_schema(tags=["auth"])
class MeView(generics.RetrieveAPIView):
    """GET /api/auth/me/ — профиль текущего пользователя (cookie или Bearer)."""

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user