"""Единый формат ошибок контракта + логирование необработанных исключений.

Формат (§1 ТЗ): {"detail": "текст для пользователя", "fields": {"email": "..."}}
- `detail` обязателен всегда (фронт показывает его в тосте);
- `fields` — опциональная карта «поле → одна строка» (не массив!).
"""

import logging

from django.db import DatabaseError, IntegrityError
from rest_framework import status
from rest_framework.exceptions import NotAuthenticated, ValidationError
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)

GENERIC_401 = "Нужно войти в аккаунт"


def _flatten(detail):
    """detail DRF (dict/list/str) → (detail_str, fields_map)."""
    if isinstance(detail, dict):
        fields = {}
        first = None
        for key, value in detail.items():
            if isinstance(value, (list, tuple)):
                msg = str(value[0]) if value else "Недопустимое значение."
            elif isinstance(value, str):
                msg = value
            else:
                msg = "Недопустимое значение."
            fields[str(key)] = msg
            if first is None:
                first = msg
        return first or "Проверьте правильность заполнения полей.", fields
    if isinstance(detail, (list, tuple)):
        return (str(detail[0]) if detail else "Ошибка запроса."), {}
    return str(detail), {}


def api_exception_handler(exc, context):
    if isinstance(exc, IntegrityError):
        # Гонка «проверили exists() → вставили» не должна превращаться в 500.
        logger.warning("IntegrityError в %s: %s", context.get("view"), exc, exc_info=True)
        return Response(
            {"detail": "Такие данные уже существуют или нарушают ограничение целостности."},
            status=status.HTTP_409_CONFLICT,
        )
    if isinstance(exc, DatabaseError):
        logger.exception("DatabaseError в %s", context.get("view"))
        return Response({"detail": "Временная проблема с базой данных, повторите позже."}, status=503)

    response = drf_exception_handler(exc, context)

    if isinstance(exc, ValidationError):
        detail_str, fields = _flatten(exc.detail)
        payload = {"detail": detail_str}
        if fields:
            payload["fields"] = fields
        return Response(payload, status=status.HTTP_400_BAD_REQUEST)

    if isinstance(exc, NotAuthenticated) and str(exc.detail) in (
        "Учетные данные не были предоставлены.",
        "Authentication credentials were not provided.",
    ):
        # Текст из ТЗ: фронт показывает его в тосте про вход.
        return Response({"detail": GENERIC_401}, status=status.HTTP_401_UNAUTHORIZED)

    if response is None:
        request = context.get("request")
        logger.exception(
            "Unhandled exception in %s (%s %s)",
            context.get("view"),
            getattr(request, "method", "?"),
            getattr(request, "path", "?"),
        )
        return response

    # Остальные ошибки: гарантируем наличие строкового `detail`.
    detail = response.data.get("detail")
    if detail is None and isinstance(response.data, dict):
        detail_str, fields = _flatten(response.data)
        payload = {"detail": detail_str}
        if fields:
            payload["fields"] = fields
        response.data = payload
    elif not isinstance(detail, str):
        response.data["detail"] = _flatten(detail)[0]
    return response
