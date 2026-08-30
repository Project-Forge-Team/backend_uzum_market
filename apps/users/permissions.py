"""Права доступа (§4 ТЗ)."""

from rest_framework import exceptions
from rest_framework.permissions import BasePermission


def forbidden(detail: str = "Недостаточно прав."):
    exc = exceptions.PermissionDenied(detail)
    return exc


class IsSellerOwnerOr404(BasePermission):
    """Для объектов каталога: действие разрешено только владельцу магазина-продавца.

    По ТЗ чужое — это 403 для своих объектов (PATCH/DELETE/status) и 404 для просмотра
    чужих черновиков. Правило «кто владелец» проверяется на уровне view/queryset.
    """

    message = "Это товар другого магазина."
