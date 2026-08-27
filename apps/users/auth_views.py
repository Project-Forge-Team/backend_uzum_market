from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .serializers import UserSerializer


class CookieTokenObtainPairView(TokenObtainPairView):
    """
    Логин с выдачей access/refresh токенов в защищённых HttpOnly cookies.
    В теле ответа — только данные пользователя, токены не возвращаются.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        access_token = str(serializer.validated_data["access"])
        refresh_token = str(serializer.validated_data["refresh"])

        user_data = UserSerializer(serializer.user, context={"request": request}).data

        response = Response(user_data, status=200)

        # --- access token cookie ---
        response.set_cookie(
            key="uzum_access_token",
            value=access_token,
            max_age=900,                          # 15 минут
            httponly=True,
            secure=not settings.DEBUG,
            samesite="Lax",
            path="/",
        )

        # --- refresh token cookie ---
        response.set_cookie(
            key="uzum_refresh_token",
            value=refresh_token,
            max_age=604800,                       # 7 дней
            httponly=True,
            secure=not settings.DEBUG,
            samesite="Lax",
            path="/api/auth/",
        )

        return response


class CookieTokenRefreshView(TokenRefreshView):
    """
    Обновление access-токена: читает refresh из cookie,
    выдаёт новый access обратно в cookie.
    При 401 — удаляет обе cookies.
    """

    permission_classes = [permissions.AllowAny]

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("uzum_refresh_token")

        if not refresh_token:
            response = Response(
                {"detail": "Refresh token not found in cookies."},
                status=401,
            )
            response.delete_cookie("uzum_access_token", path="/")
            response.delete_cookie("uzum_refresh_token", path="/api/auth/")
            return response

        request.data["refresh"] = refresh_token

        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except (InvalidToken, TokenError):
            response = Response(
                {"detail": "Token is invalid or expired."},
                status=401,
            )
            response.delete_cookie("uzum_access_token", path="/")
            response.delete_cookie("uzum_refresh_token", path="/api/auth/")
            return response

        new_access_token = str(serializer.validated_data["access"])

        response = Response(status=200)

        # Обновляем access-токен в cookie
        response.set_cookie(
            key="uzum_access_token",
            value=new_access_token,
            max_age=900,
            httponly=True,
            secure=not settings.DEBUG,
            samesite="Lax",
            path="/",
        )

        return response


class CookieTokenLogoutView(APIView):
    """
    Выход: удаляет обе cookies и добавляет refresh-токен в блэклист (если включён).
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        # Добавляем refresh-токен в блэклист
        try:
            from rest_framework_simplejwt.token_blacklist.models import (
                OutstandingToken,
                BlacklistedToken,
            )

            refresh_token = request.COOKIES.get("uzum_refresh_token")
            if refresh_token:
                token = RefreshToken(refresh_token)
                outstanding, _ = OutstandingToken.objects.get_or_create(
                    token=token,
                    defaults={
                        "user": request.user,
                        "jti": str(token["jti"]),
                        "token": str(token),
                        "expires_at": timezone.now() + timedelta(seconds=token._assertion["exp"]),
                    },
                )
                BlacklistedToken.objects.get_or_create(token=outstanding)
        except Exception:
            # Блэклист не настроен — не критично
            pass

        response = Response({"detail": "Successfully logged out."}, status=200)
        response.delete_cookie("uzum_access_token", path="/")
        response.delete_cookie("uzum_refresh_token", path="/api/auth/")
        return response
