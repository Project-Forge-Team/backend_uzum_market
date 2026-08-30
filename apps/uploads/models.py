"""media_files (§2 ТЗ): учёт загруженных картинок."""

from django.conf import settings
from django.db import models


class MediaFile(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="uploads")
    key = models.CharField(max_length=64, unique=True, db_index=True)
    filename = models.CharField(max_length=255, help_text="Исходное имя файла от клиента")
    content_type = models.CharField(max_length=64)
    size = models.PositiveIntegerField()
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Медиа-файл"
        verbose_name_plural = "Медиа-файлы"
        ordering = ["-created_at"]

    def __str__(self):
        return self.key
