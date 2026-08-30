"""Загрузка и раздача картинок (§7 ТЗ)."""

import io
import secrets
import time

from django.core.files.storage import default_storage
from django.http import FileResponse, Http404
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MediaFile

ALLOWED_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
MAX_SIZE = 2 * 1024 * 1024  # 2 МБ


def make_key(content_type: str) -> str:
    """<base36 ts>-<hex8><ext> — расширение из MIME, не из имени клиента (§7 ТЗ)."""
    base36 = ""
    ts = int(time.time() * 1000)
    while ts:
        ts, rest = divmod(ts, 36)
        base36 = "0123456789abcdefghijklmnopqrstuvwxyz"[rest] + base36
    return f"{base36}-{secrets.token_hex(4)}{ALLOWED_TYPES[content_type]}"


class UploadView(APIView):
    """POST /api/uploads/ — multipart, поле `file`, только картинка ≤ 2 МБ."""

    serializer_class = serializers.Serializer
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(tags=["uploads"], responses={201: None, 400: None})
    def post(self, request):
        file = request.FILES.get("file")
        if file is None:
            return Response(
                {"detail": "Прикрепите файл в поле «file».", "fields": {"file": "Файл не передан."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        content_type = (file.content_type or "").lower().split(";")[0].strip()
        if content_type not in ALLOWED_TYPES:
            return Response(
                {
                    "detail": "Поддерживаются только PNG, JPEG, WebP и GIF.",
                    "fields": {"file": "Поддерживаются только PNG, JPEG, WebP и GIF."},
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if file.size is None or file.size > MAX_SIZE:
            return Response(
                {"detail": "Файл больше 2 МБ.", "fields": {"file": "Максимальный размер файла — 2 МБ."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        key = make_key(content_type)
        width = height = None
        try:
            from PIL import Image as PILImage

            image = PILImage.open(file)
            width, height = image.size
            file.seek(0)
        except Exception:
            file.seek(0)

        default_storage.save(f"uploads/{key}", file)
        media = MediaFile.objects.create(
            owner=request.user,
            key=key,
            filename=file.name or key,
            content_type=content_type,
            size=file.size,
            width=width,
            height=height,
        )
        return Response({"url": f"/api/uploads/{media.key}", "name": media.filename}, status=status.HTTP_201_CREATED)


class UploadFileView(APIView):
    """GET /api/uploads/{key} — тело картинки + immutable-кэш (§7 ТЗ)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(tags=["uploads"], responses={200: None})
    def get(self, request, key: str):
        if "/" in key or ".." in key:
            raise Http404("Файл не найден.")
        try:
            media = MediaFile.objects.get(key=key)
        except MediaFile.DoesNotExist:
            raise Http404("Файл не найден.") from None
        if not default_storage.exists(f"uploads/{key}"):
            raise Http404("Файл не найден.") from None
        file = default_storage.open(f"uploads/{key}", "rb")
        response = FileResponse(io.BytesIO(file.read()), content_type=media.content_type)
        response["Cache-Control"] = "public, max-age=31536000, immutable"
        return response
