"""Единый JSON-ответ об ошибках + логирование необработанных исключений.

Без этого 500-ки выглядели как HTML-страница, а проглоченные `except Exception`
не были видны нигде (в частности именно так и сгинул баг с блэклистом в logout).
"""

import logging

from django.db import DatabaseError, IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger(__name__)


def api_exception_handler(exc, context):
    response = drf_exception_handler(exc, context)

    if isinstance(exc, IntegrityError):
        # Гонка на регистрации (проверка exists() + in-sert) не должна превращаться в 500.
        logger.warning("IntegrityError в %s: %s", context.get("view"), exc, exc_info=True)
        return Response(
            {"detail": "Такие данные уже существуют или нарушают ограничение целостности."},
            status=status.HTTP_409_CONFLICT,
        )

    if isinstance(exc, DatabaseError):
        logger.exception("DatabaseError в %s", context.get("view"))
        return Response({"detail": "Временная проблема с базой данных, повторите позже."}, status=503)

    if response is None:
        # Неожиданное исключение: Django отдаст свой 500, но в логе останется контекст.
        request = context.get("request")
        logger.exception(
            "Unhandled exception in %s (%s %s)",
            context.get("view"),
            getattr(request, "method", "?"),
            getattr(request, "path", "?"),
        )

    return response
