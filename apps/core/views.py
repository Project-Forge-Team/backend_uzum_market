"""Служебные эндпоинты: /api/health и /api/demo/reset/."""

from django.conf import settings
from django.core.management import call_command
from django.db import connection, transaction
from django.http import JsonResponse
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .datetime import iso_utc


class HealthView(APIView):
    """GET /api/health — readiness-проба. Только чтение, БД не инициализирует."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(tags=["service"], responses={200: None})
    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) FROM products_product")
            products = cursor.fetchone()[0]
        return JsonResponse(
            {
                "status": "ok",
                "service": "uzum-market-clone",
                "backend": settings.BACKEND_ID,
                "products": products,
                "time": iso_utc(timezone.now()),
            }
        )


class DemoResetView(APIView):
    """POST /api/demo/reset/ — вернуть БД к сид-состоянию.

    Только для авторизованных (анониму 401). На проде выключается env-флагом
    UZUM_LOCK_DEMO=1 → 403. После сброса текущая сессия завершается: все
    пользователи пересоздаются, и «старая» кука больше никого не представляет.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = []
    serializer_class = serializers.Serializer

    @extend_schema(tags=["service"], responses={200: None, 401: None, 403: None})
    def post(self, request):
        if settings.LOCK_DEMO:
            return Response(
                {"detail": "Сброс демо-данных отключён на этом сервере."},
                status=status.HTTP_403_FORBIDDEN,
            )
        with transaction.atomic():
            call_command("seed", reset=True, stdout=None, stderr=None)
        request.session.flush()
        response = Response({"detail": "Демо-данные восстановлены"})
        response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
        response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/")
        return response
