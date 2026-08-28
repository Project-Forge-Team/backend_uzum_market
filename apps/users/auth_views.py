"""Auth-API: JWT в HttpOnly cookies (+ поддержка Authorization: Bearer).

Один стиль для всех эндпоинтов: токены НЕ возвращаются в теле, они кладутся в cookie.
Это закрывает и расхождение с документацией (register отдавал токены в теле, но
пользоваться ими было нельзя), и XSS-вектор с localStorage.
"""

import logging

from django.core.exceptions import ObjectDoesNotExist
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .cookies import clear_auth_cookies, ensure_csrf_cookie, get_refresh_token, set_auth_cookies, tokens_for_user
from .permissions import CrossSiteCsrfProtect
from .serializers import EmailTokenObtainPairSerializer, RegisterSerializer, UserSerializer
from .throttling import ProxyAwareScopedRateThrottle

logger = logging.getLogger(__name__)


class AuthAPIView(APIView):
    """Общее для всех auth-эндпоинтов: CSRF-защита cookie-флоу + троттлинг.

    Минимальная обвязка сериализатора (у чистого APIView её нет), чтобы не тянуть
    ради этого GenericAPIView.
    """

    serializer_class = None
    permission_classes = [CrossSiteCsrfProtect]
    # Аутентификаторы не отключаем: DRF без них превращает AuthenticationFailed
    # в 403 вместо 401 (нет WWW-Authenticate) — ломается контракт логина.
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
    """POST /api/auth/refresh/ — новый access (и, при ротации, новый refresh) из cookie.

    Тело не нужно: refresh читается из cookie. При любой ошибке отзываем обе cookie,
    чтобы фронт однозначно понял «нужен логин».
    """

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

        # Не мутируем request.data: для form-encoded/multipart это неизменяемый QueryDict
        # и эндпоинт падал с 500 (AttributeError: This QueryDict instance is immutable).
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
            refresh=serializer.validated_data.get("refresh"),  # есть только при ROTATE_REFRESH_TOKENS=True
        )


@extend_schema(tags=["auth"])
class LogoutView(AuthAPIView):
    """POST /api/auth/logout/ — отзыв refresh-токена (блэклист) + чистка cookies.

    Доступен и анонимно: раньше он требовал авторизации, и пользователь с истёкшим
    access-токеном не мог разлогиниться (401 вместо чистки cookie).
    """

    permission_classes = [permissions.AllowAny, CrossSiteCsrfProtect]

    @extend_schema(request=None, responses={200: None})
    def post(self, request, *args, **kwargs):
        raw = get_refresh_token(request)
        if raw:
            try:
                # Штатный отзыв SimpleJWT: OutstandingToken создаётся сигналом jwt_signed,
                # вручную его не нужно заполнять (а попытки это делали ломали logout молча).
                RefreshToken(raw).blacklist()
            except TokenError:
                pass  # уже отозван/истёк/blacklist-приложение выключено — штатно
            except Exception:
                # Раньше здесь был «except Exception: pass», и сломанный logout не было видно.
                logger.exception("Не удалось добавить refresh-токен в блэклист")

        response = Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        return clear_auth_cookies(response)


@extend_schema(tags=["auth"])
class CsrfView(AuthAPIView):
    """GET /api/auth/csrf/ — бустрап double-submit CSRF-токена.

    Нужен, когда cookie живут в SameSite=None (фронт на другом домене): unsafe-запросы
    обязаны нести заголовок X-CSRFToken с этим значением.
    """

    permission_classes = [permissions.AllowAny]

    @extend_schema(responses={200: None})
    def get(self, request, *args, **kwargs):
        return ensure_csrf_cookie(request, Response({"detail": "ok"}, status=status.HTTP_200_OK))


@extend_schema(tags=["auth"])
class MeView(generics.RetrieveAPIView):
    """GET /api/auth/me/ — профиль текущего пользователя (cookie или Bearer)."""

    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user
